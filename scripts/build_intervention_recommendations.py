#!/usr/bin/env python3
"""Build the Intervention Recommender gold artifacts (Feature 2).

Loads the cleaned district + facility tables via the app's data module, runs the
transparent expected-value intervention engine over every district, and writes:

    output/data/intervention_recommendations.csv          (district x intervention)
    output/data/intervention_recommendations_summary.json (counts + methodology)

Idempotent: rerunning overwrites both artifacts. Runnable now from the repo root:

    .venv/bin/python scripts/build_intervention_recommendations.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Make `app/lib` importable regardless of cwd.
_ROOT = Path(__file__).resolve().parents[1]
_APP = _ROOT / "app"
if str(_APP) not in sys.path:
    sys.path.insert(0, str(_APP))

import pandas as pd  # noqa: E402

from lib import config, data, interventions  # noqa: E402


def main() -> int:
    print("Loading district and facility tables…")
    districts = data.load_districts()
    try:
        facilities = data.load_facilities()
    except Exception as exc:  # facilities are optional for the engine
        print(f"  (facilities unavailable, continuing district-only: {exc})")
        facilities = pd.DataFrame()
    print(f"  districts: {len(districts):,} rows")
    print(f"  facilities: {len(facilities):,} rows")

    print("Scoring interventions per district…")
    recs = interventions.compute_recommendations(districts)
    if recs.empty:
        print("ERROR: no recommendations produced.", file=sys.stderr)
        return 1

    # Validate: no NaN EV for valid districts.
    n_nan_ev = int(recs["ev_score"].isna().sum())
    if n_nan_ev:
        print(f"WARNING: {n_nan_ev} rows have NaN EV (investigate).", file=sys.stderr)

    out_dir = config.data_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "intervention_recommendations.csv"
    json_path = out_dir / "intervention_recommendations_summary.json"

    recs.to_csv(csv_path, index=False)
    print(f"Wrote {csv_path} ({len(recs):,} rows, "
          f"{recs['district_name'].nunique()} districts)")

    # --- summary JSON ---
    top1 = recs[recs["rank"] == 1]
    top_counts = top1["intervention"].value_counts().to_dict()
    overall_counts = recs["intervention"].value_counts().to_dict()
    conf_counts = top1["confidence"].value_counts().to_dict()
    telehealth = recs[recs["intervention"] == "Telehealth-first program"]
    telehealth_flagged = int(telehealth["not_recommended_flag"].sum())

    summary = {
        "policy_version": interventions.POLICY_VERSION,
        "generated_from": {
            "district_table": str(config.district_table_path()),
            "district_rows": int(len(districts)),
            "facility_rows": int(len(facilities)),
        },
        "row_counts": {
            "recommendation_rows": int(len(recs)),
            "districts_scored": int(recs["district_name"].nunique()),
            "candidates_per_district": int(round(len(recs) / max(recs["district_name"].nunique(), 1))),
            "nan_ev_rows": n_nan_ev,
        },
        "top_intervention_counts": {k: int(v) for k, v in top_counts.items()},
        "intervention_counts_all_ranks": {k: int(v) for k, v in overall_counts.items()},
        "top_recommendation_confidence_counts": {k: int(v) for k, v in conf_counts.items()},
        "telehealth": {
            "rows": int(len(telehealth)),
            "flagged_not_recommended": telehealth_flagged,
            "note": "Telehealth is a low-confidence default: broadband and elderly-share "
                    "signals are NOT in the dataset, so the doc's penalty cannot be applied.",
        },
        "ev_score_summary": {
            "min": round(float(recs["ev_score"].min()), 4),
            "median": round(float(recs["ev_score"].median()), 4),
            "max": round(float(recs["ev_score"].max()), 4),
        },
        "methodology_notes": [
            "EV = P(addresses_need) * benefit - P(wrong) * harm - operating_cost.",
            "benefit scales with health_need_score and the relevant NFHS/supply need gap.",
            "P(wrong) scales with district_uncertainty_level, small observed samples, "
            "high needs_human_review_rate, high critical_supply_gap_rate, and wide supply CIs.",
            "operating_cost and harm come from per-intervention priors (transparent constants).",
            "confidence (Low/Medium/High) is tied to evidence strength + fit, not measured accuracy.",
            "Missing-signal substitutions are labeled as PROXIES in the rationale; the doc's "
            "broadband and elderly-share signals do not exist in this dataset.",
        ],
        "intervention_to_signals": {
            "Mobile primary care clinic": "real_desert_candidate + low trustworthy_supply_rate + low capacity_observed_rate",
            "OB referral network + prenatal telehealth & transport": "low institutional_birth_5y_pct + high anaemia + low maternity_signal_rate",
            "Pharmacy-based chronic care screening": "high BP/blood-sugar pct + low ncd/diagnostic_signal_rate",
            "PM-JAY / insurance enrollment support": "low hh_member_covered_health_insurance_pct + referral_or_capacity_candidate",
            "Community health worker outreach": "high needs_human_review_rate + low contact_evidence_rate",
            "Verify-first data / records campaign": "phantom_desert_or_verification_gap | supply_record_quality_problem",
            "Telehealth-first program": "LOW-confidence default; broadband/elderly not in dataset",
        },
    }
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote {json_path}")

    print("\nTop #1 interventions:")
    for k, v in sorted(top_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    print(f"\nTelehealth flagged not-recommended: {telehealth_flagged} / {len(telehealth)} districts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
