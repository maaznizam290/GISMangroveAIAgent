"""Minimal `.env` loader (KEY=VALUE lines). Never overrides variables already set in the
environment and ignores empty values, so a copied .env.example changes nothing."""

from __future__ import annotations

import os
from pathlib import Path


def load_env_file(path: Path = Path(".env")) -> list[str]:
    """Set unset variables from `path`; return the names that were set."""
    if not path.is_file():
        return []
    loaded = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and value and key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
