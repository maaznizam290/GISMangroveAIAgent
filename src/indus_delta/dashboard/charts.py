"""Plotly figures built only from pipeline tables (no illustrative values)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# Reference categorical palette (validated: first three slots pass all-pairs CVD checks).
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
TEXT, TEXT_2, MUTED, GRID = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e1"
SERIES_COLOURS = {"landsat": BLUE, "sentinel2": ORANGE}
SERIES_LABELS = {"landsat": "Landsat (30 m)", "sentinel2": "Sentinel-2 (10/20 m)"}
SITE_COLOURS = {"site_a": ORANGE, "site_b": AQUA}


def _style(fig: go.Figure, title: str, y_title: str = "", height: int = 380) -> go.Figure:
    fig.update_layout(
        title={"text": title, "font": {"color": TEXT, "size": 15}},
        height=height,
        template="plotly_white",
        font={"color": TEXT_2, "size": 12},
        margin={"l": 60, "r": 20, "t": 60, "b": 50},
        hovermode="closest",
        legend={"orientation": "h", "y": -0.2},
    )
    fig.update_yaxes(title=y_title, gridcolor=GRID, zeroline=False)
    fig.update_xaxes(gridcolor=GRID, showgrid=False)
    return fig


def missing_years(df: pd.DataFrame, series: str, start: int, end: int, value: str) -> list[int]:
    """Years in [start, end] without a validated value for the series."""
    ok = df[(df["series"] == series) & (df["validation_status"] == "PASS") & df[value].notna()][
        "label_year"
    ].astype(int)
    return [y for y in range(start, end + 1) if y not in set(ok)]


def trend_figure(
    metrics: pd.DataFrame,
    periods: dict[str, tuple[int, int]],
    value: str = "mangrove_area_km2",
    y_title: str = "km²",
    title: str = "Mangrove area by year",
) -> go.Figure:
    """One trace per series (never joined). Validated points filled, unvalidated hollow;
    years without a validated value are marked along the x-axis."""
    fig = go.Figure()
    for series, (start, end) in periods.items():
        sub = metrics[metrics["series"] == series].sort_values("label_year")
        colour = SERIES_COLOURS.get(series, MUTED)
        name = SERIES_LABELS.get(series, series)
        valid = sub[(sub["validation_status"] == "PASS") & sub[value].notna()]
        # No line (and no legend entry) for a series without validated values.
        if not valid.empty:
            fig.add_trace(
                go.Scatter(
                    x=valid["label_year"],
                    y=valid[value],
                    mode="lines+markers",
                    name=name,
                    line={"color": colour, "width": 2},
                    marker={"size": 8, "color": colour},
                    hovertemplate=f"{name}<br>%{{x}}: %{{y:.2f}} {y_title}<extra>validated</extra>",
                )
            )
        unval = sub[sub["validation_status"] != "PASS"]
        if not unval.empty:
            fig.add_trace(
                go.Scatter(
                    x=unval["label_year"],
                    y=unval[value],
                    mode="markers",
                    name=f"{name}: not validated",
                    marker={"size": 9, "color": "white", "line": {"color": colour, "width": 2}},
                    hovertemplate="%{x}: %{y:.2f}<extra>NOT validated</extra>",
                )
            )
        gaps = missing_years(sub, series, start, end, value)
        if gaps:
            fig.add_trace(
                go.Scatter(
                    x=gaps,
                    y=[0] * len(gaps),
                    mode="markers",
                    name=f"{name}: no validated estimate",
                    marker={
                        "symbol": "x-thin-open",
                        "size": 9,
                        "color": colour,
                        "line": {"width": 1.5, "color": colour},
                    },
                    hovertemplate="%{x}: no validated estimate<extra></extra>",
                )
            )
    return _style(fig, title, y_title)


def gain_loss_figure(changes: pd.DataFrame) -> go.Figure:
    labels = changes["from_year"].astype(str) + "–" + changes["to_year"].astype(str)
    fig = go.Figure(
        [
            go.Bar(
                x=labels,
                y=changes["gain_km2"],
                name="Gain",
                marker_color=AQUA,
                text=changes["gain_km2"].round(2),
                textposition="outside",
            ),
            go.Bar(
                x=labels,
                y=-changes["loss_km2"],
                name="Loss",
                marker_color=ORANGE,
                text=changes["loss_km2"].round(2),
                textposition="outside",
            ),
        ]
    )
    fig.update_layout(barmode="relative", bargap=0.4)
    return _style(fig, "Mangrove gain and loss between validated epochs", "km²")


def accuracy_figure(acc: pd.DataFrame) -> go.Figure:
    """User's and producer's accuracy per class with Wilson intervals."""
    a = acc[acc["class_name"] != "OVERALL"]
    fig = go.Figure()
    for col, name, colour in (
        ("users_accuracy", "User's accuracy (precision)", BLUE),
        ("producers_accuracy", "Producer's accuracy (recall)", ORANGE),
    ):
        fig.add_trace(
            go.Bar(
                x=a["class_name"],
                y=a[col],
                name=name,
                marker_color=colour,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": a[f"{col}_ci_high"] - a[col],
                    "arrayminus": a[col] - a[f"{col}_ci_low"],
                    "color": TEXT_2,
                },
                customdata=np.c_[a["n_reference"], a["n_mapped"]],
                hovertemplate="%{x}<br>%{y:.3f}<br>reference n=%{customdata[0]}, mapped "
                "n=%{customdata[1]}<extra>" + name + "</extra>",
            )
        )
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.08)
    fig.update_yaxes(range=[0, 1.05])
    return _style(fig, "Per-class accuracy (95% Wilson intervals)", "fraction")


def confusion_figure(cm: pd.DataFrame) -> go.Figure:
    z = cm.to_numpy()
    fig = go.Figure(
        go.Heatmap(
            z=z,
            x=[c.removeprefix("map_") for c in cm.columns],
            y=[r.removeprefix("ref_") for r in cm.index],
            colorscale="Blues",
            showscale=False,
            text=z,
            texttemplate="%{text}",
            hovertemplate="reference %{y}<br>map %{x}<br>%{z} samples<extra></extra>",
        )
    )
    fig.update_yaxes(autorange="reversed", title="reference class")
    fig.update_xaxes(title="map class")
    return _style(fig, "Confusion matrix (validation samples)", height=460)


def inventory_figure(summary: pd.DataFrame, series: str) -> go.Figure:
    sub = summary[summary["series"] == series]
    piv = sub.pivot_table(index="season", columns="label_year", values="n_usable", aggfunc="sum")
    fig = go.Figure(
        go.Heatmap(
            z=piv.to_numpy(),
            x=piv.columns,
            y=piv.index,
            colorscale="Blues",
            text=piv.to_numpy(),
            texttemplate="%{text}",
            showscale=False,
            hovertemplate="%{y} %{x}: %{z} usable images<extra></extra>",
        )
    )
    return _style(fig, f"Usable images per season: {SERIES_LABELS.get(series, series)}", height=230)


def site_metrics_figure(comparison: pd.DataFrame, metric_units: dict[str, str]) -> go.Figure:
    """Small multiples: one panel per metric, so differently scaled metrics never share an
    axis. Values are labelled on the bars."""
    rows = comparison[
        comparison["metric"].isin(metric_units)
        & comparison[["site_a", "site_b"]].notna().any(axis=1)
    ]
    n = len(rows)
    fig = make_subplots(
        rows=1,
        cols=max(n, 1),
        subplot_titles=[f"{m}<br>({metric_units[m]})" for m in rows["metric"]],
    )
    for i, r in enumerate(rows.itertuples(), start=1):
        for site, col in (("site_a", r.site_a), ("site_b", r.site_b)):
            fig.add_trace(
                go.Bar(
                    x=["A" if site == "site_a" else "B"],
                    y=[col],
                    marker_color=SITE_COLOURS[site],
                    name="Site A" if site == "site_a" else "Site B",
                    showlegend=i == 1,
                    text=[f"{col:.2f}" if pd.notna(col) else "n/a"],
                    textposition="outside",
                    hovertemplate=f"{r.metric}: %{{y:.3f}}<extra></extra>",
                ),
                row=1,
                col=i,
            )
    fig.update_annotations(font_size=10)
    return _style(fig, "Site A vs Site B", height=360)


def class_proportion_figure(props: dict[str, pd.DataFrame]) -> go.Figure:
    fig = go.Figure()
    for site, df in props.items():
        fig.add_trace(
            go.Bar(
                x=df["class_name"],
                y=df["share"],
                name=site.replace("_", " ").title(),
                marker_color=SITE_COLOURS.get(site, MUTED),
                text=df["share"].round(2),
                textposition="outside",
                hovertemplate="%{x}: %{y:.2%}<extra></extra>",
            )
        )
    fig.update_layout(barmode="group", bargap=0.35)
    fig.update_yaxes(range=[0, 1.1])
    return _style(fig, "Land-cover class proportions in each site", "share of valid pixels")
