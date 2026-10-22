"""Command-line interface: `indus-delta --help`."""

from __future__ import annotations

import logging
from pathlib import Path

import typer

from indus_delta.checks import Check, worst
from indus_delta.config import ConfigError, load_configs

app = typer.Typer(
    add_completion=False, no_args_is_help=True, help="Indus Delta mangrove pipeline (Keti Bandar)."
)

ConfigDir = typer.Option(Path("configs"), "--config-dir", "-c", help="Directory with YAML configs.")


def _print(checks: list[Check]) -> None:
    for c in checks:
        colour = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}[c.status]
        typer.echo(f"[{typer.style(c.status, fg=colour)}] {c.name}: {c.detail}")


def _load(config_dir: Path):
    try:
        return load_configs(config_dir)
    except ConfigError as exc:
        typer.secho(str(exc), fg="red", err=True)
        raise typer.Exit(2) from exc


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    # Settings such as EE_PROJECT may live in ./.env (see .env.example); shell values win.
    from indus_delta.envfile import load_env_file

    load_env_file()
    # Verify HTTPS (Earth Engine, catalog, M1 downloads) against the OS trust store, so
    # TLS-inspecting antivirus or proxies with a locally trusted root do not break requests.
    import truststore

    truststore.inject_into_ssl()
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@app.command("validate-config")
def validate_config(config_dir: Path = ConfigDir) -> None:
    """Validate configs and run offline CRS/AOI/provenance checks."""
    from indus_delta.m1 import static_checks

    checks = static_checks(_load(config_dir))
    _print(checks)
    raise typer.Exit(1 if worst(checks) == "FAIL" else 0)


@app.command("check-ee")
def check_ee(
    project: str = typer.Option(None, help="Cloud project (default: $EE_PROJECT)."),
    probe_asset: str = typer.Option(None, help="Optional asset/collection ID to look up."),
) -> None:
    """Check Earth Engine authentication (no processing)."""
    from indus_delta.ee_auth import check_ee as _check

    checks = _check(project, probe_asset)
    _print(checks)
    raise typer.Exit(1 if worst(checks) == "FAIL" else 0)


@app.command("m1")
def m1(
    config_dir: Path = ConfigDir,
    out_dir: Path = typer.Option(None, help="Output root (default: project.output_dir)."),
    cache_dir: Path = typer.Option(Path("data/cache"), help="Download cache."),
) -> None:
    """M1: AOI layers, CRS checks, hydrological-context review, preview map, manifest."""
    from indus_delta.m1 import run_m1

    cfgs = _load(config_dir)
    try:
        result = run_m1(cfgs, out_dir, cache_dir)
    except (RuntimeError, OSError, ValueError) as exc:
        typer.secho(f"M1 failed: {exc}", fg="red", err=True)
        raise typer.Exit(1) from exc
    _print(result.checks)
    typer.echo(f"\nM1 status: {result.status}. Outputs in {result.out_dir}:")
    for p in result.outputs:
        typer.echo(f"  {p}")
    raise typer.Exit(1 if result.status == "FAIL" else 0)


def _ee_or_exit(project: str | None) -> None:
    from indus_delta.ee_auth import EEUnavailableError, initialize

    try:
        initialize(project)
    except EEUnavailableError as exc:
        typer.secho(f"Earth Engine unavailable: {exc}", fg="red", err=True)
        typer.secho(
            "No processing was run. See README: Earth Engine authentication.", fg="yellow", err=True
        )
        raise typer.Exit(4) from exc


EEProject = typer.Option(None, "--project", help="Cloud project (default: $EE_PROJECT).")
OutDir = typer.Option(None, "--out-dir", help="Output root (default: project.output_dir).")


