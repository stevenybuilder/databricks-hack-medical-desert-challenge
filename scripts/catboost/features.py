"""Shared feature engineering for CatBoost supply imputers.

Both the capacity and doctor-count trainers import from here so they use an
identical, leakage-free design matrix and an identical cohort-median baseline.

Targets imputed:
  - capacity_num         (2,511 observed real values)
  - number_doctors_num   (3,629 observed real values)

Leakage guards (NEVER used as features):
  - the two targets themselves
  - any *_estimate / *_confidence / *_display columns (derived from the targets)
  - trustworthy_supply_signal / contradicted_or_geo_invalid_signal
    (these are rule-derived partly FROM capacity/doctor observed-ness)
"""
from __future__ import annotations
import os
import numpy as np
import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CLEAN_CSV = os.path.join(REPO, "output", "data", "facility_health_cleaned.csv")

TARGETS = ["capacity_num", "number_doctors_num"]
OUTLIER_FLAG = {
    "capacity_num": "capacity_num_extreme_outlier",
    "number_doctors_num": "number_doctors_num_extreme_outlier",
}

# Categorical predictors (CatBoost native categoricals; NaN -> "missing").
CATEGORICAL_FEATURES = [
    "organization_type",
    "facilityTypeId",
    "operatorTypeId",
    "pincode_primary_state",
    "geo_quality",
    "specialties_status",
    "procedure_status",
    "equipment_status",
    "capability_status",
    "equipment_confidence",
]

# Numeric predictors (CatBoost handles NaN natively; left as-is).
NUMERIC_FEATURES = [
    "facility_latitude",
    "facility_longitude",
    "pincode_centroid_latitude",
    "pincode_centroid_longitude",
    "geo_distance_km_to_pincode_centroid",
    "pincode_n_districts",
    "pincode_n_states",
    "year_established_num",
    "claim_field_count",
    "description_item_count",
    "specialties_item_count",
    "procedure_item_count",
    "equipment_item_count",
    "capability_item_count",
    "specialties_len",
    "procedure_len",
    "equipment_len",
    "capability_len",
    "district_facility_count_percentile_in_sample",
    "facility_count_in_joined_district_sample",
    "population_below_age_15_years_pct",
    "institutional_birth_in_public_facility_5y_pct",
]

# Boolean signals -> treated as categorical ("True"/"False"/"missing").
BOOL_FEATURES = [
    "geo_in_india_bbox",
    "recency_valid_signal",
    "has_description",
    "has_specialties",
    "has_procedure",
    "has_equipment",
    "has_capability",
    "has_source_urls",
    "has_contact_evidence",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
]

# Cohort keys used by the existing (baseline) hierarchical-median imputation.
COHORT_KEYS = ["facilityTypeId", "operatorTypeId", "pincode_primary_state"]


def all_feature_columns() -> list[str]:
    return CATEGORICAL_FEATURES + BOOL_FEATURES + NUMERIC_FEATURES


def categorical_feature_columns() -> list[str]:
    # bools are encoded as strings -> categorical for CatBoost
    return CATEGORICAL_FEATURES + BOOL_FEATURES


def load_clean_df(path: str | None = None) -> pd.DataFrame:
    return pd.read_csv(path or CLEAN_CSV, low_memory=False)


def build_design_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Return X with CatBoost-ready dtypes (cats as filled strings, nums as float)."""
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
    return X[all_feature_columns()]


def trainable_mask(df: pd.DataFrame, target: str) -> pd.Series:
    """Rows with an observed, non-outlier, positive target value -> usable for train/eval."""
    y = pd.to_numeric(df[target], errors="coerce")
    mask = y.notna() & (y > 0)
    flag = OUTLIER_FLAG.get(target)
    if flag and flag in df.columns:
        mask &= ~df[flag].fillna(False).astype(bool)
    return mask


def split_for_target(df: pd.DataFrame, target: str):
    """Return (X_obs, y_obs, X_missing, missing_index) for a target.

    X_obs/y_obs: observed non-outlier rows (model trains + is evaluated here).
    X_missing  : rows where the target is semantically missing (model imputes these).
    """
    X = build_design_matrix(df)
    obs = trainable_mask(df, target)
    y = pd.to_numeric(df[target], errors="coerce")
    missing = ~obs & y.isna()
    return X[obs].copy(), y[obs].astype(float).copy(), X[missing].copy(), df.index[missing]


def cohort_median_baseline(df: pd.DataFrame, target: str, train_idx, eval_idx):
    """Reproduce the existing hierarchical cohort-median imputation as a fair baseline.

    Medians are computed ONLY on train_idx (no leakage), then predicted for eval_idx
    via: full 3-key cohort -> facilityType+operator -> facilityType -> operator -> global.
    Returns a prediction array aligned to eval_idx.
    """
    y = pd.to_numeric(df[target], errors="coerce")
    train = df.loc[train_idx].copy()
    train["_y"] = y.loc[train_idx].values
    global_med = float(train["_y"].median())

    def med_map(keys, min_n):
        g = train.groupby(keys)["_y"]
        m = g.median()
        n = g.size()
        return {k: v for k, v in m.items() if n[k] >= min_n}

    full = med_map(COHORT_KEYS, 5)
    ft_op = med_map(["facilityTypeId", "operatorTypeId"], 10)
    ft = med_map(["facilityTypeId"], 10)
    op = med_map(["operatorTypeId"], 10)

    preds = []
    ev = df.loc[eval_idx]
    for _, r in ev.iterrows():
        k3 = (r.get("facilityTypeId"), r.get("operatorTypeId"), r.get("pincode_primary_state"))
        k2 = (r.get("facilityTypeId"), r.get("operatorTypeId"))
        kf = r.get("facilityTypeId")
        ko = r.get("operatorTypeId")
        if k3 in full:
            preds.append(full[k3])
        elif k2 in ft_op:
            preds.append(ft_op[k2])
        elif kf in ft:
            preds.append(ft[kf])
        elif ko in op:
            preds.append(op[ko])
        else:
            preds.append(global_med)
    return np.asarray(preds, dtype=float)


if __name__ == "__main__":
    df = load_clean_df()
    print("rows:", len(df), "| features:", len(all_feature_columns()),
          "| cats:", len(categorical_feature_columns()))
    for t in TARGETS:
        Xo, yo, Xm, mi = split_for_target(df, t)
        print(f"{t}: train/eval={len(yo)}  impute(missing)={len(mi)}  "
              f"y[min/median/max]={yo.min():.0f}/{yo.median():.0f}/{yo.max():.0f}")
