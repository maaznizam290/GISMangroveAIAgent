# Limitations

Handover status: **INCOMPLETE**.

## Deliverables not available

* composite_dry ({composites_dir}/{series}_dry_{year}*_epsg32642_*m.tif)
* composite_post_monsoon ({composites_dir}/{series}_post_monsoon_{year}*_epsg32642_*m.tif)
* landcover (m4/{series}_{year}/landcover.tif)
* classification_uncertainty (m4/{series}_{year}/classification_uncertainty.tif)
* mangrove (m5/{series}_{year}/mangrove.tif)
* tidal_inundation (m5/{series}_{year}/tidal_inundation.tif)
* soil_salinity_proxy (m5/{series}_{year}/soil_salinity_proxy.tif)
* freshwater_influence_proxy (m5/{series}_{year}/freshwater_influence_proxy.tif)
* training_samples (m4/{series}_{year}/samples.gpkg:training_samples)
* validation_samples (m4/{series}_{year}/samples.gpkg:validation_samples)
* candidate_plots (m6/{series}_{year}/sites.gpkg:candidate_plots)
* site_a (m6/{series}_{year}/sites.gpkg:site_a)
* site_b (m6/{series}_{year}/sites.gpkg:site_b)
* site_alternatives (m6 site_metrics.csv + candidate_plots)
* annual_metrics (m5/annual_metrics.csv)
* site_metrics (m6/{series}_{year}/site_metrics.csv)
* classification_accuracy (m4/{series}_{year}/classification_accuracy.csv)
* candidate_site_scores (m6/{series}_{year}/candidate_site_scores.csv)
* confusion_matrix (m4/{series}_{year}/confusion_matrix.csv)
* selection_criteria (m6/{series}_{year}/selection_criteria.csv)
* site_comparison (m6/{series}_{year}/site_comparison.csv)
* accuracy_report (m4/{series}_{year}/accuracy_report.md)
* selection_report (m6/{series}_{year}/selection_report.md)
* preview_quicklook (m3/preview/preview_quicklook.png)
* model_metadata (m4/{series}_{year}/model/random_forest_metadata.json)
* qgis_project (PyQGIS)

## Unresolved scientific assumptions (from the study protocol)

