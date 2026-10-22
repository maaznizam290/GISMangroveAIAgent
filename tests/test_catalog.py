"""Catalog verification. Records built here are MOCK STAC records shaped like the real ones;
the network test reads the real catalog."""

import copy
import shutil
from datetime import date

import pytest

from indus_delta.catalog import (
    CatalogCheck,
    record_in_registry,
    run_catalog_check,
    stac_url,
    verify_entry,
)
from indus_delta.config import load_configs

from .conftest import CONFIG_DIR

TODAY = date(2026, 10, 22)


def _mock_l8_record():
    sr = [{"name": f"SR_B{i}", "gee:scale": 2.75e-05, "gee:offset": -0.2} for i in range(1, 8)]
    qa = {
        "name": "QA_PIXEL",
        "gee:bitmask": {
            "bitmask_parts": [
                {"first_bit": 0, "bit_count": 1, "description": "Fill"},
                {"first_bit": 1, "bit_count": 1, "description": "Dilated Cloud"},
                {"first_bit": 2, "bit_count": 1, "description": "Cirrus (high confidence)"},
                {"first_bit": 3, "bit_count": 1, "description": "Cloud"},
                {"first_bit": 4, "bit_count": 1, "description": "Cloud Shadow"},
                {"first_bit": 5, "bit_count": 1, "description": "Snow"},
            ]
        },
    }
    rad = {
        "name": "QA_RADSAT",
        "gee:bitmask": [
            {"first_bit": i, "bit_count": 1, "description": f"Band {i + 1} data saturated"}
            for i in range(7)
        ],
    }
    return {
        "id": "LANDSAT/LC08/C02/T1_L2",
        "gee:type": "image_collection",
        "gee:status": "ready",
        "extent": {"temporal": {"interval": [["2013-03-18T15:58:14Z", "2026-10-11T00:00:00Z"]]}},
        "summaries": {"eo:bands": [*sr, qa, rad]},
    }


def _status(checks, name):
    return next(c.status for c in checks if c.check == name)


def test_stac_url(cfgs):
    root = cfgs.preprocessing.catalog.stac_root
    ds = cfgs.datasets.datasets
    assert stac_url(root, ds["landsat8_l2"]).endswith("/LANDSAT/LANDSAT_LC08_C02_T1_L2.json")
    assert stac_url(root, ds["cgmd_extent30"]).endswith(ds["cgmd_extent30"].stac_path)


def test_mock_record_passes(cfgs):
    checks = verify_entry(
        "landsat8_l2", cfgs.datasets.datasets["landsat8_l2"], _mock_l8_record(), cfgs, TODAY
    )
    for name in (
        "id_matches",
        "type_matches",
        "required_bands",
        "scale_offset",
        "qa_pixel_bits",
        "qa_radsat_bits",
    ):
        assert _status(checks, name) == "PASS", name
    assert _status(checks, "temporal_extent") == "WARN"  # Landsat 8 starts 2013


def test_wrong_scale_fails(cfgs):
    rec = _mock_l8_record()
    rec["summaries"]["eo:bands"][2]["gee:scale"] = 1e-4
    checks = verify_entry("landsat8_l2", cfgs.datasets.datasets["landsat8_l2"], rec, cfgs, TODAY)
    assert _status(checks, "scale_offset") == "FAIL"


def test_qa_bit_meaning_change_fails(cfgs):
    rec = _mock_l8_record()
    rec["summaries"]["eo:bands"][7]["gee:bitmask"]["bitmask_parts"][3]["description"] = "Clear"
    checks = verify_entry("landsat8_l2", cfgs.datasets.datasets["landsat8_l2"], rec, cfgs, TODAY)
    assert _status(checks, "qa_pixel_bits") == "FAIL"


def test_missing_band_fails(cfgs):
    rec = _mock_l8_record()
    rec["summaries"]["eo:bands"] = [b for b in rec["summaries"]["eo:bands"] if b["name"] != "SR_B6"]
    checks = verify_entry("landsat8_l2", cfgs.datasets.datasets["landsat8_l2"], rec, cfgs, TODAY)
    assert _status(checks, "required_bands") == "FAIL"


def test_ended_collection_warns(cfgs):
    rec = copy.deepcopy(_mock_l8_record())
    rec["id"] = "LANDSAT/LT05/C02/T1_L2"
    rec["extent"]["temporal"]["interval"] = [["1984-03-16T00:00:00Z", "2012-05-05T00:00:00Z"]]
    checks = verify_entry("landsat5_l2", cfgs.datasets.datasets["landsat5_l2"], rec, cfgs, TODAY)
    temporal = next(c for c in checks if c.check == "temporal_extent")
    assert temporal.status == "WARN" and "ended 2012-05-05" in temporal.detail


def test_record_in_registry(tmp_path):
    for f in CONFIG_DIR.glob("*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    checks = [
        CatalogCheck("landsat8_l2", "x", "PASS", ""),
        CatalogCheck("sentinel2_sr", "x", "FAIL", ""),
    ]
    records = {
        "landsat8_l2": {"temporal_extent": ["2013-03-18", "2026-10-11"]},
        "sentinel2_sr": {"temporal_extent": ["2017-03-28", "2026-10-21"]},
    }
    updated = record_in_registry(tmp_path / "datasets.yaml", checks, records, "test", TODAY)
    assert updated == ["landsat8_l2"]
    ds = load_configs(tmp_path).datasets.datasets
    assert ds["landsat8_l2"].catalog_extent.end == date(2026, 10, 11)
    assert ds["landsat8_l2"].verified_by == "test"
    # Running it twice must not duplicate lines.
    record_in_registry(tmp_path / "datasets.yaml", checks, records, "test", TODAY)
    text = (tmp_path / "datasets.yaml").read_text()
    assert text.count('catalog_extent: {start: "2013-03-18"') == 1


@pytest.mark.network
def test_real_catalog(cfgs):
    checks, records = run_catalog_check(cfgs, TODAY)
    by = {(c.dataset, c.check): c.status for c in checks}
    for key in ("landsat5_l2", "landsat7_l2", "landsat8_l2", "landsat9_l2"):
        assert by[(key, "qa_pixel_bits")] == "PASS"
        assert by[(key, "scale_offset")] == "PASS"
    assert by[("sentinel2_sr", "scl_classes")] == "PASS"
    assert by[("gmw_v4", "catalog_entry")] == "FAIL"
    assert records["jrc_gsw"]["temporal_extent"][1] == "2022-01-01"
