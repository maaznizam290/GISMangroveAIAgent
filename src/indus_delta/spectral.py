"""Reference (NumPy) implementation of masks and spectral indices.

The Earth Engine code builds the same operations from the same configuration. This module
is used to test the formulas and to recompute indices from downloaded previews, so that the
Earth Engine output is checked against an independent implementation.
"""

from __future__ import annotations

import numpy as np

from indus_delta.config import (
    DifferenceOfIndices,
    IndicesConfig,
    NormalizedDifference,
    RatioOfDifferences,
)


def bits_to_mask_value(bits: list[int]) -> int:
    """Integer with the given bit positions set (pixel is masked if any of them is 1)."""
    value = 0
    for b in bits:
        if not 0 <= b < 16:
            raise ValueError(f"bit out of range: {b}")
        value |= 1 << b
    return value


def qa_clear(qa: np.ndarray, bits: list[int]) -> np.ndarray:
    """True where none of the mask bits is set."""
    return (qa.astype(np.int64) & bits_to_mask_value(bits)) == 0


def saturation_bits(band_names: list[str]) -> list[int]:
    """QA_RADSAT bit for each SR_Bn band is n-1 (confirmed against the catalog)."""
    return [int(b.removeprefix("SR_B")) - 1 for b in band_names]


def scale_reflectance(dn: np.ndarray, scale: float, offset: float) -> np.ndarray:
    return dn.astype(np.float64) * scale + offset


def valid_reflectance(refl: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """True where the value is finite and inside [lo, hi]. Values outside are masked, not
    clipped."""
    return np.isfinite(refl) & (refl >= lo) & (refl <= hi)


def _safe_ratio(num: np.ndarray, den: np.ndarray, eps: float) -> np.ndarray:
    out = np.full(np.broadcast(num, den).shape, np.nan, dtype=np.float64)
    ok = np.isfinite(num) & np.isfinite(den) & (np.abs(den) >= eps)
    np.divide(num, den, out=out, where=ok)
    return out


def compute_index(name: str, bands: dict[str, np.ndarray], cfg: IndicesConfig) -> np.ndarray:
    """Index from role-named reflectance arrays (NaN = masked)."""
    idx = cfg.indices[name]
    eps = cfg.min_abs_denominator
    if isinstance(idx, NormalizedDifference):
        a, b = bands[idx.a], bands[idx.b]
        return _safe_ratio(a - b, a + b, eps)
    if isinstance(idx, RatioOfDifferences):
        (n1, n2), (d1, d2) = idx.numerator, idx.denominator
        return _safe_ratio(bands[n1] - bands[n2], bands[d1] - bands[d2], eps)
    if isinstance(idx, DifferenceOfIndices):
        return compute_index(idx.minuend, bands, cfg) - compute_index(idx.subtrahend, bands, cfg)
    raise TypeError(f"unsupported index type for {name}")


FLOAT32_EPS = float(np.finfo(np.float32).eps)


def index_rounding_bound(
    name: str, bands: dict[str, np.ndarray], cfg: IndicesConfig, eps: float = FLOAT32_EPS
) -> np.ndarray:
    """First-order worst-case change of compute_index when every input band (and the stored
    index) is rounded to float32. It grows as a denominator approaches zero (e.g. MVI where
    SWIR1 ~ Green), which tells storage rounding apart from a formula difference."""
    idx = cfg.indices[name]
    if isinstance(idx, DifferenceOfIndices):
        return index_rounding_bound(idx.minuend, bands, cfg, eps) + index_rounding_bound(
            idx.subtrahend, bands, cfg, eps
        )
    if isinstance(idx, NormalizedDifference):
        terms = (idx.a, idx.b), (idx.a, idx.b)
    elif isinstance(idx, RatioOfDifferences):
        terms = idx.numerator, idx.denominator
    else:
        raise TypeError(f"unsupported index type for {name}")
    (n1, n2), (d1, d2) = terms
    u = eps / 2
    r = compute_index(name, bands, cfg)
    den = bands[d1] - bands[d2] if isinstance(idx, RatioOfDifferences) else bands[d1] + bands[d2]
    spread = (
        np.abs(bands[n1]) + np.abs(bands[n2]) + np.abs(r) * (np.abs(bands[d1]) + np.abs(bands[d2]))
    )
    return _safe_ratio(u * spread, np.abs(den), cfg.min_abs_denominator) + u * np.abs(r)


def index_bounds(name: str, cfg: IndicesConfig) -> tuple[float, float] | None:
    """Mathematical range of an index, where one exists (normalized differences: [-1, 1] for
    non-negative inputs; CMRI: [-2, 2]). MVI is unbounded."""
    idx = cfg.indices[name]
    if isinstance(idx, NormalizedDifference):
        return (-1.0, 1.0)
    if isinstance(idx, DifferenceOfIndices):
        lo1, hi1 = index_bounds(idx.minuend, cfg) or (-np.inf, np.inf)
        lo2, hi2 = index_bounds(idx.subtrahend, cfg) or (-np.inf, np.inf)
        return (lo1 - hi2, hi1 - lo2)
    return None
