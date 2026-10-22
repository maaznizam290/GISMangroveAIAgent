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

| series | season | label_year | window_start | window_end_exclusive | completeness | data_end | n_images | n_usable | median_valid_fraction | first_date | last_date | sensors |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| landsat | dry | 2005 | 2004-11-01 | 2005-04-01 | complete | 2026-10-10 | 8 | 6 | 0.959 | 2004-11-14 | 2005-03-22 | landsat7_l2 |
| landsat | post_monsoon | 2005 | 2005-09-01 | 2005-11-01 | complete | 2026-10-10 | 3 | 3 | 0.561 | 2005-09-14 | 2005-10-16 | landsat7_l2 |
| landsat | dry | 2006 | 2005-11-01 | 2006-04-01 | complete | 2026-10-10 | 10 | 7 | 0.905 | 2005-11-01 | 2006-03-25 | landsat7_l2 |
| landsat | post_monsoon | 2006 | 2006-09-01 | 2006-11-01 | complete | 2026-10-10 | 4 | 2 | 0.376 | 2006-09-01 | 2006-10-19 | landsat7_l2 |
| landsat | dry | 2007 | 2006-11-01 | 2007-04-01 | complete | 2026-10-10 | 9 | 8 | 0.967 | 2006-11-04 | 2007-03-28 | landsat7_l2 |
| landsat | post_monsoon | 2007 | 2007-09-01 | 2007-11-01 | complete | 2026-10-10 | 4 | 2 | 0.190 | 2007-09-04 | 2007-10-22 | landsat7_l2 |
| landsat | dry | 2008 | 2007-11-01 | 2008-04-01 | complete | 2026-10-10 | 10 | 7 | 0.921 | 2007-11-07 | 2008-03-30 | landsat7_l2 |
| landsat | post_monsoon | 2008 | 2008-09-01 | 2008-11-01 | complete | 2026-10-10 | 4 | 1 | 0.021 | 2008-09-06 | 2008-10-24 | landsat5_l2;landsat7_l2 |
| landsat | dry | 2009 | 2008-11-01 | 2009-04-01 | complete | 2026-10-10 | 17 | 17 | 0.939 | 2008-11-01 | 2009-03-25 | landsat5_l2;landsat7_l2 |
| landsat | post_monsoon | 2009 | 2009-09-01 | 2009-11-01 | complete | 2026-10-10 | 7 | 6 | 0.999 | 2009-09-01 | 2009-10-27 | landsat5_l2;landsat7_l2 |
| landsat | dry | 2010 | 2009-11-01 | 2010-04-01 | complete | 2026-10-10 | 12 | 12 | 0.936 | 2009-11-04 | 2010-03-20 | landsat5_l2;landsat7_l2 |
| landsat | post_monsoon | 2010 | 2010-09-01 | 2010-11-01 | complete | 2026-10-10 | 5 | 5 | 0.998 | 2010-09-04 | 2010-10-30 | landsat5_l2;landsat7_l2 |
| landsat | dry | 2011 | 2010-11-01 | 2011-04-01 | complete | 2026-10-10 | 13 | 13 | 0.961 | 2010-11-07 | 2011-03-31 | landsat5_l2;landsat7_l2 |
| landsat | post_monsoon | 2011 | 2011-09-01 | 2011-11-01 | complete | 2026-10-10 | 3 | 3 | 0.739 | 2011-09-15 | 2011-10-17 | landsat7_l2 |
| landsat | dry | 2012 | 2011-11-01 | 2012-04-01 | complete | 2026-10-10 | 9 | 8 | 0.878 | 2011-11-18 | 2012-03-25 | landsat7_l2 |
| landsat | post_monsoon | 2012 | 2012-09-01 | 2012-11-01 | complete | 2026-10-10 | 3 | 3 | 0.968 | 2012-09-17 | 2012-10-19 | landsat7_l2 |
| landsat | dry | 2013 | 2012-11-01 | 2013-04-01 | complete | 2026-10-10 | 8 | 7 | 0.933 | 2012-11-04 | 2013-02-24 | landsat7_l2 |
| landsat | post_monsoon | 2013 | 2013-09-01 | 2013-11-01 | complete | 2026-10-10 | 6 | 5 | 0.782 | 2013-09-12 | 2013-10-30 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2014 | 2013-11-01 | 2014-04-01 | complete | 2026-10-10 | 19 | 17 | 0.658 | 2013-11-07 | 2014-03-31 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2014 | 2014-09-01 | 2014-11-01 | complete | 2026-10-10 | 5 | 4 | 0.970 | 2014-09-15 | 2014-10-25 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2015 | 2014-11-01 | 2015-04-01 | complete | 2026-10-10 | 19 | 15 | 0.806 | 2014-11-02 | 2015-03-26 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2015 | 2015-09-01 | 2015-11-01 | complete | 2026-10-10 | 8 | 6 | 0.781 | 2015-09-02 | 2015-10-28 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2016 | 2015-11-01 | 2016-04-01 | complete | 2026-10-10 | 19 | 15 | 0.784 | 2015-11-05 | 2016-03-28 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2016 | 2016-09-01 | 2016-11-01 | complete | 2026-10-10 | 8 | 3 | 0.174 | 2016-09-04 | 2016-10-30 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2017 | 2016-11-01 | 2017-04-01 | complete | 2026-10-10 | 19 | 13 | 0.569 | 2016-11-07 | 2017-03-31 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2017 | 2017-09-01 | 2017-11-01 | complete | 2026-10-10 | 7 | 7 | 0.972 | 2017-09-07 | 2017-10-25 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2018 | 2017-11-01 | 2018-04-01 | complete | 2026-10-10 | 19 | 14 | 0.755 | 2017-11-02 | 2018-03-26 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2018 | 2018-09-01 | 2018-11-01 | complete | 2026-10-10 | 8 | 6 | 0.892 | 2018-09-02 | 2018-10-28 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2019 | 2018-11-01 | 2019-04-01 | complete | 2026-10-10 | 18 | 14 | 0.572 | 2018-11-05 | 2019-03-21 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2019 | 2019-09-01 | 2019-11-01 | complete | 2026-10-10 | 8 | 6 | 0.871 | 2019-09-05 | 2019-10-31 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2020 | 2019-11-01 | 2020-04-01 | complete | 2026-10-10 | 18 | 13 | 0.740 | 2019-11-08 | 2020-03-31 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2020 | 2020-09-01 | 2020-11-01 | complete | 2026-10-10 | 7 | 4 | 0.386 | 2020-09-07 | 2020-10-25 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2021 | 2020-11-01 | 2021-04-01 | complete | 2026-10-10 | 18 | 16 | 0.858 | 2020-11-10 | 2021-03-26 | landsat7_l2;landsat8_l2 |
| landsat | post_monsoon | 2021 | 2021-09-01 | 2021-11-01 | complete | 2026-10-10 | 8 | 4 | 0.421 | 2021-09-02 | 2021-10-28 | landsat7_l2;landsat8_l2 |
| landsat | dry | 2022 | 2021-11-01 | 2022-04-01 | complete | 2026-10-10 | 22 | 18 | 0.801 | 2021-11-05 | 2022-03-29 | landsat7_l2;landsat8_l2;landsat9_l2 |
| landsat | post_monsoon | 2022 | 2022-09-01 | 2022-11-01 | complete | 2026-10-10 | 8 | 7 | 0.877 | 2022-09-05 | 2022-10-31 | landsat8_l2;landsat9_l2 |
| landsat | dry | 2023 | 2022-11-01 | 2023-04-01 | complete | 2026-10-10 | 17 | 12 | 0.735 | 2022-11-08 | 2023-03-24 | landsat8_l2;landsat9_l2 |
| landsat | post_monsoon | 2023 | 2023-09-01 | 2023-11-01 | complete | 2026-10-10 | 7 | 4 | 0.351 | 2023-09-08 | 2023-10-26 | landsat8_l2;landsat9_l2 |
| landsat | dry | 2024 | 2023-11-01 | 2024-04-01 | complete | 2026-10-10 | 19 | 17 | 0.754 | 2023-11-03 | 2024-03-26 | landsat8_l2;landsat9_l2 |
| landsat | post_monsoon | 2024 | 2024-09-01 | 2024-11-01 | complete | 2026-10-10 | 8 | 6 | 0.772 | 2024-09-02 | 2024-10-28 | landsat8_l2;landsat9_l2 |
| landsat | dry | 2025 | 2024-11-01 | 2025-04-01 | complete | 2026-10-10 | 19 | 12 | 0.777 | 2024-11-05 | 2025-03-29 | landsat8_l2;landsat9_l2 |
| landsat | post_monsoon | 2025 | 2025-09-01 | 2025-11-01 | complete | 2026-10-10 | 8 | 7 | 0.820 | 2025-09-05 | 2025-10-31 | landsat8_l2;landsat9_l2 |
| landsat | dry | 2026 | 2025-11-01 | 2026-04-01 | complete | 2026-10-10 | 18 | 16 | 0.805 | 2025-11-08 | 2026-03-24 | landsat8_l2;landsat9_l2 |
| landsat | post_monsoon | 2026 | 2026-09-01 | 2026-11-01 | partial | 2026-10-10 | 5 | 3 | 0.667 | 2026-09-08 | 2026-10-10 | landsat8_l2;landsat9_l2 |
| sentinel2 | dry | 2020 | 2019-11-01 | 2020-04-01 | complete | 2026-10-21 | 30 | 26 | 0.999 | 2019-11-05 | 2020-03-29 | sentinel2_sr |
| sentinel2 | post_monsoon | 2020 | 2020-09-01 | 2020-11-01 | complete | 2026-10-21 | 12 | 10 | 0.648 | 2020-09-05 | 2020-10-30 | sentinel2_sr |
| sentinel2 | dry | 2021 | 2020-11-01 | 2021-04-01 | complete | 2026-10-21 | 29 | 28 | 0.999 | 2020-11-04 | 2021-03-29 | sentinel2_sr |
| sentinel2 | post_monsoon | 2021 | 2021-09-01 | 2021-11-01 | complete | 2026-10-21 | 12 | 10 | 0.872 | 2021-09-05 | 2021-10-30 | sentinel2_sr |
| sentinel2 | dry | 2022 | 2021-11-01 | 2022-04-01 | complete | 2026-10-21 | 30 | 29 | 0.999 | 2021-11-04 | 2022-03-29 | sentinel2_sr |
| sentinel2 | post_monsoon | 2022 | 2022-09-01 | 2022-11-01 | complete | 2026-10-21 | 12 | 11 | 0.962 | 2022-09-05 | 2022-10-30 | sentinel2_sr |
| sentinel2 | dry | 2023 | 2022-11-01 | 2023-04-01 | complete | 2026-10-21 | 28 | 26 | 0.999 | 2022-11-04 | 2023-03-29 | sentinel2_sr |
| sentinel2 | post_monsoon | 2023 | 2023-09-01 | 2023-11-01 | complete | 2026-10-21 | 12 | 10 | 0.777 | 2023-09-05 | 2023-10-30 | sentinel2_sr |
| sentinel2 | dry | 2024 | 2023-11-01 | 2024-04-01 | complete | 2026-10-21 | 29 | 25 | 0.999 | 2023-11-04 | 2024-03-23 | sentinel2_sr |
| sentinel2 | post_monsoon | 2024 | 2024-09-01 | 2024-11-01 | complete | 2026-10-21 | 11 | 8 | 0.890 | 2024-09-04 | 2024-10-29 | sentinel2_sr |
| sentinel2 | dry | 2025 | 2024-11-01 | 2025-04-01 | complete | 2026-10-21 | 29 | 27 | 0.999 | 2024-11-03 | 2025-03-28 | sentinel2_sr |
| sentinel2 | post_monsoon | 2025 | 2025-09-01 | 2025-11-01 | complete | 2026-10-21 | 14 | 8 | 0.397 | 2025-09-04 | 2025-10-29 | sentinel2_sr |
| sentinel2 | dry | 2026 | 2025-11-01 | 2026-04-01 | complete | 2026-10-21 | 34 | 31 | 0.999 | 2025-11-03 | 2026-03-28 | sentinel2_sr |
| sentinel2 | post_monsoon | 2026 | 2026-09-01 | 2026-11-01 | partial | 2026-10-21 | 13 | 13 | 0.877 | 2026-09-04 | 2026-10-21 | sentinel2_sr |
| sentinel1 | dry | 2020 | 2019-11-01 | 2020-04-01 | complete | 2026-10-15 | 24 | 24 | 1.000 | 2019-11-02 | 2020-03-25 | sentinel1_grd |
| sentinel1 | post_monsoon | 2020 | 2020-09-01 | 2020-11-01 | complete | 2026-10-15 | 10 | 10 | 1.000 | 2020-09-06 | 2020-10-27 | sentinel1_grd |
| sentinel1 | dry | 2021 | 2020-11-01 | 2021-04-01 | complete | 2026-10-15 | 25 | 25 | 1.000 | 2020-11-05 | 2021-03-29 | sentinel1_grd |
| sentinel1 | post_monsoon | 2021 | 2021-09-01 | 2021-11-01 | complete | 2026-10-15 | 11 | 11 | 1.000 | 2021-09-01 | 2021-10-31 | sentinel1_grd |
| sentinel1 | dry | 2022 | 2021-11-01 | 2022-04-01 | complete | 2026-10-15 | 25 | 25 | 1.000 | 2021-11-03 | 2022-03-27 | sentinel1_grd |
| sentinel1 | post_monsoon | 2022 | 2022-09-01 | 2022-11-01 | complete | 2026-10-15 | 10 | 10 | 1.000 | 2022-09-08 | 2022-10-29 | sentinel1_grd |
| sentinel1 | dry | 2023 | 2022-11-01 | 2023-04-01 | complete | 2026-10-15 | 25 | 25 | 1.000 | 2022-11-07 | 2023-03-31 | sentinel1_grd |
| sentinel1 | post_monsoon | 2023 | 2023-09-01 | 2023-11-01 | complete | 2026-10-15 | 10 | 10 | 1.000 | 2023-09-03 | 2023-10-24 | sentinel1_grd |
| sentinel1 | dry | 2024 | 2023-11-01 | 2024-04-01 | complete | 2026-10-15 | 25 | 25 | 1.000 | 2023-11-02 | 2024-03-28 | sentinel1_grd |
| sentinel1 | post_monsoon | 2024 | 2024-09-01 | 2024-11-01 | complete | 2026-10-15 | 10 | 10 | 1.000 | 2024-09-09 | 2024-10-30 | sentinel1_grd |
| sentinel1 | dry | 2025 | 2024-11-01 | 2025-04-01 | complete | 2026-10-15 | 24 | 24 | 1.000 | 2024-11-08 | 2025-03-23 | sentinel1_grd |
| sentinel1 | post_monsoon | 2025 | 2025-09-01 | 2025-11-01 | complete | 2026-10-15 | 10 | 10 | 1.000 | 2025-09-04 | 2025-10-25 | sentinel1_grd |
| sentinel1 | dry | 2026 | 2025-11-01 | 2026-04-01 | complete | 2026-10-15 | 25 | 25 | 1.000 | 2025-11-06 | 2026-03-30 | sentinel1_grd |
| sentinel1 | post_monsoon | 2026 | 2026-09-01 | 2026-11-01 | partial | 2026-10-15 | 8 | 4 | 0.562 | 2026-09-06 | 2026-10-15 | sentinel1_grd |

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
| m1\run_manifest.json | M1 | indus-delta m1 | 2026-10-22T06:40:38+00:00 | WARN | b7e39d6441e26eafc47ab27da80af7ee6a37403d-dirty | 5 |
| m2\catalog_manifest.json | M2-catalog | indus-delta catalog-check | 2026-10-22T06:41:24+00:00 | FAIL | b7e39d6441e26eafc47ab27da80af7ee6a37403d-dirty | 2 |
| m2\inventory_manifest.json | M2-inventory | indus-delta inventory | 2026-10-22T07:32:16+00:00 | WARN | b7e39d6441e26eafc47ab27da80af7ee6a37403d-dirty | 5 |
