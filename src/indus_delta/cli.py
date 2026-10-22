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


def _later(milestone: str) -> None:
    typer.secho(
        f"Not implemented yet (planned for {milestone}); no processing was run.",
        fg="yellow",
        err=True,
    )
    raise typer.Exit(3)


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
        write_plan(plan_path, plan)
        typer.echo(
            f"{len(plan)} composites planned ({total:,} pixels per band in total). "
            f"Plan: {plan_path}. Nothing submitted; rerun with --start to export."
        )
        return
    _ee_or_exit(project)
    try:
        submitted = submit_exports(cfgs, plan, gate)
    except GateError as exc:
        typer.secho(f"Export refused: {exc}", fg="red", err=True)
        raise typer.Exit(5) from exc
    write_plan(plan_path, plan, submitted)
    n = sum(1 for r in submitted if r["status"] == "submitted")
    typer.echo(f"{n} export tasks submitted, {len(submitted) - n} skipped. Record: {plan_path}")


@app.command("classify")
def classify() -> None:
    """[M4] Random Forest land-cover baseline."""
    _later("M4")


@app.command("validate")
def validate() -> None:
    """[M4] Accuracy assessment on spatially separated samples."""
    _later("M4")


@app.command("select-sites")
def select_sites() -> None:
    """[M6] Candidate Site A / Site B ranking (requires the validation gate)."""
    _later("M6")


@app.command("export")
def export() -> None:
    """[M7] GIS handover package."""
    _later("M7")
