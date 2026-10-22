"""Earth Engine helpers: geometry conversion and retrying getInfo calls."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import ee
import geopandas as gpd

log = logging.getLogger(__name__)

# Server messages that indicate a transient condition worth retrying.
_TRANSIENT = (
    "too many concurrent",
    "rate limit",
    "timed out",
    "deadline",
    "internal error",
    "service unavailable",
    "503",
    "429",
)


def with_retries[T](fn: Callable[[], T], what: str, attempts: int = 4) -> T:
    for i in range(attempts):
        try:
            return fn()
        except ee.EEException as exc:
            msg = str(exc).lower()
            if i == attempts - 1 or not any(t in msg for t in _TRANSIENT):
                raise RuntimeError(f"Earth Engine request failed ({what}): {exc}") from exc
            wait = 2 ** (i + 1)
            log.warning("%s: transient error (%s); retrying in %ss", what, exc, wait)
            time.sleep(wait)
    raise AssertionError("unreachable")


def to_ee_geometry(gdf: gpd.GeoDataFrame) -> ee.Geometry:
    """Single (multi)polygon from a GeoDataFrame, sent as planar EPSG:4326 GeoJSON."""
    geom = gdf.to_crs(4326).union_all()
    return ee.Geometry(geom.__geo_interface__, None, False)
