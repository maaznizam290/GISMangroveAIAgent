"""Importing downloaded exports and resolving the QGIS interpreter. Rasters are MOCK DATA
written to tmp; nothing here describes the study area."""

import json
import os
from datetime import date

import numpy as np
import pytest
import rasterio
from rasterio.transform import Affine

from indus_delta.gate import GateError
from indus_delta.handover import resolve_qgis_python
from indus_delta.m3_export import export_file_prefix, import_exports, plan_exports, write_plan


def _cfgs(cfgs, tmp_path):
    cl = cfgs.classification.model_copy(update={"composites_dir": tmp_path / "composites"})
    ti = cfgs.layers.tidal_inundation.model_copy(update={"input_dir": tmp_path / "m5in"})
    layers = cfgs.layers.model_copy(update={"tidal_inundation": ti})
    return cfgs.model_copy(update={"classification": cl, "layers": layers})


def _gate():
    products = {s: {"grid_offset": [15, 15]} for s in ("landsat", "sentinel2", "sentinel1")}
    return {"status": "PASS", "metadata": {"products": products}}


def _write_export(path, item, n_bands, descriptions=None):
    """MOCK export file on the planned grid, written as a COG like Earth Engine's exports
    (which may lack band names)."""
    from rasterio.shutil import copy as rio_copy

    w, h = item["dimensions"]
    path.parent.mkdir(parents=True, exist_ok=True)
    plain = path.with_suffix(".plain.tif")
    with rasterio.open(
        plain,
        "w",
        driver="GTiff",
        width=w,
        height=h,
        count=n_bands,
        dtype="float32",
        crs=item["crs"],
        transform=Affine(*item["crs_transform"]),
    ) as dst:
        for i in range(1, n_bands + 1):
            dst.write(np.full((h, w), 0.1, dtype="float32"), i)
            if descriptions:
                dst.set_band_description(i, descriptions[i - 1])
    rio_copy(plain, path, driver="COG")
    plain.unlink()


def _submitted_plan(cfgs, out):
    plan = plan_exports(cfgs, _gate(), ["landsat"], date(2026, 10, 22))[:2]
    write_plan(out / "m3" / "export_plan.json", plan, [{**p, "status": "submitted"} for p in plan])
    return plan


def test_drive_prefix_is_flat():
    item = {"file_prefix": "indus_delta/m3/landsat_dry_2005_epsg32642_30m"}
    assert export_file_prefix(item, "bucket") == item["file_prefix"]
    assert export_file_prefix(item, None) == "landsat_dry_2005_epsg32642_30m"


def test_import_names_bands_and_reports_missing(tmp_path, cfgs):
    c = _cfgs(cfgs, tmp_path)
    out, dl = tmp_path / "outputs", tmp_path / "download"
    good, missing = _submitted_plan(c, out)
    _write_export(dl / "sub" / f"{good['description']}_epsg32642_30m.tif", good, len(good["bands"]))
    status, checks, manifest = import_exports(c, out, dl)
    assert status == "WARN"
    assert [ch.status for ch in checks] == ["PASS", "WARN"]
    dest = tmp_path / "composites" / f"{good['description']}_epsg32642_30m.tif"
    with rasterio.open(dest) as src:
        assert list(src.descriptions) == good["bands"]
        assert src.nodata == c.preprocessing.composites.nodata_value
    assert json.loads(manifest.read_text())["outputs"][0]["path"] == str(dest)


def test_import_rejects_wrong_grid(tmp_path, cfgs):
    c = _cfgs(cfgs, tmp_path)
    out, dl = tmp_path / "outputs", tmp_path / "download"
    good, _ = _submitted_plan(c, out)
    shifted = {**good, "crs_transform": [30, 0, good["crs_transform"][2] + 15, 0, -30, 0]}
    shifted["crs_transform"][5] = good["crs_transform"][5]
    _write_export(dl / f"{good['description']}_epsg32642_30m.tif", shifted, len(good["bands"]))
    status, checks, _ = import_exports(c, out, dl)
    assert status == "FAIL" and "transform" in checks[0].detail
    assert not (tmp_path / "composites").exists()


