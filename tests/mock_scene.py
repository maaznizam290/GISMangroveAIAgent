"""MOCK DATA ONLY: a synthetic landscape with known land cover for end-to-end tests of
M4-M6. Nothing here describes Keti Bandar; the spectra are invented test values."""

from __future__ import annotations

import shutil
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import yaml
from shapely.geometry import Point

from indus_delta.aoi import build_aoi, reference_point
from indus_delta.config import load_configs
from indus_delta.grid import aligned_bounds
from indus_delta.layer_io import Grid, LayerMeta, write_layer
from indus_delta.spectral import compute_index

ROLES = ["blue", "green", "red", "nir", "swir1", "swir2"]
# MOCK spectra per class code (dry season); post-monsoon adds a small offset.
SPECTRA = {
    1: [0.03, 0.05, 0.03, 0.30, 0.12, 0.05],  # mangrove
    2: [0.06, 0.07, 0.05, 0.03, 0.01, 0.005],  # water
    3: [0.08, 0.10, 0.11, 0.15, 0.20, 0.15],  # mudflat
    4: [0.25, 0.28, 0.30, 0.33, 0.38, 0.33],  # bare flat
    5: [0.04, 0.08, 0.06, 0.35, 0.22, 0.12],  # other vegetation
    6: [0.12, 0.13, 0.14, 0.18, 0.22, 0.20],  # built-up
}
WATER_FREQ = {1: 0.3, 2: 0.9, 3: 0.4, 4: 0.05, 5: 0.02, 6: 0.02}


def truth_map(xx: np.ndarray, yy: np.ndarray) -> np.ndarray:
    """Class layout relative to the reference point (metres)."""
    t = np.full(xx.shape, 3, dtype=np.uint8)
    t[(yy > 500) & (yy < 2500) & (xx > -3000) & (xx < 0)] = 1
    t[(yy < -800) & (yy > -2800) & (xx > 500) & (xx < 3000)] = 4
    t[(yy < -800) & (yy > -2800) & (xx > -3200) & (xx < -1200)] = 5
    # Built-up in two patches so that both sample halves (alternating blocks) contain it.
    t[(yy > 600) & (yy < 2400) & (xx > 600) & (xx < 2400)] = 6
    t[(yy > -700) & (yy < 0) & (xx > -4000) & (xx < -1500)] = 6
    t[np.abs(yy - 200) < 150] = 2  # east-west channel
    t[(np.abs(xx + 1500) < 120) & (yy > 200) & (yy < 2600)] = 2  # creek into the mangrove
    return t


