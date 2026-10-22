"""Streamlit dashboard for the Indus Delta mangrove pipeline outputs.

Launch:  uv run indus-delta dashboard            (or)
         INDUS_DELTA_OUTPUTS=outputs uv run streamlit run src/indus_delta/dashboard/app.py

The dashboard only reads files the pipeline wrote. Changing a control changes the display;
it never reruns satellite processing.
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st

from indus_delta.config import ConfigError, load_configs
from indus_delta.dashboard import charts
from indus_delta.dashboard.data import (
    COMPARISON_UNITS,
    DashboardData,
    class_proportions,
    compare_plots,
    selectable_sites,
)

OUTPUTS = Path(os.environ.get("INDUS_DELTA_OUTPUTS", "outputs"))
CONFIGS = Path(os.environ.get("INDUS_DELTA_CONFIGS", "configs"))

st.set_page_config(page_title="Indus Delta mangrove", layout="wide")
st.title("Indus Delta mangrove study: Keti Bandar")
st.caption(
    f"Reading pipeline outputs from `{OUTPUTS}`. Controls change the display only; "
    "no satellite analysis is rerun from this page."
)

try:
    cfgs = load_configs(CONFIGS)
except ConfigError as exc:
    st.error(f"Configuration could not be loaded: {exc}")
    st.stop()

data = DashboardData(OUTPUTS)
epochs = data.epochs()
cl = cfgs.classification
classes = {c.code: c.name for c in cl.classes}

tabs = st.tabs(
    [
        "Overview",
        "Map explorer",
        "Historical trends",
        "Site comparison",
        "Classification validation",
        "Data & exports",
    ]
)


def no_data(what: str, how: str) -> None:
    st.info(f"**{what}: not available yet.** {how}")


# ------------------------------------------------------------------------- Overview
with tabs[0]:
    p = cfgs.project
    c1, c2, c3 = st.columns(3)
    c1.metric("Landsat series", f"{p.periods.landsat.start_year}–{p.periods.landsat.end_year}")
    c2.metric("Sentinel series", f"{p.periods.sentinel.start_year}–{p.periods.sentinel.end_year}")
    c3.metric("Classified epochs", len(epochs))
    loc = p.reference_location
    if loc.verification_status != "verified":
        st.warning(
            f"Reference location {loc.name} is **{loc.verification_status}** "
            f"({len(loc.sources)} source)."
        )
    if not p.aoi.operator_confirmed:
        st.warning("The AOI has not been confirmed by the operator (M1 review).")
    st.subheader("Processing and validation status")
    st.dataframe(data.milestone_status(), hide_index=True, width="stretch")
    metrics = data.annual_metrics()
    if metrics is not None and not metrics.empty:
        st.subheader("Mangrove area (validated epochs)")
        st.dataframe(metrics[metrics["validation_status"] == "PASS"], hide_index=True)
    st.subheader("Data availability")
    cat = data.catalog_verification()
    if cat is not None:
        counts = cat.groupby("status").size().to_dict()
        st.write(f"Catalog verification: {counts}")
        st.dataframe(cat[cat["status"] != "PASS"], hide_index=True, width="stretch")
    else:
        no_data("Catalog verification", "Run `indus-delta catalog-check`.")
    inv = data.inventory_summary()
    if inv is not None:
        for series in inv["series"].unique():
            st.plotly_chart(charts.inventory_figure(inv, series), width="stretch")
    else:
        no_data("Image inventory", "Run `indus-delta inventory` (needs Earth Engine).")

# ------------------------------------------------------------------------- Map explorer
with tabs[1]:
    from indus_delta.dashboard import maps

    aoi_layers = data.aoi()
    aoi = aoi_layers.get("aoi_primary")
    if not epochs:
        no_data("Classified map layers", "Classification (M4) has not run. Showing the AOI.")
    epoch = st.selectbox("Epoch (series and label year)", epochs) if epochs else None
    layers = data.raster_layers(epoch) if epoch else []
    choice = st.selectbox("Raster layer", ["(none)"] + [lyr.label for lyr in layers])
    c1, c2, c3 = st.columns(3)
    show_sites = c1.checkbox("Candidate sites", value=True)
    show_aoi_alt = c2.checkbox("Alternative AOIs", value=False)
    basemap = c3.checkbox("OpenStreetMap basemap (needs internet)", value=False)
    fig = maps.map_figure(aoi, basemap)
    legend, palette = None, None
    if choice != "(none)":
        layer = next(lyr for lyr in layers if lyr.label == choice)
        palette = (
            maps.landcover_palette(classes, cfgs.handover.landcover_colours)
            if layer.band == "landcover_class"
            else None
        )
        url, bounds, legend = maps.render_band(layer.path, layer.band, palette)
        maps.add_raster(fig, url, bounds)
        st.markdown(
            f"**{layer.label}**: {layer.kind_label}; status `{layer.status}`; units "
            f"{layer.units or 'n/a'}; pixel {layer.pixel_size_m:g} m (native grid, "
            f"EPSG:32642); epoch {layer.epoch}."
        )
        if layer.layer_type == "proxy":
            st.warning(
                "Proxy layer: relative within the AOI and uncalibrated. It is not a "
                "measurement of salinity or of freshwater delivery."
            )
        if layer.status != "validated" and layer.layer_type == "classified":
            st.warning(f"Classified layer status is `{layer.status}`: not validated.")
    if show_aoi_alt and "aoi_alternatives" in aoi_layers:
        maps.add_vector(
            fig,
            aoi_layers["aoi_alternatives"],
            "Alternative AOIs",
            "#555555",
            hover_fields=["aoi_id"],
        )
    if aoi is not None:
        maps.add_vector(fig, aoi, "AOI", "#d7301f", hover_fields=["aoi_id", "area_km2"])
    if "reference_location" in aoi_layers:
        maps.add_vector(
            fig,
            aoi_layers["reference_location"],
            "Reference point",
            "#000000",
            hover_fields=["name", "verification_status"],
        )
    if show_sites and epoch:
        geoms = data.site_geometries(epoch)
        for name, colour in (("site_a", charts.ORANGE), ("site_b", charts.AQUA)):
            if name in geoms:
                maps.add_vector(
                    fig,
                    geoms[name],
                    name.replace("_", " ").title(),
                    colour,
                    fill=True,
                    hover_fields=["plot_id", "site_a_score", "site_b_score"],
                )
    st.plotly_chart(fig, width="stretch", config={"scrollZoom": True})
    if legend:
        st.markdown(
            maps.legend_html(
                choice, legend, "display reprojection to EPSG:4326, nearest neighbour"
            ),
            unsafe_allow_html=True,
        )
    if len(epochs) > 1 and choice != "(none)":
        st.subheader("Compare years")
        a, b = st.columns(2)
        ea = a.selectbox("Left epoch", epochs, index=0)
        eb = b.selectbox("Right epoch", epochs, index=len(epochs) - 1)
        for col, e in ((a, ea), (b, eb)):
            lyr = next((x for x in data.raster_layers(e) if x.label == choice), None)
            if lyr is None:
                col.info(f"{choice} not available for {e}")
                continue
            f2 = maps.map_figure(aoi, basemap)
            u, bnd, _ = maps.render_band(lyr.path, lyr.band, palette)
            maps.add_raster(f2, u, bnd)
            col.plotly_chart(f2, width="stretch", key=f"cmp_{e}")

# ------------------------------------------------------------------------- Trends
with tabs[2]:
    metrics = data.annual_metrics()
    if metrics is None or metrics.empty:
        no_data(
            "Annual mangrove metrics", "Requires classified epochs (M4) and `indus-delta trends`."
        )
    else:
        periods = {
            "landsat": (p.periods.landsat.start_year, p.periods.landsat.end_year),
            "sentinel2": (p.periods.sentinel.start_year, p.periods.sentinel.end_year),
        }
        st.caption(
            "Landsat and Sentinel-2 are separate series and are never joined. Hollow "
            "markers: not validated. Crosses on the axis: no validated estimate. 2026 "
            "values cover the observations available so far (partial year)."
        )
        st.plotly_chart(charts.trend_figure(metrics, periods), width="stretch")
        st.plotly_chart(
            charts.trend_figure(
                metrics,
                periods,
                "mangrove_cover_pct_of_mapped",
                "% of mapped area",
                "Mangrove cover",
            ),
            width="stretch",
        )
        tt = data.trend_tests()
        if tt is not None and not tt.empty:
            st.subheader("Trend tests (Mann–Kendall, Sen's slope)")
            st.dataframe(tt, hide_index=True)
        ch = data.change_summaries()
        if ch is not None:
            st.plotly_chart(charts.gain_loss_figure(ch), width="stretch")

# ------------------------------------------------------------------------- Site comparison
with tabs[3]:
    epoch_s = st.selectbox("Epoch", epochs, key="site_epoch") if epochs else None
    sm = data.site_metrics(epoch_s) if epoch_s else None
    scores = data.candidate_scores(epoch_s) if epoch_s else None
    if sm is None or scores is None or sm.empty:
        no_data(
            "Candidate sites",
            "Site selection (M6) runs only after the validation gate "
            "passes and the selection rules are confirmed.",
        )
    else:
        opts = selectable_sites(sm)
        a_opts = opts[opts["role"].str.startswith("site_a")]
        b_opts = opts[opts["role"].str.startswith("site_b")]
        if a_opts.empty or b_opts.empty:
            st.warning("The evidence did not support both sites; see the selection report.")
        else:
            ca, cb = st.columns(2)
            la = ca.selectbox("Site A candidate", a_opts["label"])
            lb = cb.selectbox("Site B candidate", b_opts["label"])
            pa = a_opts.loc[a_opts["label"] == la, "plot_id"].iloc[0]
            pb = b_opts.loc[b_opts["label"] == lb, "plot_id"].iloc[0]
            cmp_ = compare_plots(scores, pa, pb)
            st.plotly_chart(charts.site_metrics_figure(cmp_, COMPARISON_UNITS), width="stretch")
            st.dataframe(cmp_, hide_index=True, width="stretch")
            lc = OUTPUTS / "m4" / epoch_s / "landcover.tif"
            geoms = data.site_geometries(epoch_s)
            plots = geoms.get("candidate_plots")
            if lc.is_file() and plots is not None:
                props = {
                    "site_a": class_proportions(
                        lc, plots[plots.plot_id == pa], classes, cl.nodata_class
                    ),
                    "site_b": class_proportions(
                        lc, plots[plots.plot_id == pb], classes, cl.nodata_class
                    ),
                }
                st.plotly_chart(charts.class_proportion_figure(props), width="stretch")
            for pid, label in ((pa, "Site A"), (pb, "Site B")):
                r = scores[scores.plot_id == pid].iloc[0]
                reason = r[
                    "site_a_exclusion_reasons" if label == "Site A" else "site_b_exclusion_reasons"
                ]
                if isinstance(reason, str) and reason:
                    st.warning(f"{label} plot {pid} is not eligible: {reason}")
        report = data.selection_report(epoch_s)
        if report:
            with st.expander("Selection report"):
                st.markdown(report)

# ------------------------------------------------------------------------- Validation
with tabs[4]:
    epoch_v = st.selectbox("Epoch", epochs, key="val_epoch") if epochs else None
    gate = data.validation_gate(epoch_v) if epoch_v else None
    if gate is None:
        no_data(
            "Classification validation",
            "Run `indus-delta classify` with operator "
            "reference and independent validation samples.",
        )
    else:
        (st.success if gate["status"] == "PASS" else st.error)(f"Validation gate: {gate['status']}")
        acc = data.accuracy(epoch_v)
        overall = acc[acc["class_name"] == "OVERALL"].iloc[0]
        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Overall accuracy",
            f"{overall['overall_accuracy']:.3f}",
            help=f"95% CI {overall['overall_accuracy_ci_low']:.3f}–"
            f"{overall['overall_accuracy_ci_high']:.3f}",
        )
        c2.metric("Kappa", f"{overall['kappa']:.3f}")
        c3.metric("Validation samples", int(overall["n_reference"]))
        st.plotly_chart(charts.accuracy_figure(acc), width="stretch")
        st.plotly_chart(charts.confusion_figure(data.confusion(epoch_v)), width="stretch")
        st.dataframe(acc, hide_index=True, width="stretch")
        st.dataframe(pd.DataFrame(gate["checks"]), hide_index=True, width="stretch")

# ------------------------------------------------------------------------- Data & exports
with tabs[5]:
    files = data.downloadable_files()
    if files.empty:
        no_data("Output files", "No pipeline outputs found.")
    else:
        st.dataframe(files, hide_index=True, width="stretch")
        kinds = st.multiselect(
            "File types",
            sorted(files["kind"].unique()),
            default=[k for k in ("csv", "gpkg", "tif") if k in set(files["kind"])],
        )
        for r in files[files["kind"].isin(kinds)].itertuples():
            if r.bytes > 50 * 1024 * 1024:
                st.write(f"`{r.path}` ({r.bytes / 1e6:.0f} MB): open from disk")
                continue
            st.download_button(
                f"Download {r.path}",
                (OUTPUTS / r.path).read_bytes(),
                file_name=Path(r.path).name,
                key=f"dl_{r.path}",
            )
