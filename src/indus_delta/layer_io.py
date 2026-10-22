"""Reading and writing analysis rasters with their provenance.

Every layer records, in the GeoTIFF itself:
  layer_name, layer_type (classified / proxy / measured / derived), status
  (validated / unvalidated / proxy_uncalibrated / ...), units per band, derived_from (the
  inputs whose values enter the layer) and mask_from (inputs used only to exclude pixels).
M6 reads these tags to refuse circular evidence.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import Affine


@dataclass
class LayerMeta:
    layer_name: str
    layer_type: str
    status: str
    description: str
    derived_from: list[str]
    mask_from: list[str] = field(default_factory=list)
    units: dict[str, str] = field(default_factory=dict)
    extra: dict[str, str] = field(default_factory=dict)

    def to_tags(self) -> dict[str, str]:
        return {
            "layer_name": self.layer_name,
            "layer_type": self.layer_type,
            "status": self.status,
            "description": self.description,
            "derived_from": json.dumps(self.derived_from),
            "mask_from": json.dumps(self.mask_from),
            **{f"extra_{k}": str(v) for k, v in self.extra.items()},
        }

    @classmethod
    def from_tags(cls, tags: dict[str, str]) -> LayerMeta:
        return cls(
            layer_name=tags.get("layer_name", ""),
            layer_type=tags.get("layer_type", ""),
            status=tags.get("status", ""),
            description=tags.get("description", ""),
            derived_from=json.loads(tags.get("derived_from", "[]")),
            mask_from=json.loads(tags.get("mask_from", "[]")),
            extra={k[6:]: v for k, v in tags.items() if k.startswith("extra_")},
        )


@dataclass
class Grid:
    transform: Affine
    width: int
    height: int
    epsg: int

    def same_as(self, other: Grid) -> bool:
        return (self.width, self.height, self.epsg) == (
            other.width,
            other.height,
            other.epsg,
        ) and self.transform.almost_equals(other.transform)

    @property
    def pixel_area_m2(self) -> float:
        return abs(self.transform.a * self.transform.e)


def write_layer(
    path: Path,
    bands: dict[str, np.ndarray],
    grid: Grid,
    meta: LayerMeta,
    nodata: float,
    dtype: str = "float32",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=grid.width,
        height=grid.height,
        count=len(bands),
        dtype=dtype,
        crs=f"EPSG:{grid.epsg}",
        transform=grid.transform,
        nodata=nodata,
        compress="deflate",
        tiled=True,
        blockxsize=256,
        blockysize=256,
    ) as dst:
        for i, (name, arr) in enumerate(bands.items(), start=1):
            out = np.asarray(arr, dtype=np.float64)
            out = np.where(np.isfinite(out), out, nodata).astype(dtype)
            dst.write(out, i)
            dst.set_band_description(i, name)
            if name in meta.units:
                dst.update_tags(i, units=meta.units[name])
        dst.update_tags(**meta.to_tags())
    return path


def read_layer(path: Path) -> tuple[dict[str, np.ndarray], Grid, LayerMeta]:
    """Bands as float64 with nodata set to NaN."""
    with rasterio.open(path) as src:
        grid = Grid(src.transform, src.width, src.height, src.crs.to_epsg())
        bands = {}
        for i, name in enumerate(src.descriptions, start=1):
            a = src.read(i).astype(np.float64)
            if src.nodata is not None:
                a[a == src.nodata] = np.nan
            bands[name or f"band_{i}"] = a
        meta = LayerMeta.from_tags(src.tags())
    return bands, grid, meta
