"""Checks on a downloaded preview GeoTIFF. They decide whether full processing may start."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine

from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.grid import is_aligned
from indus_delta.spectral import compute_index, index_bounds


@dataclass(frozen=True)
class PreviewExpectation:
    label: str  # e.g. "landsat", "sentinel2", "sentinel1"
    kind: str  # "optical" or "sar"
    epsg: int
    scale: float
    transform: Affine
    width: int
    height: int
    band_names: list[str]
    grid_offset: tuple[float, float]


def check_preview(path: Path, exp: PreviewExpectation, cfgs: Configs) -> list[Check]:
    pv = cfgs.preprocessing.preview
    nodata_cfg = cfgs.preprocessing.composites.nodata_value
    p = f"{exp.label}_"
    checks: list[Check] = []

    def add(name, ok, detail):
        checks.append(Check(p + name, "PASS" if ok else "FAIL", detail))

    with rasterio.open(path) as src:
        add(
            "crs",
            src.crs is not None and src.crs.to_epsg() == exp.epsg,
            f"file CRS {src.crs}, expected EPSG:{exp.epsg}",
        )
        add(
            "pixel_size",
            np.allclose(src.res, (exp.scale, exp.scale)),
            f"file pixel size {src.res}, expected {exp.scale}",
        )
        same_grid = (src.width, src.height) == (
            exp.width,
            exp.height,
        ) and src.transform.almost_equals(exp.transform)
        add(
            "grid_matches_request",
            same_grid,
            f"file {src.width}x{src.height} {tuple(src.transform)[:6]}, requested "
            f"{exp.width}x{exp.height} {tuple(exp.transform)[:6]}",
        )
        add(
            "grid_aligned_to_native",
            is_aligned(src.transform, exp.scale, exp.grid_offset),
            f"pixel edges at offset {exp.grid_offset} (mod {exp.scale} m) of the native grid",
        )
        names = list(src.descriptions)
        add("band_names", names == exp.band_names, f"bands {names}")
        add(
            "nodata",
            src.nodata is not None and src.nodata == nodata_cfg,
            f"nodata {src.nodata}, expected {nodata_cfg}",
        )
        if names != exp.band_names:
            return checks
        data = {n: src.read(i + 1).astype(np.float64) for i, n in enumerate(names)}

    nod = {n: (a == nodata_cfg) | ~np.isfinite(a) for n, a in data.items()}
    for n, a in data.items():
        a[nod[n]] = np.nan
    obs = data["valid_obs"]
    if exp.kind == "optical":
        roles = ["blue", "green", "red", "nir", "swir1", "swir2"]
        valid = np.all([~nod[r] for r in roles], axis=0) & (np.nan_to_num(obs) >= 1)
    else:
        pols = cfgs.preprocessing.sentinel1.polarisations
        valid = np.all([~nod[r] for r in pols], axis=0) & (np.nan_to_num(obs) >= 1)
    frac = float(valid.mean())
    add(
        "valid_fraction",
        frac >= pv.min_valid_fraction,
        f"{frac:.1%} of preview pixels valid (minimum {pv.min_valid_fraction:.0%})",
    )
    if valid.any():
        o = obs[valid]
        add(
            "valid_obs",
            bool(o.min() >= 1),
            f"valid observations per pixel: min {o.min():.0f}, median {np.median(o):.0f}, "
            f"max {o.max():.0f}",
        )
    if not valid.any():
        return checks

    if exp.kind == "optical":
        vr, tol = cfgs.indices.valid_reflectance, pv.reflectance_tolerance
        bad = {
            r: int(((data[r][valid] < vr.min - tol) | (data[r][valid] > vr.max + tol)).sum())
            for r in roles
        }
        add(
            "reflectance_range",
            not any(bad.values()),
            f"values outside [{vr.min}, {vr.max}]: {bad}",
        )
        bands = {r: np.where(valid, data[r], np.nan) for r in roles}
        itol = pv.index_recompute_tolerance
        for name in cfgs.indices.indices:
            ref = compute_index(name, bands, cfgs.indices)
            got = np.where(valid, data[name], np.nan)
            both = np.isfinite(ref) & np.isfinite(got)
            mask_mismatch = int((np.isfinite(ref) != np.isfinite(got))[valid].sum())
            diff = np.abs(ref[both] - got[both]) / np.maximum(1.0, np.abs(ref[both]))
            maxdiff = float(diff.max()) if diff.size else 0.0
            ok = maxdiff <= itol and mask_mismatch <= max(1, 0.001 * valid.sum())
            add(
                f"index_{name}_recomputed",
                ok,
                f"max relative difference {maxdiff:.2e} (tolerance {itol:g}); "
                f"{mask_mismatch} pixels masked in one implementation only",
            )
            bounds = index_bounds(name, cfgs.indices)
            if bounds and both.any():
                lo, hi = bounds
                out = int(((got[both] < lo - itol) | (got[both] > hi + itol)).sum())
                add(f"index_{name}_bounds", out == 0, f"{out} values outside [{lo}, {hi}]")
    else:
        lo, hi = pv.sar_db_range
        for pol in cfgs.preprocessing.sentinel1.polarisations:
            v = data[pol][valid]
            out = int(((v < lo) | (v > hi)).sum())
            add(
                f"{pol}_db_range",
                out == 0,
                f"{out} values outside the sanity range [{lo}, {hi}] dB; "
                f"median {np.median(v):.1f} dB",
            )
    return checks
