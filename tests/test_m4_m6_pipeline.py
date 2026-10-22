"""End-to-end M4 -> M5 -> M6 on the MOCK scene (tests/mock_scene.py). These tests check
mechanics and gates only; their numbers say nothing about the real study area."""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import rasterio

from indus_delta.gate import GateError
from indus_delta.layer_io import read_layer
from indus_delta.m4 import run_classification
from indus_delta.m5 import run_layers
from indus_delta.m6 import run_site_selection

from .mock_scene import build


@pytest.fixture(scope="module")
def full_run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mock_full")
    cfgs, out = build(tmp)
    status, checks, m4dir = run_classification(cfgs, out, "landsat", 2026)
    results, lchecks, m5dir = run_layers(cfgs, out, "landsat", 2026)
    sel = run_site_selection(cfgs, out, "landsat", 2026)
    return cfgs, out, status, checks, m4dir, results, m5dir, sel


def test_validation_gate_passes_on_separable_mock(full_run):
    _, _, status, checks, m4dir, *_ = full_run
    assert status == "PASS", [c for c in checks if c.status == "FAIL"]
    gate = json.loads((m4dir / "validation_gate.json").read_text())
    assert gate["overall_accuracy"] > 0.9
    with rasterio.open(m4dir / "landcover.tif") as src:
        assert src.tags()["status"] == "validated"
        assert src.nodata == 7 and src.crs.to_epsg() == 32642


def test_accuracy_tables(full_run):
    *_, m4dir, _, _, _ = full_run
    acc = pd.read_csv(m4dir / "classification_accuracy.csv")
    assert {
        "users_accuracy",
        "producers_accuracy",
        "f1",
        "iou",
        "n_reference",
        "users_accuracy_ci_low",
    } <= set(acc.columns)
    assert acc.iloc[-1]["class_name"] == "OVERALL"
    cm = pd.read_csv(m4dir / "confusion_matrix.csv", index_col=0)
    assert cm.shape == (6, 6) and cm.to_numpy().sum() == int(acc.iloc[-1]["n_reference"])
    assert "Out-of-bag" in (m4dir / "accuracy_report.md").read_text()


def test_training_and_validation_are_separated(full_run):
    cfgs, *_, m4dir, _, _, _ = full_run
    tr = gpd.read_file(m4dir / "samples.gpkg", layer="training_samples")
    va = gpd.read_file(m4dir / "samples.gpkg", layer="validation_samples")
    d = tr.geometry.apply(lambda g: va.distance(g).min())
    assert d.min() >= cfgs.classification.split.min_train_validation_distance_m
    assert not set(tr.sample_id) & set(va.sample_id)


def test_layers_are_separate_and_tagged(full_run):
    *_, results, m5dir, _ = full_run
    produced = {r.name for r in results if r.status == "produced"}
    assert produced == {
        "mangrove",
        "tidal_inundation",
        "soil_salinity_proxy",
        "freshwater_influence_proxy",
        "water_salinity_field",
    }
    _, _, meta = read_layer(m5dir / "soil_salinity_proxy.tif")
    assert meta.layer_type == "proxy" and meta.status == "proxy_uncalibrated"
    assert meta.mask_from == ["landcover", "tidal_inundation"]
    assert not any("landcover" in d or "mangrove" in d for d in meta.derived_from)


def test_salinity_proxy_only_on_eligible_pixels(full_run):
    *_, m5dir, _ = full_run
    b, _, _ = read_layer(m5dir / "soil_salinity_proxy.tif")
    proxy, code = b["soil_salinity_proxy_percentile"], b["eligibility_code"]
    assert np.all(np.isnan(proxy[code != 0]))
    assert np.nanmin(proxy) >= 0 and np.nanmax(proxy) <= 100
    m, _, _ = read_layer(m5dir / "mangrove.tif")
    assert np.all(code[m["mangrove_extent"] == 1] == 1)  # mangrove pixels excluded


