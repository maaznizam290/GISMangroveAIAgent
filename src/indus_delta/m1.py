"""Milestone M1: configuration, CRS, AOI, hydrological-context review and preview."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import box

from indus_delta import aoi as aoi_mod
from indus_delta import hydrology as hyd
from indus_delta.checks import Check, worst
from indus_delta.config import Configs
from indus_delta.crs import check_analysis_crs
from indus_delta.manifest import write_manifest
from indus_delta.preview import render_aoi_preview

log = logging.getLogger(__name__)


@dataclass
class M1Result:
    checks: list[Check]
    status: str
    out_dir: Path
    outputs: list[Path]


def static_checks(cfgs: Configs) -> list[Check]:
    """Checks that need no network: config, CRS, reference provenance, AOI geometry."""
    p = cfgs.project
    loc = p.reference_location
    checks = [
        Check(
            "config_valid",
            "PASS",
            f"project/datasets/indices configs validate (version {p.config_version})",
        )
    ]
    checks += check_analysis_crs(p.crs.analysis_epsg, loc.longitude, loc.latitude)
    checks.append(
        Check(
            "reference_location_provenance",
            "PASS" if loc.verification_status == "verified" else "WARN",
            f"{loc.name} ({loc.longitude}, {loc.latitude}); {len(loc.sources)} source(s): "
            + "; ".join(f"{s.dataset} [{s.version}]" for s in loc.sources)
            + f". Status: {loc.verification_status}.",
        )
    )
    no_catalog = cfgs.datasets.pending("catalog_verified")
    no_account = cfgs.datasets.pending("verified")
    checks.append(
        Check(
            "dataset_ids_verified",
            "PASS" if not no_account else "WARN",
            (
                f"not in the Earth Engine catalog or unchecked: {', '.join(no_catalog) or 'none'}; "
                "not yet confirmed by an authenticated inventory: "
                f"{', '.join(no_account) or 'none'}"
            )
            if no_account
            else "all required datasets verified by an authenticated inventory",
        )
    )
    aoi = aoi_mod.build_aoi(p)
    ref = aoi_mod.reference_point(p)
    geom = aoi.geometry.iloc[0]
    checks.append(
        Check(
            "aoi_geometry_valid",
            "PASS" if geom.is_valid and not geom.is_empty else "FAIL",
            f"{aoi.aoi_id.iloc[0]}: {geom.geom_type}, {aoi.area_km2.iloc[0]:.3f} km2, "
            f"CRS EPSG:{aoi.crs.to_epsg()}",
        )
    )
    checks.append(
        Check(
            "aoi_contains_reference",
            "PASS" if geom.contains(ref.geometry.iloc[0]) else "WARN",
            "primary AOI contains the reference point"
            if geom.contains(ref.geometry.iloc[0])
            else "primary AOI does not contain the reference point (allowed for operator polygons)",
        )
    )
    if p.aoi.mode == "buffer":
        expected = math.pi * p.aoi.buffer_m**2 / 1e6
        rel = abs(aoi.area_km2.iloc[0] - expected) / expected
        checks.append(
            Check(
                "aoi_buffer_area",
                "PASS" if rel < 1e-3 else "FAIL",
                f"buffer area {aoi.area_km2.iloc[0]:.3f} km2 vs pi*r^2 {expected:.3f} km2 "
                f"(relative difference {rel:.2e})",
            )
        )
    return checks


def run_m1(
    cfgs: Configs,
    out_root: Path | None = None,
    cache_dir: Path = Path("data/cache"),
    command: str = "indus-delta m1",
) -> M1Result:
    p = cfgs.project
    out_dir = (out_root or p.project.output_dir) / "m1"
    out_dir.mkdir(parents=True, exist_ok=True)
    epsg = p.crs.analysis_epsg
    hcfg = p.hydrology_review

    checks = static_checks(cfgs)
    if worst(checks) == "FAIL":
        raise RuntimeError(
            "static M1 checks failed: " + "; ".join(c.detail for c in checks if c.status == "FAIL")
        )

    log.info("building AOIs")
    ref = aoi_mod.reference_point(p)
    primary = aoi_mod.build_aoi(p)
    alts = aoi_mod.alternative_aois(p)
    aois = pd.concat([primary, alts], ignore_index=True)
    minx, miny, maxx, maxy = aois.total_bounds
    m = hcfg.review_margin_m
    extent = (minx - m, miny - m, maxx + m, maxy + m)

    log.info("reading JRC occurrence for review extent %s", [round(v) for v in extent])
    occ, tf, jrc_urls = hyd.occurrence_on_analysis_grid(p, extent)
    labels, _ = hyd.label_channels(occ, hcfg.channel_occurrence_min_pct)
    log.info("loading coarse river reference")
    river, river_md5 = hyd.load_coarse_river(p, cache_dir)
    pt = ref.geometry.iloc[0]
    stats = [hyd.aoi_stats(occ, tf, labels, row, hcfg, river, pt) for _, row in aois.iterrows()]
    touching = np.unique(
        labels[~geometry_mask([primary.geometry.iloc[0]], occ.shape, tf) & (labels > 0)]
    )
    connectivity = hyd.river_connectivity(labels, tf, touching, river, pt)
    checks += hyd.assess(stats, hcfg.channel_occurrence_min_pct, connectivity)
    status = worst(checks)

    # ---- GIS outputs
    outputs: list[Path] = []
    tif = out_dir / f"jrc_gsw14_occurrence_review_epsg{epsg}_{hcfg.analysis_resolution_m:g}m.tif"
    with rasterio.open(
        tif,
        "w",
        driver="GTiff",
        height=occ.shape[0],
        width=occ.shape[1],
        count=1,
        dtype="uint8",
        crs=f"EPSG:{epsg}",
        transform=tf,
        nodata=hyd.NODATA_OUT,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        dst.write(occ, 1)
        dst.set_band_description(1, "water_occurrence_pct_1984_2021")
        dst.update_tags(1, units="percent of valid observations", nodata_meaning="no data")
        dst.update_tags(
            source="JRC Global Surface Water v1.4 occurrence",
            source_urls=" ".join(jrc_urls),
            processing=f"nearest-neighbour reprojection from EPSG:4326 0.00025 deg to "
            f"EPSG:{epsg} {hcfg.analysis_resolution_m:g} m snapped grid; values >"
            f"{hcfg.jrc_occurrence.valid_max} set to {hyd.NODATA_OUT}",
            native_resolution="0.00025 deg (~30 m); not upsampled",
        )
    outputs.append(tif)

    channels = hyd.channel_polygons(labels, tf, touching, epsg)
    if not channels.empty:
        channels["min_occurrence_pct"] = hcfg.channel_occurrence_min_pct
        channels["source"] = "JRC GSW v1.4 occurrence (1984-2021)"
        channels["note"] = "frequently inundated water; water source not determined"
    gpkg = aoi_mod.write_layers(
        out_dir / "m1_aoi.gpkg",
        {
            "reference_location": ref,
            "aoi_primary": primary,
            "aoi_alternatives": alts,
            "coarse_indus_centerline": gpd.clip(river, gpd.GeoSeries([box(*extent)], crs=epsg)),
            "jrc_water_components_touching_primary_aoi": channels,
        },
    )
    outputs.append(gpkg)

    loc = p.reference_location
    png = render_aoi_preview(
        out_dir / "m1_aoi_preview.png",
        occurrence=occ,
        transform=tf,
        epsg=epsg,
        aoi=primary,
        alternatives=alts,
        reference=ref,
        river=river,
        title=f"M1 AOI review - {p.project.study_area_name}",
        source_note=(
            f"Reference point: {loc.sources[0].dataset} ({loc.sources[0].version}), status "
            f"{loc.verification_status}. Water occurrence: JRC Global Surface Water v1.4 "
            "(EC JRC/Google), 1984-2021, shown at native ~30 m. River: Natural Earth 1:10M "
            "(public domain), coarse reference only. Water occurrence does not indicate "
            "salinity or freshwater supply."
        ),
    )
    outputs.append(png)

    review = {
        "status": status,
        "checks": [c.to_dict() for c in checks],
        "aoi_statistics": hyd.stats_to_json(stats),
        "review_extent_m": list(extent),
        "review_nodata_fraction": float((occ == hyd.NODATA_OUT).mean()),
        "river_connectivity": {
            "line_pixels": connectivity.line_pixels,
            "line_pixels_on_primary_aoi_components": connectivity.line_pixels_on_aoi_components,
            "nearest_connected_line_pixel_km": connectivity.nearest_connected_line_pixel_km
            if connectivity.line_pixels_on_aoi_components
            else None,
        },
        "inputs": {
            "jrc_occurrence_urls": jrc_urls,
            "coarse_river": {
                "url": hcfg.coarse_river_reference.url,
                "version": hcfg.coarse_river_reference.version,
                "md5": river_md5,
            },
        },
    }
    rjson = out_dir / "m1_aoi_review.json"
    rjson.write_text(json.dumps(review, indent=2), encoding="utf-8")
    outputs.append(rjson)
    rmd = out_dir / "m1_aoi_review.md"
    rmd.write_text(render_review_markdown(cfgs, review), encoding="utf-8")
    outputs.append(rmd)

    manifest = write_manifest(
        out_dir / "run_manifest.json",
        milestone="M1",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[
            {
                "name": "jrc_gsw_v1_4_occurrence",
                "urls": jrc_urls,
                "access": "HTTP range reads (GDAL /vsicurl)",
            },
            {
                "name": "natural_earth_rivers",
                "url": hcfg.coarse_river_reference.url,
                "version": hcfg.coarse_river_reference.version,
                "md5": river_md5,
            },
            {
                "name": "reference_location",
                "sources": [s.model_dump(mode="json") for s in loc.sources],
            },
        ],
        outputs=outputs,
        status=status,
    )
    outputs.append(manifest)
    return M1Result(checks, status, out_dir, outputs)


def render_review_markdown(cfgs: Configs, review: dict) -> str:
    p = cfgs.project
    rows = []
    for s in review["aoi_statistics"]:
        cls = s["occurrence_class_km2"]
        dist = s["coarse_river_distance_km"]
        rows.append(
            f"| {s['aoi_id']} | {s['role']} | {s['area_km2']:.1f} | {s['valid_fraction']:.1%} "
            f"| {cls.get('rarely_or_never', 0):.1f} | {cls.get('intermittent', 0):.1f} "
            f"| {cls.get('frequent', 0):.1f} | {cls.get('near_permanent', 0):.1f} "
            f"| {s['channel_components']} | {s['channel_km2_inside']:.1f} "
            f"| {'yes' if s['coarse_river_intersects'] else 'no'} "
            f"| {'' if dist is None else f'{dist:.1f}'} |"
        )
    classes = ", ".join(
        f"{k} {v[0]:g}-{v[1]:g}%" for k, v in p.hydrology_review.occurrence_classes_pct.items()
    )
    columns = [
        "AOI",
        "Role",
        "Area",
        "Valid JRC",
        "Rarely/never water",
        "Intermittent",
        "Frequent",
        "Near-permanent",
        "Water components",
        "Component area inside",
        "Crosses NE Indus line",
        "Distance ref to NE Indus (km)",
    ]
    header = "| " + " | ".join(columns) + " |\n" + "|---" * len(columns) + "|"
    checks = "\n".join(f"| {c['name']} | {c['status']} | {c['detail']} |" for c in review["checks"])
    return f"""# M1 AOI review: {p.project.study_area_name}

