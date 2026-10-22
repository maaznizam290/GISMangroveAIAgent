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
| M2 | Earth Engine authentication, dataset-ID verification, scene inventory, small-area dry run | Not started. Blocked on Earth Engine credentials |
| M3 | Masking, scaling, harmonisation, seasonal composites, indices, tide tagging | Not started |
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

## Setup

Requires Python ≥ 3.12 (tested on 3.13) and [uv](https://docs.astral.sh/uv/).
Current rasterio, pyproj, numpy and scipy releases do not support 3.11.

```bash
uv sync                      # installs the locked core + dev environment (uv.lock)
uv run indus-delta --help
```

Docker (untested in the build environment): `docker compose run --rm pipeline m1`.

## Commands

| Command | What it does | Milestone |
|---|---|---|
| `indus-delta validate-config` | Validates `configs/*.yaml` and runs offline CRS, AOI and provenance checks | M1 |
| `indus-delta check-ee [--project P] [--probe-asset ID]` | Checks Earth Engine authentication; runs no processing | M1 |
| `indus-delta m1` | AOI layers, CRS checks, JRC-based hydrological review, preview map, manifest (reads public data over HTTPS) | M1 |
| `indus-delta inventory` / `preview` / `preprocess` / `classify` / `validate` / `select-sites` / `export` | Placeholders that exit with code 3 and run nothing | M2–M7 |

Exit codes: 0 = pass or warn, 1 = failed check, 2 = invalid configuration,
3 = not implemented.

## Earth Engine authentication (manual step, required from M2)

1. Use a Google Cloud project with the Earth Engine API enabled and registered for Earth
   Engine use.
2. Run `uv run earthengine authenticate`, or set `GOOGLE_APPLICATION_CREDENTIALS` to a
   service-account key stored **outside** this repository.
3. `cp .env.example .env`, set `EE_PROJECT`, then run `uv run indus-delta check-ee`.

No credentials are stored in the repository. `.env` is git-ignored.

## Configuration

* `configs/project.yaml`: reference location and provenance, CRS, AOI mode (`buffer` or
  `polygon`), alternative AOIs, periods, seasons, review parameters.
* `configs/datasets.yaml`: Earth Engine IDs and scale factors, all marked
  `verification: pending` until M2 confirms them.
* `configs/indices.yaml`: band-role mappings per sensor and index formulas, including the
  CMRI/NDWI convention.

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
uv run pytest -m network     # real-data M1 integration test (needs HTTPS access to public data)
uv run ruff check src tests
```

## Dashboard

The dashboard is planned for M8, once a functioning small-area run exists. Instructions for
launching it and connecting it to outputs will be added here then.

## Licence and data credits

The code is MIT. The data sources and their licences are listed in
[docs/repository_assessment.md](docs/repository_assessment.md).
