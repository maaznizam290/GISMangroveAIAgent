"""Versioned configuration schema.

All scientific parameters (CRS, AOI, seasons, dataset identifiers, index definitions,
review thresholds) are read from YAML under ``configs/`` and validated here. Code never
carries its own copy of these values.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_CONFIG_DIR = Path("configs")


class ConfigError(ValueError):
    """Raised when a configuration file is missing or fails validation."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------- project.yaml


class ProjectInfo(_Strict):
    name: str
    study_area_name: str
    output_dir: Path = Path("outputs")


class CRSConfig(_Strict):
    analysis_epsg: int
    geographic_epsg: int = 4326


class LocationSource(_Strict):
    dataset: str
    url: str
    version: str
    record: str
    licence: str
    retrieved: date
    file_md5: str | None = None


class ReferenceLocation(_Strict):
    name: str
    longitude: Annotated[float, Field(ge=-180, le=180)]
    latitude: Annotated[float, Field(ge=-90, le=90)]
    verification_status: Literal["provisional", "verified"]
    feature_type: str
    sources: Annotated[list[LocationSource], Field(min_length=1)]
    notes: str = ""

    @model_validator(mode="after")
    def _verified_needs_two_sources(self) -> ReferenceLocation:
        if self.verification_status == "verified" and len(self.sources) < 2:
            raise ValueError(
                "verification_status 'verified' requires at least two independent sources"
            )
        return self


class AOIConfig(_Strict):
    mode: Literal["buffer", "polygon"]
    buffer_m: Annotated[float, Field(gt=0)] | None = None
    polygon_path: Path | None = None
    alternative_buffers_m: list[Annotated[float, Field(gt=0)]] = []
    # Full-scale processing is refused until the operator confirms the AOI (M1 review).
    operator_confirmed: bool = False
    confirmation_note: str = ""

    @model_validator(mode="after")
    def _mode_fields(self) -> AOIConfig:
        if self.mode == "buffer" and self.buffer_m is None:
            raise ValueError("aoi.mode 'buffer' requires aoi.buffer_m")
        if self.mode == "polygon" and self.polygon_path is None:
            raise ValueError("aoi.mode 'polygon' requires aoi.polygon_path")
        return self


class YearRange(_Strict):
    start_year: int
    end_year: int

    @model_validator(mode="after")
    def _ordered(self) -> YearRange:
        if self.end_year < self.start_year:
            raise ValueError("end_year must be >= start_year")
        return self


class Periods(_Strict):
    landsat: YearRange
    sentinel: YearRange


class SeasonConfig(_Strict):
    months: Annotated[list[Annotated[int, Field(ge=1, le=12)]], Field(min_length=1)]
    year_assignment: Literal["end"]

    @field_validator("months")
    @classmethod
    def _contiguous(cls, months: list[int]) -> list[int]:
        if len(set(months)) != len(months):
            raise ValueError("season months must be unique")
        for prev, nxt in zip(months, months[1:], strict=False):
            if nxt != prev % 12 + 1:
                raise ValueError(f"season months must be consecutive, got {months}")
        return months


class JRCOccurrenceConfig(_Strict):
    url_template: str
    tile_size_deg: int
    nodata_value: int
    valid_max: int

    @field_validator("url_template")
    @classmethod
    def _has_tile(cls, v: str) -> str:
        if "{tile}" not in v:
            raise ValueError("url_template must contain '{tile}'")
        return v


class CoarseRiverReference(_Strict):
    dataset: str
    url: str
    version: str
    licence: str
    feature_name: str
    feature_class: str


