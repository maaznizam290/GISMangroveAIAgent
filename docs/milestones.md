# Milestone checklist

## M1: configuration, CRS, AOI, protocol ✅ (gate: WARN)

- [x] Repository and environment inspected; repository assessment and `uv.lock`
- [x] Configuration schema; reference location with provenance (provisional, one source)
- [x] EPSG:32642 checks; 5 km AOI plus alternatives and polygon mode; GeoPackage layers
- [x] Hydrological-context review on real JRC GSW v1.4 data; preview map; review report
- [x] Study protocol with unresolved assumptions

Still open from M1 (operator):

- [ ] U1: second independent source for the reference point
- [ ] U2/U3: AOI decision based on documented hydrological evidence, then
      `aoi.operator_confirmed: true`

## M2: dataset verification and inventory (partly done)

- [x] `catalog-check` **run on real data** (2026-10-22): every Earth Engine ID verified against
      the official catalog, with type, temporal extent, required bands, SR scale/offset,
      QA_PIXEL bits, QA_RADSAT bits and SCL classes. 78 of 82 checks pass; status FAIL only because
      GMW v4.1 has no Earth Engine source (`outputs/m2/catalog_verification.csv`)
- [x] Registry updated to `catalog_verified` with catalog extents (`configs/datasets.yaml`)
- [x] GMW v4.1 confirmed absent from the official catalog; CGMD-Extent30 (1984–2023) found and
      listed as an optional candidate, not adopted
- [x] `inventory` implemented: per image date, season, label year, scene cloud, AOI valid
      fraction, usability, S1 pass/orbit/polarisation compatibility, tide status. Outputs
      `image_inventory.csv`, `inventory_summary.csv`, `missing_observations.csv` and
      `s1_orbit_summary.csv`, and it fails visibly if a required dataset returns no images
- [x] **`inventory` run on real data** (2026-10-22 07:32 UTC, status WARN: every image and
      coverage check PASS; WARN only because the AOI is unconfirmed). Rerun it if the AOI
      changes
- [ ] Choose the Sentinel-1 orbit pass from `s1_orbit_summary.csv` and fix it in config
- [ ] Supply GMW v4.1 (uploaded asset or local rasters plus DOI) or decide to proceed without it

## M3: seasonal windows and preprocessing (preview run and passed; full run not started)

- [x] Season assignment and windows (dry Nov–Mar labelled by end year; post-monsoon Sep–Oct)
      with complete/partial/not-started status
- [x] Earth Engine preprocessing: masks, scaling, role renaming, median composites, indices,
      `valid_obs`; Landsat 7 limited to 2021 in the primary series
- [x] Native-grid alignment derived from the source image projection (never assumed)
- [x] Small-area `preview`: Landsat (30 m), Sentinel-2 (10 m) and Sentinel-1 (10 m)
      composites for a 3 km box, downloaded and checked locally (CRS, grid, nodata, band
      names, valid fraction, reflectance range, NumPy recomputation of every index,
      index bounds, SAR dB range), then a gate bound to the configuration hash
- [x] `preprocess`: plans per-season exports and submits them only with `--start`. It is
      refused unless the AOI is confirmed **and** the preview gate passed for the current
      configuration
- [x] **`preview` run on real data** (2026-10-22, dry 2026, 5 km AOI config): gate PASS.
      Landsat 18 images (L8/L9), Sentinel-2 32, Sentinel-1 13 (DESCENDING, chosen by the
      preview because `orbit_pass` is unset: WARN). 100% valid pixels; every index
      recomputed in NumPy; quicklook inspected (creeks, vegetated islands and the
      settlement line up across the three sensors). The gate must be rerun after the AOI
      or `orbit_pass` changes (it is bound to those configs)
- [x] `import-exports`: checks downloaded export files against their plan (CRS, grid,
      band count/names) and copies them, with band names and nodata, to `composites_dir`
      and `tidal_inundation.input_dir`
- [ ] Inspect the preview quicklook and gate; resolve U17 (SCL dark-area class) and U18
      (Cloud Score+ threshold)
- [ ] Full-scale processing: not started, and must not start before the items above

## M4: Random Forest baseline and validation (implemented, not run)

