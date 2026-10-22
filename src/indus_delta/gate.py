"""Preview gate: full-scale processing is refused until a preview for the current
configuration has passed every check."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from indus_delta.checks import Check
from indus_delta.config import Configs

GATE_FILE = "preview_gate.json"


class GateError(RuntimeError):
    pass


def gate_status(checks: list[Check]) -> str:
    return "FAIL" if any(c.status == "FAIL" for c in checks) else "PASS"


def write_gate(preview_dir: Path, cfgs: Configs, checks: list[Check], metadata: dict) -> Path:
    preview_dir.mkdir(parents=True, exist_ok=True)
    path = preview_dir / GATE_FILE
    path.write_text(
        json.dumps(
            {
                "status": gate_status(checks),
                "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "config_sha256": cfgs.combined_sha256(),
                "checks": [c.to_dict() for c in checks],
                "metadata": metadata,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def require_preview_pass(cfgs: Configs, preview_dir: Path) -> dict:
    path = preview_dir / GATE_FILE
    if not path.is_file():
        raise GateError(f"no preview gate at {path}; run `indus-delta preview` first")
    gate = json.loads(path.read_text(encoding="utf-8"))
    if gate.get("status") != "PASS":
        failed = [c["name"] for c in gate.get("checks", []) if c["status"] == "FAIL"]
        raise GateError(f"preview gate is {gate.get('status')}; failed checks: {failed}")
    if gate.get("config_sha256") != cfgs.combined_sha256():
        raise GateError("configuration changed since the preview passed; rerun the preview")
    return gate