class HydrologyReviewConfig(_Strict):
    jrc_occurrence: JRCOccurrenceConfig
    analysis_resolution_m: Annotated[float, Field(gt=0)]
    review_margin_m: Annotated[float, Field(ge=0)]
    occurrence_classes_pct: dict[str, tuple[float, float]]
    cumulative_below_pct: list[Annotated[float, Field(gt=0, le=100)]] = []
    channel_occurrence_min_pct: Annotated[float, Field(gt=0, le=100)]
    coarse_river_reference: CoarseRiverReference

    @field_validator("occurrence_classes_pct")
    @classmethod
    def _bins_cover_range(cls, bins: dict[str, tuple[float, float]]) -> dict:
        edges = sorted(bins.values())
        if not edges or edges[0][0] != 0 or edges[-1][1] != 100:
            raise ValueError("occurrence classes must span 0-100")
        for (lo, hi), (nlo, _) in zip(edges, edges[1:], strict=False):
            if hi != nlo or lo >= hi:
                raise ValueError("occurrence classes must be contiguous and non-overlapping")
        return bins


class ProjectConfig(_Strict):
    config_version: str
    project: ProjectInfo
    crs: CRSConfig
    reference_location: ReferenceLocation
    aoi: AOIConfig
    periods: Periods
    seasons: dict[str, SeasonConfig]
    hydrology_review: HydrologyReviewConfig

    @model_validator(mode="after")
    def _required_seasons(self) -> ProjectConfig:
        missing = {"dry", "post_monsoon"} - set(self.seasons)
        if missing:
            raise ValueError(f"seasons missing: {sorted(missing)}")
        return self


# --------------------------------------------------------------------------- datasets.yaml


class UsePeriod(_Strict):
    start: date
    end: date | None = None


class CatalogExtent(_Strict):
    start: date
    end: date


class DatasetEntry(_Strict):
    ee_id: str | None = None
    # Path of the STAC record below the catalog root when it does not follow the
    # "<first segment>/<id with / replaced by _>.json" convention.
    stac_path: str | None = None
    local_path: Path | None = None
    kind: Literal["image", "image_collection", "table", "reference_product"]
    sensor: str
    role: str
    use_period: UsePeriod
    reflectance_scale: float | None = None
    reflectance_offset: float | None = None
    required_bands: list[str] = []
    optional: bool = False
    doi: str | None = None
    notes: str = ""
    verification: Literal["pending", "catalog_verified", "verified"]
    verified_on: date | None = None
    verified_by: str | None = None
    catalog_extent: CatalogExtent | None = None

    @model_validator(mode="after")
    def _verified_has_record(self) -> DatasetEntry:
        if self.verification != "pending" and (self.verified_on is None or not self.verified_by):
            raise ValueError(f"{self.verification} datasets need verified_on and verified_by")
        if self.kind != "reference_product" and not self.ee_id:
            raise ValueError("Earth Engine datasets need ee_id")
        return self

    def requested_window(self, today: date) -> tuple[date, date]:
        """Requested start/end (inclusive), clipped to the catalog extent when known."""
        start, end = self.use_period.start, self.use_period.end or today
        if self.catalog_extent:
            start = max(start, self.catalog_extent.start)
            end = min(end, self.catalog_extent.end)
        return start, end


class DatasetRegistry(_Strict):
    config_version: str
    datasets: dict[str, DatasetEntry]

    def pending(self, level: str = "verified") -> list[str]:
        """Datasets not yet at the given verification level (optional ones excluded)."""
        rank = {"pending": 0, "catalog_verified": 1, "verified": 2}
        return [
            k
            for k, v in self.datasets.items()
            if not v.optional and rank[v.verification] < rank[level]
        ]


# --------------------------------------------------------------------------- preprocessing.yaml


class CatalogConfig(_Strict):
    stac_root: str


class QABit(_Strict):
    bit: Annotated[int, Field(ge=0, le=15)]
    description: str
    sensors: list[str] | None = None


class LandsatPrep(_Strict):
    members: dict[str, str]
    qa_pixel_mask_bits: list[QABit]
    mask_saturated_bands: bool
    max_scene_cloud_cover_pct: Annotated[float, Field(ge=0, le=100)]
    harmonisation: Literal["none"]

    def mask_bits_for(self, index_sensor: str) -> list[int]:
        return [
            b.bit for b in self.qa_pixel_mask_bits if b.sensors is None or index_sensor in b.sensors
        ]


class SCLClass(_Strict):
    value: Annotated[int, Field(ge=0, le=11)]
    description: str