| ID | Assumption or open question | Why it matters | How to resolve | Milestone |
|---|---|---|---|---|
| U1 | The Keti Bandar reference point is correct | It anchors the AOI | Add an independent source (official gazetteer, OSM node or field GPS) and set `verified` | before M2 |
| U2 | A creek with present-day freshwater input exists within reach of the AOI | Site B depends on it | Traceable active-channel map; Kotri-downstream discharge records for the study years; field salinity/EC | before M6 (AOI choice before M2) |
| U3 | The 5 km AOI holds enough hydrological contrast for both sites | M1 shows a 5 km AOI that is nearly all intertidal/water, with the coarse main channel 12.4 km away | Operator chooses an AOI from the review alternatives or supplies a polygon | before M2 |
| U4 | Connected water implies a creek connection to the river | The M1 connectivity test may pass through the open sea | Sea/coastline mask, then a creek-only connectivity test | M5 |
| U5 | JRC value 255 means no data (ocean or outside the product) | It affects the no-data statistics | Confirm against the JRC GSW user guide (the Earth Engine version can be compared once authenticated) | M2 |
| U6 | The dataset IDs and scale factors in `configs/datasets.yaml` are correct | Every series depends on them | **Catalog-verified 2026-10-22.** Account access and AOI coverage still need an authenticated `inventory` | M2 |
| U7 | GMW v4.1 is accessible | It is the independent extent reference | **Not in the official Earth Engine catalog.** Obtain it from the GMW distribution (DOI, licence), upload it as an asset or local raster, or decide whether CGMD-Extent30 may serve as an additional reference | M2 |
| U8 | Enough cloud-free Landsat 5/7 scenes exist for 2005–2012 dry seasons | Annual versus epoch maps depend on it | Scene inventory; fall back to multi-year epochs where coverage is thin | M2 |
| U9 | Cross-sensor reflectance is consistent (TM/ETM+ versus OLI) | Trends could reflect sensor changes | Decide on and test harmonisation (for example published transformation coefficients) against 2013 and 2021 overlap data | M3 |
| U10 | Tide state at image time can be estimated | Vegetation, soil and inundation analysis need tide filtering | Choose a documented tide model with checked licence and model-file access (pyTMD is the candidate) or a local gauge | M3 |
| U11 | Optical water detection under mangrove canopy | Occurrence probably under-reports inundation beneath canopy | Compare with Sentinel-1 for 2020+ and state the limitation | M5 |
| U12 | Reference samples are available for training and validation | Classification and validation depend on them | Operator field data or documented high-resolution interpretation, with spatial blocking | M4 |
| U13 | SWIR salinity proxies relate to soil salinity here | Site A evidence depends on it | Local field calibration; otherwise publish as an uncalibrated proxy | M5 |
| U14 | Analysis-grid alignment matches the native Landsat grid | It avoids resampling artefacts | M1 snaps to multiples of 30 m in EPSG:32642; compare with the Landsat Collection 2 pixel-corner convention during the M2 dry run | M2 |
| U15 | Planting campaigns, floods and cyclones are documented | They explain observed changes (never causes) | Gather dated, cited records; flag them, never infer them | M5 |
| U16 | Season definitions fit every year | Monsoon flood timing varies between years | Check post-monsoon windows against inventory data and documented floods | M3 |
| U17 | Sentinel-2 SCL class 2 (dark area pixels) can stay unmasked | Dark wet surfaces near creeks may be dropped or kept wrongly | Inspect the preview; compare with Cloud Score+ masking | M3 |
| U18 | A Cloud Score+ `cs_cdf` threshold of 0.6 suits this coast | Too strict loses bright mudflats; too loose keeps haze | Tune on the preview and record the value | M3 |
| U19 | Seasons between Landsat 5's end and Landsat 8's start can be represented | Only Landsat 7 SLC-off data exist for May 2012 to March 2013 | The inventory shows the valid fractions; mark these seasons low-confidence or use epochs | M3 |
| U21 | A water threshold calibrated on composite values at reference samples transfers to single images | The tidal-inundation frequency depends on it | Compare against JRC monthly history for 2013–2021 overlap years | M5 |
| U22 | Brighter dry-season SWIR on eligible bare surfaces indicates stronger salinity-related surface conditions | It sets the direction of the soil-salinity proxy | Calibrate against field soil EC/salinity; until then the proxy is relative and uncalibrated | M5 |
| U23 | The proposed acceptance criteria (OA ≥ 0.85; class minimums; ≥ 50 validation and ≥ 30 training samples per class) are adequate | The validation gate depends on them | Operator confirms or changes them in `configs/classification.yaml` | M4 |
| U24 | The proposed site rules and weights express the study's intent | They determine Site A/B eligibility and ranking | Operator confirms or changes them in `configs/site_selection.yaml` | M6 |
| U20 | One Sentinel-1 orbit pass gives a consistent series | Mixing passes changes viewing geometry and backscatter | Choose a pass from `s1_orbit_summary.csv` and fix `sentinel1.orbit_pass` | M3 |

## Interpretation and uncertainty

# Uncertainty and interpretation guide (M4–M6)

This guide explains what the classification, the analytical layers and the site ranking
can and cannot support. It applies to every output under `outputs/m4`, `outputs/m5` and
`outputs/m6`.

**Status (2026-10-22):** the M4–M6 code is implemented and tested on mock data only. No
real classification, layer or site selection exists yet. Running them needs Earth Engine
composites (M3) and operator-supplied reference samples.

## 1. Land-cover classification (M4)

