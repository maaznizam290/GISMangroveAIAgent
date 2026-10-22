"""Map rendering for display only (Plotly MapLibre; no CDN scripts needed).

Rasters are reprojected to EPSG:4326 *for the web map*
(nearest neighbour); analysis always uses the EPSG:32642 originals."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import plotly.graph_objects as go
import rasterio
from rasterio.warp import Resampling, calculate_default_transform, reproject

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.colors import to_rgba  # noqa: E402

CONTINUOUS_CMAPS = {
    "water_frequency": ("Blues", 0, 1),
    "margin": ("RdYlGn", 0, 1),
    "soil_salinity_proxy_percentile": ("YlOrBr", 0, 100),
    "distance_via_channel_km": ("Blues_r", 0, 30),
}
CATEGORICAL = {
    "mangrove_extent": {0: ("#f0f0f0", "not mangrove"), 1: ("#1b7837", "mangrove")},
    "spectral_vigour_class": {
        1: ("#d9f0d3", "low (relative)"),
        2: ("#7fbf7b", "mid"),
        3: ("#1b7837", "high (relative)"),
    },
}


def landcover_palette(classes: dict[int, str], colours: dict[str, str]) -> dict:
    return {code: (colours[name], name) for code, name in classes.items() if name in colours}


def render_band(path: Path, band: str, palette: dict | None = None) -> tuple[str, list, dict]:
    """(PNG data URL, [[south, west], [north, east]], legend {label: colour})."""
    with rasterio.open(path) as src:
        idx = list(src.descriptions).index(band) + 1
        data = src.read(idx).astype(float)
        if src.nodata is not None:
            data[data == src.nodata] = np.nan
        tf, w, h = calculate_default_transform(
            src.crs, "EPSG:4326", src.width, src.height, *src.bounds
        )
        out = np.full((h, w), np.nan)
        reproject(
            data,
            out,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=tf,
            dst_crs="EPSG:4326",
            resampling=Resampling.nearest,
            src_nodata=np.nan,
            dst_nodata=np.nan,
        )
    rgba = np.zeros((h, w, 4))
    legend: dict[str, str] = {}
    pal = palette or CATEGORICAL.get(band)
    if pal:
        for value, (colour, label) in pal.items():
            rgba[out == value] = to_rgba(colour)
            legend[label] = colour
    else:
        cmap_name, lo, hi = CONTINUOUS_CMAPS.get(band, ("viridis", np.nanmin(out), np.nanmax(out)))
        cmap = plt.get_cmap(cmap_name)
        rgba = cmap(np.clip((out - lo) / ((hi - lo) or 1), 0, 1))
        legend = {
            f"{lo:g}": matplotlib.colors.to_hex(cmap(0.0)),
            f"{hi:g}": matplotlib.colors.to_hex(cmap(1.0)),
        }
    rgba[~np.isfinite(out)] = 0
    buf = io.BytesIO()
    plt.imsave(buf, rgba, format="png")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    west, north = tf.c, tf.f
    east, south = west + w * tf.a, north + h * tf.e
    return url, [[south, west], [north, east]], legend


def _rings(geom) -> list[tuple[list[float], list[float]]]:
    polys = getattr(geom, "geoms", [geom])
    out = []
    for poly in polys:
        if poly.geom_type == "Polygon":
            xs, ys = poly.exterior.xy
            out.append((list(xs), list(ys)))
        elif poly.geom_type == "Point":
            out.append(([poly.x], [poly.y]))
    return out


def map_figure(aoi: gpd.GeoDataFrame | None, basemap: bool = False) -> go.Figure:
    """Plotly MapLibre map. With basemap=False no external tiles or scripts are needed, so it
    also works offline; the OpenStreetMap basemap needs internet access."""
    fig = go.Figure()
    centre, zoom = {"lat": 24.14, "lon": 67.45}, 10.5
    if aoi is not None and not aoi.empty:
        b = aoi.to_crs(4326).total_bounds
        centre = {"lat": (b[1] + b[3]) / 2, "lon": (b[0] + b[2]) / 2}
        zoom = 11.3
    fig.update_layout(
        map={
            "style": "open-street-map" if basemap else "white-bg",
            "center": centre,
            "zoom": zoom,
            "layers": [],
        },
        height=620,
        margin={"l": 0, "r": 0, "t": 0, "b": 0},
        legend={"orientation": "h", "y": 0.02, "x": 0.01, "bgcolor": "rgba(255,255,255,0.8)"},
    )
    return fig


def add_raster(fig: go.Figure, url: str, bounds: list, opacity: float = 0.8) -> None:
    (south, west), (north, east) = bounds
    layers = list(fig.layout.map.layers or [])
    layers.append(
        {
            "sourcetype": "image",
            "source": url,
            "opacity": opacity,
            "below": "traces",
            "coordinates": [[west, north], [east, north], [east, south], [west, south]],
        }
    )
    fig.update_layout(map={"layers": layers})


def add_vector(
    fig: go.Figure,
    gdf: gpd.GeoDataFrame,
    name: str,
    colour: str,
    fill: bool = False,
    hover_fields: list[str] | None = None,
) -> None:
    g = gdf.to_crs(4326)
    fields = [f for f in (hover_fields or []) if f in g.columns]
    first = True
    for _, row in g.iterrows():
        text = (
            "<br>".join(
                f"{f}: {row[f]:.3f}" if isinstance(row[f], float) else f"{f}: {row[f]}"
                for f in fields
            )
            or name
        )
        for xs, ys in _rings(row.geometry):
            point = len(xs) == 1
            fig.add_trace(
                go.Scattermap(
                    lon=xs,
                    lat=ys,
                    mode="markers" if point else "lines",
                    fill="toself" if fill and not point else None,
                    fillcolor=to_hex_alpha(colour, 0.25) if fill else None,
                    line={"color": colour, "width": 2},
                    marker={"size": 9, "color": colour},
                    name=name,
                    legendgroup=name,
                    showlegend=first,
                    text=text,
                    hovertemplate="%{text}<extra>" + name + "</extra>",
                )
            )
            first = False


def to_hex_alpha(colour: str, alpha: float) -> str:
    r, g, b, _ = to_rgba(colour)
    return f"rgba({int(r * 255)},{int(g * 255)},{int(b * 255)},{alpha})"


def legend_html(title: str, legend: dict[str, str], note: str) -> str:
    items = "".join(
        f"<div><span style='display:inline-block;width:12px;height:12px;"
        f"background:{c};border:1px solid #888;margin-right:6px'></span>{lab}</div>"
        for lab, c in legend.items()
    )
    return f"<div style='font-size:12px'><b>{title}</b>{items}<i>{note}</i></div>"
