"""Small-area preview (M2/M3): composites for one season over a box around the reference
point, downloaded and checked locally. Writes the preview gate."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from indus_delta import aoi as aoi_mod
from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.gate import gate_status, write_gate
from indus_delta.grid import aligned_box, grid_offset
from indus_delta.manifest import write_manifest
from indus_delta.preview_checks import PreviewExpectation, check_preview
from indus_delta.seasons import SeasonWindow, season_window

log = logging.getLogger(__name__)


def latest_complete_window(cfgs: Configs, season: str, today: date) -> SeasonWindow:
    scfg = cfgs.project.seasons[season]
    year = today.year + 1
    while True:
        w = season_window(season, scfg, year)
        if w.end <= today:
            return w
        year -= 1


def run_preview(
    cfgs: Configs, out_root: Path, today: date | None = None, command: str = "indus-delta preview"
) -> tuple[str, list[Check], Path]:
    import ee

    from indus_delta.earthengine import composite as comp
    from indus_delta.earthengine import prep
    from indus_delta.earthengine.download import download_geotiff
    from indus_delta.earthengine.util import to_ee_geometry, with_retries

    today = today or datetime.now(UTC).date()
    pp = cfgs.preprocessing
    epsg = cfgs.project.crs.analysis_epsg
    out_dir = out_root / "m3" / "preview"
    out_dir.mkdir(parents=True, exist_ok=True)

    ref = aoi_mod.reference_point(cfgs.project).geometry.iloc[0]
    half = pp.preview.half_size_m
    if pp.preview.label_year:
        w = season_window(
            pp.preview.season, cfgs.project.seasons[pp.preview.season], pp.preview.label_year
        )
    else:
        w = latest_complete_window(cfgs, pp.preview.season, today)
    completeness = w.completeness(today)
    box_gdf = gpd.GeoDataFrame(
        geometry=[box(ref.x - half, ref.y - half, ref.x + half, ref.y + half)], crs=epsg
    )
    region = to_ee_geometry(box_gdf)
    checks: list[Check] = [
        Check(
            "preview_window",
            "PASS" if completeness == "complete" else "WARN",
            f"{w.season} {w.label_year}: {w.start}..{w.end - timedelta(days=1)} ({completeness})",
        )
    ]
    meta: dict = {
        "window": {
            "season": w.season,
            "label_year": w.label_year,
            "start": w.start.isoformat(),
            "end_inclusive": (w.end - timedelta(days=1)).isoformat(),
            "completeness": completeness,
        },
        "box_half_size_m": half,
        "tide_status": "unavailable",
        "landsat_harmonisation": pp.landsat.harmonisation,
        "products": {},
    }
    files: list[Path] = []

    def native_offset(raw_col, band: str, scale: float, label: str):
        info = with_retries(
            lambda: ee.Image(raw_col.first()).select(band).projection().getInfo(),
            f"{label} native projection",
        )
        crs, tf = info.get("crs"), info.get("transform")
        if crs != f"EPSG:{epsg}":
            checks.append(
                Check(
                    f"{label}_native_crs",
                    "WARN",
                    f"native CRS {crs} differs from EPSG:{epsg}; grid offset 0 used",
                )
            )
            return (0.0, 0.0), info
        off = grid_offset(tf, scale)
        checks.append(
            Check(f"{label}_native_crs", "PASS", f"native {crs}, transform {tf}; grid offset {off}")
        )
        return off, info

    def run_product(label, kind, col, raw_col, native_band, scale, image_fn, bands):
        n = with_retries(lambda: col.size().getInfo(), f"{label} image count")
        if n == 0:
            checks.append(
                Check(
                    f"{label}_images",
                    "FAIL",
                    f"no usable images in {w.season} {w.label_year} over the preview box",
                )
            )
            return
        summary = with_retries(lambda: comp.collection_summary(col), f"{label} summary")
        checks.append(
            Check(
                f"{label}_images",
                "PASS",
                f"{n} images {summary['first_date']}..{summary['last_date']} "
                f"from {summary['datasets'] or [label]}",
            )
        )
        offset, native = native_offset(raw_col, native_band, scale, label)
        tf, width, height = aligned_box(ref.x, ref.y, half, scale, offset)
        path = out_dir / f"{label}_{w.season}_{w.label_year}_preview_epsg{epsg}_{scale:g}m.tif"
        download_geotiff(
            image_fn(col),
            path,
            epsg=epsg,
            transform=tf,
            width=width,
            height=height,
            band_names=bands,
            nodata=pp.composites.nodata_value,
        )
        files.append(path)
        exp = PreviewExpectation(label, kind, epsg, scale, tf, width, height, bands, offset)
        checks.extend(check_preview(path, exp, cfgs))
        meta["products"][label] = {
            "file": path.name,
            "scale_m": scale,
            "grid_offset": offset,
            "native_projection": native,
            "composite": summary,
        }

    end = w.end - timedelta(days=1)
    # Landsat 30 m
    lcol = comp.landsat_window_collection(cfgs, region, w)
    lraw = None
    for key in pp.landsat.members:
        s, e = cfgs.datasets.datasets[key].requested_window(end)
        if max(s, w.start) <= min(e, end):
            raw = prep.landsat_raw(cfgs, key, region, max(s, w.start), min(e, end))
            lraw = raw if lraw is None else lraw.merge(raw)
    if lraw is not None:
        run_product(
            "landsat",
            "optical",
            lcol,
            lraw,
            "QA_PIXEL",
            pp.composites.landsat_scale_m,
            lambda c: comp.optical_composite(c, cfgs),
            comp.optical_band_names(cfgs),
        )
    else:
        checks.append(Check("landsat_images", "FAIL", "no Landsat dataset covers the window"))
    # Sentinel-2 / Sentinel-1 only within the recent series.
    if w.label_year >= cfgs.project.periods.sentinel.start_year:
        scol = comp.s2_window_collection(cfgs, region, w)
        run_product(
            "sentinel2",
            "optical",
            scol,
            prep.s2_raw(cfgs, region, w.start, end),
            "B2",
            pp.composites.sentinel2_scale_m,
            lambda c: comp.optical_composite(c, cfgs),
            comp.optical_band_names(cfgs),
        )
        meta["sentinel2_effective_resolution_m"] = {
            name: cfgs.indices.effective_resolution_m(pp.sentinel2.index_sensor, name)
            for name in cfgs.indices.indices
        }
        orbit_pass = pp.sentinel1.orbit_pass
        if orbit_pass is None:
            base = prep.s1_prepared(cfgs, region, w.start, end, None)
            hist = with_retries(
                lambda: base.aggregate_histogram("orbitProperties_pass").getInfo(),
                "sentinel1 pass histogram",
            )
            orbit_pass = max(hist, key=hist.get) if hist else None
            checks.append(
                Check(
                    "sentinel1_orbit_pass",
                    "WARN",
                    f"orbit_pass not configured; preview used {orbit_pass} "
                    f"(acquisitions by pass: {hist}). Fix it in "
                    "configs/preprocessing.yaml before full processing.",
                )
            )
        s1col = prep.s1_prepared(cfgs, region, w.start, end, orbit_pass)
        run_product(
            "sentinel1",
            "sar",
            s1col,
            s1col,
            pp.sentinel1.polarisations[0],
            pp.composites.sentinel1_scale_m,
            lambda c: comp.s1_composite(c, cfgs),
            comp.s1_band_names(cfgs),
        )
        meta["sentinel1_orbit_pass"] = orbit_pass

    status = gate_status(checks)
    meta["files"] = [p.name for p in files]
    gate = write_gate(out_dir, cfgs, checks, meta)
    quicklook = _quicklook(out_dir, files)
    report = out_dir / "preview_report.json"
    report.write_text(
        json.dumps(
            {"status": status, "checks": [c.to_dict() for c in checks], "metadata": meta},
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    write_manifest(
        out_dir / "run_manifest.json",
        milestone="M3-preview",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[{"datasets": {k: v.ee_id for k, v in cfgs.datasets.datasets.items() if v.ee_id}}],
        outputs=[*files, gate, report, *([quicklook] if quicklook else [])],
        status=status,
    )
    return status, checks, out_dir


def _quicklook(out_dir: Path, files: list[Path]) -> Path | None:
    """Side-by-side display of each preview (inspection aid, no analysis)."""
    if not files:
        return None
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio

    fig, axes = plt.subplots(len(files), 3, figsize=(12, 4 * len(files)), squeeze=False)
    for row, path in zip(axes, files, strict=True):
        with rasterio.open(path) as src:
            names = list(src.descriptions)
            arr = {n: src.read(i + 1, masked=True) for i, n in enumerate(names)}
        if "red" in arr:
            rgb = np.dstack([arr[b].filled(np.nan) for b in ("red", "green", "blue")])
            lo, hi = np.nanpercentile(rgb, [2, 98])
            row[0].imshow(np.clip((rgb - lo) / (hi - lo), 0, 1))
            row[0].set_title(f"{path.stem}\nRGB (2-98% stretch)", fontsize=8)
            im = row[1].imshow(arr["ndvi"], cmap="RdYlGn", vmin=-1, vmax=1)
            row[1].set_title("NDVI", fontsize=8)
        else:
            first = names[0]
            im0 = row[0].imshow(arr[first], cmap="gray")
            row[0].set_title(f"{path.stem}\n{first} (dB)", fontsize=8)
            fig.colorbar(im0, ax=row[0], fraction=0.046)
            im = row[1].imshow(arr[names[1]], cmap="gray")
            row[1].set_title(f"{names[1]} (dB)", fontsize=8)
        fig.colorbar(im, ax=row[1], fraction=0.046)
        im2 = row[2].imshow(arr["valid_obs"], cmap="viridis")
        row[2].set_title("valid observations", fontsize=8)
        fig.colorbar(im2, ax=row[2], fraction=0.046)
        for ax in row:
            ax.set_xticks([])
            ax.set_yticks([])
    fig.tight_layout()
    path = out_dir / "preview_quicklook.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path
