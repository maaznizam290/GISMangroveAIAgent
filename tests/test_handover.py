"""M7 handover on the MOCK pipeline (tests/mock_scene.py) plus MOCK M1-M3 artifacts.
Tests mechanics and validation only; nothing here describes the real study area."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import rasterio
import yaml

from indus_delta.aoi import alternative_aois, build_aoi, reference_point, write_layers
from indus_delta.config import load_configs
from indus_delta.handover import build_handover, validate_raster
from indus_delta.inventory import build_records, missing_observations, summarise
from indus_delta.layer_io import Grid, LayerMeta, write_layer
from indus_delta.m4 import run_classification
from indus_delta.m5 import run_layers
from indus_delta.m6 import run_site_selection
from indus_delta.trends import annual_metrics, trend_table

from .mock_scene import build

QGIS_PYTHON = "/usr/bin/python3.12"


def qgis_available() -> bool:
    try:
        return (
            subprocess.run(
                [QGIS_PYTHON, "-c", "import qgis.core"], capture_output=True, timeout=60
            ).returncode
            == 0
        )
    except (OSError, subprocess.TimeoutExpired):
        return False


def add_mock_m1_m3(cfgs, out: Path) -> None:
    """MOCK artifacts standing in for the M1-M3 outputs."""
    p = cfgs.project
    write_layers(
        out / "m1" / "m1_aoi.gpkg",
        {
            "reference_location": reference_point(p),
            "aoi_primary": build_aoi(p),
            "aoi_alternatives": alternative_aois(p),
        },
    )
    tf = rasterio.Affine(30, 0, 330000, 0, -30, 2680000)
    write_layer(
        out / "m1" / "jrc_gsw14_occurrence_review_epsg32642_30m.tif",
        {"water_occurrence_pct_1984_2021": np.full((50, 50), 40.0)},
        Grid(tf, 50, 50, 32642),
        LayerMeta("MOCK jrc", "mock", "mock", "MOCK", []),
        nodata=255,
        dtype="uint8",
    )
    for name in ("m1_aoi_review.md", "m1_aoi_preview.png"):
        (out / "m1" / name).write_text("MOCK")
    (out / "m3" / "preview").mkdir(parents=True)
    (out / "m3" / "preview" / "preview_quicklook.png").write_text("MOCK")
    (out / "m2").mkdir(parents=True)
    raw = [
        {
            "dataset": "landsat8_l2",
            "image_id": "MOCK1",
            "acquired_utc": "2026-01-10T05:00:00Z",
            "valid_fraction": 0.9,
        }
    ]
    rec = build_records(raw, cfgs)
    summ = summarise(rec, cfgs, {})
    rec.to_csv(out / "m2" / "image_inventory.csv", index=False)
    summ.to_csv(out / "m2" / "inventory_summary.csv", index=False)
    missing_observations(summ).to_csv(out / "m2" / "missing_observations.csv", index=False)
    pd.DataFrame([{"dataset": "MOCK", "check": "x", "status": "PASS", "detail": "MOCK"}]).to_csv(
        out / "m2" / "catalog_verification.csv", index=False
    )
    (out / "m2" / "catalog_records.json").write_text("{}")


def mock_full(tmp: Path, qgis: bool):
    cfgs, out = build(tmp)
    cdir = tmp / "configs"
    d = yaml.safe_load((cdir / "handover.yaml").read_text())
    d["qgis"]["enabled"] = qgis
    (cdir / "handover.yaml").write_text(yaml.safe_dump(d, sort_keys=False))
    cfgs = load_configs(cdir)
    run_classification(cfgs, out, "landsat", 2026)
    run_layers(cfgs, out, "landsat", 2026)
    run_site_selection(cfgs, out, "landsat", 2026)
    m = annual_metrics(cfgs, out, 78.5)
    m.to_csv(out / "m5" / "annual_metrics.csv", index=False)
    trend_table(m, cfgs).to_csv(out / "m5" / "trend_tests.csv", index=False)
    add_mock_m1_m3(cfgs, out)
    return cfgs, out


@pytest.fixture(scope="module")
def handover_without_qgis(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("ho")
    cfgs, out = mock_full(tmp, qgis=False)
    repo = Path(__file__).resolve().parents[1]
    status, items, pkg = build_handover(cfgs, out, "landsat", 2026, repo_root=repo)
    return status, items, pkg


def _items(items):
    return {it.id: it for it in items}


def test_all_delivered_items_pass(handover_without_qgis):
    status, items, _ = handover_without_qgis
    failed = [c for it in items for c in it.checks if c.status == "FAIL"]
    assert not failed, failed[:3]
    by = _items(items)
    for rid in (
        "landcover",
        "mangrove",
        "soil_salinity_proxy",
        "freshwater_influence_proxy",
        "tidal_inundation",
        "composite_dry",
        "classification_uncertainty",
    ):
        assert by[rid].status == "delivered", rid
    # Disabled QGIS project is a missing required deliverable, so not COMPLETE.
    assert status == "INCOMPLETE" and by["qgis_project"].status == "missing"


def test_required_tables_present(handover_without_qgis):
    *_, pkg = handover_without_qgis
    for t in (
        "annual_metrics",
        "site_metrics",
        "classification_accuracy",
        "image_inventory",
        "candidate_site_scores",
    ):
        assert (pkg / "tables" / f"{t}.csv").is_file()


def test_rasters_are_cog_with_metadata(handover_without_qgis):
    *_, pkg = handover_without_qgis
    with rasterio.open(pkg / "rasters" / "soil_salinity_proxy_epsg32642.tif") as d:
        assert d.tags(ns="IMAGE_STRUCTURE")["LAYOUT"] == "COG"
        assert d.crs.to_epsg() == 32642 and d.res == (30.0, 30.0)
        assert d.tags()["layer_type"] == "proxy"
        assert d.tags(1)["units"].startswith("percentile")


def test_vector_package_layers(handover_without_qgis):
    import pyogrio

    *_, pkg = handover_without_qgis
    layers = {n for n, _ in pyogrio.list_layers(pkg / "vectors" / "indus_delta_handover.gpkg")}
    assert {
        "aoi_primary",
        "site_a",
        "site_b",
        "site_alternatives",
        "candidate_plots",
        "training_samples",
        "validation_samples",
    } <= layers


def test_generated_documents(handover_without_qgis):
    *_, pkg = handover_without_qgis
    for f in (
        "methods_report.md",
        "data_dictionary.md",
        "data_dictionary.csv",
        "limitations.md",
        "processing_history.csv",
        "software_versions.json",
    ):
        assert (pkg / "docs" / f).stat().st_size > 0, f
    assert "| U1 |" in (pkg / "docs" / "limitations.md").read_text()
    dd = pd.read_csv(pkg / "docs" / "data_dictionary.csv")
    assert {"raster band", "vector field", "table column"} <= set(dd["kind"])
    manifest = json.loads((pkg / "handover_manifest.json").read_text())
    assert any(f["path"].endswith("landcover_epsg32642.tif") for f in manifest["files"])


def test_content_change_is_detected(handover_without_qgis, tmp_path):
    *_, pkg = handover_without_qgis
    src = pkg / "rasters" / "mangrove_epsg32642.tif"
    bad = tmp_path / "bad.tif"
    shutil.copy(src, bad)
    with rasterio.open(bad, "r+", IGNORE_COG_LAYOUT_BREAK="YES") as d:
        a = d.read(1)
        a[5, 5] = 0 if a[5, 5] != 0 else 1
        d.write(a, 1)
    statuses = {c.name: c.status for c in validate_raster(src, bad, 32642, 30)}
    assert statuses["raster_content_identical"] == "FAIL"


def test_non_cog_file_is_detected(tmp_path):
    """A stripped GeoTIFF large enough to need tiling has the same pixels but is not a COG.
    (Rasters smaller than one 512 px block are valid COGs even when stripped.)"""
    from rasterio.shutil import copy as rio_copy

    from indus_delta.handover import deliver_raster

    raw = tmp_path / "raw.tif"
    write_layer(
        raw,
        {"v": np.random.default_rng(0).random((1200, 1200))},
        Grid(rasterio.Affine(30, 0, 300000, 0, -30, 2700000), 1200, 1200, 32642),
        LayerMeta("MOCK", "mock", "mock", "MOCK", []),
        nodata=-9999.0,
    )
    cog = tmp_path / "cog.tif"
    deliver_raster(raw, cog, {"handover_id": "x", "units": "MOCK"})
    plain = tmp_path / "plain.tif"
    rio_copy(cog, plain, driver="GTiff", TILED="NO", COPY_SRC_OVERVIEWS="NO")
    good = {c.name: c.status for c in validate_raster(raw, cog, 32642, 30)}
    bad = {c.name: c.status for c in validate_raster(raw, plain, 32642, 30)}
    assert good["raster_cog_layout"] == "PASS" and bad["raster_cog_layout"] == "FAIL"
    assert bad["raster_content_identical"] == "PASS"


def test_upsampled_raster_is_rejected(handover_without_qgis):
    *_, pkg = handover_without_qgis
    src = pkg / "rasters" / "mangrove_epsg32642.tif"
    statuses = {c.name: c.status for c in validate_raster(src, src, 32642, 60)}
    assert statuses["raster_not_upsampled"] == "FAIL"


def test_missing_required_inputs_reported(tmp_path, cfgs):
    status, items, pkg = build_handover(
        cfgs, tmp_path, "landsat", 2026, repo_root=Path(__file__).resolve().parents[1]
    )
    assert status == "INCOMPLETE"
    v = json.loads((pkg / "handover_validation.json").read_text())
    assert "landcover" in v["missing_required"] and "site_a" in v["missing_required"]


@pytest.mark.skipif(not qgis_available(), reason="PyQGIS not available")
def test_complete_handover_with_qgis(tmp_path):
    cfgs, out = mock_full(tmp_path, qgis=True)
    status, items, pkg = build_handover(
        cfgs, out, "landsat", 2026, repo_root=Path(__file__).resolve().parents[1]
    )
    by = _items(items)
    assert [c.status for c in by["qgis_project"].checks] == ["PASS"] * 6, [
        c.detail for c in by["qgis_project"].checks
    ]
    assert status == "COMPLETE", json.loads((pkg / "handover_validation.json").read_text())[
        "missing_required"
    ]
    assert (pkg / "qgis" / "handover_layout.png").stat().st_size > 10_000
