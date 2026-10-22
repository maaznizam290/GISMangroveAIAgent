"""Milestone M7: GIS handover package and its validation.

The package collects whatever pipeline outputs exist for one epoch, converts rasters to
Cloud Optimized GeoTIFF, merges vectors into one GeoPackage, copies the required tables and
reports, writes a data dictionary, methods report, limitations and processing history,
builds a QGIS project, and validates every delivered file against its source.

Status:
  COMPLETE    every required deliverable is present and every check passes
  INCOMPLETE  checks pass for what exists, but required deliverables are missing
  FAIL        a delivered file failed validation
"""

from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import stat
import subprocess
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.shutil import copy as rio_copy
from rio_cogeo.cogeo import cog_validate

from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.manifest import git_revision, sha256, software_versions
from indus_delta.reporting import md_table

log = logging.getLogger(__name__)

HIDDEN_BY_DEFAULT = {
    "jrc_water_components",
    "aoi_alternatives",
    "coarse_indus_centerline",
    "candidate_plots",
    "composite_post_monsoon",
    "classification_uncertainty",
}

REQUIRED_RASTER_TAGS = (
    "handover_id",
    "layer_type",
    "status",
    "description",
    "source_file",
    "source_sha256",
)


@dataclass
class Item:
    id: str
    kind: str  # raster / vector / table / document / generated
    required: bool
    source: str | None
    target: str | None = None
    status: str = "missing"  # delivered / missing
    note: str = ""
    checks: list[Check] = field(default_factory=list)


# --------------------------------------------------------------------------- source lookup


def resolve(
    out_root: Path, template: str, series: str, year: int, composites_dir: Path | None = None
) -> Path | None:
    """Newest file matching the template; relative templates are under out_root."""
    pattern = template.format(
        series=series, year=year, from_year="*", composites_dir=composites_dir or ""
    )
    base = Path(pattern) if "{composites_dir}" in template else out_root / pattern
    matches = sorted(glob.glob(str(base)))
    return Path(matches[-1]) if matches else None


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path)


# --------------------------------------------------------------------------- rasters


def deliver_raster(src: Path, dst: Path, handover_tags: dict[str, str]) -> None:
    """Copy to COG without resampling the data; overviews use nearest neighbour."""
    with rasterio.open(src) as s, tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "staged.tif"
        profile = s.profile.copy()
        profile.update(
            driver="GTiff", tiled=True, blockxsize=256, blockysize=256, compress="deflate"
        )
        with rasterio.open(tmp_path, "w", **profile) as t:
            t.write(s.read())
            tags = s.tags()
            tags.update({k: v for k, v in handover_tags.items() if v is not None})
            t.update_tags(**tags)
            for i in range(1, s.count + 1):
                t.set_band_description(i, s.descriptions[i - 1] or f"band_{i}")
                band_tags = s.tags(i)
                if "units" not in band_tags and handover_tags.get("units"):
                    band_tags["units"] = handover_tags["units"]
                if band_tags:
                    t.update_tags(i, **band_tags)
        dst.parent.mkdir(parents=True, exist_ok=True)
        rio_copy(
            tmp_path,
            dst,
            driver="COG",
            COMPRESS="DEFLATE",
            BLOCKSIZE=256,
            OVERVIEW_RESAMPLING="NEAREST",
            RESAMPLING="NEAREST",
        )


