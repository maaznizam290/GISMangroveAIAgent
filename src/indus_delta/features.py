"""Feature stacks from the seasonal composites exported in M3."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.transform import rowcol

from indus_delta.config import Configs
from indus_delta.layer_io import Grid


class CompositeMissing(FileNotFoundError):
    pass


_NAME = re.compile(
    r"^(?P<series>[a-z0-9]+)_(?P<season>[a-z_]+?)_(?P<year>\d{4})(?P<partial>_partial)?"
    r"_epsg(?P<epsg>\d+)_(?P<scale>[\d.]+)m\.tif$"
)


def find_composite(directory: Path, series: str, season: str, year: int) -> tuple[Path, bool]:
    """(path, is_partial). Raises CompositeMissing when no matching file exists."""
    matches = []
    if directory.is_dir():
        for p in sorted(directory.glob("*.tif")):
            m = _NAME.match(p.name)
            if m and (m["series"], m["season"], int(m["year"])) == (series, season, year):
                matches.append((p, bool(m["partial"])))
    if not matches:
        raise CompositeMissing(
            f"no {series} {season} {year} composite in {directory}; export it with "
            "`indus-delta preprocess --start` and download it there"
        )
    if len(matches) > 1:
        raise ValueError(f"several composites match {series} {season} {year}: {matches}")
    return matches[0]


@dataclass
class FeatureStack:
    names: list[str]
    data: np.ndarray  # (n_features, height, width), NaN = missing
    grid: Grid
    sources: dict[str, str]
    partial_seasons: list[str]

    def valid_mask(self) -> np.ndarray:
        return np.all(np.isfinite(self.data), axis=0)

    def band(self, season: str, band: str) -> np.ndarray:
        return self.data[self.names.index(f"{season}_{band}")]


def load_stack(
    cfgs: Configs, series: str, year: int, directory: Path | None = None
) -> FeatureStack:
    cl = cfgs.classification
    directory = directory or cl.composites_dir
    nodata = cfgs.preprocessing.composites.nodata_value
    names, arrays, sources, partial, grid = [], [], {}, [], None
    for season in cl.features.seasons:
        path, is_partial = find_composite(directory, series, season, year)
        if is_partial:
            partial.append(season)
        with rasterio.open(path) as src:
            g = Grid(src.transform, src.width, src.height, src.crs.to_epsg())
            if grid is None:
                grid = g
            elif not grid.same_as(g):
                raise ValueError(f"{path.name} is not on the same grid as the other seasons")
            desc = list(src.descriptions)
            for band in cl.features.bands:
                if band not in desc:
                    raise ValueError(f"{path.name} has no band {band!r} (bands: {desc})")
                a = src.read(desc.index(band) + 1).astype(np.float64)
                a[(a == nodata) | ~np.isfinite(a)] = np.nan
                names.append(f"{season}_{band}")
                arrays.append(a)
            # Pixels without valid observations are missing even if a value was written.
            if "valid_obs" in desc:
                obs = src.read(desc.index("valid_obs") + 1).astype(np.float64)
                bad = ~(obs >= 1)
                for a in arrays[-len(cl.features.bands) :]:
                    a[bad] = np.nan
        sources[season] = path.name
    return FeatureStack(names, np.stack(arrays), grid, sources, partial)


def _pixel_index(grid: Grid, points: gpd.GeoDataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Row/column of the pixel containing each point."""
    if points.empty:
        return np.array([], dtype=int), np.array([], dtype=int)
    rows, cols = rowcol(
        grid.transform, points.geometry.x.to_numpy(), points.geometry.y.to_numpy(), op=np.floor
    )
    return np.asarray(rows, dtype=int), np.asarray(cols, dtype=int)


def sample_stack(stack: FeatureStack, points: gpd.GeoDataFrame) -> pd.DataFrame:
    """Feature values at point locations (pixel containing the point); NaN outside grid."""
    rows, cols = _pixel_index(stack.grid, points)
    inside = (rows >= 0) & (rows < stack.grid.height) & (cols >= 0) & (cols < stack.grid.width)
    out = np.full((len(points), len(stack.names)), np.nan)
    out[inside] = stack.data[:, rows[inside], cols[inside]].T
    return pd.DataFrame(out, columns=stack.names, index=points.index)


def sample_raster(values: np.ndarray, grid: Grid, points: gpd.GeoDataFrame) -> np.ndarray:
    rows, cols = _pixel_index(grid, points)
    inside = (rows >= 0) & (rows < grid.height) & (cols >= 0) & (cols < grid.width)
    out = np.full(len(points), np.nan)
    out[inside] = values[rows[inside], cols[inside]]
    return out
