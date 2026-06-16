"""Train a CatBoost regression imputer for capacity_num (hospital bed count).

Honest evaluation: 5-fold CV on observed rows (out-of-fold predictions), with the
existing cohort-median imputation computed on the SAME folds as a fair baseline.
Final model refit on all observed rows, used to impute the missing rows.
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

import features as F

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TARGET = "capacity_num"
REPO = F.REPO
OUT_DIR = os.path.join(REPO, "output", "catboost")
MODEL_PATH = os.path.join(OUT_DIR, "capacity_model.cbm")
IMPUTE_PATH = os.path.join(OUT_DIR, "capacity_imputations.csv")
METRICS_PATH = os.path.join(OUT_DIR, "capacity_metrics.json")
MLRUNS_DIR = os.path.join(REPO, "output", "mlruns")

CLIP_LOW, CLIP_HIGH = 1.0, 5000.0

HPARAMS = dict(
    iterations=1500,
    learning_rate=0.05,
    depth=6,
    loss_function="RMSE",
    early_stopping_rounds=100,
    random_seed=42,
    verbose=False,
)


def make_model() -> CatBoostRegressor:
    return CatBoostRegressor(**HPARAMS)


def rmse(y_true, y_pred) -> float:
    return float(np.sqrt(np.mean((np.asarray(y_true) - np.asarray(y_pred)) ** 2)))


def metric_block(y_true, y_pred) -> dict:
    return {
        "mae": float(mean_absolute_error(y_true, y_pred)),
        "rmse": rmse(y_true, y_pred),
        "r2": float(r2_score(y_true, y_pred)),
        "median_absolute_error": float(median_absolute_error(y_true, y_pred)),
    }


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    os.makedirs(MLRUNS_DIR, exist_ok=True)

    df = F.load_clean_df()
    X_obs, y_obs, X_missing, missing_index = F.split_for_target(df, TARGET)
    cat_features = F.categorical_feature_columns()

    n_train = int(len(y_obs))
    n_missing = int(len(missing_index))
    print(f"[data] observed train/eval rows = {n_train} | missing rows to impute = {n_missing}")

    # X_obs index aligns to df index; we iterate on positional arrays for KFold.
    X_obs_reset = X_obs.reset_index(drop=True)
    y_obs_reset = y_obs.reset_index(drop=True)
    obs_df_index = X_obs.index.to_numpy()  # original df indices for the observed rows
    y_vals = y_obs_reset.to_numpy(dtype=float)

    # -------------------------------------------------------------------
    # 5-fold CV: out-of-fold predictions for CatBoost AND cohort baseline
    # -------------------------------------------------------------------
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_cat = np.full(n_train, np.nan, dtype=float)
    oof_base = np.full(n_train, np.nan, dtype=float)

    for fold, (tr_pos, va_pos) in enumerate(kf.split(X_obs_reset), start=1):
        X_tr = X_obs_reset.iloc[tr_pos]
        X_va = X_obs_reset.iloc[va_pos]
        y_tr_log = np.log1p(y_vals[tr_pos])

        train_pool = Pool(X_tr, y_tr_log, cat_features=cat_features)
        eval_pool = Pool(X_va, np.log1p(y_vals[va_pos]), cat_features=cat_features)

        model = make_model()
        model.fit(train_pool, eval_set=eval_pool, use_best_model=True)

        pred_log = model.predict(X_va)
        oof_cat[va_pos] = np.expm1(pred_log)

        # Baseline on the SAME split: medians learned only on the train fold.
        tr_df_idx = obs_df_index[tr_pos]
        va_df_idx = obs_df_index[va_pos]
        oof_base[va_pos] = F.cohort_median_baseline(df, TARGET, tr_df_idx, va_df_idx)

        print(f"[cv] fold {fold} done | best_iter={model.get_best_iteration()}")

    # Clip OOF predictions to the sane range for fair, deployment-like metrics.
    oof_cat = np.clip(oof_cat, CLIP_LOW, CLIP_HIGH)
    oof_base = np.clip(oof_base, CLIP_LOW, CLIP_HIGH)

    cat_metrics = metric_block(y_vals, oof_cat)
    base_metrics = metric_block(y_vals, oof_base)
    mae_improvement_pct = float(
        (base_metrics["mae"] - cat_metrics["mae"]) / base_metrics["mae"] * 100.0
    )

    print("\n=== Out-of-fold metrics (original units) ===")
    print(f"CatBoost : MAE={cat_metrics['mae']:.2f}  RMSE={cat_metrics['rmse']:.2f}  "
          f"R2={cat_metrics['r2']:.4f}  MedAE={cat_metrics['median_absolute_error']:.2f}")
    print(f"Baseline : MAE={base_metrics['mae']:.2f}  RMSE={base_metrics['rmse']:.2f}  "
          f"R2={base_metrics['r2']:.4f}  MedAE={base_metrics['median_absolute_error']:.2f}")
    print(f"MAE improvement vs baseline: {mae_improvement_pct:.2f}%")

    # -------------------------------------------------------------------
    # Final model on ALL observed rows; carve a small eval set for early stop.
    # -------------------------------------------------------------------
    full_pool = Pool(X_obs_reset, np.log1p(y_vals), cat_features=cat_features)
    final_model = make_model()
    final_model.fit(full_pool)
    final_model.save_model(MODEL_PATH)
    print(f"\n[model] saved final model -> {MODEL_PATH}")

    # Feature importances (top 15)
    importances = final_model.get_feature_importance()
    feat_names = list(X_obs_reset.columns)
    imp_pairs = sorted(
        ({"feature": f, "importance": float(v)} for f, v in zip(feat_names, importances)),
        key=lambda d: d["importance"],
        reverse=True,
    )
    top15 = imp_pairs[:15]

    # -------------------------------------------------------------------
    # Impute missing rows
    # -------------------------------------------------------------------
    if n_missing > 0:
        miss_pred_log = final_model.predict(X_missing)
        miss_pred = np.clip(np.expm1(miss_pred_log), CLIP_LOW, CLIP_HIGH)
    else:
        miss_pred = np.array([], dtype=float)

    impute_df = pd.DataFrame(
        {"row_index": np.asarray(missing_index), "capacity_pred": miss_pred}
    )
    impute_df.to_csv(IMPUTE_PATH, index=False)
    print(f"[impute] wrote {len(impute_df)} imputations -> {IMPUTE_PATH}")

    # -------------------------------------------------------------------
    # Metrics JSON
    # -------------------------------------------------------------------
    target_stats = {
        "min": float(y_obs.min()),
        "median": float(y_obs.median()),
        "max": float(y_obs.max()),
        "mean": float(y_obs.mean()),
    }
    metrics_payload = {
        "target": TARGET,
        "model_type": "catboost",
        "validation": "cross_val_5fold_on_observed",
        "n_train": n_train,
        "n_missing": n_missing,
        "target_stats": target_stats,
        "catboost": cat_metrics,
        "baseline_cohort_median": base_metrics,
        "mae_improvement_pct": mae_improvement_pct,
        "hyperparameters": {k: v for k, v in HPARAMS.items() if k != "verbose"},
        "top_15_importances": top15,
    }
    with open(METRICS_PATH, "w") as fh:
        json.dump(metrics_payload, fh, indent=2)
    print(f"[metrics] wrote -> {METRICS_PATH}")

    # -------------------------------------------------------------------
    # MLflow
    # -------------------------------------------------------------------
    mlflow.set_tracking_uri("file:" + os.path.abspath(MLRUNS_DIR))
    mlflow.set_experiment("caregap_scoring_policies")
    with mlflow.start_run(run_name="catboost_capacity_imputer_v1"):
        mlflow.set_tags({
            "validation": "cross_val_5fold_on_observed",
            "task": "supply_imputation_regression",
        })
        mlflow.log_params({
            "target": TARGET,
            "model_type": "catboost",
            "n_train": n_train,
            "n_missing": n_missing,
            "iterations": HPARAMS["iterations"],
            "learning_rate": HPARAMS["learning_rate"],
            "depth": HPARAMS["depth"],
            "loss_function": HPARAMS["loss_function"],
            "early_stopping_rounds": HPARAMS["early_stopping_rounds"],
            "log1p_target": True,
        })
        mlflow.log_metrics({
            "catboost_mae": cat_metrics["mae"],
            "catboost_rmse": cat_metrics["rmse"],
            "catboost_r2": cat_metrics["r2"],
            "catboost_median_ae": cat_metrics["median_absolute_error"],
            "baseline_mae": base_metrics["mae"],
            "baseline_rmse": base_metrics["rmse"],
            "baseline_r2": base_metrics["r2"],
            "mae_improvement_pct": mae_improvement_pct,
        })
        mlflow.log_artifact(MODEL_PATH, artifact_path="model")
    print(f"[mlflow] logged run 'catboost_capacity_imputer_v1' -> {MLRUNS_DIR}")

    # -------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------
    print("\n================ SUMMARY ================")
    print(f"Target: {TARGET} | train={n_train} | missing imputed={n_missing}")
    print(f"CatBoost OOF : MAE={cat_metrics['mae']:.2f}  RMSE={cat_metrics['rmse']:.2f}  "
          f"R2={cat_metrics['r2']:.4f}")
    print(f"Baseline OOF : MAE={base_metrics['mae']:.2f}  RMSE={base_metrics['rmse']:.2f}  "
          f"R2={base_metrics['r2']:.4f}")
    print(f"MAE improvement: {mae_improvement_pct:.2f}%")
    print("Top 5 features:")
    for d in top15[:5]:
        print(f"  {d['feature']:<40} {d['importance']:.3f}")
    print("=========================================")


if __name__ == "__main__":
    main()
