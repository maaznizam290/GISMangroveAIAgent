"""Full-scale seasonal composites (M3): plan, then (only on explicit request) submit Earth
Engine batch exports. Refused until the AOI is confirmed and the preview gate has passed."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from indus_delta import aoi as aoi_mod
from indus_delta.config import Configs
from indus_delta.gate import GateError, require_preview_pass
from indus_delta.grid import aligned_bounds, transform_list
from indus_delta.seasons import windows_for_years

SERIES = ("landsat", "sentinel2", "sentinel1")


def check_preconditions(cfgs: Configs, preview_dir: Path) -> dict:
    if not cfgs.project.aoi.operator_confirmed:
        raise GateError(
            "aoi.operator_confirmed is false: choose the AOI from the M1 review and record the "
            "decision in configs/project.yaml before full-scale processing"
        )
    return require_preview_pass(cfgs, preview_dir)


def plan_exports(cfgs: Configs, gate: dict, series: list[str], today: date) -> list[dict]:
    pp = cfgs.preprocessing
    epsg = cfgs.project.crs.analysis_epsg
    bounds = tuple(aoi_mod.build_aoi(cfgs.project).total_bounds)
    products = gate.get("metadata", {}).get("products", {})
    plan = []
    for s in series:
        if s not in SERIES:
            raise ValueError(f"unknown series {s!r}")
        if s not in products:
            raise GateError(f"the passed preview has no {s} product; cannot derive its grid")
        period = cfgs.project.periods.landsat if s == "landsat" else cfgs.project.periods.sentinel
        scale = {
            "landsat": pp.composites.landsat_scale_m,
            "sentinel2": pp.composites.sentinel2_scale_m,
            "sentinel1": pp.composites.sentinel1_scale_m,
        }[s]
        offset = tuple(products[s]["grid_offset"])
        tf, width, height = aligned_bounds(bounds, scale, offset)
        for w in windows_for_years(cfgs.project.seasons, period.start_year, period.end_year):
            completeness = w.completeness(today)
            if completeness == "not_started":
                continue
            tag = "" if completeness == "complete" else "_partial"
            name = f"{s}_{w.season}_{w.label_year}{tag}"
            plan.append(
                {
                    "series": s,
                    "season": w.season,
                    "label_year": w.label_year,
                    "start": w.start.isoformat(),
                    "end_inclusive": (w.end - timedelta(days=1)).isoformat(),
                    "completeness": completeness,
                    "description": name,
                    "file_prefix": f"indus_delta/m3/{name}_epsg{epsg}_{scale:g}m",
                    "crs": f"EPSG:{epsg}",
                    "crs_transform": transform_list(tf),
                    "dimensions": [width, height],
                    "pixels": width * height,
                }
            )
    return plan


def submit_exports(cfgs: Configs, plan: list[dict], gate: dict) -> list[dict]:
    """Start one batch export per planned composite. Empty windows are skipped and recorded."""
    import ee

    from indus_delta.earthengine import composite as comp
    from indus_delta.earthengine import prep
    from indus_delta.earthengine.util import to_ee_geometry, with_retries
    from indus_delta.seasons import season_window

    bucket = os.environ.get("EXPORT_BUCKET")
    folder = os.environ.get("EXPORT_DRIVE_FOLDER")
    if not bucket and not folder:
        raise GateError("set EXPORT_BUCKET (Cloud Storage) or EXPORT_DRIVE_FOLDER (Drive)")
    pp = cfgs.preprocessing
    region = to_ee_geometry(aoi_mod.build_aoi(cfgs.project))
    s1_pass = pp.sentinel1.orbit_pass or gate["metadata"].get("sentinel1_orbit_pass")
    results = []
    for item in plan:
        w = season_window(item["season"], cfgs.project.seasons[item["season"]], item["label_year"])
        end = w.end - timedelta(days=1)
        if item["series"] == "landsat":
            col = comp.landsat_window_collection(cfgs, region, w)
            make, bands = (lambda c: comp.optical_composite(c, cfgs)), comp.optical_band_names(cfgs)
        elif item["series"] == "sentinel2":
            col = comp.s2_window_collection(cfgs, region, w)
            make, bands = (lambda c: comp.optical_composite(c, cfgs)), comp.optical_band_names(cfgs)
        else:
            col = prep.s1_prepared(cfgs, region, w.start, end, s1_pass)
            make, bands = (lambda c: comp.s1_composite(c, cfgs)), comp.s1_band_names(cfgs)
        n = with_retries(lambda col=col: col.size().getInfo(), f"count {item['description']}")
        if n == 0:
            results.append({**item, "status": "skipped", "reason": "no images in window"})
            continue
        img = (
            make(col).select(bands).toFloat().clip(region).unmask(pp.composites.nodata_value, False)
        )
        kwargs = dict(
            image=img,
            description=item["description"],
            fileNamePrefix=item["file_prefix"],
            crs=item["crs"],
            crsTransform=item["crs_transform"],
            dimensions=f"{item['dimensions'][0]}x{item['dimensions'][1]}",
            maxPixels=int(1e10),
            fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": True, "noData": pp.composites.nodata_value},
        )
        task = (
            ee.batch.Export.image.toCloudStorage(bucket=bucket, **kwargs)
            if bucket
            else ee.batch.Export.image.toDrive(folder=folder, **kwargs)
        )
        task.start()
        results.append({**item, "status": "submitted", "task_id": task.id, "n_images": n})
    return results


def write_plan(path: Path, plan: list[dict], submitted: list[dict] | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "n_tasks": len(plan),
                "plan": plan,
                "submitted": submitted,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def plan_water_exports(cfgs: Configs, gate: dict, years: list[int]) -> list[dict]:
    """Annual Landsat water-frequency rasters on the Landsat composite grid."""
    if cfgs.layers.tidal_inundation.optical_threshold is None:
        raise GateError(
            "tidal_inundation.optical_threshold is not calibrated; run "
            "`indus-delta calibrate-water` and record the result in configs/layers.yaml"
        )
    epsg = cfgs.project.crs.analysis_epsg
    scale = cfgs.preprocessing.composites.landsat_scale_m
    products = gate.get("metadata", {}).get("products", {})
    if "landsat" not in products:
        raise GateError("the passed preview has no landsat product; cannot derive its grid")
    tf, width, height = aligned_bounds(
        tuple(aoi_mod.build_aoi(cfgs.project).total_bounds),
        scale,
        tuple(products["landsat"]["grid_offset"]),
    )
    return [
        {
            "series": "landsat",
            "label_year": y,
            "description": f"landsat_water_frequency_{y}",
            "file_prefix": f"indus_delta/m5/landsat_water_frequency_{y}_epsg{epsg}_{scale:g}m",
            "crs": f"EPSG:{epsg}",
            "crs_transform": transform_list(tf),
            "dimensions": [width, height],
            "pixels": width * height,
        }
        for y in years
    ]


def submit_water_exports(cfgs: Configs, plan: list[dict]) -> list[dict]:
    import ee

    from indus_delta.earthengine.util import to_ee_geometry
    from indus_delta.earthengine.water import landsat_water_frequency

    bucket = os.environ.get("EXPORT_BUCKET")
    folder = os.environ.get("EXPORT_DRIVE_FOLDER")
    if not bucket and not folder:
        raise GateError("set EXPORT_BUCKET (Cloud Storage) or EXPORT_DRIVE_FOLDER (Drive)")
    region = to_ee_geometry(aoi_mod.build_aoi(cfgs.project))
    nodata = cfgs.preprocessing.composites.nodata_value
    results = []
    for item in plan:
        img = (
            landsat_water_frequency(cfgs, region, item["label_year"])
            .toFloat()
            .clip(region)
            .unmask(nodata, False)
        )
        kwargs = dict(
            image=img,
            description=item["description"],
            fileNamePrefix=item["file_prefix"],
            crs=item["crs"],
            crsTransform=item["crs_transform"],
            dimensions=f"{item['dimensions'][0]}x{item['dimensions'][1]}",
            maxPixels=int(1e10),
            fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": True, "noData": nodata},
        )
        task = (
            ee.batch.Export.image.toCloudStorage(bucket=bucket, **kwargs)
            if bucket
            else ee.batch.Export.image.toDrive(folder=folder, **kwargs)
        )
        task.start()
        results.append({**item, "status": "submitted", "task_id": task.id})
    return results
