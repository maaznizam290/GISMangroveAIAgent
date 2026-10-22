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
