"""Surface the zero-facility medical deserts the pipeline silently drops.

The gold district table is built by aggregating FACILITY rows, so districts with
NFHS health-need data but ZERO mapped facilities never appear — yet those are the
worst deserts. NFHS-5 covers ~706 districts; the gold table has ~494. This script
adds the ~212 missing districts with zero supply and recomputes the planning scores
over the FULL universe, using the *exact* formulas from build_hackathon_dataset.py
(no re-run of the 3,020-line pipeline, no change to the facility table).

Run: .venv/bin/python scripts/add_zero_facility_districts.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))

# The builder imports plotting libs at module scope that the reused functions
# don't need. Stub them so we can import the exact logic without installing them.
import types  # noqa: E402
for _m in ("matplotlib", "matplotlib.pyplot", "seaborn"):
    sys.modules.setdefault(_m, types.ModuleType(_m))

from build_hackathon_dataset import (  # noqa: E402  reuse the exact builder logic
    KEY_HEALTH_COLUMNS,
    add_health_need_scores,
    normalize_state,
    normalize_district,
)

DATA = REPO / "output" / "data"
DISTRICT_CSV = DATA / "district_health_facility_cleaned.csv"
NFHS_CSV = DATA / "raw_nfhs_5_district_health_indicators.csv"


def _key(df: pd.DataFrame) -> pd.Series:
    """Normalized (state|district) join key — identical normalization on both sides."""
    return df.apply(
        lambda r: f"{normalize_state(r['state_ut'])}|{normalize_district(r['district_name'], r['state_ut'])}",
        axis=1,
    )


def recompute_scores(d: pd.DataFrame) -> pd.DataFrame:
    """Recompute planning scores over the full district universe (exact builder formulas)."""
    hn = d["health_need_score"]
    tsr = d["trustworthy_supply_rate"]
    d["observed_facility_count_percentile"] = d["observed_facility_rows"].rank(pct=True)
    pct = d["observed_facility_count_percentile"]
    d["district_medical_desert_priority_score"] = (0.65 * hn + 0.35 * (1 - pct)).clip(0, 1)
    d["care_gap_score"] = (
        0.55 * hn + 0.25 * (1 - pct) + 0.20 * (1 - tsr.fillna(0))
    ).clip(0, 1)
    d["trust_gap_score"] = (
        0.45 * (1 - tsr.fillna(0))
        + 0.25 * d["needs_human_review_rate"].fillna(1)
        + 0.20 * d["critical_supply_gap_rate"].fillna(1)
        + 0.10 * d["contradicted_or_geo_invalid_rate"].fillna(0)
    ).clip(0, 1)
    d["district_data_quality_score"] = (
        0.22 * d["avg_data_readiness_score"].fillna(0)
        + 0.20 * d["avg_semantic_data_quality_score"].fillna(0)
        + 0.18 * d["avg_join_confidence"].fillna(0)
        + 0.15 * d["plausible_geo_rate"].fillna(0)
        + 0.10 * d["source_url_rate"].fillna(0)
        + 0.10 * (1 - d["critical_supply_gap_rate"].fillna(1))
        + 0.05 * (1 - d["needs_human_review_rate"].fillna(1))
    ).round(3)
    d["best_care_signal_score"] = (
        0.40 * (1 - hn)
        + 0.30 * tsr.fillna(0)
        + 0.20 * d["district_data_quality_score"].fillna(0)
        + 0.10 * pct.fillna(0)
    ).clip(0, 1)
    d["district_uncertainty_level"] = np.select(
        [
            d["district_data_quality_score"].ge(0.85) & d["observed_facility_rows"].ge(5),
            d["district_data_quality_score"].ge(0.70) & d["observed_facility_rows"].ge(3),
        ],
        ["lower", "medium"],
        default="higher",
    )
    d["planning_category"] = np.select(
        [
            d["care_gap_score"].ge(0.70)
            & d["health_need_score"].ge(d["health_need_score"].quantile(0.75))
            & d["trustworthy_supply_rows"].le(2),
            d["health_need_score"].ge(d["health_need_score"].quantile(0.75))
            & d["observed_facility_rows"].ge(d["observed_facility_rows"].median())
            & d["trustworthy_supply_rate"].lt(0.60),
            d["contradicted_or_geo_invalid_rate"].ge(0.25),
            d["best_care_signal_score"].ge(d["best_care_signal_score"].quantile(0.80))
            & d["district_data_quality_score"].ge(0.75),
        ],
        [
            "real_desert_candidate",
            "phantom_desert_or_verification_gap",
            "supply_record_quality_problem",
            "referral_or_capacity_candidate",
        ],
        default="mixed_or_monitor",
    )
    return d


def main() -> None:
    existing = pd.read_csv(DISTRICT_CSV, low_memory=False)
    existing["zero_facility_desert"] = False
    cols = existing.columns.tolist()

    nfhs = add_health_need_scores(pd.read_csv(NFHS_CSV, low_memory=False))
    existing_keys = set(_key(existing))
    nfhs["_key"] = _key(nfhs)
    missing = nfhs[~nfhs["_key"].isin(existing_keys)].copy()

    if missing.empty:
        print("No zero-facility districts to add — universe already complete.")
        return

    # Build rows for the zero-facility districts, aligned to the existing schema.
    new = pd.DataFrame(index=range(len(missing)), columns=cols)
    count_cols = [c for c in cols if c.endswith("_rows")] + [
        "unique_facility_ids", "unique_pincodes_observed",
    ]
    obj_cols = existing.select_dtypes(include="object").columns
    for c in cols:
        if c in count_cols:
            new[c] = 0
        elif c in obj_cols:
            new[c] = ""
        else:
            new[c] = np.nan  # rates/avgs stay NaN -> builder fillna() semantics apply

    new["state_ut"] = missing["state_ut"].to_numpy()
    new["district_name"] = missing["district_name"].to_numpy()
    new["dataset_grain"] = "district"
    new["observed_facility_rows"] = 0
    new["health_need_score"] = missing["health_need_score"].to_numpy()
    # NOTE: KEY_HEALTH_COLUMNS includes state_ut/district_name — exclude them here,
    # else to_numeric() would coerce the district names to NaN.
    for hc in [c for c in KEY_HEALTH_COLUMNS
               if c in cols and c in missing.columns and c not in {"state_ut", "district_name"}]:
        new[hc] = pd.to_numeric(missing[hc], errors="coerce").to_numpy()
    new["facility_supply_warning"] = (
        "No FDR facility mapped to this district — zero-supply desert surfaced from NFHS health need."
    )
    new["zero_facility_desert"] = True

    combined = pd.concat([existing, new], ignore_index=True)
    combined = recompute_scores(combined)
    combined.to_csv(DISTRICT_CSV, index=False)

    added = int(new.shape[0])
    deserts = combined[combined["zero_facility_desert"]]
    top = (
        combined.sort_values("care_gap_score", ascending=False)
        .head(10)[["state_ut", "district_name", "observed_facility_rows",
                   "health_need_score", "care_gap_score", "zero_facility_desert"]]
    )
    print(f"Districts: {len(existing)} -> {len(combined)}  (+{added} zero-facility deserts)")
    print(f"Zero-facility deserts: {len(deserts)} | "
          f"in top-50 care_gap: {int(combined.nlargest(50,'care_gap_score')['zero_facility_desert'].sum())}")
    print("care_gap range now: "
          f"{combined['care_gap_score'].min():.3f}..{combined['care_gap_score'].max():.3f}")
    print("\nTop 10 by care_gap_score:")
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(top.to_string(index=False))


if __name__ == "__main__":
    main()
