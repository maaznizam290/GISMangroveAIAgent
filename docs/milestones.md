# Milestone checklist

## M1: configuration, CRS, AOI, protocol ✅ (gate: WARN)

- [x] Repository and environment inspected (empty repo; CPython 3.13; no Earth Engine or gcloud credentials)
- [x] Upstream repository assessment and dependency lockfile (`docs/repository_assessment.md`, `uv.lock`)
- [x] Configuration schema (`src/indus_delta/config.py`) for `project.yaml`, `datasets.yaml`, `indices.yaml`
- [x] Reference location from a traceable source, with provenance (provisional, single source)
- [x] CRS checks for EPSG:32642 (projected, metres, zone, round trip, scale factor)
- [x] Primary 5 km AOI plus configurable alternatives and polygon mode; GeoPackage layers
- [x] Hydrological-context review on real JRC GSW v1.4 data, plus a coarse river reference
- [x] AOI preview map (`outputs/m1/m1_aoi_preview.png`)
- [x] AOI review report (`outputs/m1/m1_aoi_review.md`) proposing alternatives
- [x] Study protocol with unresolved assumptions U1–U16 (`docs/study_protocol.md`)
- [x] Unit tests (72) and a real-data integration test (1) passing; ruff clean
- [x] CLI: `validate-config`, `check-ee`, `m1`, and placeholders for later commands

Open items carried forward:

- [ ] U1: second independent source for the reference point (operator)
- [ ] U2/U3: AOI decision based on documented freshwater evidence (operator)
- [ ] Earth Engine authentication (operator; see README)

Errors met during M1 (all handled):

- OSM Nominatim, Wikidata, Wikipedia, Zenodo and the Earth Engine catalog pages were
  unreachable from the build environment (network policy). The reference location was
  therefore taken from GeoNames via a GitHub-hosted redistribution, and dataset IDs remain
  `pending`.
- The JRC v1.4 tile declares no nodata. Value 255 was observed and is configured as no-data
  (assumption U5).

## M2: Earth Engine access and inventory (next)

- [ ] `check-ee` passes with the operator's project
- [ ] `inventory`: verify every `datasets.yaml` ID and scale factor and set `verified`
- [ ] `image_inventory.csv` by sensor, year and season, with valid-observation counts and a fail-visible rule
- [ ] Verify the GMW v4.1 distribution and the import route
- [ ] Small-area dry run (preview) on a subset of the chosen AOI
- [ ] Check grid alignment against the native Landsat grid (U14)

## M3–M8

See the README status table and `docs/study_protocol.md` sections 4–8.
