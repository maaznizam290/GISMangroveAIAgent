"""Analysis-grid alignment.

Output grids are aligned to the native grid of the source sensor: pixel edges sit at
offset + k * scale in the analysis CRS. The offset is read from a native image's projection
at preview time (never assumed) and stored with the preview gate.
"""

from __future__ import annotations

import math

from rasterio.transform import Affine


def grid_offset(transform: list[float] | tuple[float, ...], scale: float) -> tuple[float, float]:
    """(x, y) offset of pixel edges modulo scale, from a [a, b, c, d, e, f] transform."""
    a, b, c, d, e, f = transform[:6]
    if b or d:
        raise ValueError("rotated/sheared grids are not supported")
    if not (math.isclose(abs(a), scale) and math.isclose(abs(e), scale)):
        raise ValueError(f"native pixel size {a}x{e} differs from scale {scale}")
    return c % scale, f % scale


def aligned_bounds(
    bounds: tuple[float, float, float, float], scale: float, offset: tuple[float, float] = (0, 0)
) -> tuple[Affine, int, int]:
    """Smallest aligned grid covering the bounds: (transform, width, height)."""
    minx, miny, maxx, maxy = bounds
    ox, oy = offset
    x0 = math.floor((minx - ox) / scale) * scale + ox
    x1 = math.ceil((maxx - ox) / scale) * scale + ox
    y0 = math.floor((miny - oy) / scale) * scale + oy
    y1 = math.ceil((maxy - oy) / scale) * scale + oy
    return Affine(scale, 0, x0, 0, -scale, y1), round((x1 - x0) / scale), round((y1 - y0) / scale)


def aligned_box(
    cx: float, cy: float, half: float, scale: float, offset: tuple[float, float] = (0, 0)
) -> tuple[Affine, int, int]:
    return aligned_bounds((cx - half, cy - half, cx + half, cy + half), scale, offset)


def is_aligned(
    transform: Affine, scale: float, offset: tuple[float, float], tol: float = 1e-6
) -> bool:
    ox, oy = offset

    def on_grid(v: float, o: float) -> bool:
        r = (v - o) % scale
        return min(r, scale - r) <= tol

    return (
        math.isclose(transform.a, scale)
        and math.isclose(transform.e, -scale)
        and on_grid(transform.c, ox)
        and on_grid(transform.f, oy)
    )


def transform_list(t: Affine) -> list[float]:
    """Row-major [a, b, c, d, e, f], the order Earth Engine's crs_transform expects."""
    return [t.a, t.b, t.c, t.d, t.e, t.f]
