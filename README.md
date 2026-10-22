# indus-delta-mangrove-agent

A reproducible geospatial pipeline that reconstructs mangrove extent and condition,
inundation, salinity-related surface proxies and freshwater-influence proxies around
**Keti Bandar, Indus Delta (Sindh, Pakistan)** for 2005–2026. From validated evidence it
ranks two comparable candidate study sites: Site A (salinity evidence, sparse or absent
mangrove) and Site B (healthy mangrove with evidence consistent with freshwater influence).

The pipeline is deterministic and driven by configuration. An LLM may explain results, but
it never produces data, numbers or site choices. **No site coordinates are hard-coded; sites
must be discovered from validated maps.**

## Status

| Milestone | Scope | State |
|---|---|---|
| **M1** | Config schema, CRS checks, AOI, hydrological-context review, preview map, study protocol | **Done. Gate status WARN: operator decisions needed (see below)** |
| M2 | Dataset verification and image inventory | **Partly done.** Catalog verification run on real data; inventory implemented but **not run (no Earth Engine credentials)** |
| M3 | Seasonal windows, masking, scaling, composites, indices, small-area preview gate, gated full-scale exports | **Implemented and unit-tested; not run (no Earth Engine credentials).** Full-scale processing is blocked by design |
| M4 | Reference samples, Random Forest baseline, spatially blocked validation | Not started |
| M5 | Condition and vigour, inundation frequency, salinity and freshwater proxies, trends | Not started |
| M6 | 500 m plots, Site A/B ranking (after the validation gate) | Not started |
| M7 | GIS handover (COG/GPKG, QGIS project, data dictionary, methods) | Not started |
| M8 | Streamlit dashboard on real outputs | Not started |

See [docs/milestones.md](docs/milestones.md) for the full checklist and
[docs/study_protocol.md](docs/study_protocol.md) for the method and the list of
**unresolved scientific assumptions (U1–U16)**.

### M1 result in brief (real data, run 2026-10-22)

* EPSG:32642 suits the reference point: zone 42N, scale factor 0.99991.
* The 5 km AOI contains creeks: 63 frequently inundated water components covering 63 km².
  Those creeks belong to a water network of about 2,957 km² that is larger than every
  candidate AOI.
* Almost all of the 5 km AOI was observed as water at some point (JRC GSW 1984–2021). The
  coarse Natural Earth Indus line passes 12.4 km away and enters only buffers of 15 km or
  more.
* **Freshwater influence is unresolved.** Nothing in M1 can show it, and the project does
  not assume it.
* The reference location is **provisional**, with a single GeoNames-derived source.

The full report is `outputs/m1/m1_aoi_review.md`; the visual check is
`outputs/m1/m1_aoi_preview.png`.

### M2/M3 status in brief (2026-10-22)

* **Catalog verification (real, no auth needed):** every Earth Engine ID in
  `configs/datasets.yaml` exists in the official catalog. Its type, extent, required bands,
  SR scale/offset, Landsat QA_PIXEL and QA_RADSAT bits and Sentinel-2 SCL classes all match
  the configuration (78 of 82 checks pass; `outputs/m2/catalog_verification.csv`).
  * **GMW v4.1 is not in the official catalog.** It must be supplied by the operator.
  * Landsat 5 ends 2012-05-05, and Landsat 8 starts 2013-03-18. In between, only Landsat 7
    SLC-off data exist.
* **Not run:** the inventory, the small-area preview and all preprocessing need Earth Engine
  credentials, and none exist in the build environment. No image counts, composites or
  previews exist yet, and none have been substituted.
* **Full-scale processing is refused** until `aoi.operator_confirmed: true` is set and a
  preview passes every check for the current configuration.

## Setup