| Source of uncertainty | How it is handled | What remains |
|---|---|---|
| Reference-label errors | Samples must come from field survey or documented high-resolution interpretation, with interpreter and date. Conflicting labels at one location are rejected | Interpretation errors are not quantified; a second-interpreter check is recommended |
| Spatial autocorrelation (optimistic accuracy) | Validation comes from a separate file (preferred) or held-out 2 km blocks. Training samples within 500 m of any validation sample are dropped, and the gate fails if fewer than 30 per class remain | If validation is sampled in the same areas as training, the 500 m rule removes most training data. Plan separate areas or a block design from the start |
| Sample-based vs area-based accuracy | Wilson 95% intervals for overall, user's and producer's accuracy | With `design: non_probability`, accuracy describes the samples, not the map area. Only stratified random sampling by map class supports the Olofsson et al. (2014) area-adjusted accuracy and area estimates (with standard errors) |
| Model confidence | Per-pixel Random Forest vote fractions (`p_<class>`), `max_probability`, `margin` (top-1 minus top-2) and normalised `entropy` | Vote fractions are **not calibrated probabilities**. Use them as relative confidence only |
| Out-of-bag score | Recorded in the model metadata | Computed on spatially autocorrelated training data, so optimistic. **Never used by the gate** |
| Partial seasons | Composites from incomplete windows are flagged (`_partial`), and classification records a WARN | A partial season has fewer observations and may be biased toward the dates available |
| Historical epochs | A reference sample is used only for its own `label_year` | Reusing samples for another year requires an explicit recheck and a new row |

The validation gate (`validation_gate.json`) passes only when all of the following hold:

* the acceptance criteria are confirmed by the operator;
* training and validation samples are spatially separated;
* every class has enough training and validation samples;
* overall accuracy meets its minimum;
* the configured per-class user's and producer's minimums are met.

The gate is bound to the classification configuration and to the hash of `landcover.tif`.
Changing either invalidates it.

## 2. Analytical layers (M5)

| Layer | Type | What it is | What it is not |
|---|---|---|---|
| `mangrove_extent` | classified | Class 1 of the validated land-cover map | A field-verified canopy boundary; mixed pixels at creek edges are uncertain |
| `spectral_vigour_class` | derived | Terciles (1 low, 2 mid, 3 high) of dry-season NDVI **within the mapped mangrove of the same epoch** | Canopy density or health grades. Terciles are relative, so every epoch has about one-third "high" by construction |
| `tidal_inundation` | derived | Share of valid observations in a calendar year classed as water by a threshold calibrated on reference samples | Tide-corrected inundation. Tide state at image time is unknown (no tide model, U10); optical water detection under canopy is limited (U11) |
| `soil_salinity_proxy` | proxy | Mean within-AOI percentile rank of dry-season SWIR1 and SWIR2 on eligible bare surfaces | A salinity value. It is uncalibrated and relative to the AOI, and its direction (brighter SWIR = more saline) is an assumption (U22). It uses no red/NIR index |
| `freshwater_influence_proxy` | proxy | Distance along frequently inundated channels from an operator-documented freshwater source, plus an investigative post-monsoon turbidity change | Evidence that freshwater reaches a creek. Connectivity says nothing about flow direction, volume or salinity |
| `water_salinity_field` | measured | Operator field measurements, units as supplied | Converted values (EC to salinity needs temperature, which is not recorded) |

Independence rules, enforced in code:

* The salinity proxy takes values only from SWIR bands. Land cover and inundation decide
  only which pixels are eligible (`mask_from`). Mangrove pixels are always excluded.
* The freshwater proxy needs a documented source with recorded evidence. Without one, the
  layer is not produced, and M6 reports that Site B cannot be evaluated.
* M6 reads `derived_from` from each layer and refuses to run if salinity or freshwater
  evidence was derived from the mangrove map.

## 3. Site ranking (M6)

* **Plots:** 500 m × 500 m squares in EPSG:32642, aligned to multiples of 500 m and lying
  wholly inside the AOI. Each plot covers about 278 Landsat pixels, or 2,500 Sentinel-2
  pixels.
* **Scores:** weighted percentile ranks among eligible plots only. They order candidates
  within this AOI and epoch; they are not absolute measures and cannot be compared across
  runs.
* **Comparability:** among pairs at least 1 km apart, the highest combined score whose
  inundation difference is within the preferred limit is chosen. When that rule overrides
  the highest-scoring pair, the selection report says so and names the pair it passed over.
* **Limitations are reported, not hidden:** every plot carries its exclusion reasons. When
  either site has no eligible plot, the outcome is `NO_SELECTION` and no site polygons are
  written.

## 4. Known gaps before real use

1. No reference or validation samples exist yet (U12).
2. No tide information (U10).
3. Salinity proxy direction and features are uncalibrated (U13, U22).
4. No documented freshwater source has been supplied (U2).
5. The acceptance criteria and site-selection rules are proposals awaiting operator
   confirmation (U23, U24).

