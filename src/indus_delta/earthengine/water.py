"""Per-image water detection and annual water frequency (Earth Engine)."""

from __future__ import annotations

from datetime import date

import ee

from indus_delta.config import Configs
from indus_delta.earthengine import prep
from indus_delta.earthengine.composite import ee_index


def landsat_water_frequency(cfgs: Configs, region: ee.Geometry, year: int) -> ee.Image:
    """water_frequency = images with index > threshold / valid images, per pixel, in the
    calendar year; n_valid = valid images. Threshold from configs/layers.yaml."""
    ti = cfgs.layers.tidal_inundation
    if ti.optical_threshold is None:
        raise ValueError("tidal_inundation.optical_threshold is not calibrated")
    start, end = date(year, 1, 1), date(year, 12, 31)
    cols = []
    for key, entry in cfgs.datasets.datasets.items():
        if key not in cfgs.preprocessing.landsat.members:
            continue
        s, e = entry.requested_window(end)
        s, e = max(s, start), min(e, end)
        if s <= e:
            cols.append(
                prep.landsat_prepared(cfgs, key, region, s, e, apply_scene_cloud_filter=False)
            )
    if not cols:
        raise ValueError(f"no Landsat data for {year}")
    col = cols[0]
    for c in cols[1:]:
        col = col.merge(c)

    def detect(img):
        idx = ee_index(img, ti.optical_index, cfgs.indices)
        return idx.gt(ti.optical_threshold).rename("water").updateMask(idx.mask())

    water = col.map(detect)
    n_valid = water.count().rename("n_valid")
    freq = water.sum().divide(n_valid).rename("water_frequency")
    return freq.addBands(n_valid)
