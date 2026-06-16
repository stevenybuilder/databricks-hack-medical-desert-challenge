# Databricks notebook source
# MAGIC %md
# MAGIC # 07 · Train + Register CatBoost Supply Imputers in Unity Catalog
# MAGIC
# MAGIC **CareGap Agent — the project's one place for genuine supervised ML.**
# MAGIC
# MAGIC Unlike the *trust / validity* layer (which has **0 gold labels**, so we keep it as a transparent
# MAGIC Bayesian scorer — see notebook 04), **supply imputation has real observed targets**:
# MAGIC ~2,500 facilities report a real bed `capacity` and ~3,600 report a real `doctor count`. We train
# MAGIC `CatBoostRegressor` models on those observed rows to impute the missing ~64–75%, and register
# MAGIC them to Unity Catalog alongside the scoring policy.
# MAGIC
# MAGIC This mirrors the locally-developed `scripts/catboost/{features,train_capacity,train_doctors}.py`
# MAGIC (feature lists are kept in sync). Training is tiny (seconds) — serverless is used only so the
# MAGIC **registered model lives in UC** for governance + serving, not because the data needs a cluster.
# MAGIC
# MAGIC > **Honesty posture:** held-out 5-fold CV vs the previous cohort-median baseline.
# MAGIC > Capacity is a clear win (MAE −13.6%, R² 0.22 vs 0.04). Doctor count is **marginal**
# MAGIC > (MAE −1.5%, R² ≈ 0) because the target is extremely skewed (median = 2) — reported as-is.

# COMMAND ----------

# MAGIC %pip install catboost==1.2.10
# MAGIC %restart_python

# COMMAND ----------

import json
import os

import numpy as np
import pandas as pd
import mlflow
from catboost import CatBoostRegressor, Pool
from sklearn.model_selection import KFold
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

CATALOG = "workspace"
BRONZE = f"{CATALOG}.caregap_bronze"
MODELS_SCHEMA = f"{CATALOG}.caregap_models"
SOURCE_TABLE = f"{BRONZE}.raw_facility_health_cleaned"  # full 144-col cleaned facility table

mlflow.set_registry_uri("databricks-uc")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {MODELS_SCHEMA}")  # noqa: F821

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1 · Feature contract (kept in sync with `scripts/catboost/features.py`)
# MAGIC Leakage guards: the two targets, any `*_estimate/*_confidence/*_display`, and the rule-derived
# MAGIC `trustworthy_supply_signal` are **never** used as features.

# COMMAND ----------

CATEGORICAL_FEATURES = [
    "organization_type", "facilityTypeId", "operatorTypeId", "pincode_primary_state",
    "geo_quality", "specialties_status", "procedure_status", "equipment_status",
    "capability_status", "equipment_confidence",
]
NUMERIC_FEATURES = [
    "facility_latitude", "facility_longitude", "pincode_centroid_latitude",
    "pincode_centroid_longitude", "geo_distance_km_to_pincode_centroid", "pincode_n_districts",
    "pincode_n_states", "year_established_num", "claim_field_count", "description_item_count",
    "specialties_item_count", "procedure_item_count", "equipment_item_count",
    "capability_item_count", "specialties_len", "procedure_len", "equipment_len",
    "capability_len", "district_facility_count_percentile_in_sample",
    "facility_count_in_joined_district_sample", "population_below_age_15_years_pct",
    "institutional_birth_in_public_facility_5y_pct",
]
BOOL_FEATURES = [
    "geo_in_india_bbox", "recency_valid_signal", "has_description", "has_specialties",
    "has_procedure", "has_equipment", "has_capability", "has_source_urls", "has_contact_evidence",
    "has_maternity_care_signal", "has_emergency_care_signal", "has_diagnostic_signal",
    "has_ncd_care_signal",
]
CAT_COLS = CATEGORICAL_FEATURES + BOOL_FEATURES
ALL_FEATURES = CATEGORICAL_FEATURES + BOOL_FEATURES + NUMERIC_FEATURES
COHORT_KEYS = ["facilityTypeId", "operatorTypeId", "pincode_primary_state"]
OUTLIER_FLAG = {
    "capacity_num": "capacity_num_extreme_outlier",
    "number_doctors_num": "number_doctors_num_extreme_outlier",
}


