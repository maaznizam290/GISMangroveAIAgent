# Methods report: landsat 2026

Generated from the pipeline outputs. Handover status: **INCOMPLETE**. Every section reports only steps that ran; steps that did not run are named as such.

## Study area and CRS

Reference point Keti Bandar (67.45094, 24.14422), status provisional. AOI mode buffer, buffer 5000.0 m, operator confirmed: False. All distances and areas in EPSG:32642.

## Data verification (M2)

Dataset identifiers checked against the official Earth Engine catalog: {'FAIL': 1, 'PASS': 78, 'WARN': 3}. Failures and warnings:

| dataset | check | status | detail |
|---|---|---|---|
| landsat5_l2 | temporal_extent | WARN | catalog 1984-03-16..2012-05-05; requested 2004-11-01..latest; collection ended 2012-05-05 (no data after this date) |
| landsat8_l2 | temporal_extent | WARN | catalog 2013-03-18..2026-10-11; requested 2004-11-01..latest; usable 2013-03-18..2026-10-11 |
| landsat9_l2 | temporal_extent | WARN | catalog 2021-10-31..2026-10-11; requested 2004-11-01..latest; usable 2021-10-31..2026-10-11 |
| gmw_v4 | catalog_entry | FAIL | no Earth Engine ID configured; the dataset must be supplied as an uploaded asset or local raster with a recorded DOI |

## Image inventory (M2)

Not run (requires Earth Engine credentials).

## Preprocessing and preview (M3)

Not run (requires Earth Engine credentials).

## Classification and validation (M4)

Not run (requires composites and operator reference samples).

## Analytical layers (M5)

Not run.

## Site selection (M6)

Not run (requires a passed validation gate and confirmed selection rules).

## Processing history

| manifest | milestone | command | created_utc | status | git_revision | n_outputs |
|---|---|---|---|---|---|---|
| m1/run_manifest.json | M1 | indus-delta m1 | 2026-10-22T05:07:38+00:00 | WARN | d81412605eff36dcc54d684df71ec0829c8593d6 | 5 |
| m2/catalog_manifest.json | M2-catalog | indus-delta catalog-check | 2026-10-22T05:27:02+00:00 | FAIL | 7173fc3d8c3c09c8d80ceb2fbc0fe6d53ac6d043 | 2 |
