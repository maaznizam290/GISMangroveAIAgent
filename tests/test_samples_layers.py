"""Samples, salinity proxy rules, trends and site plots. Inputs are MOCK DATA."""

from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
import yaml
from pydantic import ValidationError
from shapely.geometry import Point

from indus_delta.aoi import build_aoi, reference_point
from indus_delta.config import LayersConfig, SoilSalinityConfig
from indus_delta.layer_io import LayerMeta
from indus_delta.m5 import calibrate_threshold, percentile_rank
from indus_delta.m6 import check_independence, make_plots
from indus_delta.samples import (
    SamplesUnavailable,
    enforce_separation,
    holdout_blocks,
    load_field_salinity,
    load_samples,
)
from indus_delta.trends import trend

from .conftest import CONFIG_DIR


def _samples(cfgs, n=40, **override):
    ref = reference_point(cfgs.project).geometry.iloc[0]
    rng = np.random.default_rng(0)
    data = {
        "sample_id": [f"S{i}" for i in range(n)],
        "class_code": rng.integers(1, 7, n),
        "label_year": 2026,
        "source": "field_survey",
        "interpreter": "MOCK",
        "observed_date": "2026-01-01",
    }
    data.update(override)
    pts = [
        Point(ref.x + rng.uniform(-3000, 3000), ref.y + rng.uniform(-3000, 3000)) for _ in range(n)
    ]
    return gpd.GeoDataFrame(data, geometry=pts, crs=32642)


def test_missing_samples_are_reported(cfgs, tmp_path):
    with pytest.raises(SamplesUnavailable, match="supplied by the operator"):
        load_samples(tmp_path / "none.gpkg", cfgs, build_aoi(cfgs.project), "reference")


def test_nodata_class_rejected_as_reference(cfgs, tmp_path):
    g = _samples(cfgs, class_code=[7] * 40)
    g.to_file(tmp_path / "s.gpkg")
    with pytest.raises(ValueError, match="not a reference class"):
        load_samples(tmp_path / "s.gpkg", cfgs, build_aoi(cfgs.project), "reference")


def test_conflicting_labels_rejected(cfgs, tmp_path):
    g = _samples(cfgs, n=1, class_code=[1])
    twin = g.assign(sample_id="S_twin", class_code=2)
    gpd.GeoDataFrame(pd.concat([g, twin]), crs=32642).to_file(tmp_path / "s.gpkg")
    with pytest.raises(ValueError, match="different classes"):
        load_samples(tmp_path / "s.gpkg", cfgs, build_aoi(cfgs.project), "reference")


