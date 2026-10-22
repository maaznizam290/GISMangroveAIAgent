"""Annual mangrove metrics and trend tests.

Mann-Kendall (no ties correction beyond scipy's tau-b) and Sen's slope via scipy. A trend is
reported only when the series meets the completeness rules in configs/layers.yaml; otherwise
the reason is reported instead of a number.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau, theilslopes

from indus_delta.config import Configs
from indus_delta.layer_io import read_layer


def annual_metrics(cfgs: Configs, out_root: Path, aoi_area_km2: float) -> pd.DataFrame:
    """Mangrove area and cover for every classified epoch (validated or not, flagged)."""
    rows = []
    for gate_path in sorted((out_root / "m4").glob("*_*/validation_gate.json")):
        gate = json.loads(gate_path.read_text())
        bands, grid, _ = read_layer(gate_path.parent / "landcover.tif")
        lc = bands["landcover_class"]
        code = cfgs.classification.code_of("mangrove")
        valid = np.isfinite(lc)
        px_km2 = grid.pixel_area_m2 / 1e6
        area = float((lc == code).sum() * px_km2)
        rows.append(
            {
                "series": gate["series"],
                "label_year": gate["label_year"],
                "mangrove_area_km2": area,
                "mapped_area_km2": float(valid.sum() * px_km2),
                "mangrove_cover_pct_of_mapped": 100 * area / float(valid.sum() * px_km2)
                if valid.any()
                else np.nan,
                "aoi_area_km2": aoi_area_km2,
                "validation_status": gate["status"],
                "overall_accuracy": gate.get("overall_accuracy"),
            }
        )
    return (
        pd.DataFrame(rows).sort_values(["series", "label_year"])
        if rows
        else pd.DataFrame(
            columns=[
                "series",
                "label_year",
                "mangrove_area_km2",
                "mapped_area_km2",
                "mangrove_cover_pct_of_mapped",
                "aoi_area_km2",
                "validation_status",
                "overall_accuracy",
            ]
        )
    )


@dataclass
class TrendResult:
    series: str
    variable: str
    status: str  # computed / insufficient
    reason: str
    n_years: int
    first_year: int | None
    last_year: int | None
    tau: float | None = None
    p_value: float | None = None
    sen_slope_per_year: float | None = None
    sen_slope_ci_low: float | None = None
    sen_slope_ci_high: float | None = None


def trend(
    years: np.ndarray, values: np.ndarray, cfgs: Configs, series: str, variable: str
) -> TrendResult:
    tc = cfgs.layers.trends
    ok = np.isfinite(values)
    years, values = np.asarray(years)[ok], np.asarray(values)[ok]
    if years.size == 0:
        return TrendResult(series, variable, "insufficient", "no values", 0, None, None)
    span = int(years.max() - years.min() + 1)
    missing = 1 - years.size / span
    base = dict(
        series=series,
        variable=variable,
        n_years=int(years.size),
        first_year=int(years.min()),
        last_year=int(years.max()),
    )
    if years.size < tc.min_years:
        return TrendResult(
            status="insufficient", reason=f"{years.size} years < {tc.min_years}", **base
        )
    if missing > tc.max_missing_fraction:
        return TrendResult(
            status="insufficient",
            reason=f"{missing:.0%} of years missing > {tc.max_missing_fraction:.0%}",
            **base,
        )
    tau, p = kendalltau(years, values)
    conf = 1 - tc.alpha
    slope, _, lo, hi = theilslopes(values, years, alpha=conf)
    return TrendResult(
        status="computed",
        reason="",
        tau=float(tau),
        p_value=float(p),
        sen_slope_per_year=float(slope),
        sen_slope_ci_low=float(lo),
        sen_slope_ci_high=float(hi),
        **base,
    )


def trend_table(metrics: pd.DataFrame, cfgs: Configs) -> pd.DataFrame:
    """Trends per series, validated epochs only. Landsat and Sentinel are never pooled."""
    out = []
    for series, grp in metrics[metrics["validation_status"] == "PASS"].groupby("series"):
        out.append(
            trend(
                grp["label_year"].to_numpy(),
                grp["mangrove_area_km2"].to_numpy(),
                cfgs,
                series,
                "mangrove_area_km2",
            ).__dict__
        )
    return pd.DataFrame(out)
