"""Collect per-image inventory records from Earth Engine.

For every image over the inventory region the valid fraction (share of region pixels that
survive cloud/shadow/no-data masking) is computed server-side. Requests are split by
dataset and calendar year to stay within getInfo limits.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

import ee

from indus_delta.config import Configs
from indus_delta.earthengine import prep
from indus_delta.earthengine.util import with_retries

log = logging.getLogger(__name__)


def _year_chunks(start: date, end: date):
    for year in range(start.year, end.year + 1):
        yield max(start, date(year, 1, 1)), min(end, date(year, 12, 31))


def _valid_fraction(valid: ee.Image, region: ee.Geometry, scale: float, crs: str):
    return (
        valid.unmask(0)
        .reduceRegion(
            reducer=ee.Reducer.mean(), geometry=region, scale=scale, crs=crs, maxPixels=1e9
        )
        .get("valid")
    )


def _landsat_features(cfgs: Configs, key: str, region, start, end, scale, crs):
    vr = prep.landsat_valid_and_reflectance(cfgs, key)

    def to_feature(img):
        valid, _ = vr(img)
        return ee.Feature(
            None,
            {
                "image_id": img.get("system:index"),
                "time_start": img.get("system:time_start"),
                "sensor": img.get("SPACECRAFT_ID"),
                "scene_cloud_pct": img.get("CLOUD_COVER"),
                "wrs_path": img.get("WRS_PATH"),
                "wrs_row": img.get("WRS_ROW"),
                "valid_fraction": _valid_fraction(valid, region, scale, crs),
            },
        )

    return ee.FeatureCollection(prep.landsat_raw(cfgs, key, region, start, end).map(to_feature))


def _s2_features(cfgs: Configs, region, start, end, scale, crs):
    vr = prep.s2_valid_and_reflectance(cfgs)

    def to_feature(img):
        valid, _ = vr(img)
        return ee.Feature(
            None,
            {
                "image_id": img.get("system:index"),
                "time_start": img.get("system:time_start"),
                "sensor": img.get("SPACECRAFT_NAME"),
                "scene_cloud_pct": img.get("CLOUDY_PIXEL_PERCENTAGE"),
                "tile": img.get("MGRS_TILE"),
                "valid_fraction": _valid_fraction(valid, region, scale, crs),
            },
        )

    return ee.FeatureCollection(prep.s2_raw(cfgs, region, start, end).map(to_feature))


def _s1_features(cfgs: Configs, region, start, end, scale, crs):
    pol0 = cfgs.preprocessing.sentinel1.polarisations[0]

    def to_feature(img):
        # Coverage of the region by the first configured polarisation (no clouds in SAR).
        has = img.bandNames().contains(pol0)
        valid = ee.Image(
            ee.Algorithms.If(
                has, img.select([pol0]).mask().rename("valid"), ee.Image(0).rename("valid")
            )
        )
        return ee.Feature(
            None,
            {
                "image_id": img.get("system:index"),
                "time_start": img.get("system:time_start"),
                "sensor": img.get("platform_number"),
                "orbit_pass": img.get("orbitProperties_pass"),
                "relative_orbit": img.get("relativeOrbitNumber_start"),
                "polarisations": img.get("transmitterReceiverPolarisation"),
                "resolution_m": img.get("resolution_meters"),
                "valid_fraction": _valid_fraction(valid, region, scale, crs),
            },
        )

    return ee.FeatureCollection(prep.s1_raw(cfgs, region, start, end).map(to_feature))


def collect_records(
    cfgs: Configs, region: ee.Geometry, today: date, datasets: list[str] | None = None
) -> tuple[list[dict], dict[str, str]]:
    """Raw records for indus_delta.inventory.build_records, plus per-dataset errors."""
    pp = cfgs.preprocessing
    scale = pp.inventory.valid_fraction_scale_m
    crs = f"EPSG:{cfgs.project.crs.analysis_epsg}"
    wanted = datasets or [*pp.landsat.members, pp.sentinel2.dataset, pp.sentinel1.dataset]
    records: list[dict] = []
    errors: dict[str, str] = {}
    for key in wanted:
        entry = cfgs.datasets.datasets[key]
        start, end = entry.requested_window(today)
        if start > end:
            errors[key] = f"empty request window {start}..{end}"
            continue
        for s, e in _year_chunks(start, end):
            if key in pp.landsat.members:
                fc = _landsat_features(cfgs, key, region, s, e, scale, crs)
            elif key == pp.sentinel2.dataset:
                fc = _s2_features(cfgs, region, s, e, scale, crs)
            elif key == pp.sentinel1.dataset:
                fc = _s1_features(cfgs, region, s, e, scale, crs)
            else:
                raise ValueError(f"no inventory rule for dataset {key}")
            log.info("inventory %s %s..%s", key, s, e)
            try:
                info = with_retries(lambda fc=fc: fc.getInfo(), f"inventory {key} {s.year}")
            except RuntimeError as exc:
                errors[f"{key}:{s.year}"] = str(exc)
                continue
            for feat in info.get("features", []):
                p = feat["properties"]
                rec = {
                    "dataset": key,
                    "image_id": p.get("image_id"),
                    "acquired_utc": datetime.fromtimestamp(p["time_start"] / 1000, UTC).isoformat(),
                    "sensor": p.get("sensor"),
                    "scene_cloud_pct": p.get("scene_cloud_pct"),
                    "valid_fraction": p.get("valid_fraction"),
                    "orbit_pass": p.get("orbit_pass"),
                    "relative_orbit": p.get("relative_orbit"),
                    "resolution_m": p.get("resolution_m"),
                }
                if p.get("wrs_path") is not None:
                    rec["tile"] = f"{int(p['wrs_path']):03d}/{int(p['wrs_row']):03d}"
                elif p.get("tile"):
                    rec["tile"] = p["tile"]
                if p.get("polarisations") is not None:
                    rec["polarisations"] = "+".join(p["polarisations"])
                if key == pp.sentinel1.dataset and rec["sensor"]:
                    rec["sensor"] = f"Sentinel-1{rec['sensor']}"  # platform_number "A"/"B"/"C"
                records.append(rec)
    return records, errors
