import math

import geopandas as gpd
import pyogrio
import pytest
from shapely.geometry import box

from indus_delta.aoi import alternative_aois, build_aoi, reference_point, write_layers


def test_reference_point_projected_with_provenance(cfgs):
    ref = reference_point(cfgs.project)
    assert ref.crs.to_epsg() == 32642
    assert ref.verification_status.iloc[0] == "provisional"
    assert ref.source_url.iloc[0].startswith("https://")


def test_buffer_aoi_area_and_centre(cfgs):
    aoi = build_aoi(cfgs.project)
    r = cfgs.project.aoi.buffer_m
    assert aoi.crs.to_epsg() == 32642
    assert aoi.area_km2.iloc[0] == pytest.approx(math.pi * r**2 / 1e6, rel=1e-3)
    centre = reference_point(cfgs.project).geometry.iloc[0]
    assert aoi.geometry.iloc[0].centroid.distance(centre) < 0.01


def test_buffer_radius_is_configurable(make_project):
    aoi = build_aoi(make_project(aoi__buffer_m=2500))
    assert aoi.area_km2.iloc[0] == pytest.approx(math.pi * 2.5**2, rel=1e-3)


def test_alternatives_are_proposals(cfgs):
    alts = alternative_aois(cfgs.project)
    assert set(alts.role) == {"alternative"}
    assert list(alts.buffer_m) == cfgs.project.aoi.alternative_buffers_m


def test_polygon_mode(tmp_path, make_project, cfgs):
    ref = reference_point(cfgs.project).geometry.iloc[0]
    poly = gpd.GeoDataFrame(
        geometry=[box(ref.x - 1000, ref.y - 2000, ref.x + 3000, ref.y + 2000)], crs=32642
    ).to_crs(4326)
    path = tmp_path / "custom.gpkg"
    poly.to_file(path, driver="GPKG")
    aoi = build_aoi(make_project(aoi__mode="polygon", aoi__polygon_path=str(path)))
    assert aoi.crs.to_epsg() == 32642
    assert aoi.area_km2.iloc[0] == pytest.approx(16.0, rel=1e-3)
    assert aoi["mode"].iloc[0] == "polygon"


@pytest.mark.filterwarnings("ignore:.crs. was not provided")
def test_polygon_without_crs_rejected(tmp_path, make_project):
    path = tmp_path / "nocrs.geojson"
    path.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{},'
        '"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,0]]]}}]}'
    )
    # GeoJSON implies WGS84 in GDAL, so write a CRS-less GeoPackage instead.
    gpkg = tmp_path / "nocrs.gpkg"
    gpd.read_file(path).set_crs(None, allow_override=True).to_file(gpkg, driver="GPKG")
    with pytest.raises(ValueError, match="no CRS"):
        build_aoi(make_project(aoi__mode="polygon", aoi__polygon_path=str(gpkg)))


def test_missing_polygon_file(make_project, tmp_path):
    with pytest.raises(FileNotFoundError):
        build_aoi(make_project(aoi__mode="polygon", aoi__polygon_path=str(tmp_path / "x.gpkg")))


def test_gpkg_layers_round_trip(tmp_path, cfgs):
    out = write_layers(
        tmp_path / "aoi.gpkg",
        {
            "reference_location": reference_point(cfgs.project),
            "aoi_primary": build_aoi(cfgs.project),
            "aoi_alternatives": alternative_aois(cfgs.project),
        },
    )
    layers = {name for name, _ in pyogrio.list_layers(out)}
    assert layers == {"reference_location", "aoi_primary", "aoi_alternatives"}
    back = gpd.read_file(out, layer="aoi_primary")
    assert back.crs.to_epsg() == 32642
    assert {"aoi_id", "role", "mode", "buffer_m", "area_km2", "config_version"} <= set(back.columns)
