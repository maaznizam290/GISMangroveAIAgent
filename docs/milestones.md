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
- [ ] **Run `inventory`. Blocked: no Earth Engine credentials in the build environment**
- [ ] Choose the Sentinel-1 orbit pass from `s1_orbit_summary.csv` and fix it in config
- [ ] Supply GMW v4.1 (uploaded asset or local rasters plus DOI) or decide to proceed without it

## M3: seasonal windows and preprocessing (implemented, not run)

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
- [ ] **Run `preview`. Blocked: no Earth Engine credentials**
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