Generated by `indus-delta m1`. Every number below comes from the run recorded in
`run_manifest.json`. Overall status: **{review["status"]}**.

## Gate checks

| Check | Status | Detail |
|---|---|---|
{checks}

## AOI statistics (JRC GSW v1.4 occurrence, 1984-2021)

Occurrence classes: {classes}. Channel components are 8-connected groups of pixels with
occurrence >= {p.hydrology_review.channel_occurrence_min_pct:g}%. Areas in km2 on a
{p.hydrology_review.analysis_resolution_m:g} m grid in EPSG:{p.crs.analysis_epsg}.

{header}
{chr(10).join(rows)}

No-data (value 255) covers {review["review_nodata_fraction"]:.1%} of the review extent.

## Interpretation limits

* JRC occurrence counts how often a pixel was water. Tidal sea water, river water and rain
  ponding look the same, so these numbers cannot show freshwater influence.
* The Natural Earth Indus line is a 1:10M cartographic generalisation. Its position is not
  evidence of the present active channel, of distributary connections, or of freshwater
  discharge reaching any creek.
* "Water components" that run to the edge of the review extent are part of a water network
  larger than every candidate AOI.

## Decision required from the operator

The freshwater-influence question is unresolved for every candidate AOI. Before M2 the
operator should choose the AOI (primary or an alternative, or a custom polygon via
`aoi.mode: polygon`) on the basis of documented hydrological evidence, for example:

1. A traceable active-channel / distributary map for the present-day delta (recent survey,
   published study, or channel mapping from recent imagery done and validated in M2+).
2. Discharge records downstream of Kotri Barrage for the study years, to establish whether
   and when river water reaches the delta.
3. Field creek-water salinity or electrical-conductivity measurements with date, time,
   GPS location, tide state and method (stored as `water_salinity_field`).
4. An independent second source for the Keti Bandar reference location.

The study protocol (`docs/study_protocol.md`) lists all unresolved assumptions.
"""