- [x] `configs/classification.yaml`: 7 class definitions, feature stack (dry and
      post-monsoon bands and indices), RF parameters, split, validation design and acceptance
      criteria (proposed; `operator_confirmed: false`)
- [x] Reference and validation sample schema and loader (operator-supplied; never generated)
- [x] Independent validation file (default) or held-out 2 km blocks; training samples
      within 500 m of validation are dropped; minimum training and validation counts per class
- [x] Accuracy tables: confusion matrix; user's/producer's accuracy, precision, recall, F1
      and IoU with Wilson intervals; overall accuracy and kappa; Olofsson et al. (2014)
      area-adjusted estimates for stratified random designs
- [x] Per-pixel uncertainty (vote fractions, margin, entropy); OOB score recorded but
      never used by the gate
- [x] Validation gate bound to the classification config and the map hash
- [ ] **Run `classify`. Blocked: no composites (needs Earth Engine) and no reference or
      validation samples**
- [ ] Operator: supply samples (`data/reference/`) and confirm the acceptance criteria

## M5: separate analytical layers and trends (implemented, not run)

- [x] `mangrove` (extent, RF mangrove vote fraction, relative spectral-vigour terciles)
- [x] `tidal_inundation`: threshold calibration from reference samples (`calibrate-water`);
      annual Landsat water-frequency export in Earth Engine (gated like `preprocess`)
- [x] `soil_salinity_proxy`: SWIR-only, eligible bare surfaces only, eligibility codes;
      red/NIR features and mangrove eligibility rejected by the schema
- [x] `freshwater_influence_proxy`: along-channel (Dijkstra) distance from a documented
      source, plus an investigative turbidity change; not produced without a source
- [x] `water_salinity_field` schema for operator measurements
- [x] `annual_metrics.csv` and Mann–Kendall / Sen's slope (SciPy) with completeness rules;
      Landsat and Sentinel never pooled
- [ ] **Run. Blocked on M4 and on the water-frequency exports**
- [ ] Operator: supply a documented freshwater source (U2); calibrate the water threshold

## M6: site selection (implemented, not run)

- [x] 500 m plots in EPSG:32642 inside the AOI; per-plot metrics
- [x] Site A and Site B eligibility with exclusion reasons; weighted percentile scores;
      alternatives; comparability preference with the trade-off reported
- [x] Refused unless the validation gate passed, the map is unchanged and the rules are
      confirmed; anti-circularity check on layer provenance; `NO_SELECTION` reported when
      evidence is insufficient
- [x] Outputs: `candidate_site_scores.csv`, `site_metrics.csv`, `sites.gpkg`,
      `selection_report.md`
- [ ] **Run. Blocked on M4 and M5**
- [ ] Operator: confirm the rules and weights in `configs/site_selection.yaml`

## M7: GIS handover (implemented; real run INCOMPLETE)

- [x] M6 extended: explicit `selection_criteria.csv` (every eligibility and comparability
      rule, threshold and confirmation state) and `site_comparison.csv` (Site A vs Site B
      metrics and differences)
- [x] Change layer: class transitions and mangrove gain/loss between validated epochs
- [x] `configs/handover.yaml`: deliverable registry (required or optional, native resolution)
- [x] COG rasters with provenance tags; one GeoPackage; required tables; generated data
      dictionary, methods report, limitations, processing history, software versions;
      SHA-256 manifest
- [x] QGIS project built with PyQGIS 3.34 (styled groups, print layout with map, legend,
      scale bar and source notes, relative paths), reopened and validated in a clean session
- [x] Validation of every delivered file against its source (CRS, dimensions, transform,
      no upsampling, nodata, structural COG validity, metadata, units, identical content;
      vector CRS, counts, validity, plot size; table columns and identity)
- [x] **Real run 2026-10-22: INCOMPLETE.** The delivered M1/M2 items (JRC review raster,
      AOI layers, catalog tables, AOI review) and the QGIS project pass all 41 checks.
      Every M3–M6 deliverable is missing because those stages have not run
- [x] Mock pipeline: COMPLETE, with all QGIS checks passing (tests)

## M8: dashboard (implemented)

- [x] Six tabs; reads pipeline outputs only; "not available yet" states; warnings for
      proxies, unvalidated layers, the provisional reference point and the unconfirmed AOI
