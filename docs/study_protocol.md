# Study protocol: Keti Bandar mangrove, inundation, salinity-proxy and freshwater-influence study

Status: **draft, M1**. Sections marked *planned* describe the intended method. They have
not been run. Results are reported only from runs recorded in a `run_manifest.json`.

## 1. Purpose

The study reconstructs mangrove extent and condition, surface-water and inundation behaviour,
and salinity-related and freshwater-influence surface proxies around Keti Bandar (Indus
Delta, Sindh, Pakistan) for 2005–2026. From the validated evidence it then ranks two
comparable candidate study sites:

* **Site A**: strong salinity-related surface evidence, with sparse or absent mangrove.
* **Site B**: healthy mangrove, with independent evidence consistent with freshwater
  influence and tidal mixing.

If the evidence does not support two suitable sites, the study reports that instead of
forcing a result.

## 2. Reference location and AOI

| Item | Value | Status |
|---|---|---|
| Reference point | Keti Bandar, 67.45094 E, 24.14422 N | **Provisional**. One traceable source: GeoNames via `lutangar/cities.json`, commit `c05addf`, CC BY 4.0 |
| Analysis CRS | EPSG:32642, WGS 84 / UTM 42N | Verified by the M1 checks: projected, metres, correct zone, round-trip error < 1 mm, scale factor 0.99991 |
| Primary AOI | 5 km buffer around the reference point (78.53 km²) | Configurable in `configs/project.yaml` |
| Alternatives | 10, 15, 20 and 30 km buffers, or an operator polygon | Proposals only. Never applied silently |

The reference point is a settlement location from a gazetteer, not a hydrological feature.
The point and the AOI are edited only through `configs/project.yaml`. A point may be marked
`verified` only when a second independent source is recorded; the schema enforces this.

## 3. M1 hydrological-context review

Command: `indus-delta m1`. The full results are in `outputs/m1/m1_aoi_review.md`.

Evidence used:

1. JRC Global Surface Water v1.4 occurrence (1984–2021), read from the public tile store
   at native ~30 m and regridded with nearest neighbour to a 30 m EPSG:32642 grid.
2. Natural Earth 1:10M Indus centreline, used as a coarse cartographic reference only.

Findings of the M1 run on 2026-10-22:

* **Creeks are present.** 63 groups of frequently inundated pixels (occurrence ≥ 50%)
  intersect the 5 km AOI and cover 63.1 km² inside it.
* **The creek network is larger than any candidate AOI.** Those creeks are part of one
  continuous water body of about 2,957 km². It reaches the edge of the review extent and
  includes open coastal water, so enlarging the buffer cannot "contain" the system.
* **The 5 km AOI is almost entirely water at some time.** Only 0.09 km² was observed as
  water in fewer than 10% of observations, and only 1.96 km² in fewer than 30%. Exposed
  surfaces for Site A are therefore mainly intertidal flats, which need tide-aware analysis.
* **The mapped main channel lies outside the 5 km AOI.** The coarse Natural Earth Indus line
  passes 12.4 km from the reference point and enters only the buffers of 15 km and more. 19%
  of its pixels lie on water connected to the AOI creeks, but that connection may run
  through the sea.
* **Freshwater influence is unresolved.** No M1 input can show freshwater delivery to any
  creek. **This study does not assume that a freshwater-fed creek exists in any AOI.**

**Decision required before M2:** the operator chooses the AOI on documented hydrological
evidence (Section 9, items U2–U4). Until then the 5 km buffer remains the configured primary
AOI, because the 5 km size is a project requirement, and the review report records why it
may be insufficient.

## 4. Data and periods (planned; identifiers pending verification in M2)

| Series | Source | Period | Grid |
|---|---|---|---|
| Historical | Landsat 5 TM, 7 ETM+ (through 2021 only), 8 OLI, 9 OLI-2, Collection 2 L2 SR | 2005–2026 | 30 m |
| Recent | Sentinel-2 `COPERNICUS/S2_SR_HARMONIZED`; Sentinel-1 `COPERNICUS/S1_GRD` | 2020–2026 | 10/20 m native (index effective resolution is recorded) |
| Reference | GMW v4.1 annual extent (distribution method not yet verified); JRC GSW v1.4 | 1985–2025 / 1984–2021 | native |
| Field | Operator-supplied creek salinity/EC, ground truth | as supplied | points |

* The Landsat and Sentinel trend lines are never combined. In the 2020–2026 overlap,
  Sentinel estimates are aggregated to the Landsat 30 m grid for comparison.
* Landsat 7 data after 2021 may be used only in a separate sensitivity analysis.
* A Landsat-derived water-frequency series continues the inundation record after JRC ends
  in 2021.
* Each run starts with a scene inventory by sensor, year and season (`image_inventory.csv`)
  and fails visibly when required data are missing.

## 5. Seasons

| Season | Months | Label |
|---|---|---|
| Dry | November–March | the year in which the season ends (dry 2020 = 2019-11-01 to 2020-03-31) |
| Post-monsoon | September–October | calendar year |

2026 is reported as partial wherever its window is incomplete. The actual last observation
date is always reported. Windows are produced by `indus_delta.seasons.season_window`.

## 6. Land-cover classes and spectral features (planned)

Classes: 1 mangrove, 2 water, 3 mudflat, 4 bare saline-flat candidate, 5 non-mangrove
vegetation, 6 built-up, 7 unclassified/no-data.

Features come from `configs/indices.yaml`. Every formula uses band roles, which each sensor
maps to its own bands:

