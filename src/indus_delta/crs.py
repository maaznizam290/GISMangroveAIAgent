"""Checks that the analysis CRS suits distance and area work at the study location."""

from __future__ import annotations

import math

from pyproj import CRS, Transformer

from indus_delta.checks import Check


def utm_zone_number(longitude: float) -> int:
    """Standard 6-degree UTM zone (no Norway/Svalbard exceptions; irrelevant at 67 E)."""
    if not -180 <= longitude <= 180:
        raise ValueError(f"longitude out of range: {longitude}")
    return min(int(math.floor((longitude + 180) / 6)) + 1, 60)


def check_analysis_crs(epsg: int, longitude: float, latitude: float) -> list[Check]:
    crs = CRS.from_epsg(epsg)
    checks = [
        Check(
            "crs_projected",
            "PASS" if crs.is_projected else "FAIL",
            f"EPSG:{epsg} ({crs.name}) is {'projected' if crs.is_projected else 'not projected'}",
        )
    ]
    units = {ax.unit_name for ax in crs.axis_info}
    checks.append(
        Check(
            "crs_units_metre",
            "PASS" if units == {"metre"} else "FAIL",
            f"axis units: {sorted(units)}",
        )
    )
    zone = crs.utm_zone  # e.g. "42N" or None
    expected = f"{utm_zone_number(longitude)}{'N' if latitude >= 0 else 'S'}"
    checks.append(
        Check(
            "crs_utm_zone_matches_location",
            "PASS" if zone == expected else "FAIL",
            f"CRS zone {zone}; location ({longitude:.5f}, {latitude:.5f}) falls in zone {expected}",
        )
    )
    # Round trip through the analysis CRS must be lossless at the sub-millimetre level.
    fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    inv = Transformer.from_crs(epsg, 4326, always_xy=True)
    x, y = fwd.transform(longitude, latitude)
    lon2, lat2 = inv.transform(x, y)
    err_m = math.hypot(
        (lon2 - longitude) * 111_320 * math.cos(math.radians(latitude)), (lat2 - latitude) * 110_540
    )
    checks.append(
        Check(
            "crs_round_trip",
            "PASS" if err_m < 1e-3 else "FAIL",
            f"reference point -> ({x:.2f} E, {y:.2f} N) m; round-trip error {err_m:.2e} m",
        )
    )
    # Point scale factor indicates distance distortion at the site (UTM: 0.9996 on CM).
    factor = _scale_factor(epsg, longitude, latitude)
    checks.append(
        Check(
            "crs_scale_factor",
            "PASS" if abs(factor - 1) < 1e-3 else "WARN",
            f"meridional scale factor at reference point {factor:.6f} "
            f"(distance distortion {abs(factor - 1) * 1e6:.0f} ppm)",
        )
    )
    return checks


def _scale_factor(epsg: int, longitude: float, latitude: float) -> float:
    from pyproj import Proj

    return Proj(CRS.from_epsg(epsg)).get_factors(longitude, latitude).meridional_scale