def validate_raster(src: Path, dst: Path, epsg: int, native_resolution: float) -> list[Check]:
    p = f"{dst.name}: "
    checks = []

    def add(name, ok, detail):
        checks.append(Check(name, "PASS" if ok else "FAIL", p + detail))

    with rasterio.open(src) as s, rasterio.open(dst) as d:
        add(
            "raster_crs",
            d.crs is not None and d.crs.to_epsg() == epsg,
            f"CRS {d.crs} (expected EPSG:{epsg})",
        )
        add(
            "raster_dimensions",
            (d.width, d.height, d.count) == (s.width, s.height, s.count),
            f"{d.width}x{d.height}x{d.count} (source {s.width}x{s.height}x{s.count})",
        )
        add(
            "raster_transform",
            d.transform.almost_equals(s.transform),
            f"transform {tuple(d.transform)[:6]}",
        )
        px = abs(d.transform.a)
        add(
            "raster_not_upsampled",
            px >= native_resolution - 1e-6 and np.isclose(abs(d.transform.e), px),
            f"pixel {px} m; native resolution of the source {native_resolution} m",
        )
        add(
            "raster_nodata",
            d.nodata is not None and d.nodata == s.nodata,
            f"nodata {d.nodata} (source {s.nodata})",
        )
        # Structural validation (tiling, overview order, IFD placement), not the LAYOUT tag,
        # which stays "COG" even after an in-place edit breaks the layout.
        cog_ok, cog_errors, _ = cog_validate(str(dst), quiet=True)
        add(
            "raster_cog_layout", cog_ok, "valid COG" if cog_ok else f"not a valid COG: {cog_errors}"
        )
        tags = d.tags()
        missing = [t for t in REQUIRED_RASTER_TAGS if not tags.get(t)]
        add(
            "raster_metadata",
            not missing,
            "required tags present" if not missing else f"missing tags {missing}",
        )
        desc = list(d.descriptions)
        add(
            "raster_band_descriptions",
            all(desc) and desc == [x or f"band_{i + 1}" for i, x in enumerate(s.descriptions)],
            f"bands {desc}",
        )
        no_units = [desc[i] for i in range(d.count) if not d.tags(i + 1).get("units")]
        add(
            "raster_band_units",
            not no_units,
            "units on every band" if not no_units else f"bands without units {no_units}",
        )
        same = True
        for i in range(1, s.count + 1):
            a, b = s.read(i, masked=True), d.read(i, masked=True)
            if not (
                np.array_equal(np.ma.getmaskarray(a), np.ma.getmaskarray(b))
                and np.array_equal(a.compressed(), b.compressed())
            ):
                same = False
                break
        add("raster_content_identical", same, "pixel values and nodata mask equal the source")
    return checks


# --------------------------------------------------------------------------- vectors


def validate_vector(
    src_gdf: gpd.GeoDataFrame, package: Path, layer: str, epsg: int, plot_size: float | None
) -> list[Check]:
    d = gpd.read_file(package, layer=layer)
    p = f"{package.name}:{layer}: "
    checks = [
        Check(
            "vector_crs",
            "PASS" if d.crs and d.crs.to_epsg() == epsg else "FAIL",
            p + f"CRS {d.crs}",
        ),
        Check(
            "vector_feature_count",
            "PASS" if len(d) == len(src_gdf) else "FAIL",
            p + f"{len(d)} features (source {len(src_gdf)})",
        ),
        Check(
            "vector_geometry_valid",
            "PASS" if d.geometry.is_valid.all() else "FAIL",
            p + f"{int((~d.geometry.is_valid).sum())} invalid geometries",
        ),
        Check(
            "vector_fields",
            "PASS" if set(src_gdf.columns) <= set(d.columns) else "FAIL",
            p + f"fields {sorted(set(d.columns) - {'geometry'})}",
        ),
    ]
    if plot_size is not None and len(d):
        ok = np.allclose(d.geometry.area, plot_size**2, rtol=1e-6)
        checks.append(
            Check(
                "vector_plot_size",
                "PASS" if ok else "FAIL",
                p + f"all plots {plot_size:g} m x {plot_size:g} m",
            )
        )
    return checks


# --------------------------------------------------------------------------- QGIS

