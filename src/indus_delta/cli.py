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


@app.command("inventory")
def inventory() -> None:
    """[M2] Verify dataset IDs and inventory usable scenes by sensor/year/season."""
    _later("M2")


@app.command("preview")
def preview() -> None:
    """[M2] Small-area Earth Engine dry run."""
    _later("M2")


@app.command("preprocess")
def preprocess() -> None:
    """[M3] Masked, scaled seasonal composites."""
    _later("M3")


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