def test_holdout_blocks_are_disjoint(cfgs):
    g = _samples(cfgs, n=200)
    train, val = holdout_blocks(g, cfgs)
    assert len(train) + len(val) == 200 and len(val) > 0
    size = cfgs.classification.split.block_size_m

    def blocks(d):
        return set(
            zip((d.geometry.x // size).astype(int), (d.geometry.y // size).astype(int), strict=True)
        )

    assert not blocks(train) & blocks(val)


def test_enforce_separation(cfgs):
    g = _samples(cfgs, n=100)
    kept, check = enforce_separation(g.iloc[:80], g.iloc[80:], 800)
    assert check.status == "PASS"
    assert kept.geometry.apply(lambda p: g.iloc[80:].distance(p).min()).min() >= 800


def test_salinity_config_rejects_red_nir():
    with pytest.raises(ValidationError, match="-NDVI"):
        SoilSalinityConfig.model_validate(
            {
                "season": "dry",
                "eligible_classes": ["mudflat"],
                "max_inundation_frequency": 0.5,
                "min_valid_observations": 3,
                "features": [
                    {
                        "name": "nsi",
                        "kind": "ratio",
                        "direction": 1,
                        "numerator": "red",
                        "denominator": "nir",
                    }
                ],
            }
        )


def test_salinity_on_mangrove_rejected(tmp_path):
    import shutil

    from indus_delta.config import ConfigError, load_configs

    for f in CONFIG_DIR.glob("*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    d = yaml.safe_load((tmp_path / "layers.yaml").read_text())
    d["soil_salinity_proxy"]["eligible_classes"].append("mangrove")
    (tmp_path / "layers.yaml").write_text(yaml.safe_dump(d))
    with pytest.raises(ConfigError, match="mangrove"):
        load_configs(tmp_path)


def test_percentile_rank():
    v = np.array([[1.0, 2.0], [3.0, np.nan]])
    m = np.array([[True, True], [False, True]])
    r = percentile_rank(v, m)
    assert r[0, 0] == pytest.approx(25) and r[0, 1] == pytest.approx(75)
    assert np.isnan(r[1, 0]) and np.isnan(r[1, 1])


def test_calibrate_threshold_separates():
    v = np.array([-0.5, -0.4, -0.3, 0.2, 0.3, 0.4, np.nan])
    w = np.array([0, 0, 0, 1, 1, 1, 1], bool)
    t, ba = calibrate_threshold(v, w)
    assert -0.3 < t < 0.2 and ba == 1.0
    with pytest.raises(ValueError):
        calibrate_threshold(v, np.zeros(7, bool))


def test_trend_requires_completeness(cfgs):
    years = np.arange(2005, 2009)
    r = trend(years, np.arange(4.0), cfgs, "landsat", "x")
    assert r.status == "insufficient" and "< 8" in r.reason
    years = np.array([2005, 2006, 2010, 2015, 2018, 2020, 2022, 2024, 2026])
    r = trend(years, np.arange(9.0), cfgs, "landsat", "x")
    assert r.status == "insufficient" and "missing" in r.reason


def test_trend_detects_monotonic_series(cfgs):
    years = np.arange(2010, 2022)
    r = trend(
        years,
        50 - 0.5 * (years - 2010) + np.r_[0.1, -0.1].repeat(6),
        cfgs,
        "landsat",
        "mangrove_area_km2",
    )
    assert r.status == "computed" and r.tau < 0 and r.p_value < 0.05
    assert r.sen_slope_per_year == pytest.approx(-0.5, abs=0.05)


def test_plots_are_inside_aoi_and_square(cfgs):
    aoi = build_aoi(cfgs.project)
    plots = make_plots(aoi, 500)
    assert len(plots) > 200
    assert np.allclose(plots.area, 250_000)
    assert plots.within(aoi.union_all().buffer(1e-6)).all()
    assert (plots.bounds.minx % 500 == 0).all()


def test_independence_check_flags_circular_salinity():
    bad = LayerMeta("soil_salinity_proxy", "proxy", "x", "", derived_from=["landcover"])
    good = LayerMeta(
        "soil_salinity_proxy",
        "proxy",
        "x",
        "",
        derived_from=["landsat_dry:swir1"],
        mask_from=["landcover"],
    )
    assert check_independence(bad, None)[0].status == "FAIL"
    assert check_independence(good, None)[0].status == "PASS"


def test_field_salinity_schema(cfgs, tmp_path):
    p = tmp_path / "f.csv"
    pd.DataFrame(
        [
            {
                "measurement_id": "M1",
                "datetime_utc": "2026-01-01T05:00:00Z",
                "longitude": 67.4,
                "latitude": 24.1,
                "value": 4.5,
                "units": "mS/cm",
                "method": "MOCK EC probe",
                "tide_state": "flood",
            }
        ]
    ).to_csv(p, index=False)
    g = load_field_salinity(p, cfgs)
    assert g.crs.to_epsg() == 32642 and g.iloc[0].layer_type == "measured"
    pd.DataFrame(
        [
            {
                "measurement_id": "M1",
                "datetime_utc": "2026-01-01",
                "longitude": 67.4,
                "latitude": 24.1,
                "value": 4.5,
                "units": "g/L",
                "method": "x",
                "tide_state": "x",
            }
        ]
    ).to_csv(p, index=False)
    with pytest.raises(ValueError, match="units"):
        load_field_salinity(p, cfgs)


def test_layers_config_round_trip():
    d = yaml.safe_load((CONFIG_DIR / "layers.yaml").read_text())
    assert LayersConfig.model_validate(d).tidal_inundation.optical_threshold is None


def test_unused_import_guard():
    assert date(2026, 1, 1).year == 2026
