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

## Errors met during M2/M3

- The proxy-provided `CLOUDSDK_AUTH_ACCESS_TOKEN` is rejected by Google (`invalid_token`). No
  Earth Engine or gcloud credentials exist, so `inventory` and `preview` exit with code 4.
- USGS, Copernicus Data Space, Planetary Computer and Earth Search STAC endpoints are
  blocked by the network policy. Only Google's Earth Engine STAC catalog is reachable, which
  is why the M2 work so far is catalog-level verification.
