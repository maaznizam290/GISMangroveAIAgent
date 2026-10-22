from datetime import date

from indus_delta.seasons import season_window


def test_dry_season_labelled_by_end_year(cfgs):
    w = season_window("dry", cfgs.project.seasons["dry"], 2020)
    assert (w.start, w.end) == (date(2019, 11, 1), date(2020, 4, 1))


def test_post_monsoon_window(cfgs):
    w = season_window("post_monsoon", cfgs.project.seasons["post_monsoon"], 2020)
    assert (w.start, w.end) == (date(2020, 9, 1), date(2020, 11, 1))


def test_first_landsat_dry_season_starts_in_2004(cfgs):
    w = season_window("dry", cfgs.project.seasons["dry"], cfgs.project.periods.landsat.start_year)
    assert w.start == date(2004, 11, 1)


def test_completeness_flags_partial_2026(cfgs):
    dry = season_window("dry", cfgs.project.seasons["dry"], 2026)
    post = season_window("post_monsoon", cfgs.project.seasons["post_monsoon"], 2026)
    assert dry.completeness(date(2026, 10, 15)) == "complete"
    assert post.completeness(date(2026, 10, 15)) == "partial"
    assert post.completeness(date(2026, 8, 1)) == "not_started"
