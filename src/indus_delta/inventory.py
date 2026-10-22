"""Image inventory: per-image records -> season assignment, summaries, missing observations.

The per-image records come from Earth Engine (`indus_delta.earthengine.inventory_ee`). This
module is pure Python so the bookkeeping can be tested without Earth Engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

import pandas as pd

from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.seasons import assign_season, windows_for_years

RECORD_COLUMNS = [
    "dataset",
    "series",
    "sensor",
    "image_id",
    "acquired_utc",
    "date",
    "season",
    "label_year",
    "scene_cloud_pct",
    "valid_fraction",
    "compatible",
    "usable",
    "in_primary_series",
    "tile",
    "orbit_pass",
    "relative_orbit",
    "polarisations",
    "resolution_m",
    "tide_status",
]


class InventoryError(RuntimeError):
    """Required data are unavailable; raised after the inventory files are written."""


def series_of(dataset: str, cfgs: Configs) -> str:
    pp = cfgs.preprocessing
    if dataset in pp.landsat.members:
        return "landsat"
    if dataset == pp.sentinel2.dataset:
        return "sentinel2"
    if dataset == pp.sentinel1.dataset:
        return "sentinel1"
    return dataset


def build_records(raw: list[dict], cfgs: Configs) -> pd.DataFrame:
    """Normalise raw per-image dicts and attach season, usability and series flags.

    Expected raw keys: dataset, image_id, acquired_utc (ISO string), and any of
    scene_cloud_pct, valid_fraction, tile, orbit_pass, relative_orbit, polarisations,
    resolution_m, sensor.
    """
    pp = cfgs.preprocessing
    rows = []
    for r in raw:
        acquired = pd.Timestamp(r["acquired_utc"])
        acquired = acquired.tz_localize("UTC") if acquired.tzinfo is None else acquired
        d = acquired.date()
        season = assign_season(d, cfgs.project.seasons)
        valid = r.get("valid_fraction")
        compatible = s1_compatible(r, cfgs) if r["dataset"] == pp.sentinel1.dataset else True
        primary = True
        if r["dataset"] == "landsat7_l2" and d > pp.composites.landsat7_primary_end:
            primary = False
        rows.append(
            {
                "dataset": r["dataset"],
                "series": series_of(r["dataset"], cfgs),
                "sensor": r.get("sensor") or cfgs.datasets.datasets[r["dataset"]].sensor,
                "image_id": r["image_id"],
                "acquired_utc": acquired.isoformat(),
                "date": d.isoformat(),
                "season": season[0] if season else None,
                "label_year": season[1] if season else None,
                "scene_cloud_pct": r.get("scene_cloud_pct"),
                "valid_fraction": valid,
                "compatible": compatible,
                "usable": bool(
                    compatible
                    and valid is not None
                    and valid >= pp.inventory.min_usable_valid_fraction
                ),
                "in_primary_series": primary,
                "tile": r.get("tile"),
                "orbit_pass": r.get("orbit_pass"),
                "relative_orbit": r.get("relative_orbit"),
                "polarisations": r.get("polarisations"),
                "resolution_m": r.get("resolution_m"),
                "tide_status": "unavailable" if pp.tide.provider == "none" else "pending",
            }
        )
    df = pd.DataFrame(rows, columns=RECORD_COLUMNS)
    return df.sort_values(["series", "acquired_utc", "dataset"]).reset_index(drop=True)


def s1_compatible(r: dict, cfgs: Configs) -> bool:
    """Scene has every configured polarisation, the configured pixel spacing and (if fixed)
    the configured pass."""
    s1 = cfgs.preprocessing.sentinel1
    pols = set((r.get("polarisations") or "").split("+"))
    if not set(s1.polarisations) <= pols:
        return False
    if r.get("resolution_m") is None or float(r["resolution_m"]) != s1.resolution_meters:
        return False
    return not (s1.orbit_pass and r.get("orbit_pass") != s1.orbit_pass)


def s1_orbit_summary(records: pd.DataFrame) -> pd.DataFrame:
    """Acquisition counts by pass, relative orbit and year (documents density changes)."""
    s1 = records[records["series"] == "sentinel1"].copy()
    if s1.empty:
        return pd.DataFrame(
            columns=["orbit_pass", "relative_orbit", "year", "n_scenes", "n_compatible", "n_usable"]
        )
    s1["year"] = s1["date"].str[:4].astype(int)
    return (
        s1.groupby(["orbit_pass", "relative_orbit", "year"], dropna=False)
        .agg(
            n_scenes=("image_id", "size"),
            n_compatible=("compatible", "sum"),
            n_usable=("usable", "sum"),
        )
        .reset_index()
    )


@dataclass(frozen=True)
class SeriesSpec:
    series: str
    start_year: int
    end_year: int


def series_specs(cfgs: Configs) -> list[SeriesSpec]:
    p = cfgs.project.periods
    return [
        SeriesSpec("landsat", p.landsat.start_year, p.landsat.end_year),
        SeriesSpec("sentinel2", p.sentinel.start_year, p.sentinel.end_year),
        SeriesSpec("sentinel1", p.sentinel.start_year, p.sentinel.end_year),
    ]


def summarise(records: pd.DataFrame, cfgs: Configs, data_end: dict[str, date]) -> pd.DataFrame:
    """One row per series x season x label year, including combinations with no images.

    data_end maps series -> last date with data available (latest acquisition in the
    inventory, or the request end); it decides complete/partial/not_started.
    """
    primary = records[records["in_primary_series"]]
    rows = []
    for spec in series_specs(cfgs):
        sub = primary[primary["series"] == spec.series]
        end = data_end.get(spec.series)
        for w in windows_for_years(cfgs.project.seasons, spec.start_year, spec.end_year):
            win = sub[(sub["season"] == w.season) & (sub["label_year"] == w.label_year)]
            usable = win[win["usable"]]
            rows.append(
                {
                    "series": spec.series,
                    "season": w.season,
                    "label_year": w.label_year,
                    "window_start": w.start.isoformat(),
                    "window_end_exclusive": w.end.isoformat(),
                    "completeness": w.completeness(end) if end else "unknown",
                    "data_end": end.isoformat() if end else None,
                    "n_images": len(win),
                    "n_usable": len(usable),
                    "median_valid_fraction": (
                        float(win["valid_fraction"].median())
                        if win["valid_fraction"].notna().any()
                        else None
                    ),
                    "first_date": win["date"].min() if len(win) else None,
                    "last_date": win["date"].max() if len(win) else None,
                    "sensors": ";".join(sorted(win["dataset"].unique())) if len(win) else "",
                }
            )
    return pd.DataFrame(rows)


def missing_observations(summary: pd.DataFrame) -> pd.DataFrame:
    """Season-years without usable observations, or with an incomplete window."""
    out = []
    for r in summary.itertuples(index=False):
        if r.completeness == "not_started":
            reasons = ["season window has not started"]
        else:
            reasons = []
            if r.n_images == 0:
                reasons.append("no images in window")
            elif r.n_usable == 0:
                reasons.append("images present but none usable (valid fraction below threshold)")
            if r.completeness == "partial":
                reasons.append(f"partial season: data end {r.data_end} before window end")
        if not reasons:
            continue
        out.append(
            {
                "series": r.series,
                "season": r.season,
                "label_year": r.label_year,
                "n_images": r.n_images,
                "n_usable": r.n_usable,
                "reason": "; ".join(reasons),
            }
        )
    return pd.DataFrame(
        out, columns=["series", "season", "label_year", "n_images", "n_usable", "reason"]
    )


def inventory_checks(records: pd.DataFrame, summary: pd.DataFrame, cfgs: Configs) -> list[Check]:
    checks = []
    for key in cfgs.preprocessing.inventory.required_datasets:
        n = int((records["dataset"] == key).sum())
        checks.append(
            Check(
                f"images_{key}",
                "PASS" if n else "FAIL",
                f"{n} images over the inventory region in the requested window",
            )
        )
    for series, grp in summary.groupby("series"):
        started = grp[grp["completeness"] != "not_started"]
        empty = started[started["n_usable"] == 0]
        checks.append(
            Check(
                f"coverage_{series}",
                "PASS" if empty.empty else "WARN",
                f"{len(started) - len(empty)}/{len(started)} started season-years have usable "
                f"images"
                + (
                    "; none usable: "
                    + ", ".join(f"{r.season} {r.label_year}" for r in empty.itertuples())
                    if not empty.empty
                    else ""
                ),
            )
        )
    return checks
