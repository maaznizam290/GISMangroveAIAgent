"""Run manifest: what ran, with which inputs, configuration and software."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

TRACKED_PACKAGES = (
    "indus-delta-mangrove-agent",
    "numpy",
    "pandas",
    "scipy",
    "shapely",
    "pyproj",
    "geopandas",
    "pyogrio",
    "rasterio",
    "matplotlib",
    "pydantic",
    "earthengine-api",
)


def software_versions() -> dict[str, str]:
    out = {"python": platform.python_version()}
    for pkg in TRACKED_PACKAGES:
        try:
            out[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            out[pkg] = "not installed"
    try:
        import pyproj
        import rasterio

        out["gdal"] = rasterio.__gdal_version__
        out["proj"] = pyproj.proj_version_str
    except ImportError:
        pass
    return out


def git_revision(repo: Path = Path(".")) -> str | None:
    try:
        rev = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return f"{rev}{'-dirty' if dirty else ''}"
    except (OSError, subprocess.CalledProcessError):
        return None


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_manifest(
    path: Path,
    *,
    milestone: str,
    command: str,
    config_sha256: dict[str, str],
    inputs: list[dict],
    outputs: list[Path],
    status: str,
) -> Path:
    manifest = {
        "milestone": milestone,
        "command": command,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "status": status,
        "git_revision": git_revision(),
        "config_sha256": config_sha256,
        "software": software_versions(),
        "inputs": inputs,
        "outputs": [
            {"path": str(p), "sha256": sha256(p), "bytes": p.stat().st_size}
            for p in outputs
            if p.exists()
        ],
    }
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path
