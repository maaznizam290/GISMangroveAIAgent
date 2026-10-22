"""M1 AOI hydrological-context review.

Answers one question with real data: does a candidate AOI contain the creek/channel system
around the reference location, or does it truncate it?

Evidence used:
* JRC Global Surface Water v1.4 occurrence (1984-2021), read from the public tile store.
  Occurrence says how often a pixel was observed as water. It cannot distinguish tidal
  sea water from river water, so it says nothing about freshwater supply.
* Natural Earth 1:10M Indus centreline, as a coarse cartographic reference only.

Nothing here establishes freshwater influence. The review reports it as unresolved and lists
the evidence that would be needed.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from rasterio.merge import merge
from rasterio.transform import from_origin
from rasterio.warp import Resampling, reproject, transform_bounds
from scipy import ndimage
from shapely.geometry import shape
from shapely.ops import unary_union

from indus_delta.checks import Check
from indus_delta.config import HydrologyReviewConfig, ProjectConfig

log = logging.getLogger(__name__)

NODATA_OUT = 255


# --------------------------------------------------------------------------- data access


def jrc_tile_name(lon: float, lat: float, tile_size: int = 10) -> str:
    """JRC GSW tiles are named by their top-left corner, e.g. '60E_30N'."""
    west = math.floor(lon / tile_size) * tile_size
    north = math.floor(lat / tile_size) * tile_size + tile_size
    ew = f"{abs(west)}{'E' if west >= 0 else 'W'}"
    ns = f"{abs(north)}{'N' if north >= 0 else 'S'}"
    return f"{ew}_{ns}"


def jrc_tiles_for_bounds(
    bounds: tuple[float, float, float, float], tile_size: int = 10
) -> list[str]:
    west, south, east, north = bounds
    eps = 1e-9
    lons = range(math.floor(west / tile_size), math.floor((east - eps) / tile_size) + 1)
    lats = range(math.floor(south / tile_size), math.floor((north - eps) / tile_size) + 1)
    return sorted(
        {jrc_tile_name(i * tile_size, j * tile_size, tile_size) for i in lons for j in lats}
    )


def _gdal_env() -> rasterio.Env:
    ca = os.environ.get("CURL_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    opts = {
        "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
        "GDAL_HTTP_MAX_RETRY": 4,
        "GDAL_HTTP_RETRY_DELAY": 2,
    }
    if ca:
        opts["CURL_CA_BUNDLE"] = ca
    return rasterio.Env(**opts)


def read_jrc_occurrence(
    hcfg: HydrologyReviewConfig, bounds_4326: tuple[float, float, float, float]
) -> tuple[np.ndarray, rasterio.Affine, list[str]]:
    """Read occurrence for a lon/lat box. Returns (uint8 array, transform, source URLs).

    Values > valid_max (255 observed in v1.4 tiles) are mapped to NODATA_OUT.
    """
    jcfg = hcfg.jrc_occurrence
    urls = [
        jcfg.url_template.format(tile=t)
        for t in jrc_tiles_for_bounds(bounds_4326, jcfg.tile_size_deg)
    ]
    log.info("reading JRC occurrence from %s", urls)
    with _gdal_env():
        sources = [rasterio.open(f"/vsicurl/{u}") for u in urls]
        try:
            for src in sources:
                if src.crs is None or src.crs.to_epsg() != 4326:
                    raise ValueError(f"unexpected CRS {src.crs} in {src.name}")
            arr, transform = merge(sources, bounds=bounds_4326, nodata=jcfg.nodata_value)
        finally:
            for src in sources:
                src.close()
    arr = arr[0]
    arr = np.where(arr > jcfg.valid_max, NODATA_OUT, arr).astype(np.uint8)
    return arr, transform, urls


def snapped_grid(
    bounds: tuple[float, float, float, float], resolution: float
) -> tuple[rasterio.Affine, int, int]:
    """Grid aligned to integer multiples of the resolution (so later grids can match)."""
    west, south, east, north = bounds
    west = math.floor(west / resolution) * resolution
    north = math.ceil(north / resolution) * resolution
    east = math.ceil(east / resolution) * resolution
    south = math.floor(south / resolution) * resolution
    width = round((east - west) / resolution)
    height = round((north - south) / resolution)
    return from_origin(west, north, resolution, resolution), width, height


def occurrence_on_analysis_grid(
    cfg: ProjectConfig, extent_m: tuple[float, float, float, float]
) -> tuple[np.ndarray, rasterio.Affine, list[str]]:
    """JRC occurrence reprojected (nearest neighbour) to the snapped analysis grid."""
    hcfg = cfg.hydrology_review
    epsg = cfg.crs.analysis_epsg
    bounds_ll = transform_bounds(epsg, 4326, *extent_m, densify_pts=21)
    src, src_tf, urls = read_jrc_occurrence(hcfg, bounds_ll)
    dst_tf, width, height = snapped_grid(extent_m, hcfg.analysis_resolution_m)
    dst = np.full((height, width), NODATA_OUT, dtype=np.uint8)
    reproject(
        src,
        dst,
        src_transform=src_tf,
        src_crs="EPSG:4326",
        src_nodata=NODATA_OUT,
        dst_transform=dst_tf,
        dst_crs=f"EPSG:{epsg}",
        dst_nodata=NODATA_OUT,
        resampling=Resampling.nearest,
    )
    return dst, dst_tf, urls


def fetch_cached(url: str, cache_dir: Path, retries: int = 4) -> tuple[Path, str]:
    """Download once into cache_dir; return (path, md5). Retries with backoff."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / url.rsplit("/", 1)[-1]
    if not dest.exists():
        for attempt in range(retries + 1):
            try:
                log.info("downloading %s", url)
                with urllib.request.urlopen(url, timeout=120) as resp:  # noqa: S310
                    tmp = dest.with_suffix(dest.suffix + ".part")
                    tmp.write_bytes(resp.read())
                    tmp.replace(dest)
                break
            except OSError as exc:
                if attempt == retries:
                    raise RuntimeError(f"could not download {url}: {exc}") from exc
                time.sleep(2 ** (attempt + 1))
    return dest, hashlib.md5(dest.read_bytes()).hexdigest()  # noqa: S324 (provenance only)