STYLE_SPECS = {
    "occurrence": {
        "type": "pseudocolor",
        "min": 0,
        "max": 100,
        "colors": ["#f7fbff", "#6baed6", "#08306b"],
    },
    "rgb": {"type": "rgb", "red": 3, "green": 2, "blue": 1, "min": 0.0, "max": 0.3},
    "margin": {
        "type": "pseudocolor",
        "band": 2,
        "min": 0,
        "max": 1,
        "colors": ["#d7191c", "#ffffbf", "#1a9641"],
    },
    "mangrove": {
        "type": "paletted",
        "band": 1,
        "classes": [
            {"value": 0, "color": "#f0f0f0", "label": "not mangrove"},
            {"value": 1, "color": "#1b7837", "label": "mangrove"},
        ],
    },
    "frequency": {
        "type": "pseudocolor",
        "min": 0,
        "max": 1,
        "colors": ["#ffffcc", "#41b6c4", "#253494"],
    },
    "percentile": {
        "type": "pseudocolor",
        "min": 0,
        "max": 100,
        "colors": ["#ffffd4", "#fe9929", "#993404"],
    },
    "distance": {
        "type": "pseudocolor",
        "band": 2,
        "min": 0,
        "max": 30,
        "colors": ["#08519c", "#9ecae1", "#f7fbff"],
    },
    "change": {
        "type": "paletted",
        "band": 2,
        "classes": [
            {"value": -1, "color": "#d73027", "label": "mangrove loss"},
            {"value": 0, "color": "#e0e0e0", "label": "no mangrove change"},
            {"value": 1, "color": "#1a9850", "label": "mangrove gain"},
        ],
    },
    "point": {"type": "marker", "color": "#000000", "size": 2.0},
    "point_val": {"type": "marker", "color": "#e7298a", "size": 2.0, "shape": "triangle"},
    "aoi": {"type": "fill", "fill": "none", "outline": "#d7301f", "width": 0.8},
    "aoi_alt": {
        "type": "fill",
        "fill": "none",
        "outline": "#555555",
        "width": 0.4,
        "outline_style": "dash",
    },
    "water": {"type": "fill", "fill": "#4292c680", "outline": "#2171b5", "width": 0.1},
    "river": {"type": "line", "color": "#8c510a", "width": 0.6},
    "plots": {"type": "fill", "fill": "none", "outline": "#969696", "width": 0.2},
    "site_a": {"type": "fill", "fill": "#fdae6b99", "outline": "#e6550d", "width": 1.0},
    "site_b": {"type": "fill", "fill": "#74c47699", "outline": "#238b45", "width": 1.0},
    "alternatives": {
        "type": "fill",
        "fill": "none",
        "outline": "#3f007d",
        "width": 0.6,
        "outline_style": "dash",
    },
}


def style_for(key: str, cfgs: Configs) -> dict:
    if key == "landcover":
        cl = cfgs.classification
        return {
            "type": "paletted",
            "band": 1,
            "classes": [
                {"value": cl.code_of(n), "color": c, "label": n}
                for n, c in cfgs.handover.landcover_colours.items()
            ],
        }
    if key == "none":
        return STYLE_SPECS["rgb"]
    return STYLE_SPECS.get(key, {})


def resolve_qgis_python(configured: str | None) -> str | None:
    """Interpreter with PyQGIS: $QGIS_PYTHON, then qgis.python from the config, then the
    python-qgis launcher of a standard Windows QGIS install. None when none exists."""
    for cand in (os.environ.get("QGIS_PYTHON"), configured):
        if cand and (Path(cand).is_file() or shutil.which(cand)):
            return cand
    if os.name == "nt":
        roots = [os.environ.get("PROGRAMFILES", r"C:\Program Files"), r"C:\OSGeo4W"]
        for root in roots:
            hits = sorted(glob.glob(os.path.join(root, "QGIS*", "bin", "python-qgis*.bat")))
            hits += sorted(glob.glob(os.path.join(root, "bin", "python-qgis*.bat")))
            if hits:
                return hits[-1]
    return None


def build_qgis_project(spec: dict, pkg: Path, python: str) -> dict:
    spec_path = pkg / "qgis" / "project_spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2), encoding="utf-8")
    script = Path(__file__).with_name("qgis_builder.py")
    env = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
    try:
        proc = subprocess.run(
            [python, str(script), str(spec_path)],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"error": f"could not run PyQGIS with {python}: {exc}"}
    result_path = Path(spec["result_path"])
    if not result_path.is_file():
        return {
            "error": f"PyQGIS produced no result (exit {proc.returncode}): {proc.stderr[-2000:]}"
        }
    return json.loads(result_path.read_text(encoding="utf-8"))


def stored_datasources(project_path: Path) -> list[str]:
    """Datasource strings exactly as stored in the saved .qgz/.qgs file."""
    import re
    import zipfile

    if project_path.suffix == ".qgz":
        with zipfile.ZipFile(project_path) as z:
            name = next(n for n in z.namelist() if n.endswith(".qgs"))
            xml = z.read(name).decode("utf-8")
    else:
        xml = project_path.read_text(encoding="utf-8")
    return re.findall(r"<datasource>([^<]*)</datasource>", xml)


