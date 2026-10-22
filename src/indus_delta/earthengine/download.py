"""Small synchronous GeoTIFF downloads (previews only; full runs use batch exports)."""

from __future__ import annotations

import logging
import time
import urllib.request
from pathlib import Path

import ee
import rasterio
from rasterio.transform import Affine

from indus_delta.earthengine.util import with_retries
from indus_delta.grid import transform_list

log = logging.getLogger(__name__)


def download_geotiff(
    image: ee.Image,
    path: Path,
    *,
    epsg: int,
    transform: Affine,
    width: int,
    height: int,
    band_names: list[str],
    nodata: float,
) -> Path:
    img = image.select(band_names).toFloat().unmask(nodata, False)
    params = {
        "format": "GEO_TIFF",
        "crs": f"EPSG:{epsg}",
        # Row-major [a, b, c, d, e, f]; with two-element dimensions Earth Engine extracts
        # exactly this rectangle (see ee.Image._apply_crs_and_affine).
        "crs_transform": transform_list(transform),
        "dimensions": [width, height],
        "bands": band_names,
    }
    url = with_retries(lambda: img.getDownloadURL(params), f"download URL for {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=300) as resp:  # noqa: S310
                path.write_bytes(resp.read())
            break
        except OSError as exc:
            if attempt == 3:
                raise RuntimeError(f"download of {path.name} failed: {exc}") from exc
            time.sleep(2 ** (attempt + 1))
    # Record the nodata value and band names in the file itself.
    with rasterio.open(path, "r+") as dst:
        dst.nodata = nodata
        for i, name in enumerate(band_names, start=1):
            dst.set_band_description(i, name)
    return path