def load_coarse_river(cfg: ProjectConfig, cache_dir: Path) -> tuple[gpd.GeoDataFrame, str]:
    ref = cfg.hydrology_review.coarse_river_reference
    path, md5 = fetch_cached(ref.url, cache_dir)
    rivers = gpd.read_file(path)
    sel = rivers[(rivers["name"] == ref.feature_name) & (rivers["featurecla"] == ref.feature_class)]
    if sel.empty:
        raise ValueError(f"{ref.feature_name!r} ({ref.feature_class}) not found in {ref.url}")
    sel = sel[["name", "featurecla", "scalerank", "geometry"]].to_crs(cfg.crs.analysis_epsg)
    sel["source"] = f"{ref.dataset}; {ref.version}"
    sel["note"] = "1:10M generalisation; not an active-channel or freshwater-delivery map"
    return sel, md5


# --------------------------------------------------------------------------- analysis


@dataclass
class AOIHydrologyStats:
    aoi_id: str
    role: str
    area_km2: float
    valid_fraction: float
    occurrence_class_km2: dict[str, float]
    area_below_pct_km2: dict[str, float]
    water_ever_km2: float
    channel_components: int
    channel_km2_inside: float
    channel_km2_total_of_touching: float
    channel_fraction_inside: float
    largest_component_touches_review_edge: bool
    coarse_river_intersects: bool
    coarse_river_distance_km: float
    notes: list[str] = field(default_factory=list)


def label_channels(occ: np.ndarray, min_pct: float) -> tuple[np.ndarray, int]:
    """8-connected groups of pixels observed as water at least min_pct of the time."""
    water = (occ != NODATA_OUT) & (occ >= min_pct)
    return ndimage.label(water, structure=np.ones((3, 3), dtype=bool))


