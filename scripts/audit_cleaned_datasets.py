#!/usr/bin/env python3
"""Audit cleaned hackathon datasets before upload."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
AUDIT_PATH = DATA_DIR / "cleaned_dataset_audit.json"


def issue(severity: str, check: str, detail: str, rows: int | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"severity": severity, "check": check, "detail": detail}
    if rows is not None:
        out["rows"] = int(rows)
    return out


def bounded(series: pd.Series, low: float = 0, high: float = 1) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce")
    return values.between(low, high) | values.isna()


def main() -> None:
    district = pd.read_csv(DATA_DIR / "district_health_facility_cleaned.csv")
    facility = pd.read_csv(DATA_DIR / "facility_health_cleaned.csv", low_memory=False)
    unmatched = pd.read_csv(DATA_DIR / "district_unmatched_pincode_facility_counts.csv")
    raw_facilities = pd.read_csv(DATA_DIR / "raw_facilities_selected.csv", low_memory=False)
    summary = json.loads((DATA_DIR / "analysis_summary.json").read_text())
    insights = json.loads((DATA_DIR / "actual_insights_summary.json").read_text())

    issues: list[dict[str, Any]] = []

    expected = {
        "facility_rows": 10077,
        "raw_facility_rows": 10088,
        "district_min_rows": 450,
        "district_max_rows": 706,
    }
    if len(raw_facilities) != expected["raw_facility_rows"]:
        issues.append(issue("error", "raw_facility_row_count", f"Expected 10088 raw rows, got {len(raw_facilities)}."))
    if len(facility) != expected["facility_rows"]:
        issues.append(issue("error", "facility_row_count", f"Expected 10077 deduplicated rows, got {len(facility)}."))
    if not expected["district_min_rows"] <= len(district) <= expected["district_max_rows"]:
        issues.append(
            issue(
                "error",
                "district_row_count",
                f"Expected district rows in [{expected['district_min_rows']}, {expected['district_max_rows']}], got {len(district)}.",
            )
        )

    required_district_cols = [
        "state_ut",
        "district_name",
        "observed_facility_rows",
        "health_need_score",
        "care_gap_score",
        "trust_gap_score",
        "best_care_signal_score",
        "planning_category",
        "district_data_quality_score",
        "district_uncertainty_level",
        "sample_claim_evidence",
    ]
    missing_cols = [c for c in required_district_cols if c not in district.columns]
    if missing_cols:
        issues.append(issue("error", "district_required_columns", f"Missing columns: {missing_cols}"))

    required_facility_cols = [
        "unique_id",
        "facility_name",
        "pincode_extracted",
        "join_strategy",
        "join_confidence",
        "geo_quality",
        "trustworthy_supply_signal",
        "needs_human_review",
    ]
    missing_facility_cols = [c for c in required_facility_cols if c not in facility.columns]
    if missing_facility_cols:
        issues.append(issue("error", "facility_required_columns", f"Missing columns: {missing_facility_cols}"))

    if {"state_ut", "district_name"}.issubset(district.columns):
        duplicate_districts = district.duplicated(["state_ut", "district_name"]).sum()
        if duplicate_districts:
            issues.append(issue("error", "district_uniqueness", "Duplicate state/district rows.", duplicate_districts))
        null_keys = district["state_ut"].isna().sum() + district["district_name"].isna().sum()
        if null_keys:
            issues.append(issue("error", "district_keys_not_null", "Null district key values.", null_keys))

    if "unique_id" in facility.columns:
        duplicate_ids = facility["unique_id"].duplicated().sum()
        if duplicate_ids:
            issues.append(issue("error", "facility_unique_id", "Duplicate facility unique_id values.", duplicate_ids))
    raw_duplicate_ids = raw_facilities["unique_id"].duplicated().sum()
    if raw_duplicate_ids:
        issues.append(
            issue(
                "warning",
                "raw_facility_duplicate_unique_id",
                "Raw facilities contained duplicate unique_id values; cleaned facility table keeps one row and records source occurrence count.",
                raw_duplicate_ids,
            )
        )

    bounded_cols = [
        "health_need_score",
        "district_medical_desert_priority_score",
        "care_gap_score",
        "trust_gap_score",
        "best_care_signal_score",
        "district_data_quality_score",
        "trustworthy_supply_rate",
        "needs_human_review_rate",
        "source_url_rate",
        "plausible_geo_rate",
        "capacity_parse_rate",
        "doctor_parse_rate",
    ]
    for col in bounded_cols:
        if col in district.columns:
            bad = (~bounded(district[col])).sum()
            if bad:
                issues.append(issue("error", f"{col}_bounds", f"{col} outside [0, 1].", bad))

    if {"observed_facility_rows", "trustworthy_supply_rows"}.issubset(district.columns):
        bad = (district["trustworthy_supply_rows"] > district["observed_facility_rows"]).sum()
        if bad:
            issues.append(issue("error", "trustworthy_supply_count", "Trustworthy supply rows exceed observed rows.", bad))

    if {"observed_facility_rows", "needs_human_review_rows"}.issubset(district.columns):
        bad = (district["needs_human_review_rows"] > district["observed_facility_rows"]).sum()
        if bad:
            issues.append(issue("error", "review_count", "Review rows exceed observed rows.", bad))

    valid_categories = {
        "real_desert_candidate",
        "phantom_desert_or_verification_gap",
        "supply_record_quality_problem",
        "referral_or_capacity_candidate",
        "mixed_or_monitor",
    }
    if "planning_category" in district.columns:
        unknown = sorted(set(district["planning_category"].dropna()) - valid_categories)
        if unknown:
            issues.append(issue("error", "planning_category_values", f"Unknown categories: {unknown}"))

    if "planning_category" in district.columns:
        counts = district["planning_category"].value_counts().to_dict()
        if counts.get("real_desert_candidate", 0) == 0:
            issues.append(issue("warning", "real_desert_presence", "No real desert candidates were classified."))
        if counts.get("referral_or_capacity_candidate", 0) == 0:
            issues.append(issue("warning", "referral_presence", "No referral/capacity candidates were classified."))

    if "observed_facility_rows" in district.columns:
        zero_rows = district["observed_facility_rows"].fillna(0).le(0).sum()
        if zero_rows:
            issues.append(
                issue(
                    "warning",
                    "districts_without_joined_facility_rows",
                    "District rows without joined FDR facility evidence are excluded from the current primary dataset.",
                    zero_rows,
                )
            )

    gaps = {
        "facility_rows": int(len(facility)),
        "raw_facility_rows": int(len(raw_facilities)),
        "raw_facility_duplicate_unique_id_rows": int(raw_duplicate_ids),
        "district_rows": int(len(district)),
        "unmatched_pincode_district_groups": int(len(unmatched)),
        "facility_needs_human_review_rows": int(facility["needs_human_review"].astype(str).str.lower().eq("true").sum()),
        "facility_trustworthy_supply_rows": int(facility["trustworthy_supply_signal"].astype(str).str.lower().eq("true").sum()),
        "district_planning_category_counts": district["planning_category"].value_counts(dropna=False).to_dict(),
        "district_uncertainty_counts": district["district_uncertainty_level"].value_counts(dropna=False).to_dict(),
        "top_care_gap_districts": insights["rankings"]["top_care_gaps"][:10],
        "known_limitations": [
            "NFHS indicators are district-level and older than the web-extracted facility data.",
            "Observed FDR facility counts are not a verified supply census.",
            "District matching depends on PIN code and name harmonization; unmatched pincode district groups are retained for audit.",
            "Claimed services are detected from extracted text and should be cited/verified before operational use.",
            "No travel-time or population denominator is available, so care gaps are proxy scores, not definitive access measures.",
        ],
    }

    upload_ready = not any(i["severity"] == "error" for i in issues)
    audit = {
        "upload_ready": upload_ready,
        "issues": issues,
        "metrics": gaps,
        "source_summary": summary.get("source_tables", {}),
    }
    AUDIT_PATH.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    print(json.dumps({"upload_ready": upload_ready, "issue_count": len(issues), "errors": sum(i["severity"] == "error" for i in issues)}, indent=2))
    if issues:
        print(json.dumps(issues[:10], indent=2))


if __name__ == "__main__":
    main()
