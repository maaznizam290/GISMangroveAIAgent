"""Seasonal composites and spectral indices in Earth Engine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import ee

from indus_delta.config import (
    Configs,
    DifferenceOfIndices,
    IndicesConfig,
    NormalizedDifference,
    RatioOfDifferences,
)
from indus_delta.earthengine import prep
from indus_delta.seasons import SeasonWindow

ROLE_ORDER = ["blue", "green", "red", "nir", "swir1", "swir2"]


def ee_index(img: ee.Image, name: str, cfg: IndicesConfig) -> ee.Image:
    """Same formulas and denominator guard as indus_delta.spectral.compute_index."""
    idx = cfg.indices[name]
    eps = cfg.min_abs_denominator
    if isinstance(idx, DifferenceOfIndices):
        return (
            ee_index(img, idx.minuend, cfg)
            .subtract(ee_index(img, idx.subtrahend, cfg))
            .rename(name)
        )
    if isinstance(idx, NormalizedDifference):
        a, b = img.select(idx.a), img.select(idx.b)
        num, den = a.subtract(b), a.add(b)
    elif isinstance(idx, RatioOfDifferences):
        (n1, n2), (d1, d2) = idx.numerator, idx.denominator
        num = img.select(n1).subtract(img.select(n2))
        den = img.select(d1).subtract(img.select(d2))
    else:
        raise TypeError(name)
    return num.divide(den).updateMask(den.abs().gte(eps)).rename(name)


def optical_composite(col: ee.ImageCollection, cfgs: Configs) -> ee.Image:
    """Median reflectance per role, indices from the median, and a valid-observation count."""
    med = col.select(ROLE_ORDER).median()
    out = med
    for name in cfgs.indices.indices:
        out = out.addBands(ee_index(med, name, cfgs.indices))
    count = col.select("nir").count().rename("valid_obs")
    return out.addBands(count)


def optical_band_names(cfgs: Configs) -> list[str]:
    return [*ROLE_ORDER, *cfgs.indices.indices, "valid_obs"]


def landsat_window_collection(cfgs: Configs, region: ee.Geometry, w: SeasonWindow):
    end = w.end - timedelta(days=1)
    cols = []
    for key, entry in cfgs.datasets.datasets.items():
        if key not in cfgs.preprocessing.landsat.members:
            continue
        s, e = entry.requested_window(end)
        s, e = max(s, w.start), min(e, end)
        if s <= e:
            cols.append(prep.landsat_prepared(cfgs, key, region, s, e))
    if not cols:
        return ee.ImageCollection([])
    merged = cols[0]
    for c in cols[1:]:
        merged = merged.merge(c)
    return merged


def s2_window_collection(cfgs: Configs, region: ee.Geometry, w: SeasonWindow):
    return prep.s2_prepared(cfgs, region, w.start, w.end - timedelta(days=1))


def s1_composite(col: ee.ImageCollection, cfgs: Configs) -> ee.Image:
    pols = cfgs.preprocessing.sentinel1.polarisations
    med = col.select(pols).median()
    return med.addBands(col.select(pols[0]).count().rename("valid_obs"))


def s1_band_names(cfgs: Configs) -> list[str]:
    return [*cfgs.preprocessing.sentinel1.polarisations, "valid_obs"]


def collection_summary(col: ee.ImageCollection) -> dict:
    """Client-side metadata of the images that went into a composite."""
    ids = col.aggregate_array("system:index").getInfo()
    datasets = col.aggregate_array("dataset").getInfo() if ids else []
    times = col.aggregate_array("system:time_start").getInfo() if ids else []
    dates = sorted(datetime.fromtimestamp(t / 1000, UTC).date().isoformat() for t in times)
    return {
        "n_images": len(ids),
        "image_ids": ids,
        "datasets": sorted(set(datasets)),
        "first_date": dates[0] if dates else None,
        "last_date": dates[-1] if dates else None,
    }