def aoi_stats(
    occ: np.ndarray,
    transform: rasterio.Affine,
    labels: np.ndarray,
    aoi_row: gpd.GeoSeries,
    hcfg: HydrologyReviewConfig,
    river: gpd.GeoDataFrame | None,
    reference_pt,
) -> AOIHydrologyStats:
    px_km2 = abs(transform.a * transform.e) / 1e6
    inside = ~geometry_mask([aoi_row.geometry], occ.shape, transform, all_touched=False)
    valid = inside & (occ != NODATA_OUT)
    n_inside = int(inside.sum())
    classes = {}
    for name, (lo, hi) in hcfg.occurrence_classes_pct.items():
        # Upper bin is closed so 100 % is counted.
        upper = (occ <= hi) if hi >= 100 else (occ < hi)
        classes[name] = float(((occ >= lo) & upper & valid).sum() * px_km2)
    touching = np.unique(labels[inside & (labels > 0)])
    comp_inside = float((inside & np.isin(labels, touching)).sum() * px_km2)
    comp_total = float(np.isin(labels, touching).sum() * px_km2) if touching.size else 0.0
    edge_touch = False
    if touching.size:
        sizes = ndimage.sum_labels(np.ones_like(labels), labels, touching)
        largest = touching[int(np.argmax(sizes))]
        edge = np.zeros_like(inside)
        edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
        edge_touch = bool((edge & (labels == largest)).any())
    intersects, dist_km = False, float("nan")
    if river is not None and not river.empty:
        line = unary_union(river.geometry)
        intersects = bool(line.intersects(aoi_row.geometry))
        dist_km = float(line.distance(reference_pt) / 1000)
    return AOIHydrologyStats(
        aoi_id=aoi_row.aoi_id,
        role=aoi_row.role,
        area_km2=float(aoi_row.area_km2),
        valid_fraction=float(valid.sum() / n_inside) if n_inside else 0.0,
        occurrence_class_km2=classes,
        area_below_pct_km2={
            f"{t:g}": float(((occ < t) & valid).sum() * px_km2) for t in hcfg.cumulative_below_pct
        },
        water_ever_km2=float(((occ > 0) & valid).sum() * px_km2),
        channel_components=int(touching.size),
        channel_km2_inside=comp_inside,
        channel_km2_total_of_touching=comp_total,
        channel_fraction_inside=comp_inside / comp_total if comp_total else float("nan"),
        largest_component_touches_review_edge=edge_touch,
        coarse_river_intersects=intersects,
        coarse_river_distance_km=dist_km,
    )


def channel_polygons(
    labels: np.ndarray, transform: rasterio.Affine, keep: np.ndarray, epsg: int
) -> gpd.GeoDataFrame:
    """Polygonise the given channel components for GIS inspection."""
    mask = np.isin(labels, keep)
    geoms, ids = [], []
    for geom, value in shapes(labels.astype(np.int32), mask=mask, transform=transform):
        geoms.append(shape(geom))
        ids.append(int(value))
    gdf = gpd.GeoDataFrame({"component_id": ids}, geometry=geoms, crs=epsg)
    if gdf.empty:
        return gdf
    gdf = gdf.dissolve(by="component_id", as_index=False)
    gdf["area_km2"] = gdf.geometry.area / 1e6
    return gdf


@dataclass
class RiverConnectivity:
    line_pixels: int
    line_pixels_on_aoi_components: int
    nearest_connected_line_pixel_km: float

    @property
    def fraction(self) -> float:
        return self.line_pixels_on_aoi_components / self.line_pixels if self.line_pixels else 0.0


def river_connectivity(
    labels: np.ndarray,
    transform: rasterio.Affine,
    aoi_components: np.ndarray,
    river: gpd.GeoDataFrame,
    reference_pt,
) -> RiverConnectivity:
    """How much of the coarse river line lies on water components that also reach the AOI.

    Topological connectivity through frequently inundated pixels only. It does not show the
    direction, volume or salinity of flow.
    """
    from rasterio.features import rasterize

    line = rasterize(
        [(g, 1) for g in river.geometry],
        out_shape=labels.shape,
        transform=transform,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)
    connected = line & np.isin(labels, aoi_components) & (labels > 0)
    dist = float("nan")
    if connected.any():
        rows, cols = np.nonzero(connected)
        xs, ys = rasterio.transform.xy(transform, rows, cols)
        dist = float(
            np.min(np.hypot(np.asarray(xs) - reference_pt.x, np.asarray(ys) - reference_pt.y))
            / 1000
        )
    return RiverConnectivity(int(line.sum()), int(connected.sum()), dist)


