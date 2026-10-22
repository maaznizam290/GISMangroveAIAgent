import pytest

from indus_delta.crs import check_analysis_crs, utm_zone_number

KETI = (67.45094, 24.14422)


def test_epsg32642_passes_at_reference(cfgs):
    loc = cfgs.project.reference_location
    checks = check_analysis_crs(32642, loc.longitude, loc.latitude)
    assert {c.status for c in checks} == {"PASS"}


def test_wrong_utm_zone_fails():
    checks = {c.name: c.status for c in check_analysis_crs(32643, *KETI)}
    assert checks["crs_utm_zone_matches_location"] == "FAIL"


def test_southern_zone_fails():
    checks = {c.name: c.status for c in check_analysis_crs(32742, *KETI)}
    assert checks["crs_utm_zone_matches_location"] == "FAIL"


def test_geographic_crs_fails():
    checks = {c.name: c.status for c in check_analysis_crs(4326, *KETI)}
    assert checks["crs_projected"] == "FAIL"
    assert checks["crs_units_metre"] == "FAIL"


@pytest.mark.parametrize(
    ("lon", "zone"), [(66.0, 42), (67.45, 42), (71.999, 42), (72.0, 43), (-180, 1), (180, 60)]
)
def test_utm_zone_number(lon, zone):
    assert utm_zone_number(lon) == zone


def test_utm_zone_rejects_bad_longitude():
    with pytest.raises(ValueError):
        utm_zone_number(200)