def validate_qgis(
    result: dict, expected_layers: list[str], epsg: int, project_path: Path
) -> list[Check]:
    if "error" in result:
        return [Check("qgis_project", "FAIL", result["error"][-1500:])]
    v = result["validation"]
    names = [lyr["name"] for lyr in v["layers"]]
    invalid = [lyr["name"] for lyr in v["layers"] if not lyr["valid"]]
    wrong_crs = [lyr["name"] for lyr in v["layers"] if lyr["crs"] != f"EPSG:{epsg}"]
    stored = stored_datasources(project_path) if project_path.is_file() else []
    absolute = [d for d in stored if d.startswith("/") or ":\\" in d[:3]]
    items = set(v["layout_item_types"])
    return [
        Check(
            "qgis_project_reopens",
            "PASS" if v["read_ok"] else "FAIL",
            f"QGIS {result['qgis_version']} reopened the saved project",
        ),
        Check(
            "qgis_project_crs",
            "PASS" if v["project_crs"] == f"EPSG:{epsg}" else "FAIL",
            f"project CRS {v['project_crs']}",
        ),
        Check(
            "qgis_layers_load",
            "PASS" if not invalid and sorted(names) == sorted(expected_layers) else "FAIL",
            f"{len(names)} layers loaded; invalid {invalid}; "
            f"missing {sorted(set(expected_layers) - set(names))}",
        ),
        Check(
            "qgis_layer_crs",
            "PASS" if not wrong_crs else "FAIL",
            f"layers not in EPSG:{epsg}: {wrong_crs}",
        ),
        Check(
            "qgis_relative_paths",
            "PASS" if stored and not v["absolute_paths"] and not absolute else "FAIL",
            f"{len(stored)} stored datasources; absolute: {absolute[:3]}",
        ),
        Check(
            "qgis_layout",
            "PASS"
            if v["layout_found"]
            and {
                "QgsLayoutItemMap",
                "QgsLayoutItemLegend",
                "QgsLayoutItemScaleBar",
                "QgsLayoutItemLabel",
            }
            <= items
            else "FAIL",
            f"layout items {sorted(items)}",
        ),
    ]


# --------------------------------------------------------------------------- documents


def data_dictionary(pkg: Path, items: list[Item], vector_package: Path) -> pd.DataFrame:
    rows = []
    for it in items:
        if it.status != "delivered" or not it.target:
            continue
        path = pkg / it.target
        if it.kind == "raster":
            with rasterio.open(path) as d:
                tags = d.tags()
                for i in range(1, d.count + 1):
                    rows.append(
                        {
                            "file": it.target,
                            "item": it.id,
                            "kind": "raster band",
                            "name": d.descriptions[i - 1],
                            "units": d.tags(i).get("units", ""),
                            "layer_type": tags.get("layer_type", ""),
                            "status": tags.get("status", ""),
                            "nodata": d.nodata,
                            "pixel_size_m": abs(d.transform.a),
                            "crs": str(d.crs),
                            "description": tags.get("description", ""),
                        }
                    )
        elif it.kind == "vector":
            g = gpd.read_file(vector_package, layer=it.id, rows=1)
            for col, dtype in g.dtypes.items():
                rows.append(
                    {
                        "file": f"{vector_package.name}:{it.id}",
                        "item": it.id,
                        "kind": "vector field",
                        "name": col,
                        "units": "",
                        "layer_type": "",
                        "status": "",
                        "nodata": None,
                        "pixel_size_m": None,
                        "crs": str(g.crs),
                        "description": str(dtype),
                    }
                )
        elif it.kind == "table":
            df = pd.read_csv(path, nrows=50)
            for col, dtype in df.dtypes.items():
                rows.append(
                    {
                        "file": it.target,
                        "item": it.id,
                        "kind": "table column",
                        "name": col,
                        "units": "",
                        "layer_type": "",
                        "status": "",
                        "nodata": None,
                        "pixel_size_m": None,
                        "crs": "",
                        "description": str(dtype),
                    }
                )
    return pd.DataFrame(rows)


def processing_history(out_root: Path) -> pd.DataFrame:
    rows = []
    for p in sorted(out_root.rglob("*manifest*.json")):
        if "handover" in p.parts:
            continue
        try:
            m = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        rows.append(
            {
                "manifest": str(p.relative_to(out_root)),
                "milestone": m.get("milestone"),
                "command": m.get("command"),
                "created_utc": m.get("created_utc"),
                "status": m.get("status"),
                "git_revision": m.get("git_revision"),
                "n_outputs": len(m.get("outputs", [])),
            }
        )
    return pd.DataFrame(rows).sort_values("created_utc") if rows else pd.DataFrame()


def unresolved_assumptions(protocol: Path) -> str:
    text = protocol.read_text(encoding="utf-8") if protocol.is_file() else ""
    lines = [ln for ln in text.splitlines() if ln.startswith("| U")]
    header = (
        "| ID | Assumption or open question | Why it matters | How to resolve | Milestone |\n"
        "|---|---|---|---|---|"
    )
    return header + "\n" + "\n".join(lines) if lines else "(study protocol not found)"