def assess(
    stats: list[AOIHydrologyStats],
    channel_min_pct: float,
    connectivity: RiverConnectivity | None = None,
) -> list[Check]:
    """Deterministic interpretation of the AOI statistics. No freshwater claims."""
    primary = next(s for s in stats if s.role == "primary")
    checks = [
        Check(
            "jrc_valid_coverage",
            "PASS" if primary.valid_fraction >= 0.95 else "WARN",
            f"{primary.valid_fraction:.1%} of primary-AOI pixels have valid JRC occurrence",
        ),
        Check(
            "creek_system_present",
            "PASS" if primary.channel_components > 0 else "FAIL",
            f"{primary.channel_components} water component(s) with occurrence >= "
            f"{channel_min_pct:g}% intersect the primary AOI "
            f"({primary.channel_km2_inside:.2f} km2 inside it). Presence of frequently "
            "inundated channels only; says nothing about their water source.",
        ),
    ]
    frac = primary.channel_fraction_inside
    if primary.largest_component_touches_review_edge:
        # A component running off the review extent is part of a larger (tidal/regional)
        # water network. No AOI can contain it, so containment is reported, not scored.
        status, tail = (
            "WARN",
            (
                "the largest of them continues to the edge of the review extent, i.e. the creeks "
                "are part of a water network larger than any candidate AOI. Containment cannot "
                "be achieved by enlarging a buffer; hydrological context must be judged from "
                "channel connectivity to a documented freshwater source."
            ),
        )
    else:
        status = "PASS" if frac >= 0.5 else "WARN"
        tail = "the largest of them ends within the review extent."
    checks.append(
        Check(
            "creek_network_extent",
            status,
            f"the primary AOI holds {frac:.1%} of the area of the water components it "
            f"intersects ({primary.channel_km2_total_of_touching:.1f} km2 in total); " + tail,
        )
    )
    dry = primary.occurrence_class_km2.get("rarely_or_never", float("nan"))
    checks.append(
        Check(
            "land_surface_available",
            "PASS" if dry >= 0.1 * primary.area_km2 else "WARN",
            f"{dry:.2f} km2 ({dry / primary.area_km2:.1%}) of the primary AOI was rarely or "
            "never observed as water (JRC 1984-2021). Bare saline-flat (Site A) candidates "
            "need surfaces that are exposed in the analysed images; intermittently flooded "
            "flats may still qualify under tide-filtered imagery (to be tested in M2+). "
            "Sensitivity to the class edge - area below each occurrence level: "
            + ", ".join(f"<{k}%: {v:.2f} km2" for k, v in primary.area_below_pct_km2.items()),
        )
    )
    checks.append(
        Check(
            "coarse_main_channel_in_aoi",
            "PASS" if primary.coarse_river_intersects else "WARN",
            f"Natural Earth 1:10M Indus centreline is {primary.coarse_river_distance_km:.1f} km "
            f"from the reference point and "
            f"{'intersects' if primary.coarse_river_intersects else 'does not intersect'} the "
            "primary AOI (coarse cartographic reference, not active-channel evidence).",
        )
    )
    if connectivity is not None:
        linked = connectivity.line_pixels_on_aoi_components > 0
        checks.append(
            Check(
                "river_creek_connectivity",
                # Never PASS in M1: the connected water body includes open coastal water, so
                # the link may run through the sea rather than through creeks.
                "WARN",
                f"{connectivity.fraction:.1%} of the coarse Indus line pixels in the review "
                f"extent lie on water components (occurrence >= {channel_min_pct:g}%) that also "
                "reach the primary AOI"
                + (
                    f"; nearest such pixel is {connectivity.nearest_connected_line_pixel_km:.1f} "
                    "km from the reference point"
                    if linked
                    else ""
                )
                + ". Topological connectivity only, and the connected water body includes open "
                "coastal water, so the link may run through the sea rather than through creeks "
                "(a sea/coastline mask is needed to test creek-only connectivity). Not evidence "
                "of flow direction, discharge or freshwater reaching the AOI creeks.",
            )
        )
    checks.append(
        Check(
            "freshwater_influence_candidate",
            "WARN",
            "UNRESOLVED. No M1 input can establish freshwater delivery to any creek in any "
            "candidate AOI. JRC occurrence cannot separate tidal from riverine water and the "
            "Natural Earth line is a 1:10M generalisation. See the review report for the "
            "evidence required.",
        )
    )
    return checks


def stats_to_json(stats: list[AOIHydrologyStats]) -> list[dict]:
    out = []
    for s in stats:
        d = s.__dict__.copy()
        d = {k: (None if isinstance(v, float) and math.isnan(v) else v) for k, v in d.items()}
        out.append(d)
    return json.loads(json.dumps(out))
