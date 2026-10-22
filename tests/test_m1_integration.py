"""Real-data integration test for M1 (reads public JRC tiles and Natural Earth over HTTP)."""

import json

import pyogrio
import pytest
import rasterio

from indus_delta.m1 import run_m1


@pytest.mark.network
def test_m1_end_to_end(cfgs, tmp_path):
    result = run_m1(cfgs, tmp_path, cache_dir=tmp_path / "cache", command="pytest")
    assert result.status in {"PASS", "WARN"}
    names = {p.name for p in result.outputs}
    assert {"m1_aoi.gpkg", "m1_aoi_preview.png", "m1_aoi_review.md", "run_manifest.json"} <= names
    tif = next(p for p in result.outputs if p.suffix == ".tif")
    with rasterio.open(tif) as src:
        assert src.crs.to_epsg() == 32642
        assert src.res == (30.0, 30.0)
        assert src.nodata == 255
        assert src.transform.c % 30 == 0 and src.transform.f % 30 == 0
        assert src.descriptions == ("water_occurrence_pct_1984_2021",)
    layers = {n for n, _ in pyogrio.list_layers(result.out_dir / "m1_aoi.gpkg")}
    assert {"reference_location", "aoi_primary", "aoi_alternatives"} <= layers
    review = json.loads((result.out_dir / "m1_aoi_review.json").read_text())
    fw = next(c for c in review["checks"] if c["name"] == "freshwater_influence_candidate")
    assert fw["status"] == "WARN"
