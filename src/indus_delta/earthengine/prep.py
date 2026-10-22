"""Per-image preparation: filtering, cloud/no-data masking, reflectance scaling, renaming
bands to roles. Mirrors indus_delta.spectral (the NumPy reference)."""

from __future__ import annotations

from datetime import date, timedelta

import ee

from indus_delta.config import Configs
from indus_delta.spectral import bits_to_mask_value, saturation_bits


def _end_exclusive(end: date) -> str:
    return (end + timedelta(days=1)).isoformat()


def _in_range(refl: ee.Image, cfgs: Configs) -> ee.Image:
    vr = cfgs.indices.valid_reflectance
    return refl.gte(vr.min).And(refl.lte(vr.max)).reduce(ee.Reducer.min())


def landsat_raw(cfgs: Configs, key: str, region: ee.Geometry, start: date, end: date):
    ds = cfgs.datasets.datasets[key]
    return (
        ee.ImageCollection(ds.ee_id)
        .filterBounds(region)
        .filterDate(start.isoformat(), _end_exclusive(end))
    )


def landsat_valid_and_reflectance(cfgs: Configs, key: str):
    """Returns f(img) -> (valid 0/1 image, role-named reflectance image)."""
    pp = cfgs.preprocessing
    ds = cfgs.datasets.datasets[key]
    sensor = pp.landsat.members[key]
    role_bands = cfgs.indices.sensors[sensor].bands
    roles, src = list(role_bands), list(role_bands.values())
    qa_value = bits_to_mask_value(pp.landsat.mask_bits_for(sensor))
    sat_value = bits_to_mask_value(saturation_bits(src))

    def f(img: ee.Image):
        clear = img.select("QA_PIXEL").bitwiseAnd(qa_value).eq(0)
        if pp.landsat.mask_saturated_bands:
            clear = clear.And(img.select("QA_RADSAT").bitwiseAnd(sat_value).eq(0))
        refl = img.select(src, roles).multiply(ds.reflectance_scale).add(ds.reflectance_offset)
        valid = clear.And(_in_range(refl, cfgs)).rename("valid")
        return valid, refl

    return f


def landsat_prepared(
    cfgs: Configs,
    key: str,
    region: ee.Geometry,
    start: date,
    end: date,
    apply_scene_cloud_filter: bool = True,
) -> ee.ImageCollection:
    pp = cfgs.preprocessing
    if key == "landsat7_l2":
        end = min(end, pp.composites.landsat7_primary_end)
    col = landsat_raw(cfgs, key, region, start, end)
    if apply_scene_cloud_filter:
        col = col.filter(ee.Filter.lte("CLOUD_COVER", pp.landsat.max_scene_cloud_cover_pct))
    vr = landsat_valid_and_reflectance(cfgs, key)

    def prep(img):
        valid, refl = vr(img)
        return (
            refl.updateMask(valid)
            .copyProperties(img, ["system:time_start", "system:index", "CLOUD_COVER"])
            .set({"dataset": key})
        )

    return col.map(prep)


def s2_raw(cfgs: Configs, region: ee.Geometry, start: date, end: date) -> ee.ImageCollection:
    s2 = cfgs.preprocessing.sentinel2
    col = (
        ee.ImageCollection(cfgs.datasets.datasets[s2.dataset].ee_id)
        .filterBounds(region)
        .filterDate(start.isoformat(), _end_exclusive(end))
    )
    if s2.cloud_score_plus.enabled:
        cs_id = cfgs.datasets.datasets[s2.cloud_score_plus.dataset].ee_id
        # Unmatched images get a fully masked score band, i.e. they end up fully masked.
        col = col.linkCollection(ee.ImageCollection(cs_id), [s2.cloud_score_plus.band])
    return col


def s2_valid_and_reflectance(cfgs: Configs):
    s2 = cfgs.preprocessing.sentinel2
    ds = cfgs.datasets.datasets[s2.dataset]
    role_bands = cfgs.indices.sensors[s2.index_sensor].bands
    roles, src = list(role_bands), list(role_bands.values())

    def f(img: ee.Image):
        scl = img.select(s2.scl_band)
        ok = scl.neq(s2.scl_mask_nodata_value)
        for c in s2.scl_mask_classes:
            ok = ok.And(scl.neq(c.value))
        if s2.cloud_score_plus.enabled:
            ok = ok.And(img.select(s2.cloud_score_plus.band).gte(s2.cloud_score_plus.min_score))
        refl = img.select(src, roles).multiply(ds.reflectance_scale).add(ds.reflectance_offset or 0)
        valid = ok.And(_in_range(refl, cfgs)).rename("valid")
        return valid, refl

    return f


def s2_prepared(
    cfgs: Configs,
    region: ee.Geometry,
    start: date,
    end: date,
    apply_scene_cloud_filter: bool = True,
) -> ee.ImageCollection:
    s2 = cfgs.preprocessing.sentinel2
    col = s2_raw(cfgs, region, start, end)
    if apply_scene_cloud_filter:
        col = col.filter(ee.Filter.lte("CLOUDY_PIXEL_PERCENTAGE", s2.max_scene_cloud_pct))
    vr = s2_valid_and_reflectance(cfgs)

    def prep(img):
        valid, refl = vr(img)
        return (
            refl.updateMask(valid)
            .copyProperties(img, ["system:time_start", "system:index"])
            .set({"dataset": s2.dataset})
        )

    return col.map(prep)


def s1_raw(cfgs: Configs, region: ee.Geometry, start: date, end: date) -> ee.ImageCollection:
    """All scenes in the configured instrument mode; compatibility is judged per scene."""
    s1 = cfgs.preprocessing.sentinel1
    return (
        ee.ImageCollection(cfgs.datasets.datasets[s1.dataset].ee_id)
        .filterBounds(region)
        .filterDate(start.isoformat(), _end_exclusive(end))
        .filter(ee.Filter.eq("instrumentMode", s1.instrument_mode))
    )


def s1_prepared(
    cfgs: Configs, region: ee.Geometry, start: date, end: date, orbit_pass: str | None
) -> ee.ImageCollection:
    s1 = cfgs.preprocessing.sentinel1
    col = s1_raw(cfgs, region, start, end).filter(
        ee.Filter.eq("resolution_meters", s1.resolution_meters)
    )
    for pol in s1.polarisations:
        col = col.filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
    if orbit_pass:
        col = col.filter(ee.Filter.eq("orbitProperties_pass", orbit_pass))
    return col.select(s1.polarisations)