def build_design_matrix(df: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=df.index)
    for c in CATEGORICAL_FEATURES:
        col = df[c] if c in df.columns else pd.Series(np.nan, index=df.index)
        X[c] = col.astype("object").where(col.notna(), "missing").astype(str)
    for c in BOOL_FEATURES:
        col = df[c] if c in df.columns else pd.Series(np.nan, index=df.index)
        X[c] = col.map({True: "True", False: "False"}).where(col.notna(), "missing").astype(str)
    for c in NUMERIC_FEATURES:
        col = df[c] if c in df.columns else pd.Series(np.nan, index=df.index)
        X[c] = pd.to_numeric(col, errors="coerce").astype(float)
    return X[ALL_FEATURES]


def trainable_mask(df, target):
    y = pd.to_numeric(df[target], errors="coerce")
    mask = y.notna() & (y > 0)
    flag = OUTLIER_FLAG.get(target)
    if flag and flag in df.columns:
        mask &= ~df[flag].fillna(False).astype(bool)
    return mask


def cohort_median_baseline(df, target, train_idx, eval_idx):
    y = pd.to_numeric(df[target], errors="coerce")
    tr = df.loc[train_idx].copy()
    tr["_y"] = y.loc[train_idx].values
    global_med = float(tr["_y"].median())

    def med_map(keys, min_n):
        g = tr.groupby(keys)["_y"]
        m, n = g.median(), g.size()
        return {k: v for k, v in m.items() if n[k] >= min_n}

    full = med_map(COHORT_KEYS, 5)
    ft_op = med_map(["facilityTypeId", "operatorTypeId"], 10)
    ft = med_map(["facilityTypeId"], 10)
    op = med_map(["operatorTypeId"], 10)
    preds = []
    for _, r in df.loc[eval_idx].iterrows():
        if (r.get("facilityTypeId"), r.get("operatorTypeId"), r.get("pincode_primary_state")) in full:
            preds.append(full[(r.get("facilityTypeId"), r.get("operatorTypeId"), r.get("pincode_primary_state"))])
        elif (r.get("facilityTypeId"), r.get("operatorTypeId")) in ft_op:
            preds.append(ft_op[(r.get("facilityTypeId"), r.get("operatorTypeId"))])
        elif r.get("facilityTypeId") in ft:
            preds.append(ft[r.get("facilityTypeId")])
        elif r.get("operatorTypeId") in op:
            preds.append(op[r.get("operatorTypeId")])
        else:
            preds.append(global_med)
    return np.asarray(preds, dtype=float)

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2 · Load cleaned facilities from Unity Catalog

# COMMAND ----------

