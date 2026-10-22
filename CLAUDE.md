# CLAUDE.md: working rules for this repository

## Scientific integrity (non-negotiable)
- Never fabricate data, coordinates, metrics or map results. Mock data are allowed only in
  unit tests, labelled as MOCK.
- Never hard-code site coordinates, asset paths, account details or unverified dataset IDs.
  Everything goes in `configs/*.yaml`.
- Do not claim a dataset was processed or a map validated unless a recorded run did it and
  its output was inspected.
- Freshwater influence is never inferred from proximity to the Indus or from mangrove
  presence. Salinity is never inferred from low vegetation indices alone.
- Do not start costly Earth Engine exports automatically. Do a small-area dry run first.

## Engineering
- Python ≥ 3.12, uv-managed: `uv sync`, `uv run pytest`, `uv run ruff check src tests`,
  `uv run ruff format src tests`.
- Network tests: `uv run pytest -m network`. Earth Engine tests are marked `ee`.
- Distances and areas are computed in EPSG:32642 only.
- Every command that writes outputs also writes a `run_manifest.json` (`indus_delta.manifest`).
- Keep milestones incremental: implement, test, record results, then update `README.md` and
  `docs/milestones.md`.

## Layout
- `src/indus_delta/`: package. `config.py` (schema), `crs.py`, `aoi.py`, `seasons.py`,
  `hydrology.py` (M1 review), `preview.py`, `m1.py`, `manifest.py`, `ee_auth.py`, `cli.py`,
  `catalog.py` and `m2.py` (catalog check, inventory), `inventory.py`, `spectral.py` (NumPy
  reference), `grid.py`, `preview_checks.py`, `gate.py`, `m3_preview.py`, `m3_export.py`
- `src/indus_delta/earthengine/`: all Earth Engine calls (prep, composite, inventory, download)
- Full-scale processing must go through the gate (`m3_export.check_preconditions`); never
  bypass it or start exports without `--start`.
- `configs/`: versioned parameters. `docs/`: protocol, assessment, milestones.
- `gee/`: Earth Engine script notes. `outputs/`: generated (large files git-ignored).
