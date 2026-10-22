"""Hydrology review logic. All rasters here are MOCK DATA built for unit tests."""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from rasterio.transform import from_origin
from shapely.geometry import LineString, Point, box

from indus_delta.hydrology import (
    NODATA_OUT,
    AOIHydrologyStats,
    aoi_stats,
    assess,
    jrc_tile_name,
    jrc_tiles_for_bounds,
    label_channels,
    river_connectivity,
    snapped_grid,
)


@pytest.mark.parametrize(
    ("lon", "lat", "tile"),
    [
        (67.45, 24.14, "60E_30N"),
        (60.0, 20.0, "60E_30N"),
        (69.99, 29.99, "60E_30N"),
        (70.0, 24.0, "70E_30N"),
        (-0.5, -0.5, "10W_0N"),
        (5, -15, "0E_10S"),
    ],
)
def test_jrc_tile_name(lon, lat, tile):
    assert jrc_tile_name(lon, lat) == tile


def test_tiles_for_bounds_crossing_boundary():
    assert jrc_tiles_for_bounds((69.5, 24.0, 70.5, 24.5)) == ["60E_30N", "70E_30N"]
    assert jrc_tiles_for_bounds((67.0, 23.7, 67.9, 24.5)) == ["60E_30N"]


def test_snapped_grid_is_aligned():
    tf, w, h = snapped_grid((1001.0, 2017.0, 1950.0, 2990.0), 30)
    assert tf.c % 30 == 0 and tf.f % 30 == 0
    assert tf.c <= 1001 and tf.c + w * 30 >= 1950
    assert tf.f >= 2990 and tf.f - h * 30 <= 2017


def _mock_scene():
    """10x10 MOCK raster, 100 m pixels: a channel along row 5 that leaves the grid at the
    east edge, an isolated pond, and a nodata corner."""
    occ = np.zeros((10, 10), dtype=np.uint8)
    occ[5, :] = 95  # channel
    occ[1, 1] = 80  # isolated pond
    occ[4, :] = 30  # intermittent flat
    occ[0, 9] = NODATA_OUT  # nodata
    tf = from_origin(0, 1000, 100, 100)
    return occ, tf


def _hcfg(cfgs):
    return cfgs.project.hydrology_review


def test_label_channels_ignores_nodata_and_low_values():
    occ, _ = _mock_scene()
    labels, n = label_channels(occ, 50)
    assert n == 2
    assert labels[0, 9] == 0
    assert labels[4, 0] == 0


def test_aoi_stats_on_mock_scene(cfgs):
    occ, tf = _mock_scene()
    labels, _ = label_channels(occ, 50)
    aoi = pd.Series(
        {"geometry": box(0, 400, 500, 600), "aoi_id": "t", "role": "primary", "area_km2": 0.1}
    )
    s = aoi_stats(occ, tf, labels, aoi, _hcfg(cfgs), None, Point(250, 500))
    # 5 cols x 2 rows inside: row 4 (30 %) intermittent, row 5 (95 %) near-permanent
    assert s.occurrence_class_km2["intermittent"] == pytest.approx(0.05)
    assert s.occurrence_class_km2["near_permanent"] == pytest.approx(0.05)
    assert s.channel_components == 1
    assert s.channel_fraction_inside == pytest.approx(0.5)
    assert s.largest_component_touches_review_edge
    assert s.valid_fraction == 1.0
    assert s.area_below_pct_km2["10"] == 0.0


def _stats(**kw):
    base = dict(
        aoi_id="p",
        role="primary",
        area_km2=78.5,
        valid_fraction=1.0,
        occurrence_class_km2={"rarely_or_never": 20.0},
        area_below_pct_km2={},
        water_ever_km2=60,
        channel_components=3,
        channel_km2_inside=10,
        channel_km2_total_of_touching=12,
        channel_fraction_inside=0.83,
        largest_component_touches_review_edge=False,
        coarse_river_intersects=True,
        coarse_river_distance_km=1.0,
    )
    base.update(kw)
    return AOIHydrologyStats(**base)


def test_assess_never_resolves_freshwater():
    checks = {c.name: c for c in assess([_stats()], 50)}
    assert checks["freshwater_influence_candidate"].status == "WARN"
    assert "UNRESOLVED" in checks["freshwater_influence_candidate"].detail


def test_assess_fails_without_creeks():
    checks = {
        c.name: c.status
        for c in assess([_stats(channel_components=0, channel_fraction_inside=float("nan"))], 50)
    }
    assert checks["creek_system_present"] == "FAIL"


def test_assess_warns_when_network_runs_off_extent():
    checks = {
        c.name: c.status for c in assess([_stats(largest_component_touches_review_edge=True)], 50)
    }
    assert checks["creek_network_extent"] == "WARN"


def test_assess_warns_on_little_land():
    checks = {
        c.name: c.status
        for c in assess([_stats(occurrence_class_km2={"rarely_or_never": 0.1})], 50)
    }
    assert checks["land_surface_available"] == "WARN"


def test_river_connectivity_is_never_a_pass():
    occ, tf = _mock_scene()
    labels, _ = label_channels(occ, 50)
    river = gpd.GeoDataFrame(geometry=[LineString([(850, 450), (950, 450)])], crs=32642)
    conn = river_connectivity(labels, tf, np.array([labels[5, 0]]), river, Point(50, 450))
    assert conn.line_pixels_on_aoi_components == conn.line_pixels > 0
    assert conn.nearest_connected_line_pixel_km == pytest.approx(0.8)
    checks = {c.name: c.status for c in assess([_stats()], 50, conn)}
    assert checks["river_creek_connectivity"] == "WARN"