class CloudScorePlus(_Strict):
    enabled: bool
    dataset: str
    band: str
    min_score: Annotated[float, Field(ge=0, le=1)]


class Sentinel2Prep(_Strict):
    dataset: str
    index_sensor: str
    scl_band: str
    scl_mask_classes: list[SCLClass]
    scl_mask_nodata_value: int
    cloud_score_plus: CloudScorePlus
    max_scene_cloud_pct: Annotated[float, Field(ge=0, le=100)]


class Sentinel1Prep(_Strict):
    dataset: str
    instrument_mode: str
    polarisations: Annotated[list[str], Field(min_length=1)]
    resolution_meters: float
    orbit_pass: Literal["ASCENDING", "DESCENDING"] | None
    speckle_filter: Literal["none"]


class CompositeConfig(_Strict):
    reducer: Literal["median"]
    indices_from: Literal["composite"]
    landsat_scale_m: Annotated[float, Field(gt=0)]
    sentinel2_scale_m: Annotated[float, Field(gt=0)]
    sentinel1_scale_m: Annotated[float, Field(gt=0)]
    landsat7_primary_end: date
    nodata_value: float


class TideConfig(_Strict):
    provider: Literal["none"]


class InventoryConfig(_Strict):
    region: Literal["primary_aoi"]
    valid_fraction_scale_m: Annotated[float, Field(gt=0)]
    min_usable_valid_fraction: Annotated[float, Field(ge=0, le=1)]
    required_datasets: list[str]


class PreviewConfig(_Strict):
    half_size_m: Annotated[float, Field(gt=0, le=10000)]
    season: str
    label_year: int | None = None
    min_valid_fraction: Annotated[float, Field(ge=0, le=1)]
    index_recompute_tolerance: Annotated[float, Field(gt=0)]
    reflectance_tolerance: Annotated[float, Field(ge=0)]
    sar_db_range: tuple[float, float]


class PreprocessingConfig(_Strict):
    config_version: str
    catalog: CatalogConfig
    landsat: LandsatPrep
    sentinel2: Sentinel2Prep
    sentinel1: Sentinel1Prep
    composites: CompositeConfig
    tide: TideConfig
    inventory: InventoryConfig
    preview: PreviewConfig


# --------------------------------------------------------------------------- indices.yaml

BandRole = Literal["blue", "green", "red", "nir", "swir1", "swir2"]


class SensorBands(_Strict):
    bands: dict[BandRole, str]
    native_resolution_m: dict[BandRole, float]

    @model_validator(mode="after")
    def _complete(self) -> SensorBands:
        if set(self.bands) != set(self.native_resolution_m):
            raise ValueError("bands and native_resolution_m must list the same roles")
        if len(set(self.bands.values())) != len(self.bands):
            raise ValueError("a sensor band is mapped to more than one role")
        return self


class NormalizedDifference(_Strict):
    long_name: str
    type: Literal["normalized_difference"]
    a: BandRole
    b: BandRole


class RatioOfDifferences(_Strict):
    long_name: str
    type: Literal["ratio_of_differences"]
    numerator: tuple[BandRole, BandRole]
    denominator: tuple[BandRole, BandRole]


class DifferenceOfIndices(_Strict):
    long_name: str
    type: Literal["difference_of_indices"]
    minuend: str
    subtrahend: str


IndexDef = Annotated[
    NormalizedDifference | RatioOfDifferences | DifferenceOfIndices,
    Field(discriminator="type"),
]


class ReflectanceRange(_Strict):
    min: float
    max: float


