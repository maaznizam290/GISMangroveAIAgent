"""Dashboard data loading, chart calculations and site filtering.
Pipeline outputs come from the MOCK scene (tests/mock_scene.py); nothing here is real data."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from indus_delta.dashboard import charts
from indus_delta.dashboard.data import (
    DashboardData,
    class_proportions,
    compare_plots,
    selectable_sites,
)

from .test_handover import mock_full

APP = str(Path(__file__).resolve().parents[1] / "src" / "indus_delta" / "dashboard" / "app.py")


@pytest.fixture(scope="module")
def mock_outputs(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("dash")
    cfgs, out = mock_full(tmp, qgis=False)
    return cfgs, out, tmp / "configs"


def test_empty_outputs_load_without_values(tmp_path):
    d = DashboardData(tmp_path)
    assert d.epochs() == []
    assert set(d.milestone_status()["status"]) == {"not run"}
    assert d.annual_metrics() is None and d.catalog_verification() is None
    assert d.downloadable_files().empty and d.aoi() == {}


def test_mock_outputs_load(mock_outputs):
    cfgs, out, _ = mock_outputs
    d = DashboardData(out)
    assert d.epochs() == ["landsat_2026"]
    layers = {lyr.label: lyr for lyr in d.raster_layers("landsat_2026")}
    assert layers["Soil-salinity proxy"].layer_type == "proxy"
    assert "uncalibrated" in layers["Soil-salinity proxy"].kind_label
    assert layers["Land cover"].status == "validated"
    assert layers["Inundation frequency"].pixel_size_m == 30
    status = d.milestone_status().set_index("item")["status"]
    assert status["Validation gate landsat_2026"] == "PASS"


def test_missing_years_and_series_separation():
    m = pd.DataFrame(
        {
            "series": ["landsat"] * 3 + ["sentinel2"],
            "label_year": [2005, 2007, 2008, 2021],
            "mangrove_area_km2": [10.0, 11.0, np.nan, 3.0],
            "validation_status": ["PASS", "PASS", "PASS", "FAIL"],
        }
    )
    assert charts.missing_years(m, "landsat", 2005, 2008, "mangrove_area_km2") == [2006, 2008]
    fig = charts.trend_figure(m, {"landsat": (2005, 2008), "sentinel2": (2020, 2022)})
    names = [t.name for t in fig.data]
    lines = [t for t in fig.data if t.mode == "lines+markers"]
    # Each line holds one series only; Sentinel is not validated so has no line.
    assert [t.name for t in lines] == ["Landsat (30 m)"]
    assert list(lines[0].x) == [2005, 2007]
    assert "Sentinel-2 (10/20 m): not validated" in names
    assert "Sentinel-2 (10/20 m): no validated estimate" in names


def test_site_options_and_comparison(mock_outputs):
    _, out, _ = mock_outputs
    d = DashboardData(out)
    sm, scores = d.site_metrics("landsat_2026"), d.candidate_scores("landsat_2026")
    opts = selectable_sites(sm)
    assert list(opts["role"].iloc[:2]) == ["site_a", "site_b"]
    alt_a = opts[opts.role == "site_a_alternative"]
    assert alt_a["score"].is_monotonic_decreasing
    a, b = opts.iloc[0].plot_id, opts.iloc[1].plot_id
    cmp_ = compare_plots(scores, a, b).set_index("metric")
    sa = scores.set_index("plot_id")
    assert cmp_.at["mangrove_cover", "site_a"] == sa.at[a, "mangrove_cover"]
    assert cmp_.at["mangrove_cover", "difference"] == pytest.approx(
        sa.at[a, "mangrove_cover"] - sa.at[b, "mangrove_cover"]
    )


def test_class_proportions(mock_outputs):
    cfgs, out, _ = mock_outputs
    d = DashboardData(out)
    plots = d.site_geometries("landsat_2026")["candidate_plots"]
    sm = d.site_metrics("landsat_2026")
    pid = sm[sm.role == "site_b"].plot_id.iloc[0]
    classes = {c.code: c.name for c in cfgs.classification.classes}
    props = class_proportions(
        out / "m4" / "landsat_2026" / "landcover.tif", plots[plots.plot_id == pid], classes, 7
    )
    assert props["share"].sum() == pytest.approx(1.0)
    cover = sm[sm.role == "site_b"].mangrove_cover.iloc[0]
    assert props.set_index("class_name").at["mangrove", "share"] == pytest.approx(cover, abs=1e-6)


def test_site_figure_uses_one_panel_per_metric():
    cmp_ = pd.DataFrame(
        {
            "metric": ["mangrove_cover", "channel_distance_km_min"],
            "site_a": [0.0, np.nan],
            "site_b": [0.9, 3.2],
        }
    )
    fig = charts.site_metrics_figure(
        cmp_, {"mangrove_cover": "fraction", "channel_distance_km_min": "km"}
    )
    axes = {t.yaxis for t in fig.data}
    assert axes == {"y", "y2"}  # separate y-axes, never a shared scale


def test_render_band_bounds(mock_outputs):
    from indus_delta.dashboard.maps import render_band

    _, out, _ = mock_outputs
    url, bounds, legend = render_band(
        out / "m5" / "landsat_2026" / "mangrove.tif", "mangrove_extent"
    )
    (s, w), (n, e) = bounds
    assert url.startswith("data:image/png;base64,")
    from indus_delta.dashboard.maps import add_raster, map_figure

    fig = map_figure(None)
    add_raster(fig, url, bounds)
    assert fig.layout.map.style == "white-bg"  # no external tiles needed
    assert fig.layout.map.layers[0].sourcetype == "image"
    assert 23.9 < s < n < 24.4 and 67.2 < w < e < 67.7
    assert set(legend) == {"not mangrove", "mangrove"}


def _run_app(monkeypatch, outputs, configs):
    from streamlit.testing.v1 import AppTest

    monkeypatch.setenv("INDUS_DELTA_OUTPUTS", str(outputs))
    monkeypatch.setenv("INDUS_DELTA_CONFIGS", str(configs))
    return AppTest.from_file(APP, default_timeout=180).run()


def test_app_on_mock_pipeline(monkeypatch, mock_outputs):
    _, out, cdir = mock_outputs
    at = _run_app(monkeypatch, out, cdir)
    assert not at.exception, [e.value for e in at.exception]
    assert any("Validation gate: PASS" in s.value for s in at.success)
    assert len(at.get("plotly_chart")) >= 4


def test_app_without_outputs(monkeypatch, tmp_path):
    repo = Path(__file__).resolve().parents[1]
    at = _run_app(monkeypatch, tmp_path, repo / "configs")
    assert not at.exception, [e.value for e in at.exception]
    assert any("not available yet" in i.value for i in at.info)
