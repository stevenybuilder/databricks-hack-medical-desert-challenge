#!/usr/bin/env python3
"""Build proposed coordinate corrections from Google geocoding evidence."""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
FACILITY_PATH = DATA_DIR / "facility_health_cleaned.csv"
GOOGLE_PATH = DATA_DIR / "google_geocoding_results.csv"
OUTPUT_PATH = DATA_DIR / "geo_coordinate_correction_candidates.csv"
SUMMARY_PATH = DATA_DIR / "geo_coordinate_correction_summary.json"

ACCEPT_STATUSES = {"accept_coordinate_candidate", "neighborhood_candidate_h3_only"}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return None
    radius_km = 6371.0088
    dlat = math.radians(float(lat2) - float(lat1))
    dlon = math.radians(float(lon2) - float(lon1))
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(float(lat1)))
        * math.cos(math.radians(float(lat2)))
        * math.sin(dlon / 2) ** 2
    )
    return round(2 * radius_km * math.asin(math.sqrt(a)), 3)


def correction_action(row: pd.Series) -> str:
    status = row["google_validation_status"]
    if status == "accept_coordinate_candidate":
        return "propose_replace_coordinate"
    if status == "neighborhood_candidate_h3_only":
        return "store_h3_neighborhood_candidate"
    return "keep_in_review"


def main() -> None:
    facility = pd.read_csv(FACILITY_PATH, low_memory=False)
    google = pd.read_csv(GOOGLE_PATH, low_memory=False)
    selected = google[google["google_validation_status"].isin(ACCEPT_STATUSES)].copy()

    cols = [
        "unique_id",
        "facility_name",
        "address_city",
        "address_stateOrRegion",
        "address_zipOrPostcode",
        "facility_latitude",
        "facility_longitude",
        "geo_quality",
        "geo_distance_km_to_pincode_centroid",
        "medical_desert_priority_score",
        "needs_human_review",
        "trustworthy_supply_signal",
    ]
    merged = selected.merge(facility[cols], on="unique_id", how="left", suffixes=("_google", ""))
    merged["current_to_google_distance_km"] = merged.apply(
        lambda row: haversine_km(
            row.get("facility_latitude"),
            row.get("facility_longitude"),
            row.get("google_latitude"),
            row.get("google_longitude"),
        ),
        axis=1,
    )
    merged["coordinate_correction_action"] = merged.apply(correction_action, axis=1)
    merged["correction_acceptance_note"] = merged["google_validation_status"].map(
        {
            "accept_coordinate_candidate": "Precise Google result with admin/PIN checks; review before canonical overwrite.",
            "neighborhood_candidate_h3_only": "Coarse Google result; use for H3/neighborhood planning only.",
        }
    )

    output_cols = [
        "unique_id",
        "facility_name",
        "coordinate_correction_action",
        "google_validation_status",
        "location_type",
        "partial_match",
        "formatted_address",
        "place_id",
        "google_latitude",
        "google_longitude",
        "plus_code_global",
        "plus_code_compound",
        "current_to_google_distance_km",
        "facility_latitude",
        "facility_longitude",
        "geo_quality",
        "geo_distance_km_to_pincode_centroid",
        "expected_pincode",
        "expected_state",
        "expected_city",
        "pincode_match",
        "state_match",
        "city_match",
        "medical_desert_priority_score",
        "needs_human_review",
        "trustworthy_supply_signal",
        "correction_acceptance_note",
    ]
    merged[output_cols].to_csv(OUTPUT_PATH, index=False)

    summary = {
        "input_google_rows": int(len(google)),
        "correction_candidate_rows": int(len(merged)),
        "by_action": merged["coordinate_correction_action"].value_counts(dropna=False).to_dict(),
        "by_google_validation_status": google["google_validation_status"].value_counts(dropna=False).to_dict(),
        "canonical_update_policy": "No canonical coordinates are overwritten by this script; rows are proposed corrections with provider provenance.",
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