def test_import_rejects_reordered_band_names(tmp_path, cfgs):
    c = _cfgs(cfgs, tmp_path)
    out, dl = tmp_path / "outputs", tmp_path / "download"
    good, _ = _submitted_plan(c, out)
    names = list(reversed(good["bands"]))
    _write_export(dl / f"{good['description']}_epsg32642_30m.tif", good, len(names), names)
    status, checks, _ = import_exports(c, out, dl)
    assert status == "FAIL" and "band names" in checks[0].detail


def test_import_needs_a_plan(tmp_path, cfgs):
    (tmp_path / "dl").mkdir()
    with pytest.raises(GateError, match="no export plan"):
        import_exports(_cfgs(cfgs, tmp_path), tmp_path / "outputs", tmp_path / "dl")


def test_import_without_submission_record_uses_plan(tmp_path, cfgs):
    """An interrupted --start leaves only the plan; files are still checked against it."""
    c = _cfgs(cfgs, tmp_path)
    out, dl = tmp_path / "outputs", tmp_path / "download"
    plan = plan_exports(c, _gate(), ["landsat"], date(2026, 10, 22))[:2]
    write_plan(out / "m3" / "export_plan.json", plan)
    _write_export(dl / f"{plan[0]['description']}_epsg32642_30m.tif", plan[0], 13)
    status, checks, _ = import_exports(c, out, dl)
    assert [ch.status for ch in checks] == ["PASS", "WARN"] and status == "WARN"


def _fake_tasks(monkeypatch, tasks):
    import ee

    monkeypatch.setattr(ee.data, "getTaskList", lambda: tasks)


def test_existing_tasks_are_reused_not_duplicated(monkeypatch, cfgs):
    """MOCK task list. Live tasks (queued, running, done) block a duplicate export; failed
    or cancelled ones do not."""
    from indus_delta.m3_export import _already, existing_tasks

    _fake_tasks(
        monkeypatch,
        [
            {"description": "a", "state": "COMPLETED", "id": "T1", "creation_timestamp_ms": 1},
            {"description": "a", "state": "READY", "id": "T2", "creation_timestamp_ms": 2},
            {"description": "b", "state": "FAILED", "id": "T3", "creation_timestamp_ms": 3},
            {"description": "c", "state": "CANCELLED", "id": "T4", "creation_timestamp_ms": 4},
            {"description": "x", "state": "READY", "id": "T5", "creation_timestamp_ms": 5},
        ],
    )
    live = existing_tasks({"a", "b", "c"})
    assert set(live) == {"a"} and live["a"]["id"] == "T2"
    assert _already({"description": "a"}, live)["task_id"] == "T2"
    assert _already({"description": "b"}, live) is None


def test_dry_run_keeps_submission_record(tmp_path):
    from indus_delta.cli import _dry_run_path

    path = tmp_path / "export_plan.json"
    assert _dry_run_path(path) == path
    write_plan(path, [{"description": "a"}])
    assert _dry_run_path(path) == path
    write_plan(path, [{"description": "a"}], [{"description": "a", "status": "submitted"}])
    assert _dry_run_path(path).name == "export_plan_dryrun.json"


def test_qgis_python_resolution(tmp_path, monkeypatch):
    monkeypatch.delenv("QGIS_PYTHON", raising=False)
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    if os.name == "nt":
        launcher = tmp_path / "QGIS 3.40.4" / "bin" / "python-qgis-ltr.bat"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("")
        assert resolve_qgis_python(str(tmp_path / "no_such_python")) == str(launcher)
    exe = tmp_path / "python-qgis.bat"
    exe.write_text("")
    monkeypatch.setenv("QGIS_PYTHON", str(exe))
    assert resolve_qgis_python("/usr/bin/python3.12") == str(exe)
