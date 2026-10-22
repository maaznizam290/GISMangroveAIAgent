"""Area of interest: reference point, primary AOI and alternative AOIs.

All geometry operations run in the analysis CRS (metres). GeoPackage layers keep that CRS;
QGIS reprojects on the fly for display.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point
from shapely.validation import explain_validity

from indus_delta.config import ProjectConfig

# Segments per quarter circle; 64 keeps the buffer area within 0.01 % of pi * r^2.
BUFFER_QUAD_SEGS = 64


def reference_point(cfg: ProjectConfig) -> gpd.GeoDataFrame:
    loc = cfg.reference_location
    src = loc.sources[0]
    gdf = gpd.GeoDataFrame(
        {
            "name": [loc.name],
            "verification_status": [loc.verification_status],
            "feature_type": [loc.feature_type],
            "n_sources": [len(loc.sources)],
            "source_dataset": [src.dataset],
            "source_url": [src.url],
            "source_version": [src.version],
            "source_licence": [src.licence],
            "source_retrieved": [src.retrieved.isoformat()],
        },
        geometry=[Point(loc.longitude, loc.latitude)],
        crs=cfg.crs.geographic_epsg,
    )
    return gdf.to_crs(cfg.crs.analysis_epsg)


def _buffer(cfg: ProjectConfig, radius_m: float, aoi_id: str, role: str) -> gpd.GeoDataFrame:
    pt = reference_point(cfg).geometry.iloc[0]
    geom = pt.buffer(radius_m, quad_segs=BUFFER_QUAD_SEGS)
    return gpd.GeoDataFrame(
        {
            "aoi_id": [aoi_id],
            "role": [role],
            "mode": ["buffer"],
            "buffer_m": [float(radius_m)],
            "area_km2": [geom.area / 1e6],
            "config_version": [cfg.config_version],
        },
        geometry=[geom],
        crs=cfg.crs.analysis_epsg,
    )


def build_aoi(cfg: ProjectConfig, base_dir: Path = Path(".")) -> gpd.GeoDataFrame:
    """Primary AOI from the configuration (buffer or operator polygon)."""
    if cfg.aoi.mode == "buffer":
        return _buffer(cfg, cfg.aoi.buffer_m, f"buffer_{cfg.aoi.buffer_m:.0f}m", "primary")

    path = base_dir / cfg.aoi.polygon_path
    if not path.is_file():
        raise FileNotFoundError(f"AOI polygon not found: {path}")
    poly = gpd.read_file(path)
    if poly.crs is None:
        raise ValueError(f"AOI polygon {path} has no CRS; refusing to guess one")
    geom = poly.to_crs(cfg.crs.analysis_epsg).union_all()
    if geom.is_empty or not geom.is_valid:
        raise ValueError(f"AOI polygon {path} is invalid: {explain_validity(geom)}")
    if geom.geom_type not in {"Polygon", "MultiPolygon"}:
        raise ValueError(f"AOI polygon {path} has geometry type {geom.geom_type}")
    return gpd.GeoDataFrame(
        {
            "aoi_id": [f"polygon_{path.stem}"],
            "role": ["primary"],
            "mode": ["polygon"],
            "buffer_m": [None],
            "area_km2": [geom.area / 1e6],
            "config_version": [cfg.config_version],
        },
        geometry=[geom],
        crs=cfg.crs.analysis_epsg,
    )


def alternative_aois(cfg: ProjectConfig) -> gpd.GeoDataFrame:
    """Proposed alternatives for the AOI review. Never used for processing unless adopted."""
    parts = [
        _buffer(cfg, r, f"buffer_{r:.0f}m", "alternative") for r in cfg.aoi.alternative_buffers_m
    ]
    if not parts:
        return gpd.GeoDataFrame(geometry=[], crs=cfg.crs.analysis_epsg)
    return gpd.GeoDataFrame(gpd.pd.concat(parts, ignore_index=True), crs=cfg.crs.analysis_epsg)


def write_layers(path: Path, layers: dict[str, gpd.GeoDataFrame]) -> Path:
    """Write layers to one GeoPackage, replacing the file to avoid stale layers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    for name, gdf in layers.items():
        if len(gdf):
            gdf.to_file(path, layer=name, driver="GPKG")
    return path