# --------------------------------------------------------------------------- orchestration


def _rmtree(path: Path) -> None:
    """shutil.rmtree that also removes entries carrying the Windows read-only attribute
    (RemoveDirectory refuses them with 'Access is denied')."""

    def clear_readonly(func, p, exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onexc=clear_readonly)


def build_handover(
    cfgs: Configs,
    out_root: Path,
    series: str,
    year: int,
    repo_root: Path = Path("."),
    command: str = "indus-delta handover",
) -> tuple[str, list[Item], Path]:
    ho = cfgs.handover
    epsg = cfgs.project.crs.analysis_epsg
    pkg = out_root / ho.package_dir
    if pkg.exists():
        _rmtree(pkg)
    for sub in ("rasters", "vectors", "tables", "docs", "qgis", "config"):
        (pkg / sub).mkdir(parents=True)
    items: list[Item] = []
    gpkg = pkg / "vectors" / ho.vector_package

    for spec in ho.rasters:
        src = resolve(out_root, spec.source, series, year, cfgs.classification.composites_dir)
        it = Item(spec.id, "raster", spec.required, spec.source)
        items.append(it)
        if src is None:
            continue
        with rasterio.open(src) as s:
            tags = s.tags()
        target = f"rasters/{spec.id}_epsg{epsg}.tif"
        deliver_raster(
            src,
            pkg / target,
            {
                "handover_id": spec.id,
                "source_file": _rel(src, out_root),
                "source_sha256": sha256(src),
                "layer_type": tags.get("layer_type") or spec.layer_type,
                "status": tags.get("status") or spec.status,
                "description": tags.get("description") or spec.description,
                "units": spec.units,
            },
        )
        it.target, it.status = target, "delivered"
        it.checks = validate_raster(src, pkg / target, epsg, spec.native_resolution_m)

    for spec in ho.vectors:
        src = resolve(out_root, spec.source, series, year)
        it = Item(spec.id, "vector", spec.required, f"{spec.source}:{spec.layer}")
        items.append(it)
        if src is None:
            continue
        import pyogrio

        if spec.layer not in {n for n, _ in pyogrio.list_layers(src)}:
            it.note = f"layer {spec.layer} not in {src.name}"
            continue
        g = gpd.read_file(src, layer=spec.layer).to_crs(epsg)
        g.to_file(gpkg, layer=spec.id, driver="GPKG")
        it.target, it.status = f"vectors/{ho.vector_package}", "delivered"
        plot = (
            cfgs.site_selection.plot_size_m
            if spec.id in ("candidate_plots", "site_a", "site_b")
            else None
        )
        it.checks = validate_vector(g, gpkg, spec.id, epsg, plot)

    # Alternatives: plots listed as alternatives in site_metrics.csv.
    sm = resolve(out_root, "m6/{series}_{year}/site_metrics.csv", series, year)
    plots_src = resolve(out_root, "m6/{series}_{year}/sites.gpkg", series, year)
    it = Item("site_alternatives", "vector", True, "m6 site_metrics.csv + candidate_plots")
    items.append(it)
    if sm is not None and plots_src is not None:
        metrics = pd.read_csv(sm)
        alts = metrics[metrics["role"].str.endswith("_alternative")][["plot_id", "role"]]
        plots = gpd.read_file(plots_src, layer="candidate_plots")
        g = plots.merge(alts, on="plot_id").to_crs(epsg)
        g.to_file(gpkg, layer="site_alternatives", driver="GPKG")
        it.target, it.status = f"vectors/{ho.vector_package}", "delivered"
        it.checks = validate_vector(
            g, gpkg, "site_alternatives", epsg, cfgs.site_selection.plot_size_m
        )

    if ho.write_shapefiles and gpkg.is_file():
        import pyogrio

        for name, _ in pyogrio.list_layers(gpkg):
            gpd.read_file(gpkg, layer=name).to_file(pkg / "vectors" / f"{name}.shp")

    for spec in ho.tables:
        src = resolve(out_root, spec.source, series, year)
        it = Item(spec.id, "table", spec.required, spec.source)
        items.append(it)
        if src is None:
            continue
        target = f"tables/{spec.id}.csv"
        shutil.copy2(src, pkg / target)
        it.target, it.status = target, "delivered"
        df = pd.read_csv(pkg / target)
        missing = [c for c in spec.columns if c not in df.columns]
        it.checks = [
            Check(
                "table_columns",
                "FAIL" if missing else "PASS",
                f"{target}: missing columns {missing}" if missing else f"{target}: columns ok",
            ),
            Check(
                "table_identical",
                "PASS" if sha256(src) == sha256(pkg / target) else "FAIL",
                f"{target}: {len(df)} rows, identical to source",
            ),
        ]

    for spec in ho.documents:
        src = resolve(out_root, spec.source, series, year)
        it = Item(spec.id, "document", spec.required, spec.source)
        items.append(it)
        if src is None:
            continue
        target = f"docs/{src.name}"
        shutil.copy2(src, pkg / target)
        it.target, it.status = target, "delivered"
        it.checks = [
            Check("document_nonempty", "PASS" if (pkg / target).stat().st_size else "FAIL", target)
        ]

    # Configuration and generated documentation.
    for f in sorted((repo_root / "configs").glob("*.yaml")):
        shutil.copy2(f, pkg / "config" / f.name)
    for name in ("study_protocol.md", "uncertainty.md", "repository_assessment.md"):
        if (repo_root / "docs" / name).is_file():
            shutil.copy2(repo_root / "docs" / name, pkg / "docs" / name)
    history = processing_history(out_root)
    history.to_csv(pkg / "docs" / "processing_history.csv", index=False)
    versions = software_versions()

    # QGIS project.
    qgis_layers, expected = [], []
    groups = ["Sites", "Analytical layers", "Classification", "Reference", "Inputs"]
    for it2 in items:
        if it2.status != "delivered" or it2.kind not in ("raster", "vector"):
            continue
        if it2.kind == "raster":
            spec = next(s for s in ho.rasters if s.id == it2.id)
            path = f"../{it2.target}"
            style = style_for(spec.style, cfgs)
            with rasterio.open(pkg / it2.target) as d:
                note = (
                    f"{d.tags().get('description', '')} Status: {d.tags().get('status', '')}. "
                    f"Source: {d.tags().get('source_file', '')}."
                )
            group = spec.group
        else:
            spec = next((s for s in ho.vectors if s.id == it2.id), None)
            path = f"../vectors/{ho.vector_package}|layername={it2.id}"
            style = STYLE_SPECS["alternatives"] if spec is None else style_for(spec.style, cfgs)
            group = "Sites" if spec is None else spec.group
            note = f"Source: {it2.source}"
        # Optional context layers start hidden to keep the overview readable.
        visible = it2.id not in HIDDEN_BY_DEFAULT
        qgis_layers.append(
            {
                "name": it2.id,
                "kind": it2.kind,
                "path": path,
                "group": group,
                "style": style,
                "source_note": note,
                "visible": visible,
            }
        )
        expected.append(it2.id)
    # Order: sites first (drawn on top), then analytical layers, classification, reference.
    qgis_layers.sort(key=lambda layer: groups.index(layer["group"]))
    qgis_item = Item("qgis_project", "generated", True, "PyQGIS")
    items.append(qgis_item)
    qgis_result: dict = {}
    qgis_python = resolve_qgis_python(ho.qgis.python) if ho.qgis.enabled else None
    if ho.qgis.enabled and qgis_python is None:
        # Not a failed check: the project is simply not delivered (handover INCOMPLETE).
        qgis_item.note = (
            f"no PyQGIS interpreter found (qgis.python={ho.qgis.python!r}); install QGIS and "
            "set QGIS_PYTHON or qgis.python in configs/handover.yaml"
        )
    elif ho.qgis.enabled:
        project_path = pkg / "qgis" / ho.qgis.project_name
        # PyQGIS resolves the relative layer paths against the project file location.
        spec = {
            "project_path": str(project_path),
            "crs": f"EPSG:{epsg}",
            "title": f"Indus Delta mangrove handover: {series} {year}",
            "groups": groups,
            "layers": qgis_layers,
            "result_path": str(pkg / "qgis" / "qgis_build_result.json"),
            "layout_png": str(pkg / "qgis" / "handover_layout.png"),
            "layout": {
                "name": "Handover overview",
                "title": f"Indus Delta mangrove study, Keti Bandar: {series} {year} "
                "(EPSG:32642, grid north up)",
                "extent_layers": ["aoi_primary"],
                "scalebar_segment_km": 1.0,
                "notes": "Sources: Landsat/Sentinel via Google Earth Engine; JRC Global "
                "Surface Water v1.4; GeoNames reference point (provisional). "
                "Proxy layers are relative and uncalibrated, not salinity "
                "measurements or evidence of freshwater delivery. See docs/.",
            },
        }
        # Layer paths are relative to the qgis/ folder.
        for layer in spec["layers"]:
            rel = layer["path"].split("|")[0]
            layer["path"] = str((pkg / "qgis" / rel).resolve()) + (
                "|" + layer["path"].split("|", 1)[1] if "|" in layer["path"] else ""
            )
        qgis_result = build_qgis_project(spec, pkg, qgis_python)
        qgis_item.checks = validate_qgis(qgis_result, expected, epsg, project_path)
        if "error" not in qgis_result:
            qgis_item.target, qgis_item.status = f"qgis/{ho.qgis.project_name}", "delivered"
            versions["qgis"] = qgis_result.get("qgis_version", "")
    else:
        qgis_item.note = "QGIS project generation disabled in configs/handover.yaml"
    (pkg / "docs" / "software_versions.json").write_text(json.dumps(versions, indent=2))

    # Status and generated reports.
    failed = [c for it2 in items for c in it2.checks if c.status == "FAIL"]
    missing_required = [it2.id for it2 in items if it2.required and it2.status != "delivered"]
    status = "FAIL" if failed else ("INCOMPLETE" if missing_required else "COMPLETE")
    dd = data_dictionary(pkg, items, gpkg)
    dd.to_csv(pkg / "docs" / "data_dictionary.csv", index=False)
    (pkg / "docs" / "data_dictionary.md").write_text(
        "# Data dictionary\n\nGenerated from the delivered files.\n\n" + md_table(dd),
        encoding="utf-8",
    )
    (pkg / "docs" / "limitations.md").write_text(
        _limitations(repo_root, items, status), encoding="utf-8"
    )
    (pkg / "docs" / "methods_report.md").write_text(
        _methods(cfgs, out_root, series, year, items, status, history), encoding="utf-8"
    )
    validation = {
        "status": status,
        "series": series,
        "label_year": year,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_revision": git_revision(),
        "missing_required": missing_required,
        "items": [
            {
                **{k: v for k, v in asdict(it2).items() if k != "checks"},
                "checks": [c.to_dict() for c in it2.checks],
            }
            for it2 in items
        ],
    }
    (pkg / "handover_validation.json").write_text(json.dumps(validation, indent=2))
    (pkg / "handover_validation.md").write_text(_validation_md(validation), encoding="utf-8")
    (pkg / "README.md").write_text(
        _readme(series, year, status, missing_required, ho), encoding="utf-8"
    )
    files = sorted(p for p in pkg.rglob("*") if p.is_file() and p.name != "handover_manifest.json")
    (pkg / "handover_manifest.json").write_text(
        json.dumps(
            {
                "status": status,
                "created_utc": validation["created_utc"],
                "command": command,
                "config_sha256": cfgs.sha256,
                "files": [
                    {
                        "path": str(p.relative_to(pkg)),
                        "sha256": sha256(p),
                        "bytes": p.stat().st_size,
                    }
                    for p in files
                ],
            },
            indent=2,
        )
    )
    return status, items, pkg


