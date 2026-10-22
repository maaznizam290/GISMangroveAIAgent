"""Milestone M6: candidate plots, eligibility, ranking and Site A / Site B selection.

Refused unless (1) the M4 validation gate passed for the epoch and the current
classification configuration, (2) the operator confirmed the site-selection rules and (3)
the layers carry no circular evidence. If the evidence does not support two suitable sites,
the limitation is reported and no sites are written.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from rasterio.features import geometry_mask
from shapely.geometry import box

from indus_delta import aoi as aoi_mod
from indus_delta.aoi import write_layers
from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.gate import GateError
from indus_delta.layer_io import Grid, LayerMeta, read_layer
from indus_delta.manifest import write_manifest
from indus_delta.reporting import md_table

log = logging.getLogger(__name__)

# Inputs that must never contribute values to the salinity or freshwater evidence.
MANGROVE_DERIVED = ("landcover", "classification_uncertainty", "mangrove")


def make_plots(aoi: gpd.GeoDataFrame, size: float) -> gpd.GeoDataFrame:
    """Square plots aligned to multiples of `size` in the analysis CRS, fully inside the AOI."""
    minx, miny, maxx, maxy = aoi.total_bounds
    x0, y0 = math.floor(minx / size) * size, math.floor(miny / size) * size
    poly = aoi.union_all()
    cells = []
    for x in np.arange(x0, maxx, size):
        for y in np.arange(y0, maxy, size):
            cell = box(x, y, x + size, y + size)
            if poly.contains(cell):
                cells.append(cell)
    plots = gpd.GeoDataFrame(
        {"plot_id": [f"P{i:04d}" for i in range(len(cells))]}, geometry=cells, crs=aoi.crs
    )
    return plots


def check_independence(salinity: LayerMeta | None, freshwater: LayerMeta | None) -> list[Check]:
    checks = []
    for meta, label in ((salinity, "salinity"), (freshwater, "freshwater")):
        if meta is None:
            continue
        bad = [d for d in meta.derived_from if any(d.startswith(m) for m in MANGROVE_DERIVED)]
        checks.append(
            Check(
                f"{label}_evidence_independent_of_mangrove_map",
                "FAIL" if bad else "PASS",
                f"{meta.layer_name} values derived from {meta.derived_from}; "
                f"used as mask only: {meta.mask_from}"
                + (f"; circular inputs: {bad}" if bad else ""),
            )
        )
    return checks


def plot_metrics(
    plots: gpd.GeoDataFrame, grid: Grid, layers: dict[str, np.ndarray], cfgs: Configs
) -> pd.DataFrame:
    rows = []
    for plot in plots.itertuples():
        inside = ~geometry_mask([plot.geometry], (grid.height, grid.width), grid.transform)
        n = int(inside.sum())

        def vals(name, inside=inside):
            return layers[name][inside] if name in layers else np.array([])

        def mean(name):
            v = vals(name)
            v = v[np.isfinite(v)]
            return float(v.mean()) if v.size else np.nan

        ext = vals("mangrove_extent")
        valid = np.isfinite(ext)
        row = {
            "plot_id": plot.plot_id,
            "n_pixels": n,
            "valid_pixel_fraction": float(valid.mean()) if n else 0.0,
            "mangrove_cover": float(np.nanmean(ext)) if valid.any() else np.nan,
            "mangrove_probability_mean": mean("mangrove_probability"),
            "classification_margin_mean": mean("margin"),
        }
        vig = vals("spectral_vigour_class")
        in_m = np.isfinite(vig)
        row["high_vigour_fraction"] = float((vig[in_m] == 3).mean()) if in_m.any() else np.nan
        if "eligibility_code" in layers:
            code = vals("eligibility_code")
            row["eligible_bare_fraction"] = float((code == 0).mean()) if n else np.nan
            row["salinity_percentile_mean"] = mean("soil_salinity_proxy_percentile")
        if "water_frequency" in layers:
            row["inundation_frequency_mean"] = mean("water_frequency")
            row["n_valid_observations_mean"] = mean("n_valid_observations")
        if "distance_via_channel_km" in layers:
            d = vals("distance_via_channel_km")
            row["channel_distance_km_min"] = float(np.nanmin(d)) if np.isfinite(d).any() else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def _rank(series: pd.Series, higher_better: bool = True) -> pd.Series:
    r = series.rank(pct=True, method="average")
    return r if higher_better else 1 - r + 1 / max(len(series), 1)


def evaluate(metrics: pd.DataFrame, cfgs: Configs, have: set[str]) -> pd.DataFrame:
    """Eligibility (with exclusion reasons) and scores for Site A and Site B."""
    ss = cfgs.site_selection
    a, b = ss.site_a, ss.site_b
    df = metrics.copy()
    reasons_a, reasons_b = [], []
    for r in df.itertuples():
        ra, rb = [], []
        if r.valid_pixel_fraction < ss.min_valid_pixel_fraction:
            ra.append("too few valid pixels")
            rb.append("too few valid pixels")
        if "soil_salinity_proxy" not in have:
            ra.append("soil_salinity_proxy unavailable")
        else:
            if not r.mangrove_cover <= a.max_mangrove_cover:
                ra.append(f"mangrove cover {r.mangrove_cover:.2f} > {a.max_mangrove_cover}")
            if not r.eligible_bare_fraction >= a.min_eligible_bare_fraction:
                ra.append(
                    f"eligible bare fraction {r.eligible_bare_fraction:.2f} < "
                    f"{a.min_eligible_bare_fraction}"
                )
            if not r.salinity_percentile_mean >= a.min_salinity_percentile_mean:
                ra.append("salinity proxy below minimum or undefined")
        if not r.mangrove_cover >= b.min_mangrove_cover:
            rb.append(f"mangrove cover {r.mangrove_cover:.2f} < {b.min_mangrove_cover}")
        if not r.high_vigour_fraction >= b.min_high_vigour_fraction:
            rb.append("high-vigour fraction below minimum or undefined")
        if "freshwater_influence_proxy" not in have:
            rb.append("freshwater_influence_proxy unavailable (no documented source)")
        elif not r.channel_distance_km_min <= b.max_channel_distance_km:
            rb.append("not connected within the maximum channel distance")
        reasons_a.append("; ".join(ra))
        reasons_b.append("; ".join(rb))
    df["site_a_eligible"] = [not x for x in reasons_a]
    df["site_a_exclusion_reasons"] = reasons_a
    df["site_b_eligible"] = [not x for x in reasons_b]
    df["site_b_exclusion_reasons"] = reasons_b

    df["site_a_score"] = np.nan
    ea = df["site_a_eligible"]
    if ea.any():
        comp = {
            "salinity_percentile_mean": _rank(df.loc[ea, "salinity_percentile_mean"]),
            "eligible_bare_fraction": _rank(df.loc[ea, "eligible_bare_fraction"]),
            "low_uncertainty": _rank(df.loc[ea, "classification_margin_mean"]),
        }
        df.loc[ea, "site_a_score"] = sum(w * comp[k] for k, w in a.weights.items())
    df["site_b_score"] = np.nan
    eb = df["site_b_eligible"]
    if eb.any():
        comp = {
            "mangrove_cover": _rank(df.loc[eb, "mangrove_cover"]),
            "high_vigour_fraction": _rank(df.loc[eb, "high_vigour_fraction"]),
            "channel_proximity": _rank(df.loc[eb, "channel_distance_km_min"], False),
            "low_uncertainty": _rank(df.loc[eb, "classification_margin_mean"]),
        }
        df.loc[eb, "site_b_score"] = sum(w * comp[k] for k, w in b.weights.items())
    return df


def choose_pair(scored: pd.DataFrame, plots: gpd.GeoDataFrame, cfgs: Configs) -> dict:
    """Best A/B pair: highest summed score with sufficient separation, preferring similar
    inundation. Returns the pair (or None) and the notes explaining the choice."""
    cmp_ = cfgs.site_selection.comparability
    A = scored[scored["site_a_eligible"]].sort_values("site_a_score", ascending=False)
    B = scored[scored["site_b_eligible"]].sort_values("site_b_score", ascending=False)
    if A.empty or B.empty:
        missing = [n for n, d in (("Site A", A), ("Site B", B)) if d.empty]
        return {"pair": None, "notes": [f"no eligible candidate for {', '.join(missing)}"]}
    centres = plots.set_index("plot_id").geometry.centroid
    best, best_pref = None, None
    for ra in A.itertuples():
        for rb in B.itertuples():
            sep = centres[ra.plot_id].distance(centres[rb.plot_id]) / 1000
            if sep < cmp_.min_separation_km:
                continue
            score = ra.site_a_score + rb.site_b_score
            diff = abs(
                getattr(ra, "inundation_frequency_mean", np.nan)
                - getattr(rb, "inundation_frequency_mean", np.nan)
            )
            cand = (score, ra.plot_id, rb.plot_id, diff, sep)
            if best is None or score > best[0]:
                best = cand
            if (
                np.isfinite(diff)
                and diff <= cmp_.max_inundation_difference
                and (best_pref is None or score > best_pref[0])
            ):
                best_pref = cand
    if best is None:
        return {"pair": None, "notes": ["no A/B pair meets the minimum separation"]}
    chosen = best_pref or best
    notes = []
    if best_pref is None:
        notes.append(
            f"no pair within the preferred inundation difference "
            f"({cmp_.max_inundation_difference}); best pair differs by {chosen[3]:.2f}"
        )
    elif best_pref[0] < best[0]:
        notes.append(
            f"comparability preference applied: the highest-scoring pair (Site A {best[1]}, "
            f"Site B {best[2]}, combined score {best[0]:.3f}) differs in inundation frequency "
            f"by {best[3]:.2f}, above the preferred {cmp_.max_inundation_difference}; the "
            f"selected pair scores {best_pref[0]:.3f}. Review the alternatives before accepting"
        )
    return {
        "pair": {
            "site_a": chosen[1],
            "site_b": chosen[2],
            "combined_score": chosen[0],
            "inundation_difference": chosen[3],
            "separation_km": chosen[4],
        },
        "notes": notes,
    }


def criteria_table(cfgs: Configs) -> pd.DataFrame:
    """Every eligibility and comparability rule, with its threshold and confirmation state."""
    ss = cfgs.site_selection
    a, b, c = ss.site_a, ss.site_b, ss.comparability
    rows = [
        ("both", "eligibility", "valid_pixel_fraction", ">=", ss.min_valid_pixel_fraction),
        ("site_a", "eligibility", "mangrove_cover", "<=", a.max_mangrove_cover),
        ("site_a", "eligibility", "eligible_bare_fraction", ">=", a.min_eligible_bare_fraction),
        ("site_a", "eligibility", "salinity_percentile_mean", ">=", a.min_salinity_percentile_mean),
        ("site_b", "eligibility", "mangrove_cover", ">=", b.min_mangrove_cover),
        ("site_b", "eligibility", "high_vigour_fraction", ">=", b.min_high_vigour_fraction),
        ("site_b", "eligibility", "channel_distance_km_min", "<=", b.max_channel_distance_km),
        (
            "pair",
            "comparability (preferred)",
            "inundation_frequency_difference",
            "<=",
            c.max_inundation_difference,
        ),
        ("pair", "comparability (required)", "separation_km", ">=", c.min_separation_km),
    ]
    rows += [("site_a", "score weight", k, "=", v) for k, v in a.weights.items()]
    rows += [("site_b", "score weight", k, "=", v) for k, v in b.weights.items()]
    df = pd.DataFrame(rows, columns=["applies_to", "kind", "metric", "operator", "value"])
    df["plot_size_m"] = ss.plot_size_m
    df["operator_confirmed"] = ss.operator_confirmed
    return df


COMPARISON_METRICS = (
    "mangrove_cover",
    "salinity_percentile_mean",
    "eligible_bare_fraction",
    "high_vigour_fraction",
    "inundation_frequency_mean",
    "n_valid_observations_mean",
    "channel_distance_km_min",
    "classification_margin_mean",
    "valid_pixel_fraction",
)


def site_comparison(scored: pd.DataFrame, pair: dict | None, cfgs: Configs) -> pd.DataFrame:
    """Site A vs Site B side by side; differences are reported, not hidden."""
    if not pair:
        return pd.DataFrame(columns=["metric", "site_a", "site_b", "difference", "note"])
    a = scored.set_index("plot_id").loc[pair["site_a"]]
    b = scored.set_index("plot_id").loc[pair["site_b"]]
    lim = cfgs.site_selection.comparability.max_inundation_difference
    rows = []
    for m in COMPARISON_METRICS:
        va, vb = a.get(m, np.nan), b.get(m, np.nan)
        note = ""
        if m == "inundation_frequency_mean" and np.isfinite(va) and np.isfinite(vb):
            note = (
                "within preferred limit"
                if abs(va - vb) <= lim
                else f"exceeds preferred limit {lim}"
            )
        rows.append({"metric": m, "site_a": va, "site_b": vb, "difference": va - vb, "note": note})
    rows.append(
        {
            "metric": "separation_km",
            "site_a": np.nan,
            "site_b": np.nan,
            "difference": pair["separation_km"],
            "note": "centre-to-centre",
        }
    )
    return pd.DataFrame(rows)


def run_site_selection(
    cfgs: Configs, out_root: Path, series: str, year: int, command: str = "indus-delta select-sites"
) -> tuple[str, list[Check], Path]:
    from indus_delta.m4 import require_validation_pass

    if not cfgs.site_selection.operator_confirmed:
        raise GateError(
            "site_selection.operator_confirmed is false: confirm the eligibility "
            "rules and weights in configs/site_selection.yaml"
        )
    gate = require_validation_pass(cfgs, out_root, series, year)
    layer_dir = out_root / "m5" / f"{series}_{year}"
    m_bands, grid, _ = read_layer(layer_dir / "mangrove.tif")
    unc, _, _ = read_layer(out_root / "m4" / f"{series}_{year}" / "classification_uncertainty.tif")
    layers = {**m_bands, "margin": unc["margin"]}
    have = {"mangrove"}
    metas: dict[str, LayerMeta] = {}
    for name in ("tidal_inundation", "soil_salinity_proxy", "freshwater_influence_proxy"):
        p = layer_dir / f"{name}.tif"
        if p.is_file():
            bands, g, meta = read_layer(p)
            if not g.same_as(grid):
                raise GateError(f"{p.name} is not on the mangrove-layer grid")
            layers.update(bands)
            metas[name] = meta
            have.add(name)
    checks = [
        Check(
            "validation_gate",
            "PASS",
            f"{series} {year} validated (overall accuracy {gate['overall_accuracy']:.3f})",
        )
    ]
    checks += check_independence(
        metas.get("soil_salinity_proxy"), metas.get("freshwater_influence_proxy")
    )
    if any(c.status == "FAIL" for c in checks):
        raise GateError(
            "circular evidence: " + "; ".join(c.detail for c in checks if c.status == "FAIL")
        )
    for name in ("tidal_inundation", "soil_salinity_proxy", "freshwater_influence_proxy"):
        checks.append(
            Check(
                f"layer_{name}",
                "PASS" if name in have else "WARN",
                "available" if name in have else "not available",
            )
        )

    aoi = aoi_mod.build_aoi(cfgs.project)
    plots = make_plots(aoi, cfgs.site_selection.plot_size_m)
    metrics = plot_metrics(plots, grid, layers, cfgs)
    scored = evaluate(metrics, cfgs, have)
    choice = choose_pair(scored, plots, cfgs)
    out = out_root / "m6" / f"{series}_{year}"
    out.mkdir(parents=True, exist_ok=True)

    n_alt = cfgs.site_selection.comparability.n_alternatives
    scored["rank_site_a"] = scored["site_a_score"].rank(ascending=False, method="min")
    scored["rank_site_b"] = scored["site_b_score"].rank(ascending=False, method="min")
    scores_path = out / "candidate_site_scores.csv"
    scored.to_csv(scores_path, index=False)
    plots_scored = plots.merge(scored, on="plot_id")
    layers_out = {"candidate_plots": plots_scored}
    status = "NO_SELECTION"
    site_rows = []
    if choice["pair"]:
        status = "SELECTED"
        for role, pid in (
            ("site_a", choice["pair"]["site_a"]),
            ("site_b", choice["pair"]["site_b"]),
        ):
            layers_out[role] = plots_scored[plots_scored.plot_id == pid].assign(role=role)
            site_rows.append(scored[scored.plot_id == pid].assign(role=role, selected=True))
    for role, col in (("site_a", "site_a_score"), ("site_b", "site_b_score")):
        chosen = choice["pair"][role] if choice["pair"] else None
        alts = scored[scored[col].notna() & (scored.plot_id != chosen)].nlargest(n_alt, col)
        site_rows.append(alts.assign(role=f"{role}_alternative", selected=False))
    site_metrics = pd.concat(site_rows, ignore_index=True) if site_rows else pd.DataFrame()
    sm_path = out / "site_metrics.csv"
    site_metrics.to_csv(sm_path, index=False)
    crit_path = out / "selection_criteria.csv"
    criteria_table(cfgs).to_csv(crit_path, index=False)
    cmp_path = out / "site_comparison.csv"
    site_comparison(scored, choice["pair"], cfgs).to_csv(cmp_path, index=False)
    gpkg = write_layers(out / "sites.gpkg", layers_out)
    checks.append(
        Check("selection", "PASS" if status == "SELECTED" else "WARN", json.dumps(choice))
    )
    report = out / "selection_report.md"
    report.write_text(
        _report(series, year, status, choice, checks, scored, site_metrics), encoding="utf-8"
    )
    write_manifest(
        out / "run_manifest.json",
        milestone="M6",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[{"layers": sorted(have), "validation_gate": gate["config_sha256"]}],
        outputs=[scores_path, sm_path, crit_path, cmp_path, gpkg, report],
        status=status,
    )
    return status, checks, out


def _report(series, year, status, choice, checks, scored, site_metrics) -> str:
    lines = [f"# Candidate site selection: {series} {year}", "", f"Outcome: **{status}**", ""]
    if choice["pair"]:
        p = choice["pair"]
        lines += [
            f"* Site A: plot {p['site_a']}",
            f"* Site B: plot {p['site_b']}",
            f"* Separation: {p['separation_km']:.2f} km; inundation-frequency "
            f"difference: {p['inundation_difference']:.2f}",
        ]
    lines += [f"* {n}" for n in choice["notes"]]
    lines += [
        "",
        "Selection uses validated land cover and uncalibrated proxies. The proxies are "
        "relative within the AOI; they are not salinity measurements or evidence of "
        "freshwater delivery. See docs/uncertainty.md.",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {c.status} | {c.detail} |" for c in checks]
    lines += [
        "",
        f"Eligible plots: Site A {int(scored.site_a_eligible.sum())}, "
        f"Site B {int(scored.site_b_eligible.sum())} of {len(scored)}.",
        "",
    ]
    if not site_metrics.empty:
        cols = [
            c
            for c in (
                "role",
                "plot_id",
                "site_a_score",
                "site_b_score",
                "mangrove_cover",
                "salinity_percentile_mean",
                "high_vigour_fraction",
                "inundation_frequency_mean",
                "channel_distance_km_min",
                "classification_margin_mean",
            )
            if c in site_metrics.columns
        ]
        lines += ["## Selected sites and alternatives", "", md_table(site_metrics[cols])]
    return "\n".join(lines)
