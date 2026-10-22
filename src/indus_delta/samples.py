"""Reference and validation samples, and field water-salinity measurements.

Samples are operator-supplied. Nothing here creates or modifies sample labels.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

from indus_delta.checks import Check
from indus_delta.config import Configs


class SamplesUnavailable(FileNotFoundError):
    pass


def load_samples(
    path: Path, cfgs: Configs, aoi: gpd.GeoDataFrame, role: str
) -> tuple[gpd.GeoDataFrame, list[Check]]:
    """Load and validate a sample file. Invalid rows raise; rows outside the AOI are dropped
    and reported."""
    cl = cfgs.classification
    if not path.is_file():
        raise SamplesUnavailable(
            f"{role} samples not found at {path}. Reference samples must be supplied by the "
            "operator (field survey or documented high-resolution interpretation)."
        )
    gdf = gpd.read_file(path)
    checks: list[Check] = []
    if gdf.crs is None:
        raise ValueError(f"{path} has no CRS")
    missing = [f for f in cl.samples.required_fields if f not in gdf.columns]
    if missing:
        raise ValueError(f"{path} lacks required fields {missing}")
    if not (gdf.geometry.geom_type == "Point").all():
        raise ValueError(f"{path}: samples must be Point geometries")
    if gdf["sample_id"].duplicated().any():
        dup = gdf.loc[gdf["sample_id"].duplicated(), "sample_id"].tolist()[:5]
        raise ValueError(f"{path}: duplicate sample_id values, e.g. {dup}")
    bad_class = ~gdf["class_code"].isin(cl.trainable_codes())
    if bad_class.any():
        raise ValueError(
            f"{path}: class_code must be one of {cl.trainable_codes()} "
            f"(class {cl.nodata_class} is not a reference class); "
            f"offending sample_ids {gdf.loc[bad_class, 'sample_id'].tolist()[:5]}"
        )
    bad_source = ~gdf["source"].isin(cl.samples.allowed_sources)
    if bad_source.any():
        raise ValueError(f"{path}: source must be one of {cl.samples.allowed_sources}")
    gdf = gdf.to_crs(cfgs.project.crs.analysis_epsg)
    gdf["class_code"] = gdf["class_code"].astype(int)
    gdf["label_year"] = gdf["label_year"].astype(int)
    conflicts = (
        gdf.assign(x=gdf.geometry.x.round(1), y=gdf.geometry.y.round(1))
        .groupby(["x", "y", "label_year"])["class_code"]
        .nunique()
    )
    if (conflicts > 1).any():
        raise ValueError(f"{path}: same location and year labelled with different classes")
    inside = gdf.within(aoi.union_all())
    if (~inside).any():
        checks.append(
            Check(
                f"{role}_outside_aoi",
                "WARN",
                f"{int((~inside).sum())} samples outside the AOI were dropped",
            )
        )
    gdf = gdf[inside].copy()
    checks.append(Check(f"{role}_samples_loaded", "PASS", f"{len(gdf)} samples from {path}"))
    return gdf, checks


def assign_blocks(gdf: gpd.GeoDataFrame, block_size: float) -> pd.Series:
    bx = np.floor(gdf.geometry.x / block_size).astype(int)
    by = np.floor(gdf.geometry.y / block_size).astype(int)
    return pd.Series([f"{a}_{b}" for a, b in zip(bx, by, strict=True)], index=gdf.index)


def holdout_blocks(
    gdf: gpd.GeoDataFrame, cfgs: Configs
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """Hold out whole spatial blocks until holdout_fraction of the samples is reached."""
    sp = cfgs.classification.split
    blocks = assign_blocks(gdf, sp.block_size_m)
    order = np.random.default_rng(sp.random_state).permutation(sorted(blocks.unique()))
    target = sp.holdout_fraction * len(gdf)
    held: set[str] = set()
    count = 0
    for b in order:
        if count >= target:
            break
        held.add(b)
        count += int((blocks == b).sum())
    is_val = blocks.isin(held)
    return gdf[~is_val].copy(), gdf[is_val].copy()


def enforce_separation(
    train: gpd.GeoDataFrame, val: gpd.GeoDataFrame, min_distance: float
) -> tuple[gpd.GeoDataFrame, Check]:
    """Drop training samples within min_distance of any validation sample."""
    if train.empty or val.empty:
        return train, Check(
            "train_validation_separation", "FAIL", "training or validation set is empty"
        )
    tree = cKDTree(np.c_[val.geometry.x, val.geometry.y])
    dist, _ = tree.query(np.c_[train.geometry.x, train.geometry.y])
    keep = dist >= min_distance
    kept = train[keep].copy()
    if kept.empty:
        return kept, Check(
            "train_validation_separation",
            "FAIL",
            f"no training sample is at least {min_distance:g} m from validation",
        )
    min_after = float(dist[keep].min())
    return kept, Check(
        "train_validation_separation",
        "PASS",
        f"dropped {int((~keep).sum())} training samples within {min_distance:g} m of a "
        f"validation sample; minimum remaining distance {min_after:.0f} m",
    )


def class_counts(gdf: gpd.GeoDataFrame, cfgs: Configs) -> dict[str, int]:
    cl = cfgs.classification
    counts = gdf["class_code"].value_counts()
    return {cl.name_of(c): int(counts.get(c, 0)) for c in cl.trainable_codes()}


# --------------------------------------------------------------------------- field salinity


def load_field_salinity(path: Path, cfgs: Configs) -> gpd.GeoDataFrame:
    """Measured creek-water salinity / EC. Units are kept as supplied: converting EC to
    salinity needs temperature and is not done here."""
    fc = cfgs.layers.water_salinity_field
    if not path.is_file():
        raise SamplesUnavailable(f"no field water-salinity data at {path}")
    df = pd.read_csv(path)
    missing = [c for c in fc.required_columns if c not in df.columns]
    if missing:
        raise ValueError(f"{path} lacks columns {missing}")
    bad_units = ~df["units"].isin(fc.allowed_units)
    if bad_units.any():
        raise ValueError(f"{path}: units must be one of {fc.allowed_units}")
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], utc=True, errors="raise")
    if df[["longitude", "latitude", "value"]].isna().any().any():
        raise ValueError(f"{path}: longitude, latitude and value are required in every row")
    gdf = gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df.longitude, df.latitude), crs=4326)
    gdf["layer_type"] = "measured"
    return gdf.to_crs(cfgs.project.crs.analysis_epsg)