Requires Python ≥ 3.12 (tested on 3.13) and [uv](https://docs.astral.sh/uv/).
Current rasterio, pyproj, numpy and scipy releases do not support 3.11.

```bash
uv sync                      # installs the locked core + dev environment (uv.lock)
uv run indus-delta --help
```

Docker (untested in the build environment): `docker compose run --rm pipeline m1`.

## Commands

| Command | What it does | Needs Earth Engine |
|---|---|---|
| `indus-delta validate-config` | Validates `configs/*.yaml` and runs offline CRS, AOI and provenance checks | no |
| `indus-delta m1` | AOI layers, JRC-based hydrological review, preview map, manifest | no (public HTTPS) |
| `indus-delta catalog-check [--record]` | Verifies dataset IDs, extents, bands, scale/offset and QA definitions against the official catalog; `--record` writes `catalog_verified` into `datasets.yaml` | no (public HTTPS) |
| `indus-delta check-ee` | Checks Earth Engine authentication | yes |
| `indus-delta inventory [--dataset KEY ...]` | Per-image inventory over the primary AOI: `image_inventory.csv`, `inventory_summary.csv`, `missing_observations.csv`, `s1_orbit_summary.csv` | yes |
| `indus-delta preview` | Small-area dry run (3 km box): Landsat, Sentinel-2 and Sentinel-1 seasonal composites, downloaded and checked; writes `outputs/m3/preview/preview_gate.json` | yes |
| `indus-delta preprocess [--series ...] [--start]` | Plans full-AOI seasonal exports; submits them only with `--start`. Refused until the AOI is confirmed and the preview gate passed | yes, for `--start` |
| `indus-delta classify` / `validate` / `select-sites` / `export` | Placeholders; exit code 3, nothing run | |

Exit codes: 0 = pass or warn, 1 = failed check, 2 = invalid configuration,
3 = not implemented, 4 = Earth Engine unavailable, 5 = refused by a gate.

Recommended order once credentials exist:
`check-ee`, then `inventory`, then fix `sentinel1.orbit_pass` from `s1_orbit_summary.csv`,
then `preview`, then inspect `preview_quicklook.png` and `preview_gate.json`, then confirm
the AOI, then `preprocess` (plan), then `preprocess --start`.

## Earth Engine authentication (manual step, required from M2)

1. Use a Google Cloud project with the Earth Engine API enabled and registered for Earth
   Engine use.
2. Run `uv run earthengine authenticate`, or set `GOOGLE_APPLICATION_CREDENTIALS` to a
   service-account key stored **outside** this repository.
3. `cp .env.example .env`, set `EE_PROJECT`, then run `uv run indus-delta check-ee`.
4. For full-scale exports also set `EXPORT_BUCKET` (Cloud Storage) or `EXPORT_DRIVE_FOLDER`.

In a Claude Code cloud environment, add `EE_PROJECT` and a service-account key (via
`GOOGLE_APPLICATION_CREDENTIALS`) in the environment settings; never paste keys into chat.

No credentials are stored in the repository. `.env` is git-ignored.

## Configuration

* `configs/project.yaml`: reference location and provenance, CRS, AOI mode (`buffer` or
  `polygon`), alternative AOIs, periods, seasons, review parameters.
* `configs/datasets.yaml`: Earth Engine IDs, scale factors and required bands, with the
  verification level each has reached (`pending`, `catalog_verified` or `verified`).
* `configs/indices.yaml`: band-role mappings per sensor and index formulas, including the
  CMRI/NDWI convention.
* `configs/preprocessing.yaml`: mask bits and classes (with the catalog's descriptions),
  Cloud Score+ threshold, Sentinel-1 filters, composite settings, inventory and preview
  parameters.

To use a custom AOI, set `aoi.mode: polygon` and `aoi.polygon_path` to a GeoPackage or
GeoJSON file that has a CRS.

## Outputs (M1)

`outputs/m1/` contains:

* `m1_aoi.gpkg`: layers `reference_location`, `aoi_primary`, `aoi_alternatives`,
  `coarse_indus_centerline`, `jrc_water_components_touching_primary_aoi` (EPSG:32642).
* `jrc_gsw14_occurrence_review_epsg32642_30m.tif`: uint8 percentage values, nodata 255, at
  native ~30 m (not upsampled).
* `m1_aoi_preview.png`, `m1_aoi_review.md`, `m1_aoi_review.json`, `run_manifest.json`.

The GeoTIFF and GeoPackage are regenerated by `indus-delta m1` and are not committed. Their
hashes are in `run_manifest.json`.

## Tests

```bash
uv run pytest                # offline unit tests (synthetic data only in clearly labelled tests)
uv run pytest -m network     # real-data tests: M1 review and the live catalog check
uv run pytest -m ee          # authenticated Earth Engine tests (need EE_PROJECT + credentials)
uv run ruff check src tests
```

## Dashboard

The dashboard is planned for M8, once a functioning small-area run exists. Instructions for
launching it and connecting it to outputs will be added here then.

## Licence and data credits

The code is MIT. The data sources and their licences are listed in
[docs/repository_assessment.md](docs/repository_assessment.md).
