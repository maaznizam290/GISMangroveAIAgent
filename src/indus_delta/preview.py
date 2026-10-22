"""Static AOI inspection map (PNG). Display only; no analysis happens here."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from matplotlib.colors import ListedColormap  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from indus_delta.hydrology import NODATA_OUT  # noqa: E402


def _nice_length(span_m: float) -> float:
    target = span_m / 5
    for step in (1000, 2000, 5000, 10000, 20000, 50000):
        if step >= target:
            return step
    return 100000


def render_aoi_preview(
    path: Path,
    *,
    occurrence: np.ndarray,
    transform: rasterio.Affine,
    epsg: int,
    aoi: gpd.GeoDataFrame,
    alternatives: gpd.GeoDataFrame,
    reference: gpd.GeoDataFrame,
    river: gpd.GeoDataFrame | None,
    title: str,
    source_note: str,
) -> Path:
    h, w = occurrence.shape
    extent = (
        transform.c,
        transform.c + w * transform.a,
        transform.f + h * transform.e,
        transform.f,
    )
    fig, ax = plt.subplots(figsize=(10, 10.6), dpi=150)
    nodata = np.ma.masked_where(occurrence != NODATA_OUT, np.ones_like(occurrence))
    ax.imshow(nodata, extent=extent, cmap=ListedColormap(["#d9d9d9"]), interpolation="nearest")
    occ = np.ma.masked_equal(occurrence, NODATA_OUT)
    img = ax.imshow(occ, extent=extent, cmap="Blues", vmin=0, vmax=100, interpolation="nearest")
    cbar = fig.colorbar(img, ax=ax, fraction=0.035, pad=0.02)
    cbar.set_label("JRC GSW v1.4 water occurrence 1984-2021 (% of valid observations)")

    handles = []
    if river is not None and not river.empty:
        river.plot(ax=ax, color="#8c510a", linewidth=1.6)
        handles.append(
            Line2D(
                [],
                [],
                color="#8c510a",
                lw=1.6,
                label="Indus, Natural Earth 1:10M (coarse reference)",
            )
        )
    if not alternatives.empty:
        alternatives.boundary.plot(ax=ax, color="#555555", linewidth=0.9, linestyle="--")
        for _, row in alternatives.iterrows():
            x, y = row.geometry.exterior.coords[0]
            ax.annotate(
                f"{row.buffer_m / 1000:g} km",
                (x, y),
                xytext=(3, 0),
                textcoords="offset points",
                fontsize=8,
                color="#333333",
            )
        handles.append(
            Line2D([], [], color="#555555", lw=0.9, ls="--", label="Alternative AOIs (proposals)")
        )
    aoi.boundary.plot(ax=ax, color="#d7301f", linewidth=2.2)
    handles.append(
        Line2D([], [], color="#d7301f", lw=2.2, label=f"Primary AOI ({aoi.aoi_id.iloc[0]})")
    )
    reference.plot(ax=ax, color="black", marker="*", markersize=140, zorder=5)
    status = reference.verification_status.iloc[0]
    handles.append(
        Line2D(
            [],
            [],
            color="black",
            marker="*",
            lw=0,
            markersize=11,
            label=f"{reference.name.iloc[0]} reference point ({status})",
        )
    )
    handles.append(
        Line2D(
            [],
            [],
            color="#d9d9d9",
            marker="s",
            lw=0,
            markersize=10,
            label="No data in JRC tile (value 255)",
        )
    )

    ax.set_xlim(extent[0], extent[1])
    ax.set_ylim(extent[2], extent[3])
    ax.set_xlabel(f"Easting (m), EPSG:{epsg}")
    ax.set_ylabel(f"Northing (m), EPSG:{epsg}")
    ax.ticklabel_format(style="plain")
    ax.tick_params(labelsize=8)
    ax.legend(handles=handles, loc="upper left", fontsize=8, framealpha=0.9)

    # Scale bar (true metres in the projected CRS) and grid-north arrow.
    span = extent[1] - extent[0]
    length = _nice_length(span)
    x0 = extent[0] + 0.05 * span
    y0 = extent[2] + 0.05 * (extent[3] - extent[2])
    ax.plot([x0, x0 + length], [y0, y0], color="black", lw=4, solid_capstyle="butt")
    ax.text(
        x0 + length / 2,
        y0 + 0.012 * span,
        f"{length / 1000:g} km",
        ha="center",
        fontsize=9,
        bbox={"fc": "white", "ec": "none", "alpha": 0.8, "pad": 1},
    )
    ax.annotate(
        "N",
        xy=(0.95, 0.95),
        xytext=(0.95, 0.87),
        xycoords="axes fraction",
        ha="center",
        fontsize=11,
        fontweight="bold",
        arrowprops={"arrowstyle": "-|>", "color": "black", "lw": 1.5},
    )
    ax.text(0.95, 0.845, "grid north", transform=ax.transAxes, ha="center", fontsize=7)

    ax.set_title(title, fontsize=12)
    fig.text(0.01, 0.01, source_note, fontsize=6.5, va="bottom", wrap=True)
    fig.tight_layout(rect=(0, 0.06, 1, 1))
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path