def _validation_md(v: dict) -> str:
    lines = [
        f"# Handover validation: {v['series']} {v['label_year']}",
        "",
        f"Status: **{v['status']}**",
        "",
    ]
    if v["missing_required"]:
        lines += ["Missing required deliverables:", ""] + [f"* {m}" for m in v["missing_required"]]
        lines += [""]
    lines += [
        "| Item | Kind | Required | Delivered | Checks passed | Failed checks |",
        "|---|---|---|---|---|---|",
    ]
    for it in v["items"]:
        n_ok = sum(c["status"] == "PASS" for c in it["checks"])
        bad = "; ".join(c["detail"] for c in it["checks"] if c["status"] == "FAIL")
        lines.append(
            f"| {it['id']} | {it['kind']} | {'yes' if it['required'] else 'no'} | "
            f"{it['status']} | {n_ok}/{len(it['checks'])} | {bad} |"
        )
    return "\n".join(lines) + "\n"


def _readme(series, year, status, missing, ho) -> str:
    miss = "\n".join(f"* {m}" for m in missing) or "* none"
    return f"""# Indus Delta mangrove study: GIS handover ({series} {year})

Handover status: **{status}** (see `handover_validation.md`).

Missing required deliverables:

{miss}

## Contents

* `rasters/`: Cloud Optimized GeoTIFFs in EPSG:32642, at the native grid of their source
  (never upsampled). Band names, units, nodata, layer type, validation status and source are
  stored in each file.
* `vectors/{ho.vector_package}`: AOI, reference point, samples, candidate plots, Site A,
  Site B and alternatives, reference water layers (EPSG:32642).
* `tables/`: annual_metrics, site_metrics, classification_accuracy, image_inventory,
  candidate_site_scores and supporting tables.
* `qgis/{ho.qgis.project_name}`: QGIS project (relative paths), with the "Handover overview"
  print layout (map, legend, scale bar, source notes). `handover_layout.png` is a preview.
* `docs/`: methods report, data dictionary, limitations, processing history, software
  versions, study protocol, uncertainty guide, AOI review and run reports.
* `config/`: the configuration used.
* `handover_manifest.json`: SHA-256 of every file.

Open the package by double-clicking `qgis/{ho.qgis.project_name}` in QGIS 3.34 or later.
"""


