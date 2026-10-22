"""Earth Engine authentication check. Never stores or prints credentials."""

from __future__ import annotations

import os

from indus_delta.checks import Check

PROJECT_ENV = "EE_PROJECT"


def check_ee(project: str | None = None, probe_asset: str | None = None) -> list[Check]:
    project = project or os.environ.get(PROJECT_ENV)
    try:
        import ee
    except ImportError:
        return [Check("ee_import", "FAIL", "earthengine-api is not installed")]
    checks = [Check("ee_import", "PASS", f"earthengine-api {ee.__version__}")]
    if not project:
        checks.append(
            Check("ee_project", "FAIL", f"no Cloud project: set {PROJECT_ENV} (see .env.example)")
        )
        return checks
    try:
        ee.Initialize(project=project)
    except Exception as exc:  # ee raises several exception types for auth problems
        checks.append(
            Check(
                "ee_initialize",
                "FAIL",
                f"ee.Initialize(project=...) failed: {type(exc).__name__}: {exc}. "
                "Run `earthengine authenticate` (or set GOOGLE_APPLICATION_CREDENTIALS to a "
                "service-account key kept outside the repository) and retry.",
            )
        )
        return checks
    checks.append(Check("ee_initialize", "PASS", "Earth Engine initialised"))
    if probe_asset:
        try:
            info = ee.data.getAsset(probe_asset)
            checks.append(Check("ee_probe_asset", "PASS", f"{probe_asset}: {info.get('type')}"))
        except Exception as exc:
            checks.append(Check("ee_probe_asset", "FAIL", f"{probe_asset}: {exc}"))
    return checks


class EEUnavailableError(RuntimeError):
    """Earth Engine cannot be used in this environment (no project or no credentials)."""


def initialize(project: str | None = None) -> str:
    """Initialise Earth Engine or raise EEUnavailableError with the manual steps needed."""
    checks = check_ee(project)
    failed = [c for c in checks if c.status == "FAIL"]
    if failed:
        raise EEUnavailableError("; ".join(f"{c.name}: {c.detail}" for c in failed))
    return project or os.environ[PROJECT_ENV]
