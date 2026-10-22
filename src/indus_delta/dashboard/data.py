"""Read-only access to pipeline outputs for the dashboard.

Every loader returns None (or an empty frame) when an output does not exist. Nothing here
creates, estimates or fills in values: the dashboard shows only what the pipeline wrote.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask

# Raster layers the map can show: (folder template, file, display band, label).
LAYER_FILES = [
    ("m4/{epoch}", "landcover.tif", "landcover_class", "Land cover"),
    ("m4/{epoch}", "classification_uncertainty.tif", "margin", "Classification margin"),
    ("m5/{epoch}", "mangrove.tif", "mangrove_extent", "Mangrove extent"),
    ("m5/{epoch}", "mangrove.tif", "spectral_vigour_class", "Mangrove spectral vigour"),
    ("m5/{epoch}", "tidal_inundation.tif", "water_frequency", "Inundation frequency"),
    (
        "m5/{epoch}",
        "soil_salinity_proxy.tif",
        "soil_salinity_proxy_percentile",
        "Soil-salinity proxy",
    ),
    (
        "m5/{epoch}",
        "freshwater_influence_proxy.tif",
        "distance_via_channel_km",
        "Freshwater-influence proxy (channel distance)",
    ),
]


@dataclass(frozen=True)
class RasterLayer:
    label: str
    path: Path
    band: str
    epoch: str
    layer_type: str
    status: str
    units: str
    pixel_size_m: float
    description: str

    @property
    def kind_label(self) -> str:
        """How a reader should treat the values."""
        return {
            "classified": "classified",
            "proxy": "proxy (relative, uncalibrated)",
            "measured": "measured",
            "derived": "derived",
            "reference": "external reference",
        }.get(self.layer_type, self.layer_type)


def _read_csv(path: Path) -> pd.DataFrame | None:
    return pd.read_csv(path) if path.is_file() else None


def _read_json(path: Path) -> dict | list | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


class DashboardData:
    def __init__(self, outputs: Path):
        self.root = Path(outputs)

    # ---------------------------------------------------------------- discovery
    def epochs(self) -> list[str]:
        """Epoch folder names (e.g. 'landsat_2026') that have a classification."""
        d = self.root / "m4"
        return (
            sorted(p.name for p in d.iterdir() if (p / "validation_gate.json").is_file())
            if d.is_dir()
            else []
        )

    def milestone_status(self) -> pd.DataFrame:
        """One row per milestone: what ran and with what result, from manifests and gates."""
        rows = []

        def add(milestone, item, path, status_key="status"):
            data = _read_json(path)
            rows.append(
                {
                    "milestone": milestone,
                    "item": item,
                    "status": (data or {}).get(status_key, "not run")
                    if isinstance(data, dict)
                    else "not run",
                    "recorded": (data or {}).get("created_utc", "")
                    if isinstance(data, dict)
                    else "",
                }
            )

        add("M1", "AOI review", self.root / "m1" / "run_manifest.json")
        add("M2", "Catalog verification", self.root / "m2" / "catalog_manifest.json")
        add("M2", "Image inventory", self.root / "m2" / "inventory_manifest.json")
        add("M3", "Preview gate", self.root / "m3" / "preview" / "preview_gate.json")
        for e in self.epochs() or [None]:
            label = e or "(no epoch)"
            add(
                "M4",
                f"Validation gate {label}",
                self.root / "m4" / (e or "_") / "validation_gate.json",
            )
            add(
                "M6", f"Site selection {label}", self.root / "m6" / (e or "_") / "run_manifest.json"
            )
        add("M7", "Handover", self.root / "m7" / "handover" / "handover_validation.json")
        return pd.DataFrame(rows)

    # ---------------------------------------------------------------- M1 / M2
    def aoi(self) -> dict[str, gpd.GeoDataFrame]:
        path = self.root / "m1" / "m1_aoi.gpkg"
        if not path.is_file():
            return {}
        import pyogrio

        return {name: gpd.read_file(path, layer=name) for name, _ in pyogrio.list_layers(path)}

    def aoi_review(self) -> dict | None:
        return _read_json(self.root / "m1" / "m1_aoi_review.json")

    def catalog_verification(self) -> pd.DataFrame | None:
        return _read_csv(self.root / "m2" / "catalog_verification.csv")

    def inventory_summary(self) -> pd.DataFrame | None:
        return _read_csv(self.root / "m2" / "inventory_summary.csv")

    def image_inventory(self) -> pd.DataFrame | None:
        return _read_csv(self.root / "m2" / "image_inventory.csv")

    # ---------------------------------------------------------------- M4
    def validation_gate(self, epoch: str) -> dict | None:
        return _read_json(self.root / "m4" / epoch / "validation_gate.json")

    def accuracy(self, epoch: str) -> pd.DataFrame | None:
        return _read_csv(self.root / "m4" / epoch / "classification_accuracy.csv")

    def confusion(self, epoch: str) -> pd.DataFrame | None:
        p = self.root / "m4" / epoch / "confusion_matrix.csv"
        return pd.read_csv(p, index_col=0) if p.is_file() else None

    # ---------------------------------------------------------------- M5
    def annual_metrics(self) -> pd.DataFrame | None:
        return _read_csv(self.root / "m5" / "annual_metrics.csv")

    def trend_tests(self) -> pd.DataFrame | None:
        return _read_csv(self.root / "m5" / "trend_tests.csv")

    def change_summaries(self) -> pd.DataFrame | None:
        rows = []
        for p in (
            sorted((self.root / "m5").glob("change_*.tif")) if (self.root / "m5").is_dir() else []
        ):
            with rasterio.open(p) as src:
                t = src.tags()
            rows.append(
                {
                    "file": p.name,
                    "from_year": int(t["extra_from_year"]),
                    "to_year": int(t["extra_to_year"]),
                    "gain_km2": float(t["extra_mangrove_gain_km2"]),
                    "loss_km2": float(t["extra_mangrove_loss_km2"]),
                }
            )
        return pd.DataFrame(rows) if rows else None

    def raster_layers(self, epoch: str) -> list[RasterLayer]:
        out = []
        for folder, fname, band, label in LAYER_FILES:
            path = self.root / folder.format(epoch=epoch) / fname
            if not path.is_file():
                continue
            with rasterio.open(path) as src:
                names = list(src.descriptions)
                if band not in names:
                    continue
                tags = src.tags()
                out.append(
                    RasterLayer(
                        label,
                        path,
                        band,
                        epoch,
                        tags.get("layer_type", ""),
                        tags.get("status", ""),
                        src.tags(names.index(band) + 1).get("units", ""),
                        abs(src.transform.a),
                        tags.get("description", ""),
                    )
                )
        return out

    def layer_availability(self, epoch: str) -> list[dict] | None:
        data = _read_json(self.root / "m5" / epoch / "layers.json")
        return data if isinstance(data, list) else None

    # ---------------------------------------------------------------- M6
    def site_metrics(self, epoch: str) -> pd.DataFrame | None:
        return _read_csv(self.root / "m6" / epoch / "site_metrics.csv")

    def candidate_scores(self, epoch: str) -> pd.DataFrame | None:
        return _read_csv(self.root / "m6" / epoch / "candidate_site_scores.csv")

    def site_comparison(self, epoch: str) -> pd.DataFrame | None:
        return _read_csv(self.root / "m6" / epoch / "site_comparison.csv")

    def site_geometries(self, epoch: str) -> dict[str, gpd.GeoDataFrame]:
        path = self.root / "m6" / epoch / "sites.gpkg"
        if not path.is_file():
            return {}
        import pyogrio

        return {name: gpd.read_file(path, layer=name) for name, _ in pyogrio.list_layers(path)}

    def selection_report(self, epoch: str) -> str | None:
        p = self.root / "m6" / epoch / "selection_report.md"
        return p.read_text(encoding="utf-8") if p.is_file() else None

    # ---------------------------------------------------------------- downloads
    def downloadable_files(self) -> pd.DataFrame:
        rows = []
        if self.root.is_dir():
            for p in sorted(self.root.rglob("*")):
                if (
                    p.suffix.lower() in (".csv", ".tif", ".gpkg", ".md", ".json", ".qgz")
                    and p.is_file()
                ):
                    rows.append(
                        {
                            "path": str(p.relative_to(self.root)),
                            "kind": p.suffix[1:],
                            "bytes": p.stat().st_size,
                        }
                    )
        return pd.DataFrame(rows, columns=["path", "kind", "bytes"])


# ---------------------------------------------------------------- site helpers (pure)


def site_rows(site_metrics: pd.DataFrame, plot_id: str) -> pd.DataFrame:
    """Rows of site_metrics for one plot (a plot can be a site and an alternative)."""
    return site_metrics[site_metrics["plot_id"] == plot_id]


def selectable_sites(site_metrics: pd.DataFrame) -> pd.DataFrame:
    """Selected sites first, then alternatives in score order, with a display label."""
    order = {"site_a": 0, "site_b": 1, "site_a_alternative": 2, "site_b_alternative": 3}
    df = site_metrics.copy()
    df["_o"] = df["role"].map(order)
    df["score"] = df["site_a_score"].fillna(df["site_b_score"])
    df = df.sort_values(["_o", "score"], ascending=[True, False]).drop(columns="_o")
    names = {
        "site_a": "Site A (selected)",
        "site_b": "Site B (selected)",
        "site_a_alternative": "Site A alternative",
        "site_b_alternative": "Site B alternative",
    }
    df["label"] = df["role"].map(names) + " - " + df["plot_id"]
    return df


def class_proportions(
    landcover_path: Path,
    plot: gpd.GeoSeries | gpd.GeoDataFrame,
    classes: dict[int, str],
    nodata_class: int,
) -> pd.DataFrame:
    """Share of each land-cover class among valid pixels whose centres fall in the plot."""
    with rasterio.open(landcover_path) as src:
        geom = plot.geometry.iloc[0] if hasattr(plot, "geometry") else plot
        inside = ~geometry_mask([geom], (src.height, src.width), src.transform)
        vals = src.read(1)[inside]
    vals = vals[vals != nodata_class]
    total = vals.size
    return pd.DataFrame(
        [
            {
                "class_code": c,
                "class_name": n,
                "share": float((vals == c).sum() / total) if total else np.nan,
                "n_pixels": int((vals == c).sum()),
            }
            for c, n in classes.items()
            if c != nodata_class
        ]
    )


COMPARISON_UNITS = {
    "mangrove_cover": "fraction",
    "high_vigour_fraction": "fraction of mangrove",
    "salinity_percentile_mean": "percentile (proxy)",
    "eligible_bare_fraction": "fraction",
    "inundation_frequency_mean": "fraction of observations",
    "channel_distance_km_min": "km",
    "classification_margin_mean": "RF margin (0-1)",
}


def compare_plots(scores: pd.DataFrame, plot_a: str, plot_b: str) -> pd.DataFrame:
    """Metrics of two candidate plots side by side, from candidate_site_scores.csv."""
    s = scores.set_index("plot_id")
    rows = []
    for m in COMPARISON_UNITS:
        if m not in s.columns:
            continue
        va, vb = s.at[plot_a, m], s.at[plot_b, m]
        rows.append(
            {
                "metric": m,
                "units": COMPARISON_UNITS[m],
                "site_a": va,
                "site_b": vb,
                "difference": va - vb if pd.notna(va) and pd.notna(vb) else np.nan,
            }
        )
    return pd.DataFrame(rows)
