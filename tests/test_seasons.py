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


from indus_delta.seasons import assign_season, windows_for_years  # noqa: E402


def test_assign_season(cfgs):
    s = cfgs.project.seasons
    assert assign_season(date(2019, 11, 1), s) == ("dry", 2020)
    assert assign_season(date(2019, 12, 31), s) == ("dry", 2020)
    assert assign_season(date(2020, 3, 31), s) == ("dry", 2020)
    assert assign_season(date(2020, 9, 15), s) == ("post_monsoon", 2020)
    assert assign_season(date(2020, 6, 1), s) is None


def test_assign_season_matches_window(cfgs):
    s = cfgs.project.seasons
    for d in (date(2004, 11, 1), date(2005, 3, 31), date(2026, 10, 21)):
        name, year = assign_season(d, s)
        w = season_window(name, s[name], year)
        assert w.start <= d < w.end


def test_windows_for_years(cfgs):
    ws = windows_for_years(cfgs.project.seasons, 2005, 2026)
    assert len(ws) == 44
    assert ws[0].start == date(2004, 11, 1)