class IndicesConfig(_Strict):
    config_version: str
    band_roles: list[BandRole]
    sensors: dict[str, SensorBands]
    valid_reflectance: ReflectanceRange
    min_abs_denominator: Annotated[float, Field(gt=0)]
    indices: dict[str, IndexDef]

    @model_validator(mode="after")
    def _consistent(self) -> IndicesConfig:
        for name, sensor in self.sensors.items():
            missing = set(self.band_roles) - set(sensor.bands)
            if missing:
                raise ValueError(f"sensor {name} lacks band roles {sorted(missing)}")
        for name, idx in self.indices.items():
            if isinstance(idx, DifferenceOfIndices):
                for ref in (idx.minuend, idx.subtrahend):
                    if ref not in self.indices or isinstance(
                        self.indices[ref], DifferenceOfIndices
                    ):
                        raise ValueError(f"index {name} references unknown base index {ref}")
        return self

    def effective_resolution_m(self, sensor: str, index: str) -> float:
        """Coarsest native resolution among the bands an index uses."""
        bands = self.sensors[sensor].native_resolution_m
        return max(bands[r] for r in self.roles_used(index))

    def roles_used(self, index: str) -> set[str]:
        idx = self.indices[index]
        if isinstance(idx, NormalizedDifference):
            return {idx.a, idx.b}
        if isinstance(idx, RatioOfDifferences):
            return {*idx.numerator, *idx.denominator}
        return self.roles_used(idx.minuend) | self.roles_used(idx.subtrahend)


# --------------------------------------------------------------------------- loading


class Configs(_Strict):
    project: ProjectConfig
    datasets: DatasetRegistry
    indices: IndicesConfig
    preprocessing: PreprocessingConfig
    sha256: dict[str, str]

    def combined_sha256(self) -> str:
        """One hash over all config files, used to bind gate results to a configuration."""
        joined = "".join(f"{k}={v};" for k, v in sorted(self.sha256.items()))
        return hashlib.sha256(joined.encode()).hexdigest()


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"configuration file not found: {path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return data


def _validate(model: type[BaseModel], path: Path):
    try:
        return model.model_validate(_read_yaml(path))
    except ValueError as exc:  # pydantic.ValidationError subclasses ValueError
        if isinstance(exc, ConfigError):
            raise
        raise ConfigError(f"{path} is invalid:\n{exc}") from exc


def load_configs(config_dir: Path = DEFAULT_CONFIG_DIR) -> Configs:
    paths = {
        "project": config_dir / "project.yaml",
        "datasets": config_dir / "datasets.yaml",
        "indices": config_dir / "indices.yaml",
        "preprocessing": config_dir / "preprocessing.yaml",
    }
    cfgs = Configs(
        project=_validate(ProjectConfig, paths["project"]),
        datasets=_validate(DatasetRegistry, paths["datasets"]),
        indices=_validate(IndicesConfig, paths["indices"]),
        preprocessing=_validate(PreprocessingConfig, paths["preprocessing"]),
        sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.values()},
    )
    _cross_check(cfgs)
    return cfgs


def _cross_check(cfgs: Configs) -> None:
    """References between config files must resolve."""
    ds, pp, idx = cfgs.datasets.datasets, cfgs.preprocessing, cfgs.indices
    errors = []
    for key, sensor in pp.landsat.members.items():
        if key not in ds:
            errors.append(f"preprocessing.landsat.members: unknown dataset {key!r}")
        if sensor not in idx.sensors:
            errors.append(f"preprocessing.landsat.members: unknown index sensor {sensor!r}")
    for key in (
        pp.sentinel2.dataset,
        pp.sentinel2.cloud_score_plus.dataset,
        pp.sentinel1.dataset,
        *pp.inventory.required_datasets,
    ):
        if key not in ds:
            errors.append(f"preprocessing references unknown dataset {key!r}")
    if pp.sentinel2.index_sensor not in idx.sensors:
        errors.append(f"unknown index sensor {pp.sentinel2.index_sensor!r}")
    if pp.preview.season not in cfgs.project.seasons:
        errors.append(f"preview.season {pp.preview.season!r} is not a configured season")
    for key, sensor in [
        *pp.landsat.members.items(),
        (pp.sentinel2.dataset, pp.sentinel2.index_sensor),
    ]:
        if key in ds and sensor in idx.sensors:
            missing = set(idx.sensors[sensor].bands.values()) - set(ds[key].required_bands)
            if missing:
                errors.append(f"datasets.{key}.required_bands lacks index bands {sorted(missing)}")
    if errors:
        raise ConfigError("configuration cross-check failed:\n" + "\n".join(errors))
