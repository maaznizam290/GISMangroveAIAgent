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
    """MOCK export file on the planned grid (EE exports may lack band names)."""
    w, h = item["dimensions"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
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


def test_import_needs_submitted_plan(tmp_path, cfgs):
    (tmp_path / "dl").mkdir()
    with pytest.raises(GateError, match="preprocess --start"):
        import_exports(_cfgs(cfgs, tmp_path), tmp_path / "outputs", tmp_path / "dl")


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