def _limitations(repo_root: Path, items: list[Item], status: str) -> str:
    unc = repo_root / "docs" / "uncertainty.md"
    missing = [
        f"* {it.id} ({it.source})" for it in items if it.required and it.status != "delivered"
    ]
    return "\n".join(
        [
            "# Limitations",
            "",
            f"Handover status: **{status}**.",
            "",
            "## Deliverables not available",
            "",
            *(missing or ["* none"]),
            "",
            "## Unresolved scientific assumptions (from the study protocol)",
            "",
            unresolved_assumptions(repo_root / "docs" / "study_protocol.md"),
            "",
            "## Interpretation and uncertainty",
            "",
            unc.read_text(encoding="utf-8") if unc.is_file() else "(docs/uncertainty.md missing)",
            "",
        ]
    )


def _methods(cfgs, out_root, series, year, items, status, history) -> str:
    def section(title, body):
        return [f"## {title}", "", body, ""]

    def table_or(path, note, cols=None):
        if path is None or not Path(path).is_file():
            return note
        df = pd.read_csv(path)
        return md_table(df[cols] if cols else df)

    lines = [
        f"# Methods report: {series} {year}",
        "",
        f"Generated from the pipeline outputs. Handover status: **{status}**. Every "
        "section reports only steps that ran; steps that did not run are named as such.",
        "",
    ]
    p = cfgs.project
    lines += section(
        "Study area and CRS",
        (
            f"Reference point {p.reference_location.name} ({p.reference_location.longitude}, "
            f"{p.reference_location.latitude}), status {p.reference_location.verification_status}. "
            f"AOI mode {p.aoi.mode}, buffer {p.aoi.buffer_m} m, operator confirmed: "
            f"{p.aoi.operator_confirmed}. All distances and areas in EPSG:{p.crs.analysis_epsg}."
        ),
    )
    cat = out_root / "m2" / "catalog_verification.csv"
    if cat.is_file():
        df = pd.read_csv(cat)
        summ = df.groupby("status").size().to_dict()
        body = (
            f"Dataset identifiers checked against the official Earth Engine catalog: {summ}. "
            "Failures and warnings:\n\n" + md_table(df[df.status != "PASS"])
        )
    else:
        body = "Not run."
    lines += section("Data verification (M2)", body)
    lines += section(
        "Image inventory (M2)",
        table_or(
            out_root / "m2" / "inventory_summary.csv",
            "Not run (requires Earth Engine credentials).",
        ),
    )
    gate = out_root / "m3" / "preview" / "preview_gate.json"
    lines += section(
        "Preprocessing and preview (M3)",
        (
            f"Preview gate: {json.loads(gate.read_text())['status']}."
            if gate.is_file()
            else "Not run (requires Earth Engine credentials)."
        ),
    )
    acc = resolve(out_root, "m4/{series}_{year}/classification_accuracy.csv", series, year)
    lines += section(
        "Classification and validation (M4)",
        table_or(acc, "Not run (requires composites and operator reference samples).", None),
    )
    lay = resolve(out_root, "m5/{series}_{year}/layers.json", series, year)
    lines += section(
        "Analytical layers (M5)",
        (md_table(pd.DataFrame(json.loads(Path(lay).read_text()))) if lay else "Not run."),
    )
    sel = resolve(out_root, "m6/{series}_{year}/site_comparison.csv", series, year)
    lines += section(
        "Site selection (M6)",
        table_or(sel, "Not run (requires a passed validation gate and confirmed selection rules)."),
    )
    lines += section("Processing history", md_table(history) if not history.empty else "None.")
    return "\n".join(lines)