- [x] Charts: Landsat and Sentinel separate, unvalidated hollow, missing years marked;
      small multiples for site metrics (no shared or dual axis); validated categorical
      palette (blue, orange, aqua); table views beside charts
- [x] Site selection updates metrics, class proportions and exclusion reasons
- [x] Tests: data loading, chart calculations, site filtering and class proportions, plus
      `AppTest` runs on empty and mock outputs; rendered and inspected in Chromium

## Review and fixes (2026-10-22, Windows run)

- **HTTPS failed behind TLS-inspecting antivirus (Avast).** Python did not trust the
  antivirus root, so `ee.Initialize` failed with `CERTIFICATE_VERIFY_FAILED`. The CLI now
  verifies against the OS trust store (`truststore`); `check-ee` passes. `uv` needs
  `--system-certs` on such machines.
- **Preview MVI check failed on real data (2.7e-4 > 1e-4).** Analysis of the downloaded
  preview: only 3 of 10 201 Landsat and 2 of 90 601 Sentinel-2 pixels exceeded the
  tolerance, all where SWIR1 ≈ Green (near-zero MVI denominator), and every difference was
  within the propagated float32 rounding of the stored bands (max 0.66 and 0.90 of the
  bound); elsewhere the implementations agree within 3e-6. The check now allows twice that
  bound on top of the tolerance and reports how many pixels needed it; a 0.1% formula error
  still fails (tests).
- **Water frequency would have been 0 or 1 only:** `sum / count` of two integer images is
  integer division in Earth Engine. Cast to float before dividing.
- **Handover returned FAIL instead of INCOMPLETE without QGIS** (Linux interpreter path on
  Windows). The interpreter is now `$QGIS_PYTHON`, `qgis.python`, or an auto-detected Windows
  QGIS install; without one the project is reported missing.
- **Handover crashed on rerun on Windows**: read-only folders could not be removed. Fixed.
- **scikit-learn was an optional extra**, so a plain `uv sync` (and the Docker image) could
  not run `classify`, `select-sites` or the tests. It is now a core dependency.
- **Drive exports used a path-like file name prefix**; Drive folders are flat, so only the
  file name is used there (Cloud Storage keeps the folder structure).
- **No step connected the downloaded exports to `classify` / `layers`**; added
  `import-exports`.

## Errors and findings during M7–M8

- **The COG check was too weak.** The `LAYOUT=COG` tag survives edits that break the
  layout, so it was replaced by structural validation with `rio-cogeo`.
- **The QGIS layout had defects the checks did not catch:** the map overran the notes,
  8-digit hex colours were misread, and the legend listed hidden layers. They were found by
  rendering the layout and fixed (`zoomToExtent`, `r,g,b,a` colours, a map-filtered legend).
- **The folium map needed a CDN at view time.** It failed in the sandbox and would fail
  offline, so the map was switched to Plotly MapLibre and folium dependencies were dropped.
- **Chart edge cases:** a series with no validated values got an empty legend entry, and a
  validated year without a value was drawn. Both fixed and tested.
- **Stray output folder:** `classify` created its output folder before checking its inputs.
  Fixed and tested.

## Errors and findings during M4–M6

- **Spatial separation can starve training.** With validation points spread across the
  AOI, the 500 m exclusion removed almost every training sample in a test scene; the gate
  failed correctly. A training-count check was added so this fails with a clear reason.
  Validation samples must be planned in separate areas or blocks.
- **The comparability preference can select weaker evidence.** In the mock scene the
  strongest Site A plots flooded far less often than the mangrove plots, so a weaker plot
  was chosen. The report now names the higher-scoring pair that was passed over.

## Errors met during M2/M3

- The proxy-provided `CLOUDSDK_AUTH_ACCESS_TOKEN` is rejected by Google (`invalid_token`). No
  Earth Engine or gcloud credentials exist, so `inventory` and `preview` exit with code 4.
- USGS, Copernicus Data Space, Planetary Computer and Earth Search STAC endpoints are
  blocked by the network policy. Only Google's Earth Engine STAC catalog is reachable, which
  is why the M2 work so far is catalog-level verification.
