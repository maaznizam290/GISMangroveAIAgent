"""Milestone M4: Random Forest land-cover baseline with independent validation and a gate.

Outputs (outputs/m4/{series}_{year}/):
  landcover.tif, classification_uncertainty.tif, samples.gpkg (training / validation),
  classification_accuracy.csv, confusion_matrix.csv, accuracy_report.md,
  validation_gate.json, model files, run_manifest.json
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from indus_delta import aoi as aoi_mod
from indus_delta.accuracy import class_metrics, confusion, olofsson, overall
from indus_delta.aoi import write_layers
from indus_delta.checks import Check
from indus_delta.config import Configs
from indus_delta.features import load_stack, sample_raster, sample_stack
from indus_delta.layer_io import Grid, LayerMeta, write_layer
from indus_delta.manifest import sha256, write_manifest
from indus_delta.reporting import md_table
from indus_delta.rf import predict, save_model, train
from indus_delta.samples import (
    class_counts,
    enforce_separation,
    holdout_blocks,
    load_samples,
)

log = logging.getLogger(__name__)

VALIDATION_GATE = "validation_gate.json"
# Configuration files that determine the classification. The gate is bound to these, so
# confirming site-selection rules later does not invalidate it.
GATE_CONFIGS = (
    "project.yaml",
    "datasets.yaml",
    "indices.yaml",
    "preprocessing.yaml",
    "classification.yaml",
)


def classification_config_hash(cfgs: Configs) -> str:
    joined = "".join(f"{k}={cfgs.sha256[k]};" for k in GATE_CONFIGS)
    return hashlib.sha256(joined.encode()).hexdigest()


def epoch_dir(out_root: Path, series: str, year: int) -> Path:
    return out_root / "m4" / f"{series}_{year}"


def gate_checks(
    cfgs: Configs,
    metrics: pd.DataFrame,
    oa: float,
    n_val: dict[str, int],
    n_train: dict[str, int],
    separation: Check,
    source: str,
) -> list[Check]:
    acc = cfgs.classification.acceptance
    checks = [separation]
    few = {k: v for k, v in n_train.items() if v < acc.min_training_samples_per_class}
    checks.append(
        Check(
            "training_sample_counts",
            "FAIL" if few else "PASS",
            f"classes below {acc.min_training_samples_per_class} training samples after spatial "
            f"separation: {few}"
            if few
            else f"all classes have >= {acc.min_training_samples_per_class} training samples",
        )
    )
    checks.append(
        Check(
            "acceptance_criteria_confirmed",
            "PASS" if acc.operator_confirmed else "FAIL",
            "acceptance criteria confirmed by the operator"
            if acc.operator_confirmed
            else "acceptance.operator_confirmed is false in configs/classification.yaml",
        )
    )
    checks.append(
        Check(
            "validation_independent",
            "PASS" if source == "independent_file" else "WARN",
            "validation samples come from a separate operator file"
            if source == "independent_file"
            else "validation samples are held-out spatial blocks of the reference set",
        )
    )
    low = {k: v for k, v in n_val.items() if v < acc.min_validation_samples_per_class}
    checks.append(
        Check(
            "validation_sample_counts",
            "FAIL" if low else "PASS",
            f"classes below {acc.min_validation_samples_per_class} validation samples: {low}"
            if low
            else f"all classes have >= {acc.min_validation_samples_per_class} samples",
        )
    )
    checks.append(
        Check(
            "overall_accuracy",
            "PASS" if oa >= acc.overall_accuracy_min else "FAIL",
            f"overall accuracy {oa:.3f} (minimum {acc.overall_accuracy_min})",
        )
    )
    by_name = metrics.set_index("class_name")
    for name, req in acc.class_minimums.items():
        ua = by_name.loc[name, "users_accuracy"]
        pa = by_name.loc[name, "producers_accuracy"]
        ok = bool(
            np.isfinite(ua)
            and np.isfinite(pa)
            and ua >= req.users_accuracy
            and pa >= req.producers_accuracy
        )
        checks.append(
            Check(
                f"class_{name}",
                "PASS" if ok else "FAIL",
                f"user's {ua:.3f} (min {req.users_accuracy}), producer's {pa:.3f} "
                f"(min {req.producers_accuracy})",
            )
        )
    return checks


def run_classification(
    cfgs: Configs, out_root: Path, series: str, year: int, command: str = "indus-delta classify"
) -> tuple[str, list[Check], Path]:
    cl = cfgs.classification
    out = epoch_dir(out_root, series, year)
    out.mkdir(parents=True, exist_ok=True)
    aoi = aoi_mod.build_aoi(cfgs.project)
    checks: list[Check] = []

    # ---- samples (operator-supplied; never generated here)
    ref, c = load_samples(cl.samples.reference_path, cfgs, aoi, "reference")
    checks += c
    ref = ref[ref["label_year"] == year]
    if cl.split.validation_source == "independent_file":
        val, c = load_samples(cl.samples.validation_path, cfgs, aoi, "validation")
        checks += c
        val = val[val["label_year"] == year]
        overlap = set(ref["sample_id"]) & set(val["sample_id"])
        if overlap:
            raise ValueError(
                f"sample_ids present in both reference and validation: {sorted(overlap)[:5]}"
            )
        train_gdf = ref
    else:
        train_gdf, val = holdout_blocks(ref, cfgs)
    train_gdf, separation = enforce_separation(
        train_gdf, val, cl.split.min_train_validation_distance_m
    )

    # ---- features and model
    stack = load_stack(cfgs, series, year)
    if stack.partial_seasons:
        checks.append(
            Check(
                "composite_completeness", "WARN", f"partial seasons used: {stack.partial_seasons}"
            )
        )
    X = sample_stack(stack, train_gdf)
    ok = X.notna().all(axis=1)
    if (~ok).any():
        checks.append(
            Check(
                "training_samples_without_data",
                "WARN",
                f"{int((~ok).sum())} training samples fall on missing data",
            )
        )
    train_gdf, X = train_gdf[ok], X[ok]
    tm = train(X.to_numpy(), train_gdf["class_code"].to_numpy(), stack.names, cfgs)
    pred = predict(tm, stack, cl.nodata_class)

    # ---- map outputs
    status_tag = "pending_validation"  # replaced by the gate outcome below
    lc_path = write_layer(
        out / "landcover.tif",
        {"landcover_class": pred.classes},
        stack.grid,
        LayerMeta(
            "landcover",
            "classified",
            status_tag,
            "Random Forest land cover; class codes in configs/classification.yaml; "
            f"{cl.nodata_class} = unclassified/no data",
            derived_from=[f"{series}_{s}_{year}" for s in cl.features.seasons],
            units={"landcover_class": "class code"},
            extra={"classes": json.dumps({c.code: c.name for c in cl.classes})},
        ),
        nodata=cl.nodata_class,
        dtype="uint8",
    )
    unc_bands = {
        "max_probability": pred.max_probability,
        "margin": pred.margin,
        "entropy": pred.entropy,
    }
    for k, code in enumerate(tm.classes):
        unc_bands[f"p_{cl.name_of(code)}"] = pred.probabilities[k]
    unc_path = write_layer(
        out / "classification_uncertainty.tif",
        unc_bands,
        stack.grid,
        LayerMeta(
            "classification_uncertainty",
            "derived",
            "uncalibrated",
            "Random Forest vote fractions. Not calibrated probabilities: use as a "
            "relative confidence measure only.",
            derived_from=["landcover model"],
            units={k: "fraction (0-1)" for k in unc_bands},
        ),
        nodata=-9999.0,
    )

    # ---- independent validation
    val = val.copy()
    val["mapped_code"] = sample_raster(pred.classes.astype(float), stack.grid, val)
    off_map = val["mapped_code"].isna() | (val["mapped_code"] == cl.nodata_class)
    if off_map.any():
        checks.append(
            Check(
                "validation_samples_without_map",
                "WARN",
                f"{int(off_map.sum())} validation samples fall on unclassified "
                "pixels and are excluded from accuracy",
            )
        )
    v = val[~off_map]
    codes = cl.trainable_codes()
    names = [cl.name_of(c) for c in codes]
    cm = confusion(v["class_code"].to_numpy(), v["mapped_code"].astype(int).to_numpy(), codes)
    metrics = class_metrics(cm, codes, names, cl.validation.confidence_level)
    oa = overall(cm, cl.validation.confidence_level)
    area_rows = None
    if cl.validation.design == "stratified_random_by_map_class":
        inside = _aoi_mask(aoi, stack.grid)
        counts = np.array([int(((pred.classes == c) & inside).sum()) for c in codes])
        est = olofsson(cm, counts, stack.grid.pixel_area_m2)
        area_rows = pd.DataFrame(
            {
                "class_name": names,
                "mapped_area_km2": est["mapped_area"] / 1e6,
                "estimated_area_km2": est["area"] / 1e6,
                "estimated_area_se_km2": est["area_se"] / 1e6,
                "users_accuracy_area_weighted": est["users_accuracy"],
                "users_accuracy_se": est["users_accuracy_se"],
                "producers_accuracy_area_weighted": est["producers_accuracy"],
                "producers_accuracy_se": est["producers_accuracy_se"],
            }
        )
        area_rows.to_csv(out / "area_adjusted_estimates.csv", index=False)
        checks.append(
            Check(
                "area_adjusted_overall_accuracy",
                "PASS",
                f"{est['overall_accuracy']:.3f} +/- {est['overall_accuracy_se']:.3f} "
                "(SE, Olofsson et al. 2014)",
            )
        )
    else:
        checks.append(
            Check(
                "area_adjusted_estimates",
                "WARN",
                "validation design is non_probability: area-adjusted accuracy and "
                "area estimates are not reported; accuracy describes the samples",
            )
        )

    n_val = class_counts(v, cfgs)
    checks += gate_checks(
        cfgs,
        metrics,
        oa.overall_accuracy,
        n_val,
        class_counts(train_gdf, cfgs),
        separation,
        cl.split.validation_source,
    )
    status = "FAIL" if any(c.status == "FAIL" for c in checks) else "PASS"

    # ---- tables
    overall_row = {
        "class_code": None,
        "class_name": "OVERALL",
        "n_reference": oa.n,
        "n_mapped": oa.n,
        "n_correct": int(np.trace(cm)),
        "overall_accuracy": oa.overall_accuracy,
        "overall_accuracy_ci_low": oa.ci_low,
        "overall_accuracy_ci_high": oa.ci_high,
        "kappa": oa.kappa,
    }
    acc_table = pd.concat([metrics, pd.DataFrame([overall_row])], ignore_index=True)
    acc_table.insert(0, "label_year", year)
    acc_table.insert(0, "series", series)
    acc_path = out / "classification_accuracy.csv"
    acc_table.to_csv(acc_path, index=False)
    cm_df = pd.DataFrame(cm, index=[f"ref_{n}" for n in names], columns=[f"map_{n}" for n in names])
    cm_path = out / "confusion_matrix.csv"
    cm_df.to_csv(cm_path)

    samples_path = write_layers(
        out / "samples.gpkg",
        {
            "training_samples": train_gdf.assign(split="training"),
            "validation_samples": val.assign(split="validation"),
        },
    )
    model_files = save_model(
        tm,
        out / "model",
        {
            "series": series,
            "label_year": year,
            "composites": stack.sources,
            "config_sha256": classification_config_hash(cfgs),
        },
    )

    # Record the validation outcome in the map itself before hashing it.
    import rasterio

    with rasterio.open(lc_path, "r+") as dst:
        dst.update_tags(status="validated" if status == "PASS" else "validation_failed")
    gate = {
        "status": status,
        "series": series,
        "label_year": year,
        "created_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "config_sha256": classification_config_hash(cfgs),
        "landcover_sha256": sha256(lc_path),
        "checks": [c.to_dict() for c in checks],
        "overall_accuracy": oa.overall_accuracy,
        "oob_score": tm.oob_score,
        "n_training": int(len(train_gdf)),
        "n_validation": int(len(v)),
    }
    gate_path = out / VALIDATION_GATE
    gate_path.write_text(json.dumps(gate, indent=2), encoding="utf-8")
    report = out / "accuracy_report.md"
    report.write_text(
        _report(cfgs, series, year, status, checks, acc_table, cm_df, tm, area_rows),
        encoding="utf-8",
    )
    write_manifest(
        out / "run_manifest.json",
        milestone="M4",
        command=command,
        config_sha256=cfgs.sha256,
        inputs=[
            {
                "reference_samples": str(cl.samples.reference_path),
                "validation_samples": str(cl.samples.validation_path)
                if cl.split.validation_source == "independent_file"
                else None,
                "composites": stack.sources,
            }
        ],
        outputs=[
            lc_path,
            unc_path,
            acc_path,
            cm_path,
            samples_path,
            gate_path,
            report,
            *model_files,
        ],
        status=status,
    )
    return status, checks, out


def _aoi_mask(aoi: gpd.GeoDataFrame, grid: Grid) -> np.ndarray:
    from rasterio.features import geometry_mask

    return ~geometry_mask(list(aoi.geometry), (grid.height, grid.width), grid.transform)


def _report(cfgs, series, year, status, checks, acc_table, cm_df, tm, area_rows) -> str:
    lines = [
        f"# Classification accuracy: {series} {year}",
        "",
        f"Validation gate: **{status}**. Rows of the confusion matrix are reference "
        "classes, columns are map classes. Intervals are Wilson "
        f"{cfgs.classification.validation.confidence_level:.0%} intervals on sample "
        "counts.",
        "",
        "## Gate checks",
        "",
        "| Check | Status | Detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {c.status} | {c.detail} |" for c in checks]
    lines += [
        "",
        "## Per-class accuracy",
        "",
        md_table(acc_table),
        "",
        "## Confusion matrix",
        "",
        md_table(cm_df, index=True),
        "",
        f"Out-of-bag score on training samples: {tm.oob_score:.3f}. This is optimistic "
        "(training samples are spatially autocorrelated) and is not used by the gate.",
        "",
    ]
    if area_rows is not None:
        lines += ["## Area-adjusted estimates (Olofsson et al. 2014)", "", md_table(area_rows), ""]
    lines += ["See docs/uncertainty.md for how to interpret these numbers."]
    return "\n".join(lines)


def require_validation_pass(cfgs: Configs, out_root: Path, series: str, year: int) -> dict:
    from indus_delta.gate import GateError

    path = epoch_dir(out_root, series, year) / VALIDATION_GATE
    if not path.is_file():
        raise GateError(f"no validation gate for {series} {year}; run `indus-delta classify`")
    gate = json.loads(path.read_text(encoding="utf-8"))
    if gate.get("status") != "PASS":
        failed = [c["name"] for c in gate.get("checks", []) if c["status"] == "FAIL"]
        raise GateError(
            f"validation gate for {series} {year} is {gate.get('status')}; failed checks: {failed}"
        )
    if gate.get("config_sha256") != classification_config_hash(cfgs):
        raise GateError("classification configuration changed since validation; reclassify")
    lc = epoch_dir(out_root, series, year) / "landcover.tif"
    if not lc.is_file() or sha256(lc) != gate.get("landcover_sha256"):
        raise GateError("landcover.tif differs from the validated map")
    return gate