@app.command("catalog-check")
def catalog_check(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    record: bool = typer.Option(
        False, "--record", help="Write catalog_verified status into datasets.yaml."
    ),
) -> None:
    """[M2] Verify dataset IDs, extents, bands, scale/offset and QA definitions against the
    official Earth Engine catalog (no authentication needed)."""
    from indus_delta.m2 import run_catalog

    cfgs = _load(config_dir)
    status, path = run_catalog(
        cfgs,
        out_dir or cfgs.project.project.output_dir,
        record_to=config_dir / "datasets.yaml" if record else None,
    )
    import pandas as pd

    df = pd.read_csv(path / "catalog_verification.csv")
    for r in df.itertuples():
        if r.status != "PASS" or r.check == "temporal_extent":
            typer.echo(f"[{r.status}] {r.dataset}.{r.check}: {r.detail}")
    typer.echo(
        f"\n{(df.status == 'PASS').sum()}/{len(df)} checks passed; status {status}. "
        f"Details: {path / 'catalog_verification.csv'}"
    )
    raise typer.Exit(1 if status == "FAIL" else 0)


@app.command("inventory")
def inventory(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    project: str = EEProject,
    dataset: list[str] = typer.Option(None, "--dataset", help="Limit to these dataset keys."),
) -> None:
    """[M2] Inventory images by sensor, year and season over the primary AOI (Earth Engine)."""
    from indus_delta.inventory import InventoryError
    from indus_delta.m2 import run_inventory

    cfgs = _load(config_dir)
    _ee_or_exit(project)
    try:
        status, checks, path = run_inventory(
            cfgs, out_dir or cfgs.project.project.output_dir, datasets=dataset or None
        )
    except InventoryError as exc:
        typer.secho(f"Inventory FAILED: {exc}", fg="red", err=True)
        raise typer.Exit(1) from exc
    _print(checks)
    typer.echo(f"\nInventory status {status}; files in {path}")


@app.command("preview")
def preview(config_dir: Path = ConfigDir, out_dir: Path = OutDir, project: str = EEProject) -> None:
    """[M3] Small-area dry run: seasonal composites for a box around the reference point,
    downloaded and checked. Writes the preview gate."""
    from indus_delta.m3_preview import run_preview

    cfgs = _load(config_dir)
    _ee_or_exit(project)
    status, checks, path = run_preview(cfgs, out_dir or cfgs.project.project.output_dir)
    _print(checks)
    typer.echo(f"\nPreview gate: {status}. Files in {path}")
    raise typer.Exit(0 if status == "PASS" else 1)


@app.command("preprocess")
def preprocess(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    project: str = EEProject,
    series: list[str] = typer.Option(["landsat", "sentinel2", "sentinel1"], "--series"),
    start: bool = typer.Option(
        False, "--start", help="Actually submit the Earth Engine export tasks."
    ),
    resubmit: bool = typer.Option(
        False, "--resubmit", help="Export again even where a task is queued, running or done."
    ),
) -> None:
    """[M3] Full-AOI seasonal composites. Plans only, unless --start is given. Refused until
    the AOI is confirmed and the preview gate has passed for the current configuration."""
    from datetime import UTC, datetime

    from indus_delta.gate import GateError
    from indus_delta.m3_export import check_preconditions, plan_exports, submit_exports, write_plan

    cfgs = _load(config_dir)
    root = out_dir or cfgs.project.project.output_dir
    try:
        gate = check_preconditions(cfgs, root / "m3" / "preview")
        plan = plan_exports(cfgs, gate, series, datetime.now(UTC).date())
    except GateError as exc:
        typer.secho(f"Full-scale processing refused: {exc}", fg="red", err=True)
        raise typer.Exit(5) from exc
    plan_path = root / "m3" / "export_plan.json"
    total = sum(p["pixels"] for p in plan)
    if not start:
        path = _dry_run_path(plan_path)
        write_plan(path, plan)
        typer.echo(
            f"{len(plan)} composites planned ({total:,} pixels per band in total). "
            f"Plan: {path}. Nothing submitted; rerun with --start to export."
        )
        return
    _ee_or_exit(project)
    try:
        submitted = submit_exports(
            cfgs, plan, gate, lambda r: write_plan(plan_path, plan, r), resubmit
        )
    except GateError as exc:
        typer.secho(f"Export refused: {exc}", fg="red", err=True)
        raise typer.Exit(5) from exc
    _report_submitted(submitted, plan_path)