* NDVI = (NIR − Red)/(NIR + Red)
* NDMI = (NIR − SWIR1)/(NIR + SWIR1)
* MNDWI = (Green − SWIR1)/(Green + SWIR1)
* MVI = (NIR − Green)/(SWIR1 − Green)
* CMRI = NDVI − NDWI, where NDWI uses the McFeeters convention (Green − NIR)/(Green + NIR)

Rules:

* Denominators below 1e-6, masked pixels and reflectance outside 0–1 are masked, never
  clipped.
* No thresholds are fixed in code. Thresholds are estimated from reference samples and
  versioned with the model.
* A Random Forest is the baseline. Training and validation samples are spatially separated
  in blocks, and samples are rechecked before reuse in historical epochs.

## 7. Analytical outputs (planned)

* `soil_salinity_proxy`: SWIR-based features on eligible bare-soil pixels only. Mangrove,
  water, cloud, shadow and wet surfaces are excluded. Low vegetation alone never means
  saline, and no red/NIR index that reduces to −NDVI is used. The output stays provisional
  until it is calibrated with field data.
* `water_salinity_field`: measured values only, with units, date/time, GPS, tide state and
  method. Imagery never claims to measure creek salinity.
* `freshwater_influence_proxy`: traceable active-channel and connectivity data,
  distance-to-channel, and post-monsoon turbidity features, with provenance and uncertainty.
  Proximity to the historic Indus channel is not treated as freshwater input.
* `tidal_inundation`: optical and radar water frequency, with valid-observation counts,
  time windows and tide information where available.
* Condition is reported as spectral-vigour classes until locally calibrated
  dense/moderate/sparse criteria exist.
* Trends use Mann–Kendall and Sen's slope only where completeness supports them. Observed
  change is kept separate from possible explanations, and no causal claims are made.

## 8. Site selection (planned, after the validation gate)

* Plots are equal 500 m × 500 m cells in EPSG:32642 (about 278 Landsat pixels each).
* Ranking follows the brief, with these anti-circularity rules: salinity evidence must not
  be derived from the mangrove map, and freshwater mixing must not be defined by mangrove
  presence.
* Site A and Site B should have similar inundation frequency and observation conditions;
  unavoidable differences are reported.

## 9. Unresolved scientific assumptions (must be addressed before progressing)

| ID | Assumption or open question | Why it matters | How to resolve | Milestone |
|---|---|---|---|---|
| U1 | The Keti Bandar reference point is correct | It anchors the AOI | Add an independent source (official gazetteer, OSM node or field GPS) and set `verified` | before M2 |
| U2 | A creek with present-day freshwater input exists within reach of the AOI | Site B depends on it | Traceable active-channel map; Kotri-downstream discharge records for the study years; field salinity/EC | before M6 (AOI choice before M2) |
| U3 | The 5 km AOI holds enough hydrological contrast for both sites | M1 shows a 5 km AOI that is nearly all intertidal/water, with the coarse main channel 12.4 km away | Operator chooses an AOI from the review alternatives or supplies a polygon | before M2 |
| U4 | Connected water implies a creek connection to the river | The M1 connectivity test may pass through the open sea | Sea/coastline mask, then a creek-only connectivity test | M5 |
| U5 | JRC value 255 means no data (ocean or outside the product) | It affects the no-data statistics | Confirm against the JRC GSW user guide | M2 |
| U6 | The dataset IDs and scale factors in `configs/datasets.yaml` are correct | Every series depends on them | `indus-delta inventory` verifies them against Earth Engine (needs authentication) | M2 |
| U7 | GMW v4.1 is accessible | It is the independent extent reference | Verify the distribution (DOI, licence, format); import it as an asset or local raster | M2 |
| U8 | Enough cloud-free Landsat 5/7 scenes exist for 2005–2012 dry seasons | Annual versus epoch maps depend on it | Scene inventory; fall back to multi-year epochs where coverage is thin | M2 |
| U9 | Cross-sensor reflectance is consistent (TM/ETM+ versus OLI) | Trends could reflect sensor changes | Decide on and test harmonisation (for example published transformation coefficients) against 2013 and 2021 overlap data | M3 |
| U10 | Tide state at image time can be estimated | Vegetation, soil and inundation analysis need tide filtering | Choose a documented tide model with checked licence and model-file access (pyTMD is the candidate) or a local gauge | M3 |
| U11 | Optical water detection under mangrove canopy | Occurrence probably under-reports inundation beneath canopy | Compare with Sentinel-1 for 2020+ and state the limitation | M5 |
| U12 | Reference samples are available for training and validation | Classification and validation depend on them | Operator field data or documented high-resolution interpretation, with spatial blocking | M4 |
| U13 | SWIR salinity proxies relate to soil salinity here | Site A evidence depends on it | Local field calibration; otherwise publish as an uncalibrated proxy | M5 |
| U14 | Analysis-grid alignment matches the native Landsat grid | It avoids resampling artefacts | M1 snaps to multiples of 30 m in EPSG:32642; compare with the Landsat Collection 2 pixel-corner convention during the M2 dry run | M2 |
| U15 | Planting campaigns, floods and cyclones are documented | They explain observed changes (never causes) | Gather dated, cited records; flag them, never infer them | M5 |
| U16 | Season definitions fit every year | Monsoon flood timing varies between years | Check post-monsoon windows against inventory data and documented floods | M3 |

## 10. Reproducibility

* All parameters are in `configs/*.yaml` (versioned, and their SHA-256 is written to every
  manifest).
* Dependencies are locked in `uv.lock`, with Python ≥ 3.12 (tested on 3.13).
* Each command writes `run_manifest.json` with inputs, output hashes, software versions and
  the git revision.
* No mock data appear in outputs. Synthetic arrays are confined to unit tests.
