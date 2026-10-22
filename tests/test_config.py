import copy

import pytest
import yaml
from pydantic import ValidationError

from indus_delta.config import (
    ConfigError,
    DatasetRegistry,
    IndicesConfig,
    load_configs,
)

from .conftest import CONFIG_DIR


def test_repository_configs_validate(cfgs):
    assert cfgs.project.crs.analysis_epsg == 32642
    assert cfgs.project.aoi.mode == "buffer"
    assert set(cfgs.sha256) == {
        f"{n}.yaml"
        for n in (
            "project",
            "datasets",
            "indices",
            "preprocessing",
            "classification",
            "layers",
            "site_selection",
            "handover",
        )
    }
    assert len(cfgs.combined_sha256()) == 64


def test_missing_config_dir_is_readable_error(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_configs(tmp_path)


def test_buffer_mode_requires_radius(make_project):
    with pytest.raises(ValidationError, match="buffer_m"):
        make_project(aoi__buffer_m=None)


def test_polygon_mode_requires_path(make_project):
    with pytest.raises(ValidationError, match="polygon_path"):
        make_project(aoi__mode="polygon")


def test_negative_buffer_rejected(make_project):
    with pytest.raises(ValidationError):
        make_project(aoi__buffer_m=-5)


def test_verified_location_needs_two_sources(make_project):
    with pytest.raises(ValidationError, match="two independent sources"):
        make_project(reference_location__verification_status="verified")


def test_location_requires_a_source(make_project):
    with pytest.raises(ValidationError):
        make_project(reference_location__sources=[])


def test_unknown_keys_rejected(make_project):
    with pytest.raises(ValidationError):
        make_project(aoi__radius=5000)


def test_season_months_must_be_consecutive(make_project, raw_project):
    seasons = copy.deepcopy(raw_project["seasons"])
    seasons["dry"]["months"] = [11, 1, 2]
    with pytest.raises(ValidationError, match="consecutive"):
        make_project(seasons=seasons)


def test_required_seasons(make_project, raw_project):
    with pytest.raises(ValidationError, match="post_monsoon"):
        make_project(seasons={"dry": raw_project["seasons"]["dry"]})


def test_occurrence_classes_must_be_contiguous(make_project):
    with pytest.raises(ValidationError, match="contiguous"):
        make_project(hydrology_review__occurrence_classes_pct={"a": [0, 40], "b": [50, 100]})


def test_jrc_url_template_needs_tile(make_project, raw_project):
    j = copy.deepcopy(raw_project["hydrology_review"]["jrc_occurrence"])
    j["url_template"] = "https://example.invalid/occurrence.tif"
    with pytest.raises(ValidationError, match="tile"):
        make_project(hydrology_review__jrc_occurrence=j)


# ------------------------------------------------------------------ datasets


def _datasets() -> dict:
    return yaml.safe_load((CONFIG_DIR / "datasets.yaml").read_text())


def test_no_dataset_claims_account_verification(cfgs):
    # No authenticated inventory has run yet; no entry may claim the "verified" level.
    assert not any(d.verification == "verified" for d in cfgs.datasets.datasets.values())
    assert "gmw_v4" in cfgs.datasets.pending("catalog_verified")


def test_catalog_verified_entries_carry_record(cfgs):
    for d in cfgs.datasets.datasets.values():
        if d.verification == "catalog_verified":
            assert d.verified_on and d.verified_by and d.catalog_extent


def test_brief_collection_ids_present(cfgs):
    ids = {d.ee_id for d in cfgs.datasets.datasets.values()}
    assert {"COPERNICUS/S2_SR_HARMONIZED", "COPERNICUS/S1_GRD"} <= ids


def test_gmw_has_no_assumed_ee_asset(cfgs):
    assert cfgs.datasets.datasets["gmw_v4"].ee_id is None


def test_requested_windows_start_with_a_full_dry_season(cfgs):
    ds = cfgs.datasets.datasets
    assert ds["landsat8_l2"].use_period.start.isoformat() == "2004-11-01"
    assert ds["sentinel2_sr"].use_period.start.isoformat() == "2019-11-01"


def test_cross_reference_errors_are_reported(tmp_path):
    import shutil

    for f in CONFIG_DIR.glob("*.yaml"):
        shutil.copy(f, tmp_path / f.name)
    pp = yaml.safe_load((tmp_path / "preprocessing.yaml").read_text())
    pp["landsat"]["members"]["landsat_x"] = "landsat_oli"
    (tmp_path / "preprocessing.yaml").write_text(yaml.safe_dump(pp))
    with pytest.raises(ConfigError, match="unknown dataset 'landsat_x'"):
        load_configs(tmp_path)


def test_landsat7_primary_series_stops_2021(cfgs):
    assert cfgs.datasets.datasets["landsat7_l2"].use_period.end.year == 2021


def test_verified_dataset_needs_record():
    data = _datasets()
    data["datasets"]["landsat8_l2"]["verification"] = "verified"
    data["datasets"]["landsat8_l2"].pop("verified_on", None)
    with pytest.raises(ValidationError, match="verified_on"):
        DatasetRegistry.model_validate(data)


def test_ee_dataset_needs_id():
    data = _datasets()
    data["datasets"]["landsat8_l2"]["ee_id"] = None
    with pytest.raises(ValidationError, match="ee_id"):
        DatasetRegistry.model_validate(data)


# ------------------------------------------------------------------ indices


def _indices() -> dict:
    return yaml.safe_load((CONFIG_DIR / "indices.yaml").read_text())


def test_band_mapping_differs_between_landsat_generations(cfgs):
    s = cfgs.indices.sensors
    assert s["landsat_tm_etm"].bands["nir"] == "SR_B4"
    assert s["landsat_oli"].bands["nir"] == "SR_B5"
    assert s["sentinel2_msi"].bands["swir1"] == "B11"


@pytest.mark.parametrize(
    ("sensor", "index", "expected"),
    [
        ("sentinel2_msi", "ndvi", 10),
        ("sentinel2_msi", "mndwi", 20),
        ("sentinel2_msi", "ndmi", 20),
        ("sentinel2_msi", "mvi", 20),
        ("sentinel2_msi", "cmri", 10),
        ("landsat_oli", "mvi", 30),
    ],
)
def test_effective_resolution(cfgs, sensor, index, expected):
    assert cfgs.indices.effective_resolution_m(sensor, index) == expected


def test_cmri_uses_mcfeeters_ndwi(cfgs):
    cmri = cfgs.indices.indices["cmri"]
    ndwi = cfgs.indices.indices[cmri.subtrahend]
    assert (cmri.minuend, ndwi.a, ndwi.b) == ("ndvi", "green", "nir")


def test_formulas_match_brief(cfgs):
    idx = cfgs.indices.indices
    assert (idx["ndvi"].a, idx["ndvi"].b) == ("nir", "red")
    assert (idx["ndmi"].a, idx["ndmi"].b) == ("nir", "swir1")
    assert (idx["mndwi"].a, idx["mndwi"].b) == ("green", "swir1")
    assert idx["mvi"].numerator == ("nir", "green")
    assert idx["mvi"].denominator == ("swir1", "green")


def test_duplicate_band_assignment_rejected():
    data = _indices()
    data["sensors"]["landsat_oli"]["bands"]["red"] = "SR_B5"
    with pytest.raises(ValidationError, match="more than one role"):
        IndicesConfig.model_validate(data)


def test_unknown_base_index_rejected():
    data = _indices()
    data["indices"]["cmri"]["subtrahend"] = "ndwi_unknown"
    with pytest.raises(ValidationError, match="unknown base index"):
        IndicesConfig.model_validate(data)
