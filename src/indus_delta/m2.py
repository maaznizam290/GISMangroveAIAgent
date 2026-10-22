"""Milestone M2: catalog verification (no auth) and image inventory (Earth Engine)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from indus_delta import aoi as aoi_mod
from indus_delta.catalog import checks_to_rows, record_in_registry, run_catalog_check
from indus_delta.checks import Check, worst
from indus_delta.config import Configs
from indus_delta.inventory import (
    InventoryError,
    build_records,
    inventory_checks,
    missing_observations,
    s1_orbit_summary,
    summarise,
)
from indus_delta.manifest import write_manifest

log = logging.getLogger(__name__)


def run_catalog(
    cfgs: Configs,
    out_root: Path,
    today: date | None = None,
    command: str = "indus-delta catalog-check",
    record_to: Path | None = None,
) -> tuple[str, Path]:
    today = today or datetime.now(UTC).date()
    out_dir = out_root / "m2"
    out_dir.mkdir(parents=True, exist_ok=True)
    checks, records = run_catalog_check(cfgs, today)
    status = worst([Check(c.check, c.status, c.detail) for c in checks])
    csv = out_dir / "catalog_verification.csv"
    pd.DataFrame(checks_to_rows(checks)).to_csv(csv, index=False)
    js = out_dir / "catalog_records.json"
    js.write_text(
        json.dumps(
            {
                "status": status,
                "retrieved_utc": datetime.now(UTC).isoformat(timespec="seconds"),
                "records": records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    write_manifest(
        out_dir / "catalog_manifest.json",
        milestone="M2-catalog",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[
            {
                "stac_root": cfgs.preprocessing.catalog.stac_root,
                "records": {k: v["record_sha256"] for k, v in records.items()},
            }
        ],
        outputs=[csv, js],
        status=status,
    )
    if record_to is not None:
        updated = record_in_registry(
            record_to,
            checks,
            records,
            f"indus-delta catalog-check ({out_dir / 'catalog_records.json'})",
            today,
        )
        log.info("recorded catalog verification for %s in %s", updated, record_to)
    return status, out_dir


def run_inventory(
    cfgs: Configs,
    out_root: Path,
    today: date | None = None,
    datasets: list[str] | None = None,
    command: str = "indus-delta inventory",
) -> tuple[str, list[Check], Path]:
    from indus_delta.earthengine.inventory_ee import collect_records
    from indus_delta.earthengine.util import to_ee_geometry

    today = today or datetime.now(UTC).date()
    out_dir = out_root / "m2"
    out_dir.mkdir(parents=True, exist_ok=True)
    region = to_ee_geometry(aoi_mod.build_aoi(cfgs.project))
    raw, errors = collect_records(cfgs, region, today, datasets)
    records = build_records(raw, cfgs)
    data_end = {}
    for series, grp in records.groupby("series"):
        data_end[series] = date.fromisoformat(grp["date"].max())
    summary = summarise(records, cfgs, data_end)
    missing = missing_observations(summary)
    checks = inventory_checks(records, summary, cfgs)
    checks += [Check(f"request_{k}", "FAIL", v) for k, v in errors.items()]
    if not cfgs.project.aoi.operator_confirmed:
        checks.append(
            Check(
                "aoi_confirmed",
                "WARN",
                "inventory region is the configured primary AOI, which the operator "
                "has not yet confirmed (M1 review)",
            )
        )
    status = worst(checks)

    outputs = []
    for name, df in [
        ("image_inventory.csv", records),
        ("inventory_summary.csv", summary),
        ("missing_observations.csv", missing),
        ("s1_orbit_summary.csv", s1_orbit_summary(records)),
    ]:
        path = out_dir / name
        df.to_csv(path, index=False)
        outputs.append(path)
    cj = out_dir / "inventory_checks.json"
    cj.write_text(
        json.dumps(
            {
                "status": status,
                "data_end": {k: v.isoformat() for k, v in data_end.items()},
                "checks": [c.to_dict() for c in checks],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    outputs.append(cj)
    write_manifest(
        out_dir / "inventory_manifest.json",
        milestone="M2-inventory",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[
            {
                "datasets": {
                    k: cfgs.datasets.datasets[k].ee_id
                    for k in (datasets or cfgs.preprocessing.inventory.required_datasets)
                }
            }
        ],
        outputs=outputs,
        status=status,
    )
    if status == "FAIL":
        raise InventoryError(
            "; ".join(c.detail for c in checks if c.status == "FAIL")
            + f" (inventory written to {out_dir})"
        )
    return status, checks, out_dir
