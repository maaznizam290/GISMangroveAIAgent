"""Inventory bookkeeping. Records here are MOCK DATA, not Earth Engine output."""

from datetime import date

import pandas as pd

from indus_delta.inventory import (
    build_records,
    inventory_checks,
    missing_observations,
    s1_orbit_summary,
    summarise,
)


def _no_pass(cfgs):
    """The MOCK Sentinel-1 records are ASCENDING; test with no orbit pass chosen yet."""
    s1 = cfgs.preprocessing.sentinel1.model_copy(update={"orbit_pass": None})
    pp = cfgs.preprocessing.model_copy(update={"sentinel1": s1})
    return cfgs.model_copy(update={"preprocessing": pp})


def _raw():
    return [
        {
            "dataset": "landsat8_l2",
            "image_id": "MOCK_L8_A",
            "acquired_utc": "2019-12-10T05:50:00Z",
            "valid_fraction": 0.9,
            "scene_cloud_pct": 3.0,
        },
        {
            "dataset": "landsat8_l2",
            "image_id": "MOCK_L8_B",
            "acquired_utc": "2020-02-12T05:50:00Z",
            "valid_fraction": 0.1,
            "scene_cloud_pct": 70.0,
        },
        {
            "dataset": "landsat7_l2",
            "image_id": "MOCK_L7_late",
            "acquired_utc": "2022-01-05T05:40:00Z",
            "valid_fraction": 0.8,
        },
        {
            "dataset": "landsat8_l2",
            "image_id": "MOCK_L8_C",
            "acquired_utc": "2020-06-01T05:50:00Z",
            "valid_fraction": 0.95,
        },
        {
            "dataset": "sentinel1_grd",
            "image_id": "MOCK_S1_ok",
            "acquired_utc": "2020-01-03T13:30:00Z",
            "valid_fraction": 1.0,
            "polarisations": "VV+VH",
            "resolution_m": 10,
            "orbit_pass": "ASCENDING",
            "relative_orbit": 49,
        },
        {
            "dataset": "sentinel1_grd",
            "image_id": "MOCK_S1_vvonly",
            "acquired_utc": "2020-01-15T13:30:00Z",
            "valid_fraction": 1.0,
            "polarisations": "VV",
            "resolution_m": 10,
            "orbit_pass": "ASCENDING",
            "relative_orbit": 49,
        },
    ]


def test_build_records_assigns_seasons_and_flags(cfgs):
    df = build_records(_raw(), _no_pass(cfgs)).set_index("image_id")
    assert (df.loc["MOCK_L8_A", "season"], df.loc["MOCK_L8_A", "label_year"]) == ("dry", 2020)
    assert df.loc["MOCK_L8_A", "usable"] and not df.loc["MOCK_L8_B", "usable"]
    assert not df.loc["MOCK_L7_late", "in_primary_series"]
    assert pd.isna(df.loc["MOCK_L8_C", "season"])  # June: outside both seasons
    assert df.loc["MOCK_S1_ok", "compatible"] and not df.loc["MOCK_S1_vvonly", "compatible"]
    assert not df.loc["MOCK_S1_vvonly", "usable"]
    assert set(df["tide_status"]) == {"unavailable"}


def test_summary_lists_every_season_year(cfgs):
    df = build_records(_raw(), cfgs)
    summary = summarise(df, cfgs, {"landsat": date(2026, 10, 11), "sentinel1": date(2026, 10, 21)})
    land = summary[summary.series == "landsat"]
    assert len(land) == 44  # 22 years x 2 seasons, including empty ones
    row = land[(land.season == "dry") & (land.label_year == 2020)].iloc[0]
    assert (row.n_images, row.n_usable, row.completeness) == (2, 1, "complete")
    late = land[(land.season == "post_monsoon") & (land.label_year == 2026)].iloc[0]
    assert late.completeness == "partial"
    assert summary[summary.series == "sentinel2"]["completeness"].eq("unknown").all()


def test_missing_observations_reasons(cfgs):
    df = build_records(_raw(), cfgs)
    summary = summarise(df, cfgs, {"landsat": date(2026, 10, 11)})
    miss = missing_observations(summary)
    keys = zip(miss.series, miss.season, miss.label_year, strict=True)
    reasons = dict(zip(keys, miss.reason, strict=True))
    assert reasons[("landsat", "dry", 2006)] == "no images in window"
    assert reasons[("landsat", "post_monsoon", 2026)] == (
        "no images in window; partial season: data end 2026-10-11 before window end"
    )
    assert ("landsat", "dry", 2020) not in reasons


def test_missing_required_dataset_fails(cfgs):
    df = build_records(_raw(), cfgs)
    summary = summarise(df, cfgs, {})
    checks = {c.name: c.status for c in inventory_checks(df, summary, cfgs)}
    assert checks["images_landsat8_l2"] == "PASS"
    assert checks["images_sentinel2_sr"] == "FAIL"


def test_s1_orbit_summary(cfgs):
    s = s1_orbit_summary(build_records(_raw(), _no_pass(cfgs)))
    row = s.iloc[0]
    assert (row.orbit_pass, row.relative_orbit, row.year, row.n_scenes, row.n_compatible) == (
        "ASCENDING",
        49,
        2020,
        2,
        1,
    )