def build(
    tmp: Path, *, confirm_acceptance=True, confirm_sites=True, freshwater=True, n_estimators=100
) -> tuple[object, Path]:
    """Write configs, composites, samples and inputs under tmp; return (cfgs, out_root)."""
    repo = Path(__file__).resolve().parents[1]
    cdir = tmp / "configs"
    cdir.mkdir()
    for f in (repo / "configs").glob("*.yaml"):
        shutil.copy(f, cdir / f.name)
    data, out = tmp / "data", tmp / "outputs"

    def edit(name, fn):
        d = yaml.safe_load((cdir / name).read_text())
        fn(d)
        (cdir / name).write_text(yaml.safe_dump(d, sort_keys=False))

    def cls(d):
        d["composites_dir"] = str(data / "composites")
        d["samples"]["reference_path"] = str(data / "reference.gpkg")
        d["samples"]["validation_path"] = str(data / "validation.gpkg")
        d["acceptance"]["operator_confirmed"] = confirm_acceptance
        d["random_forest"]["n_estimators"] = n_estimators
        d["random_forest"]["n_jobs"] = 1

    def lay(d):
        d["tidal_inundation"]["input_dir"] = str(data / "water")
        d["tidal_inundation"]["optical_threshold"] = 0.0
        d["freshwater_influence_proxy"]["source_path"] = str(data / "freshwater_source.gpkg")
        d["water_salinity_field"]["path"] = str(data / "field.csv")

    def sites(d):
        d["operator_confirmed"] = confirm_sites

    edit("classification.yaml", cls)
    edit("layers.yaml", lay)
    edit("site_selection.yaml", sites)
    cfgs = load_configs(cdir)

    ref = reference_point(cfgs.project).geometry.iloc[0]
    aoi = build_aoi(cfgs.project)
    tf, w, h = aligned_bounds(tuple(aoi.total_bounds), 30, (15, 15))
    grid = Grid(tf, w, h, 32642)
    cols, rows = np.meshgrid(np.arange(w), np.arange(h))
    xx = tf.c + (cols + 0.5) * 30 - ref.x
    yy = tf.f - (rows + 0.5) * 30 - ref.y
    truth = truth_map(xx, yy)
    rng = np.random.default_rng(7)
    nodata = cfgs.preprocessing.composites.nodata_value
    for season, shift in (("dry", 0.0), ("post_monsoon", 0.01)):
        bands = {}
        for k, role in enumerate(ROLES):
            base = np.vectorize(lambda c, k=k: SPECTRA[int(c)][k])(truth).astype(float)
            if role == "nir":  # mangrove vigour gradient west -> east
                base = np.where(truth == 1, base + 0.1 * (xx + 3000) / 3000, base)
            bands[role] = np.clip(base + shift + rng.normal(0, 0.01, truth.shape), 0.001, 1)
        allb = dict(bands)
        for name in cfgs.indices.indices:
            allb[name] = compute_index(name, bands, cfgs.indices)
        allb["valid_obs"] = np.full(truth.shape, 12.0)
        write_layer(
            data / "composites" / f"landsat_{season}_2026_epsg32642_30m.tif",
            allb,
            grid,
            LayerMeta(f"MOCK {season}", "mock", "mock", "MOCK composite", []),
            nodata=nodata,
        )
    freq = np.vectorize(WATER_FREQ.get)(truth).astype(float)
    write_layer(
        data / "water" / "landsat_water_frequency_2026_epsg32642_30m.tif",
        {"water_frequency": freq, "n_valid": np.full(truth.shape, 20.0)},
        grid,
        LayerMeta("MOCK water", "mock", "mock", "MOCK", []),
        nodata=nodata,
    )

    # Reference and validation samples come from alternating 2 km blocks (checkerboard),
    # as a spatially separated design would; samples near block edges are later dropped by
    # the 500 m separation rule.
    ax, ay = xx + ref.x, yy + ref.y
    parity = (np.floor(ax / 2000) + np.floor(ay / 2000)).astype(int) % 2

    def draw(n_per_class, seed, block_parity):
        r = np.random.default_rng(seed)
        pts = []
        for code in range(1, 7):
            rr, cc = np.nonzero(
                (truth == code) & (parity == block_parity) & (xx**2 + yy**2 < 4800**2)
            )
            pick = r.choice(rr.size, size=min(n_per_class, rr.size), replace=False)
            for i in pick:
                pts.append((code, tf.c + (cc[i] + 0.5) * 30, tf.f - (rr[i] + 0.5) * 30))
        return pts

    def write_samples(pts, path, prefix):
        gdf = gpd.GeoDataFrame(
            {
                "sample_id": [f"{prefix}{i}" for i in range(len(pts))],
                "class_code": [p[0] for p in pts],
                "label_year": 2026,
                "source": "field_survey",
                "interpreter": "MOCK",
                "observed_date": "2026-01-15",
            },
            geometry=[Point(p[1], p[2]) for p in pts],
            crs=32642,
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(path, driver="GPKG")

    write_samples(draw(150, 1, 0), data / "reference.gpkg", "R")
    write_samples(draw(60, 2, 1), data / "validation.gpkg", "V")
    if freshwater:
        src = gpd.GeoDataFrame(
            {
                "source_id": ["MOCK1"],
                "description": ["MOCK channel inflow"],
                "evidence": ["MOCK"],
                "evidence_reference": ["MOCK"],
                "valid_from": ["2020-01-01"],
            },
            geometry=[Point(ref.x + 4500, ref.y + 200)],
            crs=32642,
        )
        src.to_file(data / "freshwater_source.gpkg", driver="GPKG")
    pd.DataFrame(
        [
            {
                "measurement_id": "M1",
                "datetime_utc": "2026-01-15T06:00:00Z",
                "longitude": 67.45,
                "latitude": 24.14,
                "value": 38.0,
                "units": "PSU",
                "method": "MOCK refractometer",
                "tide_state": "ebb",
            }
        ]
    ).to_csv(data / "field.csv", index=False)
    return cfgs, out
