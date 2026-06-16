"""Production CatBoost regression imputer for number_doctors_num (doctor count).

Trains on log1p(doctor count) to tame heavy right-skew (1..5000, median 2).
Honest 5-fold CV on observed non-outlier rows; the existing cohort-median
imputation is benchmarked on the *same* folds. Final model refit on all
observed rows, imputes the missing rows, logs everything to MLflow + JSON.

Run: .venv/bin/python scripts/catboost/train_doctors.py
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor, Pool
from sklearn.metrics import (
    mean_absolute_error,
    median_absolute_error,
    r2_score,
)
from sklearn.model_selection import KFold

import mlflow

import features as F  # shared, already-tested module (same dir)

TARGET = "number_doctors_num"
PRED_CLIP = (1.0, 5000.0)

REPO = F.REPO
OUT_DIR = os.path.join(REPO, "output", "catboost")
MODEL_PATH = os.path.join(OUT_DIR, "doctors_model.cbm")
IMPUTE_PATH = os.path.join(OUT_DIR, "doctors_imputations.csv")
METRICS_PATH = os.path.join(OUT_DIR, "doctors_metrics.json")
MLRUNS_PATH = os.path.join(REPO, "output", "mlruns")

HYPERPARAMS = dict(
    iterations=1500,
    learning_rate=0.05,
    depth=6,
    loss_function="RMSE",
    early_stopping_rounds=100,
    random_seed=42,
    verbose=False,
)

CAT_FEATURES = F.categorical_feature_columns()


def make_model() -> CatBoostRegressor:
    return CatBoostRegressor(**HYPERPARAMS)


def fit_one(X_tr, y_tr_log, X_val=None, y_val_log=None) -> CatBoostRegressor:
    """Fit a CatBoost model on log1p target; optional val set for early stopping."""
    model = make_model()
    train_pool = Pool(X_tr, y_tr_log, cat_features=CAT_FEATURES)
    eval_pool = None
    if X_val is not None:
        eval_pool = Pool(X_val, y_val_log, cat_features=CAT_FEATURES)
    model.fit(train_pool, eval_set=eval_pool, use_best_model=eval_pool is not None)
    return model


def predict_orig(model: CatBoostRegressor, X) -> np.ndarray:
    """Predict in log space, invert with expm1 back to original units."""
    log_pred = model.predict(Pool(X, cat_features=CAT_FEATURES))
    return np.expm1(log_pred)


def reg_metrics(y_true, y_pred) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2))),
        "r2": float(r2_score(y_true, y_pred)),
        "median_ae": float(median_absolute_error(y_true, y_pred)),
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)

    df = F.load_clean_df()
    X_obs, y_obs, X_missing, missing_index = F.split_for_target(df, TARGET)
    n_train = int(len(y_obs))
    n_missing = int(len(missing_index))
    print(f"Loaded {len(df)} rows | observed (train/eval)={n_train} | missing (impute)={n_missing}")

    # Original-index positions for the observed rows -> needed for the baseline,
    # which computes medians over the original df by index.
    obs_index = X_obs.index.to_numpy()
    y_obs_vals = y_obs.to_numpy(dtype=float)
    y_obs_log = np.log1p(y_obs_vals)

    # -------- Honest 5-fold cross-validation (out-of-fold predictions) --------
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_cat = np.full(n_train, np.nan)
    oof_base = np.full(n_train, np.nan)

    for fold, (tr_pos, va_pos) in enumerate(kf.split(obs_index), start=1):
        X_tr = X_obs.iloc[tr_pos]
        X_va = X_obs.iloc[va_pos]
        y_tr_log = y_obs_log[tr_pos]
        y_va_log = y_obs_log[va_pos]

        model = fit_one(X_tr, y_tr_log, X_va, y_va_log)
        oof_cat[va_pos] = predict_orig(model, X_va)

        # Baseline on the SAME split (medians from train original-indices only).
        train_idx = obs_index[tr_pos]
        eval_idx = obs_index[va_pos]
        oof_base[va_pos] = F.cohort_median_baseline(df, TARGET, train_idx, eval_idx)

        print(f"  fold {fold}: train={len(tr_pos)} val={len(va_pos)} "
              f"best_iter={model.get_best_iteration()}")

    # Clip OOF preds to sane range before scoring (same policy as imputation).
    oof_cat_clipped = np.clip(oof_cat, *PRED_CLIP)
    oof_base_clipped = np.clip(oof_base, *PRED_CLIP)

    cat_m = reg_metrics(y_obs_vals, oof_cat_clipped)
    base_m = reg_metrics(y_obs_vals, oof_base_clipped)
    mae_improvement_pct = float((base_m["mae"] - cat_m["mae"]) / base_m["mae"] * 100.0)

    print("\n=== 5-fold OOF metrics (original units, held-out) ===")
    print(f"  CatBoost : MAE={cat_m['mae']:.3f} RMSE={cat_m['rmse']:.3f} "
          f"R2={cat_m['r2']:.4f} medAE={cat_m['median_ae']:.3f}")
    print(f"  Baseline : MAE={base_m['mae']:.3f} RMSE={base_m['rmse']:.3f} "
          f"R2={base_m['r2']:.4f} medAE={base_m['median_ae']:.3f}")
    print(f"  MAE improvement: {mae_improvement_pct:.2f}%")

    # -------- Refit final model on ALL observed rows --------
    final_model = make_model()
    final_model.fit(Pool(X_obs, y_obs_log, cat_features=CAT_FEATURES))
    final_model.save_model(MODEL_PATH)
    print(f"\nSaved final model -> {MODEL_PATH}")

    # Feature importances (top 15).
    importances = final_model.get_feature_importance()
    feat_names = list(X_obs.columns)
    imp_pairs = sorted(
        ({"feature": f, "importance": float(i)} for f, i in zip(feat_names, importances)),
        key=lambda d: d["importance"],
        reverse=True,
    )
    top15 = imp_pairs[:15]
    print("\nTop 15 feature importances:")
    for d in top15:
        print(f"  {d['feature']:<45} {d['importance']:.3f}")

    # -------- Impute missing rows --------
    if n_missing > 0:
        miss_pred = np.clip(predict_orig(final_model, X_missing), *PRED_CLIP)
    else:
        miss_pred = np.array([], dtype=float)
    impute_df = pd.DataFrame(
        {"row_index": np.asarray(missing_index), "doctors_pred": miss_pred}
    )
    impute_df.to_csv(IMPUTE_PATH, index=False)
    print(f"\nSaved {len(impute_df)} imputations -> {IMPUTE_PATH}")

    # -------- Target stats --------
    target_stats = {
        "min": float(y_obs_vals.min()),
        "median": float(np.median(y_obs_vals)),
        "mean": float(y_obs_vals.mean()),
        "max": float(y_obs_vals.max()),
        "std": float(y_obs_vals.std()),
    }

    # -------- MLflow logging --------
    mlflow.set_tracking_uri("file:" + MLRUNS_PATH)
    mlflow.set_experiment("caregap_scoring_policies")
    with mlflow.start_run(run_name="catboost_doctors_imputer_v1"):
        mlflow.log_params({
            "target": TARGET,
            "model_type": "catboost",
            "n_train": n_train,
            "n_missing": n_missing,
            "iterations": HYPERPARAMS["iterations"],
            "learning_rate": HYPERPARAMS["learning_rate"],
            "depth": HYPERPARAMS["depth"],
            "loss_function": HYPERPARAMS["loss_function"],
            "early_stopping_rounds": HYPERPARAMS["early_stopping_rounds"],
            "target_transform": "log1p",
            "pred_clip": f"{PRED_CLIP[0]}-{PRED_CLIP[1]}",
        })
        mlflow.log_metrics({
            "catboost_mae": cat_m["mae"],
            "catboost_rmse": cat_m["rmse"],
            "catboost_r2": cat_m["r2"],
            "catboost_median_ae": cat_m["median_ae"],
            "baseline_mae": base_m["mae"],
            "baseline_rmse": base_m["rmse"],
            "baseline_r2": base_m["r2"],
            "mae_improvement_pct": mae_improvement_pct,
        })
        mlflow.set_tags({
            "validation": "cross_val_5fold_on_observed",
            "task": "supply_imputation_regression",
        })
        mlflow.log_artifact(MODEL_PATH)

    print(f"\nLogged MLflow run -> {MLRUNS_PATH} (experiment: caregap_scoring_policies)")

    # -------- Metrics JSON --------
    metrics_out = {
        "target": TARGET,
        "n_train": n_train,
        "n_missing": n_missing,
        "validation": "cross_val_5fold_on_observed",
        "target_transform": "log1p",
        "pred_clip": list(PRED_CLIP),
        "target_stats": target_stats,
        "catboost": cat_m,
        "baseline": base_m,
        "mae_improvement_pct": mae_improvement_pct,
        "hyperparams": HYPERPARAMS,
        "top_15_importances": top15,
    }
    with open(METRICS_PATH, "w") as fh:
        json.dump(metrics_out, fh, indent=2)
    print(f"Saved metrics JSON -> {METRICS_PATH}")

    # -------- Summary --------
    print("\n" + "=" * 60)
    print("SUMMARY: CatBoost doctor-count imputer (number_doctors_num)")
    print("=" * 60)
    print(f"  n_train={n_train}  n_missing={n_missing}")
    print(f"  CatBoost MAE={cat_m['mae']:.3f}  RMSE={cat_m['rmse']:.3f}  R2={cat_m['r2']:.4f}")
    print(f"  Baseline MAE={base_m['mae']:.3f}  RMSE={base_m['rmse']:.3f}  R2={base_m['r2']:.4f}")
    print(f"  MAE improvement over baseline: {mae_improvement_pct:.2f}%")
    print(f"  Top feature: {top15[0]['feature']} ({top15[0]['importance']:.2f})")
    print("  Artifacts: model.cbm, imputations.csv, metrics.json, mlflow run -> all written")


if __name__ == "__main__":
    main()