pdf = spark.table(SOURCE_TABLE).toPandas()  # noqa: F821
pdf = pdf.reset_index(drop=True)
print(f"Loaded {len(pdf):,} facilities x {pdf.shape[1]} cols from {SOURCE_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3 · Train, cross-validate vs baseline, register to UC — one function, two targets

# COMMAND ----------

CB_PARAMS = dict(iterations=1500, learning_rate=0.05, depth=6, loss_function="RMSE",
                 random_seed=42, early_stopping_rounds=100, verbose=False)


def fit_catboost(X, y_log, X_val=None, y_val_log=None):
    model = CatBoostRegressor(**CB_PARAMS)
    train_pool = Pool(X, y_log, cat_features=CAT_COLS)
    eval_pool = Pool(X_val, y_val_log, cat_features=CAT_COLS) if X_val is not None else None
    model.fit(train_pool, eval_set=eval_pool, use_best_model=eval_pool is not None)
    return model


def train_and_register(target, registered_name, run_name):
    X_all = build_design_matrix(pdf)
    obs = trainable_mask(pdf, target)
    y = pd.to_numeric(pdf[target], errors="coerce")
    obs_idx = pdf.index[obs]
    Xo, yo = X_all.loc[obs_idx], y.loc[obs_idx].astype(float)

    # Honest 5-fold OOF CV: CatBoost vs cohort-median baseline on identical folds.
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    oof_cb = np.zeros(len(obs_idx)); oof_bl = np.zeros(len(obs_idx)); oof_y = yo.values
    pos = {ix: i for i, ix in enumerate(obs_idx)}
    for tr, va in kf.split(obs_idx):
        tr_idx, va_idx = obs_idx[tr], obs_idx[va]
        m = fit_catboost(Xo.loc[tr_idx], np.log1p(yo.loc[tr_idx]),
                         Xo.loc[va_idx], np.log1p(yo.loc[va_idx]))
        for ix, p in zip(va_idx, np.expm1(m.predict(Xo.loc[va_idx]))):
            oof_cb[pos[ix]] = p
        for ix, p in zip(va_idx, cohort_median_baseline(pdf, target, tr_idx, va_idx)):
            oof_bl[pos[ix]] = p
    oof_cb = np.clip(oof_cb, 1, 5000)

    metrics = {
        "catboost_mae": float(mean_absolute_error(oof_y, oof_cb)),
        "catboost_rmse": float(np.sqrt(mean_squared_error(oof_y, oof_cb))),
        "catboost_r2": float(r2_score(oof_y, oof_cb)),
        "baseline_mae": float(mean_absolute_error(oof_y, oof_bl)),
        "baseline_rmse": float(np.sqrt(mean_squared_error(oof_y, oof_bl))),
    }
    metrics["mae_improvement_pct"] = 100 * (metrics["baseline_mae"] - metrics["catboost_mae"]) / metrics["baseline_mae"]

    # Final model on all observed rows + impute the missing.
    final = fit_catboost(Xo, np.log1p(yo))
    missing_idx = pdf.index[~obs & y.isna()]
    imputed = np.clip(np.expm1(final.predict(X_all.loc[missing_idx])), 1, 5000)

    with mlflow.start_run(run_name=run_name):
        mlflow.log_params({"target": target, "model_type": "catboost", "n_train": len(obs_idx),
                           "n_missing": len(missing_idx), **{f"cb_{k}": v for k, v in CB_PARAMS.items()}})
        mlflow.log_metrics(metrics)
        mlflow.set_tags({"validation": "cross_val_5fold_on_observed",
                         "task": "supply_imputation_regression",
                         "validation_posture": "real_observed_targets_not_proxy"})
        mlflow.catboost.log_model(final, artifact_path="model",
                                  registered_model_name=registered_name)
    print(f"[{target}] CatBoost MAE={metrics['catboost_mae']:.2f} vs baseline "
          f"{metrics['baseline_mae']:.2f} ({metrics['mae_improvement_pct']:+.1f}%) | "
          f"R2={metrics['catboost_r2']:.3f} | registered -> {registered_name}")
    return metrics


results = {
    "capacity_num": train_and_register(
        "capacity_num", f"{MODELS_SCHEMA}.caregap_capacity_imputer", "catboost_capacity_imputer_v1"),
    "number_doctors_num": train_and_register(
        "number_doctors_num", f"{MODELS_SCHEMA}.caregap_doctor_imputer", "catboost_doctors_imputer_v1"),
}

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4 · Summary
# MAGIC Two CatBoost regressors registered to Unity Catalog under `workspace.caregap_models`.
# MAGIC Capacity is the real win; doctor count is reported honestly as marginal.

# COMMAND ----------

print(json.dumps(results, indent=2))
