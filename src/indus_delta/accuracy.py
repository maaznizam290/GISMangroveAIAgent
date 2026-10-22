"""Accuracy assessment.

Confusion matrices here use rows = reference class, columns = map class.
For stratified random validation by map class, `olofsson` gives area-weighted accuracy and
area estimates with standard errors (Olofsson et al. 2014, Remote Sens. Environ. 148: 42-57),
whose formulas use the transposed (map x reference) layout internally.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm


def confusion(reference: np.ndarray, mapped: np.ndarray, codes: list[int]) -> np.ndarray:
    index = {c: i for i, c in enumerate(codes)}
    cm = np.zeros((len(codes), len(codes)), dtype=np.int64)
    for r, m in zip(reference, mapped, strict=True):
        if r in index and m in index:
            cm[index[r], index[m]] += 1
    return cm


def wilson(successes: float, n: float, confidence: float) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    z = norm.ppf(0.5 + confidence / 2)
    p = successes / n
    den = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / den
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def _div(a: float, b: float) -> float:
    return float(a / b) if b else float("nan")


def class_metrics(
    cm: np.ndarray, codes: list[int], names: list[str], confidence: float
) -> pd.DataFrame:
    """Per-class sample-count metrics with Wilson intervals for user's/producer's accuracy."""
    rows = []
    for i, (code, name) in enumerate(zip(codes, names, strict=True)):
        tp = cm[i, i]
        n_ref, n_map = cm[i, :].sum(), cm[:, i].sum()
        ua, pa = _div(tp, n_map), _div(tp, n_ref)
        f1 = _div(2 * ua * pa, ua + pa) if np.isfinite(ua) and np.isfinite(pa) else float("nan")
        ua_lo, ua_hi = wilson(tp, n_map, confidence)
        pa_lo, pa_hi = wilson(tp, n_ref, confidence)
        rows.append(
            {
                "class_code": code,
                "class_name": name,
                "n_reference": int(n_ref),
                "n_mapped": int(n_map),
                "n_correct": int(tp),
                "users_accuracy": ua,
                "users_accuracy_ci_low": ua_lo,
                "users_accuracy_ci_high": ua_hi,
                "producers_accuracy": pa,
                "producers_accuracy_ci_low": pa_lo,
                "producers_accuracy_ci_high": pa_hi,
                "precision": ua,
                "recall": pa,
                "f1": f1,
                "iou": _div(tp, n_ref + n_map - tp),
            }
        )
    return pd.DataFrame(rows)


@dataclass
class OverallAccuracy:
    overall_accuracy: float
    ci_low: float
    ci_high: float
    n: int
    kappa: float


def overall(cm: np.ndarray, confidence: float) -> OverallAccuracy:
    n = int(cm.sum())
    correct = int(np.trace(cm))
    lo, hi = wilson(correct, n, confidence)
    po = _div(correct, n)
    pe = _div(float((cm.sum(0) * cm.sum(1)).sum()), float(n) ** 2)
    kappa = _div(po - pe, 1 - pe) if n else float("nan")
    return OverallAccuracy(po, lo, hi, n, kappa)


def olofsson(cm_ref_by_map: np.ndarray, map_pixel_counts: np.ndarray, pixel_area: float) -> dict:
    """Area-weighted estimators for stratified random sampling by map class.

    cm_ref_by_map: rows reference, columns map (this module's convention).
    map_pixel_counts: mapped pixels per class (same order), i.e. stratum sizes N_i.
    Returns overall accuracy, user's/producer's accuracy, area proportions and areas with
    standard errors.
    """
    n = cm_ref_by_map.T.astype(np.float64)  # n[i, j]: map class i, reference class j
    n_i = n.sum(axis=1)
    if np.any(n_i == 0):
        raise ValueError("every map stratum needs validation samples for area estimation")
    N_i = np.asarray(map_pixel_counts, dtype=np.float64)
    W = N_i / N_i.sum()
    p = W[:, None] * n / n_i[:, None]
    oa = float(np.trace(p))
    ua = np.diag(p) / p.sum(axis=1)
    p_ref = p.sum(axis=0)
    pa = np.divide(np.diag(p), p_ref, out=np.full_like(p_ref, np.nan), where=p_ref > 0)
    dof = np.maximum(n_i - 1, 1)
    se_oa = float(np.sqrt(np.sum(W**2 * ua * (1 - ua) / dof)))
    se_ua = np.sqrt(ua * (1 - ua) / dof)
    frac = n / n_i[:, None]
    se_p_ref = np.sqrt(np.sum(W[:, None] ** 2 * frac * (1 - frac) / dof[:, None], axis=0))
    # Producer's accuracy variance (Olofsson et al. 2014, eq. 7).
    N_ref = (N_i[:, None] * frac).sum(axis=0)
    se_pa = np.full(len(N_i), np.nan)
    for j in range(len(N_i)):
        if N_ref[j] <= 0:
            continue
        t1 = N_i[j] ** 2 * (1 - pa[j]) ** 2 * ua[j] * (1 - ua[j]) / dof[j]
        others = [i for i in range(len(N_i)) if i != j]
        t2 = pa[j] ** 2 * sum(N_i[i] ** 2 * frac[i, j] * (1 - frac[i, j]) / dof[i] for i in others)
        se_pa[j] = np.sqrt((t1 + t2) / N_ref[j] ** 2)
    total_area = N_i.sum() * pixel_area
    return {
        "overall_accuracy": oa,
        "overall_accuracy_se": se_oa,
        "users_accuracy": ua,
        "users_accuracy_se": se_ua,
        "producers_accuracy": pa,
        "producers_accuracy_se": se_pa,
        "area_proportion": p_ref,
        "area_proportion_se": se_p_ref,
        "area": p_ref * total_area,
        "area_se": se_p_ref * total_area,
        "mapped_area": N_i * pixel_area,
    }
