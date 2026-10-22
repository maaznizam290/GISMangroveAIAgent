# gee/

The Earth Engine code lives in the package, so it is versioned, imported and tested like
the rest of the pipeline:

| Module | Purpose |
|---|---|
| `src/indus_delta/earthengine/prep.py` | Collection filtering; Landsat QA_PIXEL/QA_RADSAT masks, Sentinel-2 SCL plus Cloud Score+ masks, reflectance scaling, renaming bands to roles; Sentinel-1 mode, polarisation, resolution and pass filters |
| `src/indus_delta/earthengine/composite.py` | Seasonal median composites, indices computed from the composite, `valid_obs` count band |
| `src/indus_delta/earthengine/inventory_ee.py` | Per-image inventory records with the AOI valid fraction |
| `src/indus_delta/earthengine/download.py` | Small synchronous GeoTIFF downloads (preview only) |

All identifiers, mask bits and parameters come from `configs/`. The NumPy reference
implementation (`src/indus_delta/spectral.py`) recomputes every index from the downloaded
preview, so the Earth Engine output is checked against independent code.

**Execution status:** none of this code has run against Earth Engine yet. The build
environment has no Earth Engine credentials.