def test_sites_selected_from_expected_zones(full_run):
    *_, sel = full_run
    status, checks, m6dir = sel
    assert status == "SELECTED"
    scores = pd.read_csv(m6dir / "candidate_site_scores.csv")
    sites = pd.read_csv(m6dir / "site_metrics.csv")
    a = sites[sites.role == "site_a"].iloc[0]
    b = sites[sites.role == "site_b"].iloc[0]
    assert a.mangrove_cover <= 0.05 and a.salinity_percentile_mean >= 75
    assert b.mangrove_cover >= 0.6
    assert (sites.role == "site_a_alternative").sum() >= 1
    assert scores["site_a_exclusion_reasons"].fillna("").str.len().gt(0).any()
    assert {"site_a", "site_b", "candidate_plots"} <= {
        n for n, _ in __import__("pyogrio").list_layers(m6dir / "sites.gpkg")
    }


def test_plots_are_500m_inside_aoi(full_run):
    *_, sel = full_run
    plots = gpd.read_file(sel[2] / "sites.gpkg", layer="candidate_plots")
    assert np.allclose(plots.geometry.area, 250_000)
    assert plots.crs.to_epsg() == 32642


def test_selection_refused_when_validation_fails(tmp_path):
    cfgs, out = build(tmp_path, confirm_acceptance=False)
    status, checks, _ = run_classification(cfgs, out, "landsat", 2026)
    assert status == "FAIL"
    assert {c.name for c in checks if c.status == "FAIL"} == {"acceptance_criteria_confirmed"}
    run_layers(cfgs, out, "landsat", 2026)
    with pytest.raises(GateError, match="validation gate"):
        run_site_selection(cfgs, out, "landsat", 2026)


def test_selection_refused_without_confirmed_rules(tmp_path):
    cfgs, out = build(tmp_path, confirm_sites=False)
    with pytest.raises(GateError, match="operator_confirmed"):
        run_site_selection(cfgs, out, "landsat", 2026)


def test_no_freshwater_source_means_no_selection(tmp_path):
    cfgs, out = build(tmp_path, freshwater=False)
    run_classification(cfgs, out, "landsat", 2026)
    results, _, _ = run_layers(cfgs, out, "landsat", 2026)
    fw = next(r for r in results if r.name == "freshwater_influence_proxy")
    assert fw.status == "unavailable" and "documented freshwater source" in fw.detail
    status, _, m6dir = run_site_selection(cfgs, out, "landsat", 2026)
    assert status == "NO_SELECTION"
    assert not (m6dir / "sites.gpkg").exists() or "site_a" not in {
        n for n, _ in __import__("pyogrio").list_layers(m6dir / "sites.gpkg")
    }
    report = (m6dir / "selection_report.md").read_text()
    assert "no eligible candidate for Site B" in report


def test_tampered_map_invalidates_gate(tmp_path):
    cfgs, out = build(tmp_path)
    run_classification(cfgs, out, "landsat", 2026)
    run_layers(cfgs, out, "landsat", 2026)
    with rasterio.open(out / "m4" / "landsat_2026" / "landcover.tif", "r+") as dst:
        a = dst.read(1)
        a[0, 0] = 1 if a[0, 0] != 1 else 2
        dst.write(a, 1)
    with pytest.raises(GateError, match="differs from the validated map"):
        run_site_selection(cfgs, out, "landsat", 2026)


def test_report_explains_comparability_tradeoff(full_run):
    *_, sel = full_run
    report = (sel[2] / "selection_report.md").read_text()
    # MOCK scene: the strongest Site A plots flood far less often than the mangrove plots.
    assert "comparability preference applied" in report


def test_criteria_and_comparison_tables(full_run):
    *_, sel = full_run
    crit = pd.read_csv(sel[2] / "selection_criteria.csv")
    assert {"site_a", "site_b", "pair", "both"} <= set(crit.applies_to)
    assert crit["operator_confirmed"].all()
    cmp_ = pd.read_csv(sel[2] / "site_comparison.csv").set_index("metric")
    row = cmp_.loc["inundation_frequency_mean"]
    assert row.difference == pytest.approx(row.site_a - row.site_b)
    assert cmp_.loc["separation_km", "difference"] >= 1.0


def test_classify_does_not_create_output_without_inputs(tmp_path, cfgs):
    from indus_delta.samples import SamplesUnavailable

    with pytest.raises(SamplesUnavailable):
        run_classification(cfgs, tmp_path, "landsat", 2026)
    assert not (tmp_path / "m4").exists()
