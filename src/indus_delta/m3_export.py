"""Full-scale seasonal composites (M3): plan, then (only on explicit request) submit Earth
Engine batch exports. Refused until the AOI is confirmed and the preview gate has passed."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from indus_delta import aoi as aoi_mod
from indus_delta.config import Configs
from indus_delta.gate import GateError, require_preview_pass
from indus_delta.grid import aligned_bounds, transform_list
from indus_delta.seasons import windows_for_years

SERIES = ("landsat", "sentinel2", "sentinel1")


_BUCKET_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{1,220}[a-z0-9]$")


def export_destination() -> tuple[str | None, str | None]:
    """(bucket, drive_folder) from EXPORT_BUCKET / EXPORT_DRIVE_FOLDER, validated.

    EXPORT_BUCKET is a Cloud Storage bucket *name*; EXPORT_DRIVE_FOLDER is a folder *name*
    in the authenticated account's Google Drive. URLs are rejected: Earth Engine accepts
    neither a bucket URL nor a Drive link.
    """
    bucket = (os.environ.get("EXPORT_BUCKET") or "").strip() or None
    folder = (os.environ.get("EXPORT_DRIVE_FOLDER") or "").strip() or None
    if not bucket and not folder:
        raise GateError(
            "set EXPORT_BUCKET (Cloud Storage bucket name) or EXPORT_DRIVE_FOLDER "
            "(Google Drive folder name)"
        )
    if bucket and (bucket.startswith(("http", "gs://")) or not _BUCKET_NAME.match(bucket)):
        raise GateError(
            f"EXPORT_BUCKET={bucket!r} is not a Cloud Storage bucket name (expected e.g. "
            "'my-exports'; lowercase letters, digits, '-', '_', '.'). For Google Drive set "
            "EXPORT_DRIVE_FOLDER to a folder name instead"
        )
    if folder and ("://" in folder or "/" in folder or "?" in folder):
        raise GateError(
            f"EXPORT_DRIVE_FOLDER={folder!r} looks like a link or path. Use a plain folder "
            "name such as 'indus_delta_exports'; Earth Engine creates or reuses a folder with "
            "that name in the authenticated account's Drive"
        )
    return bucket, folder


def export_file_prefix(item: dict, bucket: str | None) -> str:
    """Cloud Storage keeps the folder structure of the prefix; a Drive folder is flat, so
    only the file name is used there."""
    return item["file_prefix"] if bucket else item["file_prefix"].rsplit("/", 1)[-1]


def band_names(cfgs: Configs, series: str) -> list[str]:
    """Band order of an exported composite (the same lists the export selects)."""
    from indus_delta.earthengine import composite as comp

    return comp.s1_band_names(cfgs) if series == "sentinel1" else comp.optical_band_names(cfgs)


WATER_BANDS = ["water_frequency", "n_valid"]


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
                    "bands": band_names(cfgs, s),
                }
            )
    return plan


# Task states meaning the export is queued, running or done; another task would duplicate it.
LIVE_TASK_STATES = ("UNSUBMITTED", "READY", "RUNNING", "COMPLETED")


def existing_tasks(descriptions: set[str]) -> dict[str, dict]:
    """Most recent live Earth Engine task per description, among the given descriptions."""
    import ee

    from indus_delta.earthengine.util import with_retries

    found: dict[str, dict] = {}
    tasks = with_retries(ee.data.getTaskList, "list export tasks")
    for t in sorted(tasks, key=lambda t: t.get("creation_timestamp_ms", 0)):
        if t.get("description") in descriptions and t.get("state") in LIVE_TASK_STATES:
            found[t["description"]] = t
    return found


def _start_task(kwargs: dict, bucket: str | None, folder: str | None) -> str:
    import ee

    task = (
        ee.batch.Export.image.toCloudStorage(bucket=bucket, **kwargs)
        if bucket
        else ee.batch.Export.image.toDrive(folder=folder, **kwargs)
    )
    task.start()
    return task.id


def _already(item: dict, live: dict[str, dict]) -> dict | None:
    t = live.get(item["description"])
    if t is None:
        return None
    return {
        **item,
        "status": "submitted",
        "task_id": t["id"],
        "task_state": t["state"],
        "note": "existing task reused; rerun with --resubmit to export again",
    }


def submit_exports(
    cfgs: Configs,
    plan: list[dict],
    gate: dict,
    record: Callable[[list[dict]], object] | None = None,
    resubmit: bool = False,
) -> list[dict]:
    """Start one batch export per planned composite. Empty windows are skipped and recorded.
    Composites that already have a queued, running or completed task are not exported again
    (unless resubmit). `record` is called after every item, so an interrupted run keeps its
    record."""

    from indus_delta.earthengine import composite as comp
    from indus_delta.earthengine import prep
    from indus_delta.earthengine.util import to_ee_geometry, with_retries
    from indus_delta.seasons import season_window

    bucket, folder = export_destination()
    pp = cfgs.preprocessing
    region = to_ee_geometry(aoi_mod.build_aoi(cfgs.project))
    s1_pass = pp.sentinel1.orbit_pass or gate["metadata"].get("sentinel1_orbit_pass")
    live = {} if resubmit else existing_tasks({i["description"] for i in plan})
    results = []
    for item in plan:
        if done := _already(item, live):
            results.append(done)
            if record:
                record(results)
            continue
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
            if record:
                record(results)
            continue
        img = (
            make(col).select(bands).toFloat().clip(region).unmask(pp.composites.nodata_value, False)
        )
        kwargs = dict(
            image=img,
            description=item["description"],
            fileNamePrefix=export_file_prefix(item, bucket),
            crs=item["crs"],
            crsTransform=item["crs_transform"],
            dimensions=f"{item['dimensions'][0]}x{item['dimensions'][1]}",
            maxPixels=int(1e10),
            fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": True, "noData": pp.composites.nodata_value},
        )
        task_id = _start_task(kwargs, bucket, folder)
        results.append({**item, "status": "submitted", "task_id": task_id, "n_images": n})
        if record:
            record(results)
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
            "bands": WATER_BANDS,
        }
        for y in years
    ]


def submit_water_exports(
    cfgs: Configs,
    plan: list[dict],
    record: Callable[[list[dict]], object] | None = None,
    resubmit: bool = False,
) -> list[dict]:
    """Like submit_exports, for the annual water-frequency rasters."""
    from indus_delta.earthengine.util import to_ee_geometry
    from indus_delta.earthengine.water import landsat_water_frequency

    bucket, folder = export_destination()
    region = to_ee_geometry(aoi_mod.build_aoi(cfgs.project))
    nodata = cfgs.preprocessing.composites.nodata_value
    live = {} if resubmit else existing_tasks({i["description"] for i in plan})
    results = []
    for item in plan:
        if done := _already(item, live):
            results.append(done)
            if record:
                record(results)
            continue
        img = (
            landsat_water_frequency(cfgs, region, item["label_year"])
            .toFloat()
            .clip(region)
            .unmask(nodata, False)
        )
        kwargs = dict(
            image=img,
            description=item["description"],
            fileNamePrefix=export_file_prefix(item, bucket),
            crs=item["crs"],
            crsTransform=item["crs_transform"],
            dimensions=f"{item['dimensions'][0]}x{item['dimensions'][1]}",
            maxPixels=int(1e10),
            fileFormat="GeoTIFF",
            formatOptions={"cloudOptimized": True, "noData": nodata},
        )
        results.append(
            {**item, "status": "submitted", "task_id": _start_task(kwargs, bucket, folder)}
        )
        if record:
            record(results)
    return results


# --------------------------------------------------------------------------- import downloads


def _export_problems(path: Path, item: dict, bands: list[str]) -> list[str]:
    """Differences between a downloaded export and the grid and bands it was planned with."""
    import rasterio
    from rasterio.transform import Affine

    with rasterio.open(path) as src:
        problems = []
        epsg = int(item["crs"].split(":")[1])
        if src.crs is None or src.crs.to_epsg() != epsg:
            problems.append(f"CRS {src.crs}, planned {item['crs']}")
        if [src.width, src.height] != list(item["dimensions"]):
            problems.append(f"size {src.width}x{src.height}, planned {item['dimensions']}")
        if not src.transform.almost_equals(Affine(*item["crs_transform"])):
            problems.append(
                f"transform {tuple(src.transform)[:6]}, planned {item['crs_transform']}"
            )
        if src.count != len(bands):
            problems.append(f"{src.count} bands, planned {len(bands)} {bands}")
        named = [d for d in src.descriptions if d]
        if named and list(src.descriptions) != bands:
            problems.append(f"band names {list(src.descriptions)}, planned {bands}")
    return problems


def import_exports(
    cfgs: Configs,
    out_root: Path,
    download_dir: Path,
    command: str = "indus-delta import-exports",
):
    """Check files downloaded from Drive / Cloud Storage against the export plans and copy
    them, with band names and nodata recorded, to where `classify` (composites_dir) and
    `layers` (tidal_inundation.input_dir) read them. Files that do not match their plan are
    reported and not imported."""
    import shutil

    import rasterio

    from indus_delta.checks import Check, worst
    from indus_delta.manifest import write_manifest

    if not download_dir.is_dir():
        raise FileNotFoundError(f"download folder {download_dir} does not exist")
    plans = [
        (out_root / "m3" / "export_plan.json", cfgs.classification.composites_dir, None),
        (
            out_root / "m5" / "water_export_plan.json",
            cfgs.layers.tidal_inundation.input_dir,
            WATER_BANDS,
        ),
    ]
    nodata = cfgs.preprocessing.composites.nodata_value
    found = {p.name: p for p in sorted(download_dir.rglob("*.tif"))}
    checks: list[Check] = []
    imported: list[Path] = []
    used_plans: list[Path] = []
    for plan_path, dest_dir, fixed_bands in plans:
        if not plan_path.is_file():
            continue
        record = json.loads(plan_path.read_text(encoding="utf-8"))
        submitted = [s for s in record.get("submitted") or [] if s.get("status") == "submitted"]
        if not record.get("submitted"):
            # No submission record (e.g. an interrupted --start): every planned file may
            # exist; each one is still checked against its planned grid and bands.
            submitted = record.get("plan") or []
        if submitted:
            used_plans.append(plan_path)
        for item in submitted:
            stem = item["file_prefix"].rsplit("/", 1)[-1]
            name = f"{stem}.tif"
            src = found.get(name)
            if src is None:
                tiles = [n for n in found if n.startswith(f"{stem}-")]
                checks.append(
                    Check(
                        f"import_{stem}",
                        "WARN",
                        f"exported in {len(tiles)} tiles; mosaic them into {name} first"
                        if tiles
                        else f"{name} not in {download_dir} (task still running, or not "
                        "downloaded yet)",
                    )
                )
                continue
            bands = item.get("bands") or fixed_bands or band_names(cfgs, item["series"])
            problems = _export_problems(src, item, bands)
            if problems:
                checks.append(Check(f"import_{stem}", "FAIL", f"{src}: " + "; ".join(problems)))
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / name
            shutil.copy2(src, dest)
            with rasterio.open(dest) as d:
                needs_tags = d.nodata != nodata or list(d.descriptions) != bands
            if needs_tags:
                # Earth Engine writes COGs; GDAL edits them only when told the layout may
                # change (the handover rebuilds COGs from these files).
                with rasterio.open(dest, "r+", IGNORE_COG_LAYOUT_BREAK="YES") as dst:
                    dst.nodata = nodata
                    for i, b in enumerate(bands, start=1):
                        dst.set_band_description(i, b)
            imported.append(dest)
            checks.append(Check(f"import_{stem}", "PASS", f"{src.name} -> {dest}"))
    if not used_plans:
        raise GateError(
            "no export plan found in m3/export_plan.json or m5/water_export_plan.json; run "
            "`indus-delta preprocess` (and `--start`) first"
        )
    status = worst(checks)
    manifest = out_root / "m3" / "import_manifest.json"
    write_manifest(
        manifest,
        milestone="M3-import",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[{"download_dir": str(download_dir), "plans": [str(p) for p in used_plans]}],
        outputs=imported,
        status=status,
    )
    return status, checks, manifest
