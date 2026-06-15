#!/usr/bin/env python3
"""Train supervised facility prediction models from gold/silver labels.

The first model family is intentionally conservative:

- scikit-learn preprocessing for mixed numeric/categorical features;
- balanced logistic regression for each task;
- sigmoid calibration when each class has enough examples;
- explicit abstention/coverage metrics from predicted probability.

If the input only contains bronze/conflict seed rows, the script writes a report
and exits without training. That is expected until external corroboration promotes
rows to gold/silver.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score, log_loss
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
MODEL_DIR = ROOT / "output" / "models" / "facility_prediction_supervised"

DEFAULT_TRAINING_SET = DATA_DIR / "golden_facility_training_set_seed.csv"
DEFAULT_FEATURES = DATA_DIR / "facility_prediction_features_seed.csv"
DEFAULT_REPORT = DATA_DIR / "facility_prediction_model_report.json"

MIN_TRAINABLE_ROWS = 50
MIN_HOLDOUT_ROWS = 10
RANDOM_STATE = 42


NUMERIC_FEATURES = [
    "lat",
    "lon",
    "join_confidence",
    "join_match_score",
    "data_readiness_score",
    "semantic_data_quality_score",
    "supply_data_confidence_score",
    "health_need_score",
    "medical_desert_priority_score",
    "source_url_count",
    "capacity_estimate",
    "capacity_interval_width",
    "doctor_count_estimate",
    "doctor_count_interval_width",
    "geo_distance_km_to_pincode_centroid",
]

CATEGORICAL_FEATURES = [
    "facility_type_raw",
    "operator_type_raw",
    "h3_res7",
    "geo_quality",
]

BOOLEAN_FEATURES = [
    "has_pincode",
    "pincode_is_ambiguous",
    "has_source_urls",
    "has_contact_evidence",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
    "capacity_is_estimated",
    "doctor_count_is_estimated",
    "contradicted_or_geo_invalid_signal",
    "needs_human_review",
]


@dataclass(frozen=True)
class TaskSpec:
    name: str
    target: str
    kind: str = "multiclass"


TASKS = [
    TaskSpec("trust_posture", "trust_posture"),
    TaskSpec("facility_type", "facilityTypeId"),
    TaskSpec("capacity_band", "capacity_band"),
    TaskSpec("doctor_count_band", "doctor_count_band"),
    TaskSpec("service_maternity", "service_maternity", kind="binary"),
    TaskSpec("service_emergency", "service_emergency", kind="binary"),
    TaskSpec("service_diagnostic", "service_diagnostic", kind="binary"),
    TaskSpec("service_ncd", "service_ncd", kind="binary"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training-set", type=Path, default=DEFAULT_TRAINING_SET)
    parser.add_argument("--features", type=Path, default=DEFAULT_FEATURES)
    parser.add_argument("--model-dir", type=Path, default=MODEL_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--min-trainable-rows", type=int, default=MIN_TRAINABLE_ROWS)
    parser.add_argument("--holdout-size", type=float, default=0.25)
    return parser.parse_args()


def load_inputs(training_path: Path, feature_path: Path) -> pd.DataFrame:
    if not training_path.exists():
        raise FileNotFoundError(f"Missing training set: {training_path}")
    if not feature_path.exists():
        raise FileNotFoundError(f"Missing feature table: {feature_path}")

    training = pd.read_csv(training_path, low_memory=False)
    features = pd.read_csv(feature_path, low_memory=False)
    key_cols = ["golden_facility_id", "unique_id"]
    df = training.merge(features, on=key_cols, how="inner", suffixes=("", "_feature"))
    df["trainable_supervised_label"] = coerce_bool(df.get("trainable_supervised_label", False))
    df["evidence_tier"] = df.get("evidence_tier", "").fillna("").astype(str).str.lower()
    prepare_feature_types(df)
    add_service_targets(df)
    return df


def coerce_bool(value: Any) -> pd.Series:
    if isinstance(value, pd.Series):
        text = value.astype("string").fillna("").str.lower().str.strip()
        return text.isin({"true", "1", "yes", "y"})
    return pd.Series([bool(value)])


def add_service_targets(df: pd.DataFrame) -> None:
    parsed = df.get("service_labels", pd.Series("[]", index=df.index)).fillna("[]")
    label_sets = []
    for value in parsed:
        try:
            labels = json.loads(value) if isinstance(value, str) else []
        except json.JSONDecodeError:
            labels = []
        label_sets.append({str(label).lower() for label in labels})
    for label in ["maternity", "emergency", "diagnostic", "ncd"]:
        df[f"service_{label}"] = [label in labels for labels in label_sets]


def prepare_feature_types(df: pd.DataFrame) -> None:
    for col in NUMERIC_FEATURES:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BOOLEAN_FEATURES:
        if col in df:
            df[col] = coerce_bool(df[col]).astype(int)
    for col in CATEGORICAL_FEATURES:
        if col in df:
            df[col] = df[col].astype("string").fillna("")


def trainable_slice(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["trainable_supervised_label"] & df["evidence_tier"].isin(["gold", "silver"])].copy()


def available_features(df: pd.DataFrame) -> tuple[list[str], list[str], list[str]]:
    numeric = [col for col in NUMERIC_FEATURES if col in df.columns and df[col].notna().any()]
    categorical = [
        col for col in CATEGORICAL_FEATURES
        if col in df.columns and df[col].astype("string").fillna("").str.len().gt(0).any()
    ]
    boolean = [col for col in BOOLEAN_FEATURES if col in df.columns]
    return numeric, categorical, boolean


def build_estimator(df: pd.DataFrame, y: pd.Series) -> Pipeline | CalibratedClassifierCV:
    numeric, categorical, boolean = available_features(df)
    bool_pipeline = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("scale", StandardScaler(with_mean=False)),
        ]
    )
    preprocessor = ColumnTransformer(
        [
            ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), numeric),
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", OneHotEncoder(handle_unknown="ignore", min_frequency=5)),
                    ]
                ),
                categorical,
            ),
            ("boolean", bool_pipeline, boolean),
        ],
        remainder="drop",
    )
    base = Pipeline(
        [
            ("preprocess", preprocessor),
            (
                "classifier",
                LogisticRegression(
                    max_iter=2000,
                    class_weight="balanced",
                    n_jobs=None,
                    random_state=RANDOM_STATE,
                ),
            ),
        ]
    )
    min_class_count = int(y.value_counts().min())
    if min_class_count >= 3:
        cv = min(3, min_class_count)
        return CalibratedClassifierCV(estimator=base, method="sigmoid", cv=cv)
    return base


def task_skip_reason(df: pd.DataFrame, task: TaskSpec, min_rows: int) -> str | None:
    if task.target not in df.columns:
        return f"missing target column {task.target}"
    work = df[df[task.target].notna()].copy()
    if len(work) < min_rows:
        return f"only {len(work)} trainable rows; need at least {min_rows}"
    if work[task.target].nunique(dropna=True) < 2:
        return "target has fewer than two classes"
    if work[task.target].value_counts().min() < 2:
        return "at least one class has fewer than two examples"
    return None


def split_data(df: pd.DataFrame, y: pd.Series, holdout_size: float) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    min_class_count = y.value_counts().min()
    stratify = y if min_class_count >= 2 else None
    test_size = holdout_size
    if len(df) * test_size < MIN_HOLDOUT_ROWS:
        test_size = min(0.5, max(MIN_HOLDOUT_ROWS / len(df), holdout_size))
    return train_test_split(
        df,
        y,
        test_size=test_size,
        random_state=RANDOM_STATE,
        stratify=stratify,
    )


def evaluate(estimator: Any, x_test: pd.DataFrame, y_test: pd.Series) -> dict[str, Any]:
    y_pred = estimator.predict(x_test)
    report: dict[str, Any] = {
        "holdout_rows": int(len(y_test)),
        "accuracy": round(float(accuracy_score(y_test, y_pred)), 4),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_test, y_pred)), 4),
        "f1_macro": round(float(f1_score(y_test, y_pred, average="macro", zero_division=0)), 4),
        "class_counts_holdout": y_test.value_counts().to_dict(),
    }
    if hasattr(estimator, "predict_proba"):
        probabilities = estimator.predict_proba(x_test)
        classes = list(getattr(estimator, "classes_", []))
        if len(classes) == probabilities.shape[1]:
            try:
                report["log_loss"] = round(float(log_loss(y_test, probabilities, labels=classes)), 4)
            except ValueError as exc:
                report["log_loss_error"] = str(exc)
            confidence = probabilities.max(axis=1)
            pred = np.asarray([classes[i] for i in probabilities.argmax(axis=1)])
            for threshold in [0.5, 0.7, 0.8, 0.9]:
                mask = confidence >= threshold
                key = f"coverage_at_{threshold:.1f}"
                if mask.any():
                    report[key] = {
                        "coverage": round(float(mask.mean()), 4),
                        "rows": int(mask.sum()),
                        "accuracy": round(float(accuracy_score(y_test[mask], pred[mask])), 4),
                    }
                else:
                    report[key] = {"coverage": 0.0, "rows": 0, "accuracy": None}
    return report


def train_task(df: pd.DataFrame, task: TaskSpec, args: argparse.Namespace) -> dict[str, Any]:
    reason = task_skip_reason(df, task, args.min_trainable_rows)
    if reason:
        return {"task": task.name, "status": "skipped", "reason": reason}

    work = df[df[task.target].notna()].copy()
    if not any(available_features(work)):
        return {"task": task.name, "status": "skipped", "reason": "no usable feature columns"}
    y = work[task.target].astype(str)
    x_train, x_test, y_train, y_test = split_data(work, y, args.holdout_size)
    estimator = build_estimator(work, y_train)
    estimator.fit(x_train, y_train)
    metrics = evaluate(estimator, x_test, y_test)

    args.model_dir.mkdir(parents=True, exist_ok=True)
    model_path = args.model_dir / f"{task.name}.joblib"
    joblib.dump(
        {
            "task": task.name,
            "target": task.target,
            "model_family": "calibrated_logistic_regression"
            if isinstance(estimator, CalibratedClassifierCV)
            else "logistic_regression",
            "estimator": estimator,
            "feature_columns": available_features(work),
        },
        model_path,
    )
    return {
        "task": task.name,
        "status": "trained",
        "target": task.target,
        "model_path": display_path(model_path),
        "train_rows": int(len(x_train)),
        "holdout_rows": int(len(x_test)),
        "class_counts_train": y_train.value_counts().to_dict(),
        "metrics": metrics,
    }


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_report(df: pd.DataFrame, task_reports: list[dict[str, Any]]) -> dict[str, Any]:
    trained = [report for report in task_reports if report["status"] == "trained"]
    skipped = [report for report in task_reports if report["status"] == "skipped"]
    return {
        "model_policy": {
            "primary_model": "calibrated logistic regression",
            "why": (
                "Best first supervised model for a small source-corroborated tabular "
                "label set: interpretable coefficients, class weighting, probabilities "
                "for abstention, and a defensible baseline before trying boosted trees."
            ),
            "upgrade_path": (
                "Compare against LightGBM/CatBoost after there are enough gold/silver "
                "labels per task and report slice metrics by state/source tier."
            ),
            "abstention_rule": "Use max predicted probability thresholds plus evidence_tier/source conflict checks.",
        },
        "input_rows": int(len(df)),
        "trainable_rows": int(len(trainable_slice(df))),
        "evidence_tier_counts": df.get("evidence_tier", pd.Series(dtype=str)).value_counts(dropna=False).to_dict(),
        "trained_tasks": len(trained),
        "skipped_tasks": len(skipped),
        "tasks": task_reports,
    }


def main() -> None:
    args = parse_args()
    df = load_inputs(args.training_set, args.features)
    trainable = trainable_slice(df)
    task_reports = [train_task(trainable, task, args) for task in TASKS]
    report = build_report(df, task_reports)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