def _dry_run_path(plan_path: Path) -> Path:
    """A dry run never overwrites a record of submitted tasks."""
    import json

    if plan_path.is_file() and json.loads(plan_path.read_text(encoding="utf-8")).get("submitted"):
        return plan_path.with_name(plan_path.stem + "_dryrun.json")
    return plan_path


def _report_submitted(submitted: list[dict], record: Path) -> None:
    new = sum(r["status"] == "submitted" and "task_state" not in r for r in submitted)
    reused = sum("task_state" in r for r in submitted)
    skipped = sum(r["status"] == "skipped" for r in submitted)
    typer.echo(
        f"{new} export tasks submitted, {reused} already queued/running/done (not "
        f"duplicated), {skipped} skipped (no images). Record: {record}"
    )


@app.command("import-exports")
def import_exports(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    from_dir: Path = typer.Option(
        ..., "--from", help="Folder with the GeoTIFFs downloaded from Drive / Cloud Storage."
    ),
) -> None:
    """[M3/M5] Check downloaded exports against their plans (CRS, grid, bands) and copy them
    to the folders `classify` and `layers` read. Mismatching files are not imported."""
    from indus_delta.gate import GateError
    from indus_delta.m3_export import import_exports as _import

    cfgs = _load(config_dir)
    try:
        status, checks, manifest = _import(
            cfgs, out_dir or cfgs.project.project.output_dir, from_dir
        )
    except (GateError, FileNotFoundError) as exc:
        typer.secho(f"Import refused: {exc}", fg="red", err=True)
        raise typer.Exit(5) from exc
    _print(checks)
    n = sum(c.status == "PASS" for c in checks)
    typer.echo(f"\n{n} of {len(checks)} planned files imported; status {status}. {manifest}")
    raise typer.Exit(1 if status == "FAIL" else 0)


Series = typer.Option("landsat", "--series", help="landsat or sentinel2")
Year = typer.Option(..., "--year", help="Label year of the epoch.")


def _gated(fn, *args):
    from indus_delta.gate import GateError
    from indus_delta.m5 import LayerUnavailable
    from indus_delta.samples import SamplesUnavailable

    try:
        return fn(*args)
    except (GateError, SamplesUnavailable, LayerUnavailable, FileNotFoundError) as exc:
        typer.secho(f"Refused / not possible: {exc}", fg="red", err=True)
        raise typer.Exit(5) from exc


@app.command("classify")
def classify(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M4] Random Forest land cover from exported composites and operator reference samples,
    validated on independent, spatially separated samples. Writes the validation gate."""
    from indus_delta.m4 import run_classification

    cfgs = _load(config_dir)
    status, checks, path = _gated(
        run_classification, cfgs, out_dir or cfgs.project.project.output_dir, series, year
    )
    _print(checks)
    typer.echo(f"\nValidation gate: {status}. Accuracy tables and report in {path}")
    raise typer.Exit(0 if status == "PASS" else 1)


@app.command("validate")
def validate(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M4] Show the stored validation gate and accuracy of a classified epoch."""
    import json

    from indus_delta.m4 import VALIDATION_GATE, epoch_dir

    cfgs = _load(config_dir)
    d = epoch_dir(out_dir or cfgs.project.project.output_dir, series, year)
    if not (d / VALIDATION_GATE).is_file():
        typer.secho(
            f"No validation gate in {d}; run `indus-delta classify` first.", fg="red", err=True
        )
        raise typer.Exit(5)
    gate = json.loads((d / VALIDATION_GATE).read_text())
    _print([Check(c["name"], c["status"], c["detail"]) for c in gate["checks"]])
    typer.echo(f"\nGate {gate['status']}; tables: {d / 'classification_accuracy.csv'}")
    raise typer.Exit(0 if gate["status"] == "PASS" else 1)


