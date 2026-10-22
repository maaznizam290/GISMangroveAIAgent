# Upstream repository and dependency assessment

Assessed on 2026-10-22. Package versions, licences and supported Python versions come from
the PyPI JSON API. Licences of GitHub-only repositories come from their `LICENSE` file on
the default branch, read from raw.githubusercontent.com. The GitHub REST API was not
available from the build environment, so stars, last-push dates and open-issue counts were
**not** checked. Where a release date is shown it is the date of the latest PyPI release,
which serves as a maintenance signal.

Classes: **1** production dependency, **2** scientific or implementation reference,
**3** optional future integration.

| Repository | Class | Licence | Latest release (PyPI) | Python | Use in this project |
|---|---|---|---|---|---|
| google/earthengine-api | 1 | Apache-2.0 | 1.7.49 (2026-10-19) | ≥3.11 | Main processing engine. Installed; authentication check in M1, processing from M2 |
| gee-community/geemap | 3 | MIT | 0.38.9 (2026-10-01) | ≥3.12 | **Not used.** Its value is live Earth Engine layers (needs credentials); the dashboard shows local pipeline outputs with Plotly MapLibre instead |
| geopandas/geopandas | 1 | BSD-3-Clause | 1.2.0 (2026-09-28) | ≥3.11 | Vector I/O and GeoPackage (M1) |
| rasterio/rasterio | 1 | BSD-3-Clause | 1.5.2 (2026-09-30) | ≥3.12 | Raster I/O and COG export (M1). Bundles GDAL 3.12.2 in its wheel |
| OSGeo/gdal | 1 (indirect) | MIT | 3.13.3 (2026-08-18) | ≥3.8 | Used through the rasterio and pyogrio wheels. The PyPI `GDAL` package is source-only, so it is not installed directly |
| scikit-learn/scikit-learn | 1 | BSD-3-Clause | 1.9.1 (2026-09-10) | ≥3.11 | Random Forest baseline and metrics (M4). Optional extra (locked, not installed by default) |
| shapely/shapely | 1 | BSD-3-Clause | 2.2.0 (2026-10-07) | ≥3.11 | Geometry (M1) |
| pyproj4/pyproj | 1 | MIT | 3.8.0 (2026-09-05) | ≥3.12 | CRS checks and transforms (M1). PROJ 9.8.1 |
| streamlit/streamlit | 1 (dashboard) | Apache-2.0 | 1.66.1 (2026-10-21) | ≥3.11 | Dashboard (M8) |
| plotly/plotly.py | 1 (dashboard) | MIT | 7.1.0 (2026-09-15) | ≥3.8 | Dashboard charts (M8) |
| mmhs013/pyMannKendall | 2 | MIT | 1.4.3 (2023-01-14) | not declared | Reference only. **Not used:** no release since 2023, so M5 implements Mann–Kendall (Kendall's tau) and Sen's slope (`theilslopes`) with SciPy |
| lucasjvds/MangroveAI | 2 | MIT | n/a | n/a | Deep-learning mangrove segmentation on Sentinel-2 (MagSet-2, GMW labels). Reference only; deep learning is deferred until the RF baseline is validated |
| UCSD-E4E/ml-mangrove | 2 | **No LICENSE file found** | n/a | n/a | Drone and satellite mangrove ML. Reference for ideas only; **no code may be copied** |
| globalmangrovewatch (org) | 2 | not checked (github.com was unreachable) | n/a | n/a | GMW methods and data distribution. The v4.1 distribution route must be verified in M2 |
| giswqs/earthengine-py-notebooks | 2 | MIT | n/a | n/a | Earth Engine Python examples |
| gee-community/qgis-earthengine-plugin | 3 | MIT | n/a | n/a | Optional QGIS-side Earth Engine viewing |
| pyTMD/pyTMD | 3 | MIT | 3.0.9 (2026-07-02) | ~=3.9 | Candidate tide-prediction library (assumption U10). Tide-model *files* have their own licences, to be checked separately |
| apache/airflow | 3 | Apache-2.0 (project licence; not re-checked) | not checked | not checked | Later-stage scheduling only. Not an MVP dependency |
| docker/compose | 3 | Apache-2.0 (project licence; not re-checked) | n/a | n/a | `compose.yaml` convenience only |
| randyzwitch/streamlit-folium | 3 | MIT | 0.27.4 (2026-08-03) | ≥3.11 | **Tried and dropped:** folium loads Leaflet from a CDN at view time, which fails offline (and in the build sandbox) |

## Added during M7–M8

| Component | Class | Licence | Version | Use |
|---|---|---|---|---|
| cogeotiff/rio-cogeo | 1 | BSD-3-Clause | 7.0.4 (Python ≥ 3.11) | Structural COG validation of handover rasters |
| QGIS / PyQGIS (Ubuntu `python3-qgis`) | 1 (optional system dependency) | GPL-2.0+ | 3.34.4 | Builds and reopens the handover QGIS project in a separate process; not imported by the package |

## Python version decision

Current releases of rasterio, pyproj, numpy, scipy and geemap require **Python ≥ 3.12**, so
the brief's Python 3.11 target cannot be met with a maintained, locked dependency set. The
project declares `requires-python = ">=3.12,<3.14"` and is tested on CPython 3.13.

## Reuse record

No code, model weights or datasets have been copied from any repository above. Data read at
run time are recorded in each run manifest:

| Component | Source | Licence | Version |
|---|---|---|---|
| Keti Bandar gazetteer entry | GeoNames via lutangar/cities.json | CC BY 4.0 | commit c05addfe79dce8a87076ef3fd487eab7e5fe4abd |
| Indus centreline | Natural Earth 1:10m rivers (nvkelso/natural-earth-vector) | Public domain | commit ca96624a56bd078437bca8184e78163e5039ad19 |
| Surface-water occurrence | JRC Global Surface Water v1.4, public tile store | Copernicus programme data policy (to be confirmed in M2) | v1.4 (1984–2021) |

## Lockfile

`uv.lock` pins 148 packages for Python ≥ 3.12, including the `classification` and
`dashboard` extras (for example scikit-learn 1.9.1, streamlit 1.66.1, geemap 0.38.9,
plotly 7.1.0). `uv sync` installs only the core and dev groups. The
extras are installed with `uv sync --extra classification` or `--extra dashboard` when their
milestones start, and are not yet exercised by tests.
