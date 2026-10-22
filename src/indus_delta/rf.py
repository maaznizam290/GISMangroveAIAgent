"""Random Forest baseline: training, prediction and per-pixel uncertainty."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import sklearn
from sklearn.ensemble import RandomForestClassifier

from indus_delta.config import Configs
from indus_delta.features import FeatureStack


@dataclass
class TrainedModel:
    model: RandomForestClassifier
    feature_names: list[str]
    classes: list[int]
    oob_score: float
    n_train: dict[int, int]


def train(X: np.ndarray, y: np.ndarray, feature_names: list[str], cfgs: Configs) -> TrainedModel:
    rf = cfgs.classification.random_forest
    if np.isnan(X).any():
        raise ValueError("training features contain NaN; drop those samples first")
    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        raise ValueError("at least two classes are needed to train")
    model = RandomForestClassifier(
        n_estimators=rf.n_estimators,
        max_features=rf.max_features,
        min_samples_leaf=rf.min_samples_leaf,
        class_weight=rf.class_weight,
        random_state=rf.random_state,
        n_jobs=rf.n_jobs,
        oob_score=True,
        bootstrap=True,
    )
    model.fit(X, y)
    return TrainedModel(
        model,
        feature_names,
        [int(c) for c in model.classes_],
        float(model.oob_score_),
        {int(c): int(n) for c, n in zip(classes, counts, strict=True)},
    )


@dataclass
class Prediction:
    classes: np.ndarray  # uint8 class codes, nodata class where features are missing
    probabilities: np.ndarray  # (n_classes, h, w) float32, NaN where missing
    max_probability: np.ndarray
    margin: np.ndarray  # top-1 minus top-2 vote fraction
    entropy: np.ndarray  # normalised Shannon entropy of the vote fractions (0-1)


def predict(
    tm: TrainedModel, stack: FeatureStack, nodata_class: int, chunk: int = 200_000
) -> Prediction:
    if stack.names != tm.feature_names:
        raise ValueError("feature stack does not match the trained model's features")
    h, w = stack.grid.height, stack.grid.width
    flat = stack.data.reshape(len(stack.names), -1).T
    valid = np.all(np.isfinite(flat), axis=1)
    k = len(tm.classes)
    proba = np.full((h * w, k), np.nan, dtype=np.float32)
    idx = np.flatnonzero(valid)
    for start in range(0, idx.size, chunk):
        sel = idx[start : start + chunk]
        proba[sel] = tm.model.predict_proba(flat[sel])
    cls = np.full(h * w, nodata_class, dtype=np.uint8)
    cls[valid] = np.asarray(tm.classes, dtype=np.uint8)[np.argmax(proba[valid], axis=1)]
    srt = np.sort(proba, axis=1)
    pmax = srt[:, -1]
    margin = srt[:, -1] - srt[:, -2] if k > 1 else np.ones(h * w, dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        ent = -np.nansum(np.where(proba > 0, proba * np.log(proba), 0.0), axis=1) / np.log(k)
    ent[~valid] = np.nan
    return Prediction(
        cls.reshape(h, w),
        proba.T.reshape(k, h, w),
        pmax.reshape(h, w),
        margin.reshape(h, w),
        ent.reshape(h, w).astype(np.float32),
    )


def save_model(tm: TrainedModel, directory: Path, metadata: dict) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    mpath = directory / "random_forest.joblib"
    joblib.dump(tm.model, mpath)
    meta = {
        **metadata,
        "sklearn_version": sklearn.__version__,
        "feature_names": tm.feature_names,
        "classes": tm.classes,
        "oob_score": tm.oob_score,
        "n_train_per_class": tm.n_train,
        "feature_importance": dict(
            zip(tm.feature_names, map(float, tm.model.feature_importances_), strict=True)
        ),
        "params": tm.model.get_params(),
        "note": "OOB accuracy is computed on training samples (spatially autocorrelated); it "
        "is not a substitute for the independent validation.",
    }
    jpath = directory / "random_forest_metadata.json"
    jpath.write_text(json.dumps(meta, indent=2, default=str), encoding="utf-8")
    return [mpath, jpath]