@app.command("calibrate-water")
def calibrate_water(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M5] Water-index threshold from reference samples (water vs other classes) on the dry
    composite. Prints the result; record it in configs/layers.yaml yourself."""
    import json

    from indus_delta import aoi as aoi_mod
    from indus_delta.features import load_stack, sample_stack
    from indus_delta.m5 import calibrate_threshold
    from indus_delta.samples import load_samples

    cfgs = _load(config_dir)
    ti = cfgs.layers.tidal_inundation
    ref, _ = _gated(
        load_samples,
        cfgs.classification.samples.reference_path,
        cfgs,
        aoi_mod.build_aoi(cfgs.project),
        "reference",
    )
    ref = ref[ref["label_year"] == year]
    stack = _gated(load_stack, cfgs, series, year)
    vals = sample_stack(stack, ref)[f"dry_{ti.optical_index}"].to_numpy()
    water = (ref["class_code"] == cfgs.classification.code_of("water")).to_numpy()
    t, ba = calibrate_threshold(vals, water)
    root = out_dir or cfgs.project.project.output_dir
    path = root / "m5" / f"water_threshold_{series}_{year}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "index": f"dry_{ti.optical_index}",
                "threshold": t,
                "balanced_accuracy_on_reference": ba,
                "n_water": int(water.sum()),
                "n_other": int((~water).sum()),
                "note": "calibrated on composite values at reference samples; "
                "applied per image in Earth Engine",
            },
            indent=2,
        )
    )
    typer.echo(
        f"{ti.optical_index} threshold {t:.4f} (balanced accuracy {ba:.3f} on "
        f"{len(ref)} reference samples). Saved {path}. To use it, set "
        "tidal_inundation.optical_threshold and calibration_note in configs/layers.yaml."
    )


@app.command("water-frequency")
def water_frequency(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    project: str = EEProject,
    year: list[int] = typer.Option(..., "--year"),
    start: bool = typer.Option(False, "--start", help="Submit the Earth Engine exports."),
    resubmit: bool = typer.Option(
        False, "--resubmit", help="Export again even where a task is queued, running or done."
    ),
) -> None:
    """[M5] Annual Landsat water-frequency exports (gated like `preprocess`)."""
    from indus_delta.m3_export import (
        check_preconditions,
        plan_water_exports,
        submit_water_exports,
        write_plan,
    )

    cfgs = _load(config_dir)
    root = out_dir or cfgs.project.project.output_dir
    gate = _gated(check_preconditions, cfgs, root / "m3" / "preview")
    plan = _gated(plan_water_exports, cfgs, gate, list(year))
    path = root / "m5" / "water_export_plan.json"
    if not start:
        dry = _dry_run_path(path)
        write_plan(dry, plan)
        typer.echo(f"{len(plan)} water-frequency exports planned: {dry}. Nothing submitted.")
        return
    _ee_or_exit(project)
    submitted = _gated(
        submit_water_exports, cfgs, plan, lambda r: write_plan(path, plan, r), resubmit
    )
    _report_submitted(submitted, path)


@app.command("layers")
def layers(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M5] Separate mangrove, tidal-inundation, soil-salinity-proxy, freshwater-influence-proxy
    and field water-salinity layers. Unavailable layers are reported, never substituted."""
    from indus_delta.m5 import run_layers

    cfgs = _load(config_dir)
    results, checks, path = _gated(
        run_layers, cfgs, out_dir or cfgs.project.project.output_dir, series, year
    )
    _print(checks)
    typer.echo(f"\nLayers in {path}")


