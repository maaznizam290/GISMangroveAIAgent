"""Milestone M5: separate analytical layers.

  mangrove_extent             classified  (from the validated land-cover map)
  mangrove_spectral_vigour    derived     (relative terciles; not canopy-health grades)
  tidal_inundation            derived     (water frequency from per-image detection)
  soil_salinity_proxy         proxy       (SWIR features on eligible bare surfaces only)
  freshwater_influence_proxy  proxy       (along-channel distance to a documented source,
                                           plus an investigative turbidity-change band)
  water_salinity_field        measured    (operator field data, if supplied)

Each layer records what its values are derived from and what was used only as a mask.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
from rasterio.features import rasterize
from scipy import ndimage, sparse
from scipy.sparse.csgraph import dijkstra
from scipy.stats import rankdata

from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.features import FeatureStack, find_composite, load_stack
from indus_delta.layer_io import Grid, LayerMeta, read_layer, write_layer

log = logging.getLogger(__name__)

NODATA_U8 = 255
NODATA_F = -9999.0

# Eligibility codes of the soil-salinity proxy.
ELIGIBLE, EXCL_MANGROVE, EXCL_WATER, EXCL_OTHER_CLASS, EXCL_WET, EXCL_NO_DATA = 0, 1, 2, 3, 4, 5
ELIGIBILITY_CODES = {
    ELIGIBLE: "eligible bare surface",
    EXCL_MANGROVE: "excluded: mangrove",
    EXCL_WATER: "excluded: open water",
    EXCL_OTHER_CLASS: "excluded: other land-cover class",
    EXCL_WET: "excluded: inundated too often",
    EXCL_NO_DATA: "excluded: no data / too few obs",
}


class LayerUnavailable(RuntimeError):
    """A layer cannot be produced from the available inputs (reason in the message)."""


# --------------------------------------------------------------------------- mangrove


def mangrove_layers(
    landcover: np.ndarray, p_mangrove: np.ndarray, stack: FeatureStack, cfgs: Configs
) -> dict[str, np.ndarray]:
    cl, mc = cfgs.classification, cfgs.layers.mangrove
    mangrove_code = cl.code_of("mangrove")
    nodata = landcover == cl.nodata_class
    extent = np.where(nodata, np.nan, (landcover == mangrove_code).astype(float))
    vig_src = stack.band(mc.vigour_season, mc.vigour_index)
    in_m = (landcover == mangrove_code) & np.isfinite(vig_src)
    vigour = np.full(landcover.shape, np.nan)
    if in_m.any():
        q1, q2 = np.quantile(vig_src[in_m], mc.vigour_quantiles)
        vigour[in_m] = 1 + (vig_src[in_m] > q1) + (vig_src[in_m] > q2)
    return {
        "mangrove_extent": extent,
        "mangrove_probability": p_mangrove,
        "spectral_vigour_class": vigour,
    }


# --------------------------------------------------------------------------- inundation


def calibrate_threshold(values: np.ndarray, is_water: np.ndarray) -> tuple[float, float]:
    """Threshold on an index maximising balanced accuracy (water above the threshold).
    Returns (threshold, balanced_accuracy)."""
    ok = np.isfinite(values)
    v, w = values[ok], is_water[ok].astype(bool)
    if w.sum() == 0 or (~w).sum() == 0:
        raise ValueError("calibration needs both water and non-water samples with data")
    cands = np.unique(v)
    mids = (cands[:-1] + cands[1:]) / 2 if cands.size > 1 else cands
    best = (np.nan, -1.0)
    for t in mids:
        tpr = np.mean(v[w] > t)
        tnr = np.mean(v[~w] <= t)
        ba = (tpr + tnr) / 2
        if ba > best[1]:
            best = (float(t), float(ba))
    return best


def inundation_path(cfgs: Configs, series: str, year: int) -> Path:
    d = cfgs.layers.tidal_inundation.input_dir
    matches = sorted(d.glob(f"{series}_water_frequency_{year}_epsg*_*m.tif")) if d.is_dir() else []
    if not matches:
        raise LayerUnavailable(
            f"no water-frequency raster for {series} {year} in {d}; calibrate the threshold "
            "(`indus-delta calibrate-water`) and export it (`indus-delta water-frequency`)"
        )
    return matches[0]


def load_inundation(
    cfgs: Configs, series: str, year: int, grid: Grid
) -> tuple[np.ndarray, np.ndarray, Path]:
    path = inundation_path(cfgs, series, year)
    bands, g, _ = read_layer(path)
    if not g.same_as(grid):
        raise LayerUnavailable(f"{path.name} is not on the land-cover grid")
    freq, n = bands["water_frequency"], bands["n_valid"]
    freq = np.where(n >= cfgs.layers.tidal_inundation.min_valid_observations, freq, np.nan)
    return freq, n, path


# --------------------------------------------------------------------------- soil salinity proxy


def percentile_rank(values: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.full(values.shape, np.nan)
    sel = mask & np.isfinite(values)
    if sel.any():
        out[sel] = 100 * (rankdata(values[sel]) - 0.5) / sel.sum()
    return out


def salinity_proxy(
    landcover: np.ndarray, stack: FeatureStack, inundation: np.ndarray, cfgs: Configs
) -> dict[str, np.ndarray]:
    """SWIR-feature percentile ranks among eligible bare-surface pixels.

    The land-cover map and inundation frequency only decide eligibility; the proxy values
    come exclusively from the configured SWIR features.
    """
    cl, sc = cfgs.classification, cfgs.layers.soil_salinity_proxy
    eligible_codes = [cl.code_of(n) for n in sc.eligible_classes]
    code = np.full(landcover.shape, EXCL_OTHER_CLASS, dtype=float)
    code[np.isin(landcover, eligible_codes)] = ELIGIBLE
    code[landcover == cl.code_of("mangrove")] = EXCL_MANGROVE
    code[landcover == cl.code_of("water")] = EXCL_WATER
    wet = np.isfinite(inundation) & (inundation > sc.max_inundation_frequency)
    code[(code == ELIGIBLE) & wet] = EXCL_WET
    feats = []
    for f in sc.features:
        if f.kind == "band":
            v = stack.band(sc.season, f.name)
        else:
            num, den = stack.band(sc.season, f.numerator), stack.band(sc.season, f.denominator)
            v = np.divide(num, den, out=np.full(num.shape, np.nan), where=np.abs(den) > 1e-6)
        feats.append(f.direction * v)
    missing = (
        (landcover == cl.nodata_class)
        | ~np.isfinite(inundation)
        | ~np.all([np.isfinite(v) for v in feats], axis=0)
    )
    code[missing] = EXCL_NO_DATA
    eligible = code == ELIGIBLE
    ranks = [percentile_rank(v, eligible) for v in feats]
    proxy = np.full(code.shape, np.nan)
    if eligible.any():
        proxy[eligible] = np.mean(np.stack([r[eligible] for r in ranks]), axis=0)
    return {"soil_salinity_proxy_percentile": proxy, "eligibility_code": code}


# --------------------------------------------------------------------------- freshwater proxy


def load_freshwater_source(cfgs: Configs) -> gpd.GeoDataFrame:
    fc = cfgs.layers.freshwater_influence_proxy
    if not fc.source_path.is_file():
        raise LayerUnavailable(
            f"no documented freshwater source at {fc.source_path}. Supply the active "
            "channel/outlet with its evidence (discharge records, survey, publication); "
            "proximity to the historic Indus channel is not accepted"
        )
    src = gpd.read_file(fc.source_path)
    missing = [f for f in fc.required_source_fields if f not in src.columns]
    if missing or src.empty:
        raise LayerUnavailable(f"{fc.source_path} lacks fields {missing} or is empty")
    if src[fc.required_source_fields].isna().any().any():
        raise LayerUnavailable(f"{fc.source_path}: every source needs documented evidence")
    if src.crs is None:
        raise LayerUnavailable(f"{fc.source_path} has no CRS")
    return src.to_crs(cfgs.project.crs.analysis_epsg)


def along_channel_distance(channel: np.ndarray, sources: np.ndarray, pixel: float) -> np.ndarray:
    """Shortest path (m) through 8-connected channel pixels from any source pixel.

    NaN off the channel network and on channel pixels not connected to a source.
    """
    h, w = channel.shape
    idx = -np.ones((h, w), dtype=np.int64)
    nodes = np.flatnonzero(channel)
    idx.flat[nodes] = np.arange(nodes.size)
    rows, cols, wts = [], [], []
    # Each undirected neighbour pair once: right, down, down-right, down-left.
    for dr, dc in ((0, 1), (1, 0), (1, 1), (1, -1)):
        a = idx[0 : h - dr, max(0, -dc) : w - max(0, dc)]
        b = idx[dr:h, max(0, dc) : w + min(0, dc)]
        both = (a >= 0) & (b >= 0)
        rows.append(a[both])
        cols.append(b[both])
        wts.append(np.full(int(both.sum()), pixel * (np.sqrt(2) if dr and dc else 1.0)))
    out = np.full((h, w), np.nan)
    src_nodes = idx[sources & channel]
    if nodes.size == 0 or src_nodes.size == 0:
        return out
    n = nodes.size
    graph = sparse.coo_matrix(
        (np.concatenate(wts), (np.concatenate(rows), np.concatenate(cols))), shape=(n, n)
    ).tocsr()
    dist = dijkstra(graph, directed=False, indices=src_nodes, min_only=True)
    out.flat[nodes] = np.where(np.isfinite(dist), dist, np.nan)
    return out


def freshwater_proxy(
    source: gpd.GeoDataFrame, inundation: np.ndarray, stack: FeatureStack, grid: Grid, cfgs: Configs
) -> dict[str, np.ndarray]:
    fc = cfgs.layers.freshwater_influence_proxy
    pixel = abs(grid.transform.a)
    channel = np.isfinite(inundation) & (inundation >= fc.channel_min_frequency)
    src = rasterize(
        [(g, 1) for g in source.geometry],
        out_shape=(grid.height, grid.width),
        transform=grid.transform,
        all_touched=True,
        dtype="uint8",
    ).astype(bool)
    along = along_channel_distance(channel, src, pixel)
    # Distance from every pixel to its nearest channel pixel, plus that pixel's along-channel
    # distance. Approximate: the nearest channel pixel may be unconnected while another is.
    if channel.any():
        edt, (ri, ci) = ndimage.distance_transform_edt(
            ~channel, sampling=pixel, return_indices=True
        )
        total = edt + along[ri, ci]
    else:
        total = np.full(channel.shape, np.nan)
    dry_b = stack.band("dry", fc.turbidity_band)
    post_b = stack.band("post_monsoon", fc.turbidity_band)
    turb = np.where(channel, post_b - dry_b, np.nan)
    return {
        "along_channel_distance_km": along / 1000,
        "distance_via_channel_km": total / 1000,
        "connected_to_source": np.where(channel, np.isfinite(along).astype(float), np.nan),
        "post_monsoon_minus_dry_" + fc.turbidity_band: turb,
    }


# --------------------------------------------------------------------------- orchestration


@dataclass
class LayerResult:
    name: str
    status: str  # produced / unavailable
    detail: str
    path: Path | None = None


def run_layers(
    cfgs: Configs, out_root: Path, series: str, year: int
) -> tuple[list[LayerResult], list[Check], Path]:
    from indus_delta.m4 import epoch_dir

    src_dir = epoch_dir(out_root, series, year)
    gate_path = src_dir / "validation_gate.json"
    if not gate_path.is_file():
        raise LayerUnavailable(f"no classification for {series} {year}; run `indus-delta classify`")
    gate = json.loads(gate_path.read_text())
    validated = gate["status"] == "PASS"
    lc_bands, grid, _ = read_layer(src_dir / "landcover.tif")
    cl = cfgs.classification
    landcover = np.nan_to_num(lc_bands["landcover_class"], nan=cl.nodata_class).astype(int)
    unc, _, _ = read_layer(src_dir / "classification_uncertainty.tif")
    stack = load_stack(cfgs, series, year)
    if not stack.grid.same_as(grid):
        raise LayerUnavailable("composites and land-cover map are on different grids")
    out = out_root / "m5" / f"{series}_{year}"
    results: list[LayerResult] = []
    checks = [
        Check(
            "classification_validated",
            "PASS" if validated else "WARN",
            f"validation gate {gate['status']}; layers depending on the land-cover "
            f"map are tagged {'validated' if validated else 'unvalidated'}",
        )
    ]
    lc_status = "validated" if validated else "unvalidated"
    composite_names = [f"{series}_{s}_{year}" for s in cl.features.seasons]

    # A class absent from training has no probability band; keep the layer, mark it missing.
    p_mangrove = unc.get("p_mangrove", np.full(landcover.shape, np.nan))
    m = mangrove_layers(landcover, p_mangrove, stack, cfgs)
    p = write_layer(
        out / "mangrove.tif",
        m,
        grid,
        LayerMeta(
            "mangrove",
            "classified",
            lc_status,
            "Mangrove extent (1/0) from the land-cover map, Random Forest mangrove vote fraction, "
            "and relative spectral-vigour terciles (1 low, 2 mid, 3 high) of "
            f"{cfgs.layers.mangrove.vigour_season} {cfgs.layers.mangrove.vigour_index} within the "
            "mapped mangrove. Vigour classes are NOT canopy-health or density grades.",
            derived_from=["landcover", "classification_uncertainty", *composite_names],
            units={
                "mangrove_extent": "1 mangrove / 0 other",
                "mangrove_probability": "fraction",
                "spectral_vigour_class": "relative tercile 1-3",
            },
        ),
        nodata=NODATA_F,
    )
    results.append(LayerResult("mangrove", "produced", lc_status, p))

    try:
        freq, nvalid, ipath = load_inundation(cfgs, series, year, grid)
    except LayerUnavailable as exc:
        freq = None
        results.append(LayerResult("tidal_inundation", "unavailable", str(exc)))
    if freq is not None:
        ti = cfgs.layers.tidal_inundation
        p = write_layer(
            out / "tidal_inundation.tif",
            {"water_frequency": freq, "n_valid_observations": nvalid},
            grid,
            LayerMeta(
                "tidal_inundation",
                "derived",
                "threshold_calibrated_unvalidated",
                f"Share of valid observations in {year} classed as water "
                f"({ti.optical_index} > {ti.optical_threshold}). Tide state "
                "at image time unknown (no tide model).",
                derived_from=[ipath.name],
                units={"water_frequency": "fraction (0-1)", "n_valid_observations": "count"},
            ),
            nodata=NODATA_F,
        )
        results.append(LayerResult("tidal_inundation", "produced", "", p))

        sp = salinity_proxy(landcover, stack, freq, cfgs)
        p = write_layer(
            out / "soil_salinity_proxy.tif",
            sp,
            grid,
            LayerMeta(
                "soil_salinity_proxy",
                "proxy",
                "proxy_uncalibrated",
                "Mean within-AOI percentile rank of SWIR features on eligible bare surfaces. "
                "Relative and uncalibrated: NOT a salinity measurement. Eligibility codes: "
                + json.dumps(ELIGIBILITY_CODES),
                derived_from=[
                    f"{series}_{cfgs.layers.soil_salinity_proxy.season}_{year}:"
                    + "+".join(f.name for f in cfgs.layers.soil_salinity_proxy.features)
                ],
                mask_from=["landcover", "tidal_inundation"],
                units={
                    "soil_salinity_proxy_percentile": "percentile rank 0-100",
                    "eligibility_code": "code",
                },
            ),
            nodata=NODATA_F,
        )
        results.append(LayerResult("soil_salinity_proxy", "produced", "uncalibrated", p))
        checks.append(
            Check(
                "salinity_eligible_pixels",
                "PASS" if (sp["eligibility_code"] == ELIGIBLE).any() else "WARN",
                f"{int((sp['eligibility_code'] == ELIGIBLE).sum())} eligible pixels",
            )
        )
    else:
        results.append(
            LayerResult(
                "soil_salinity_proxy",
                "unavailable",
                "needs tidal_inundation to exclude frequently wet surfaces",
            )
        )

    try:
        if freq is None:
            raise LayerUnavailable("needs tidal_inundation to define the channel network")
        source = load_freshwater_source(cfgs)
        fw = freshwater_proxy(source, freq, stack, grid, cfgs)
        p = write_layer(
            out / "freshwater_influence_proxy.tif",
            fw,
            grid,
            LayerMeta(
                "freshwater_influence_proxy",
                "proxy",
                "proxy_unvalidated",
                "Along-channel distance to the documented freshwater source through frequently "
                "inundated pixels, and the post-monsoon minus dry change of the turbidity band in "
                "channels (investigative). Connectivity is not evidence of freshwater delivery.",
                derived_from=["freshwater_source", "tidal_inundation", *composite_names],
                units={
                    k: (
                        "km"
                        if k.endswith("_km")
                        else "reflectance difference"
                        if k.startswith("post_monsoon")
                        else "1 connected / 0 not"
                    )
                    for k in fw
                },
            ),
            nodata=NODATA_F,
        )
        results.append(LayerResult("freshwater_influence_proxy", "produced", "unvalidated", p))
    except LayerUnavailable as exc:
        results.append(LayerResult("freshwater_influence_proxy", "unavailable", str(exc)))

    try:
        from indus_delta.samples import SamplesUnavailable, load_field_salinity

        field = load_field_salinity(cfgs.layers.water_salinity_field.path, cfgs)
        from indus_delta.aoi import write_layers

        p = write_layers(out / "water_salinity_field.gpkg", {"water_salinity_field": field})
        results.append(
            LayerResult("water_salinity_field", "produced", f"{len(field)} measurements", p)
        )
    except SamplesUnavailable as exc:
        results.append(LayerResult("water_salinity_field", "unavailable", str(exc)))

    for r in results:
        checks.append(
            Check(
                f"layer_{r.name}",
                "PASS" if r.status == "produced" else "WARN",
                r.detail or r.status,
            )
        )
    (out / "layers.json").write_text(
        json.dumps(
            [
                {
                    "name": r.name,
                    "status": r.status,
                    "detail": r.detail,
                    "path": str(r.path) if r.path else None,
                }
                for r in results
            ],
            indent=2,
        )
    )
    return results, checks, out


def composite_exists(cfgs: Configs, series: str, season: str, year: int) -> bool:
    try:
        find_composite(cfgs.classification.composites_dir, series, season, year)
        return True
    except FileNotFoundError:
        return False


# --------------------------------------------------------------------------- change


def change_layers(
    lc_from: np.ndarray, lc_to: np.ndarray, mangrove_code: int, nodata_class: int
) -> dict[str, np.ndarray]:
    """Class transitions (from*10 + to) and mangrove gain (+1) / loss (-1) / stable (0)."""
    valid = (lc_from != nodata_class) & (lc_to != nodata_class)
    transition = np.where(valid, lc_from * 10 + lc_to, np.nan)
    m0, m1 = lc_from == mangrove_code, lc_to == mangrove_code
    gain_loss = np.where(valid, m1.astype(int) - m0.astype(int), np.nan)
    return {"class_transition": transition, "mangrove_gain_loss": gain_loss}


def run_change(
    cfgs: Configs, out_root: Path, series: str, from_year: int, to_year: int
) -> tuple[Path, dict]:
    """Change between two validated epochs on the same grid."""
    from indus_delta.m4 import epoch_dir, require_validation_pass

    for y in (from_year, to_year):
        require_validation_pass(cfgs, out_root, series, y)
    cl = cfgs.classification
    a, ga, _ = read_layer(epoch_dir(out_root, series, from_year) / "landcover.tif")
    b, gb, _ = read_layer(epoch_dir(out_root, series, to_year) / "landcover.tif")
    if not ga.same_as(gb):
        raise LayerUnavailable("the two land-cover maps are on different grids")
    la = np.nan_to_num(a["landcover_class"], nan=cl.nodata_class).astype(int)
    lb = np.nan_to_num(b["landcover_class"], nan=cl.nodata_class).astype(int)
    bands = change_layers(la, lb, cl.code_of("mangrove"), cl.nodata_class)
    px = ga.pixel_area_m2 / 1e6
    summary = {
        "from_year": from_year,
        "to_year": to_year,
        "mangrove_gain_km2": float((bands["mangrove_gain_loss"] == 1).sum() * px),
        "mangrove_loss_km2": float((bands["mangrove_gain_loss"] == -1).sum() * px),
        "mangrove_stable_km2": float(
            ((la == cl.code_of("mangrove")) & (lb == cl.code_of("mangrove"))).sum() * px
        ),
    }
    path = write_layer(
        out_root / "m5" / f"change_{series}_{from_year}_{to_year}.tif",
        bands,
        ga,
        LayerMeta(
            "mangrove_change",
            "derived",
            "derived_from_validated_maps",
            f"Land-cover change {from_year} to {to_year}: class_transition = "
            "from_code*10 + to_code; mangrove_gain_loss = +1 gain, -1 loss, "
            "0 no change. Errors of both maps compound in the change map.",
            derived_from=[f"landcover_{series}_{from_year}", f"landcover_{series}_{to_year}"],
            units={"class_transition": "code", "mangrove_gain_loss": "code"},
            extra={k: str(v) for k, v in summary.items()},
        ),
        nodata=NODATA_F,
    )
    return path, summary