@app.command("trends")
def trends(config_dir: Path = ConfigDir, out_dir: Path = OutDir) -> None:
    """[M5] annual_metrics.csv for all classified epochs and Mann-Kendall / Sen's slope where
    completeness allows (validated epochs only; series never pooled)."""
    from indus_delta import aoi as aoi_mod
    from indus_delta.trends import annual_metrics, trend_table

    cfgs = _load(config_dir)
    root = out_dir or cfgs.project.project.output_dir
    metrics = annual_metrics(cfgs, root, float(aoi_mod.build_aoi(cfgs.project).area_km2.iloc[0]))
    (root / "m5").mkdir(parents=True, exist_ok=True)
    metrics.to_csv(root / "m5" / "annual_metrics.csv", index=False)
    tt = trend_table(metrics, cfgs)
    tt.to_csv(root / "m5" / "trend_tests.csv", index=False)
    typer.echo(
        f"{len(metrics)} epochs in annual_metrics.csv; {len(tt)} trend rows "
        f"(see status/reason). Files in {root / 'm5'}"
    )


@app.command("change")
def change(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    series: str = Series,
    from_year: int = typer.Option(..., "--from-year"),
    to_year: int = typer.Option(..., "--to-year"),
) -> None:
    """[M5] Class transitions and mangrove gain/loss between two validated epochs."""
    from indus_delta.m5 import run_change

    cfgs = _load(config_dir)
    path, summary = _gated(
        run_change, cfgs, out_dir or cfgs.project.project.output_dir, series, from_year, to_year
    )
    typer.echo(f"{path}: {summary}")


@app.command("select-sites")
def select_sites(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M6] Rank 500 m plots and select Site A / Site B. Refused until the validation gate has
    passed and the selection rules are confirmed; reports a limitation instead of forcing a
    result."""
    from indus_delta.m6 import run_site_selection

    cfgs = _load(config_dir)
    status, checks, path = _gated(
        run_site_selection, cfgs, out_dir or cfgs.project.project.output_dir, series, year
    )
    _print(checks)
    typer.echo(f"\nSelection outcome: {status}. Files in {path}")


@app.command("handover")
def handover(
    config_dir: Path = ConfigDir, out_dir: Path = OutDir, series: str = Series, year: int = Year
) -> None:
    """[M7] Build and validate the GIS handover package (COG, GeoPackage, tables, QGIS
    project, reports). Status COMPLETE only when every required deliverable is present and
    every check passes."""
    from indus_delta.handover import build_handover

    cfgs = _load(config_dir)
    status, items, pkg = build_handover(
        cfgs, out_dir or cfgs.project.project.output_dir, series, year
    )
    for it in items:
        bad = [c for c in it.checks if c.status == "FAIL"]
        mark = (
            "FAIL"
            if bad
            else ("ok" if it.status == "delivered" else "MISSING" if it.required else "absent")
        )
        typer.echo(f"[{mark}] {it.kind:9s} {it.id}" + (f": {bad[0].detail}" if bad else ""))
    typer.echo(f"\nHandover status: {status}. Package: {pkg} (see handover_validation.md)")
    raise typer.Exit({"COMPLETE": 0, "INCOMPLETE": 0, "FAIL": 1}[status])


@app.command("dashboard")
def dashboard(
    config_dir: Path = ConfigDir,
    out_dir: Path = OutDir,
    port: int = typer.Option(8501, "--port"),
) -> None:
    """[M8] Launch the Streamlit dashboard on the pipeline outputs (display only)."""
    import os
    import subprocess
    import sys

    cfgs = _load(config_dir)
    env = {
        **os.environ,
        "INDUS_DELTA_OUTPUTS": str(out_dir or cfgs.project.project.output_dir),
        "INDUS_DELTA_CONFIGS": str(config_dir),
    }
    app_path = Path(__file__).with_name("dashboard") / "app.py"
    raise typer.Exit(
        subprocess.call(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                str(app_path),
                "--server.port",
                str(port),
                "--server.headless",
                "true",
            ],
            env=env,
        )
    )
