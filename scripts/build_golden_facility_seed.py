#!/usr/bin/env python3
"""Build seed artifacts for the golden facility prediction phase.

This does not create supervised ground truth. It turns the current cleaned
facility table into auditable bronze/conflict seed rows, feature rows, and
rule-baseline prediction outputs so the next phase has a concrete table contract.
Tier A/B registry or open-data matches should later promote rows to trainable
gold/silver labels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import h3
except ImportError:  # pragma: no cover - local app requirements include h3
    h3 = None


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"

FACILITY_PATH = DATA_DIR / "facility_health_cleaned.csv"
GEO_CANDIDATES_PATH = DATA_DIR / "geo_validation_candidates.csv"

SOURCE_MATCHES_PATH = DATA_DIR / "golden_facility_source_matches_seed.csv"
TRAINING_SET_PATH = DATA_DIR / "golden_facility_training_set_seed.csv"
FEATURES_PATH = DATA_DIR / "facility_prediction_features_seed.csv"
PREDICTIONS_PATH = DATA_DIR / "facility_prediction_outputs_seed.csv"
REPORT_PATH = DATA_DIR / "golden_facility_seed_report.json"


BASE_COLUMNS = [
    "unique_id",
    "facility_name",
    "facilityTypeId",
    "operatorTypeId",
    "address_line1",
    "address_line2",
    "address_line3",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "pincode_extracted",
    "pincode_primary_district",
    "pincode_primary_state",
    "pincode_is_ambiguous",
    "facility_latitude",
    "facility_longitude",
    "geo_quality",
    "geo_distance_km_to_pincode_centroid",
    "district_name",
    "state_ut",
    "join_strategy",
    "join_confidence",
    "join_match_score",
    "join_uncertainty_reason",
    "data_readiness_score",
    "supply_data_confidence_score",
    "semantic_data_quality_score",
    "medical_desert_priority_score",
    "health_need_score",
    "trustworthy_supply_signal",
    "needs_human_review",
    "contradicted_or_geo_invalid_signal",
    "has_source_urls",
    "has_contact_evidence",
    "source_urls",
    "officialWebsite",
    "officialPhone",
    "email",
    "claim_text",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
    "capacity_status",
    "capacity_estimate",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "capacity_confidence",
    "capacity_is_estimated",
    "doctor_count_status",
    "doctor_count_estimate",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
    "doctor_count_confidence",
    "doctor_count_is_estimated",
    "capacity_num_extreme_outlier",
    "number_doctors_num_extreme_outlier",
]

NUMERIC_COLUMNS = [
    "facility_latitude",
    "facility_longitude",
    "geo_distance_km_to_pincode_centroid",
    "join_confidence",
    "join_match_score",
    "data_readiness_score",
    "supply_data_confidence_score",
    "semantic_data_quality_score",
    "medical_desert_priority_score",
    "health_need_score",
    "capacity_estimate",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "doctor_count_estimate",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
]

BOOLEAN_COLUMNS = [
    "pincode_is_ambiguous",
    "trustworthy_supply_signal",
    "needs_human_review",
    "contradicted_or_geo_invalid_signal",
    "has_source_urls",
    "has_contact_evidence",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
    "capacity_is_estimated",
    "doctor_count_is_estimated",
    "capacity_num_extreme_outlier",
    "number_doctors_num_extreme_outlier",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=FACILITY_PATH)
    parser.add_argument("--geo-candidates", type=Path, default=GEO_CANDIDATES_PATH)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional row limit for quick local smoke tests. 0 means all rows.",
    )
    return parser.parse_args()


def load_facilities(path: Path, limit: int = 0) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing cleaned facility file: {path}")

    header = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [col for col in BASE_COLUMNS if col in header]
    kwargs = {"usecols": usecols, "low_memory": False}
    if limit > 0:
        kwargs["nrows"] = limit
    df = pd.read_csv(path, **kwargs)

    for col in NUMERIC_COLUMNS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BOOLEAN_COLUMNS:
        if col in df:
            df[col] = coerce_bool(df[col])
    return df


def coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    text = series.astype("string").fillna("").str.lower().str.strip()
    return text.isin({"true", "1", "yes", "y"})


def clean_text(value: object) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "[]"}:
        return ""
    return text


def normalize_text(value: object) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def stable_id(*parts: object, prefix: str) -> str:
    payload = "||".join(clean_text(part).lower() for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def first_url(raw: object) -> str:
    text = clean_text(raw)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in parsed:
                url = clean_text(item)
                if url:
                    return url
    except json.JSONDecodeError:
        pass
    return text.strip('[]"').split(",")[0].strip()


def source_count(raw: object) -> int:
    text = clean_text(raw)
    if not text:
        return 0
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return sum(1 for item in parsed if clean_text(item))
    except json.JSONDecodeError:
        pass
    return 1


def h3_cell(lat: object, lon: object, resolution: int) -> str:
    if h3 is None:
        return ""
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        return ""
    if not np.isfinite(lat_f) or not np.isfinite(lon_f):
        return ""
    return h3.latlng_to_cell(lat_f, lon_f, resolution)


def capacity_band(value: object) -> str:
    val = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(val):
        return "unknown"
    if val <= 0:
        return "none_or_unknown"
    if val < 30:
        return "small"
    if val < 100:
        return "medium"
    if val < 300:
        return "large"
    return "very_large"


def doctor_band(value: object) -> str:
    val = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(val):
        return "unknown"
    if val <= 0:
        return "none_or_unknown"
    if val <= 2:
        return "solo_or_small_team"
    if val <= 10:
        return "medium_team"
    if val <= 50:
        return "large_team"
    return "very_large_team"


def service_labels(row: pd.Series) -> list[str]:
    labels = []
    mapping = {
        "has_maternity_care_signal": "maternity",
        "has_emergency_care_signal": "emergency",
        "has_diagnostic_signal": "diagnostic",
        "has_ncd_care_signal": "ncd",
    }
    for col, label in mapping.items():
        if bool(row.get(col, False)):
            labels.append(label)
    return labels


def evidence_tier(row: pd.Series) -> str:
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "conflict"
    return "bronze"


def trust_posture(row: pd.Series) -> str:
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "contradicted_or_geo_invalid"
    if bool(row.get("trustworthy_supply_signal", False)) and not bool(row.get("needs_human_review", False)):
        return "passed_proxy_checks"
    if bool(row.get("needs_human_review", False)):
        return "needs_review"
    return "unknown"


def trainable(row: pd.Series) -> bool:
    return evidence_tier(row) in {"gold", "silver"}


def recommended_action(row: pd.Series) -> str:
    posture = row.get("trust_posture", trust_posture(row))
    if posture == "contradicted_or_geo_invalid":
        return "verify_location_before_use"
    if bool(row.get("needs_human_review", False)):
        return "source_enrichment_or_manual_review"
    if evidence_tier(row) == "bronze":
        return "use_as_proxy_only"
    return "candidate_for_recommendation"


def abstain_reason(row: pd.Series) -> str:
    tier = row.get("evidence_tier", evidence_tier(row))
    if tier == "conflict":
        return "source_or_geography_conflict"
    if tier == "bronze":
        return "no_tier_a_or_b_corroborated_label"
    return ""


def prediction_confidence(row: pd.Series) -> float:
    readiness = float(row.get("data_readiness_score", 0) or 0)
    join = float(row.get("join_confidence", 0) or 0)
    semantic = float(row.get("semantic_data_quality_score", 0) or 0)
    confidence = 0.42 * readiness + 0.30 * join + 0.28 * semantic
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        confidence *= 0.45
    if bool(row.get("needs_human_review", False)):
        confidence *= 0.75
    return round(float(np.clip(confidence, 0, 1)), 4)


def add_ids_and_labels(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["golden_facility_id"] = [
        stable_id(row.unique_id, row.facility_name, row.address_zipOrPostcode, prefix="gfac")
        for row in out.itertuples(index=False)
    ]
    out["facility_name_norm"] = out["facility_name"].map(normalize_text)
    out["address_city_norm"] = out["address_city"].map(normalize_text)
    out["state_norm"] = out["state_ut"].map(normalize_text)
    out["pincode_norm"] = out["address_zipOrPostcode"].map(lambda v: re.sub(r"\D", "", clean_text(v))[:6])
    out["first_source_url"] = out["source_urls"].map(first_url)
    out["source_url_count"] = out["source_urls"].map(source_count)
    out["evidence_tier"] = out.apply(evidence_tier, axis=1)
    out["trust_posture"] = out.apply(trust_posture, axis=1)
    out["service_labels"] = out.apply(lambda row: json.dumps(service_labels(row)), axis=1)
    out["capacity_band"] = out["capacity_estimate"].map(capacity_band)
    out["doctor_count_band"] = out["doctor_count_estimate"].map(doctor_band)
    out["trainable_supervised_label"] = out.apply(trainable, axis=1)
    out["recommended_action"] = out.apply(recommended_action, axis=1)
    out["abstain_reason"] = out.apply(abstain_reason, axis=1)
    out["rule_baseline_confidence"] = out.apply(prediction_confidence, axis=1)
    out["h3_res7"] = [h3_cell(lat, lon, 7) for lat, lon in zip(out["facility_latitude"], out["facility_longitude"])]
    out["h3_res9"] = [h3_cell(lat, lon, 9) for lat, lon in zip(out["facility_latitude"], out["facility_longitude"])]
    return out


def build_source_matches(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in df.itertuples(index=False):
        source_url_count_value = int(getattr(row, "source_url_count", 0) or 0)
        rows.append(
            {
                "golden_facility_id": row.golden_facility_id,
                "unique_id": row.unique_id,
                "source_system": "fdr_cleaned_facility",
                "source_tier": "C",
                "source_record_id": row.unique_id,
                "source_url": row.first_source_url,
                "match_type": "self_seed",
                "match_score": 1.0,
                "source_agreement_status": "claim_seed",
                "source_url_count": source_url_count_value,
                "conflict_reason": row.abstain_reason if row.evidence_tier == "conflict" else "",
                "can_promote_label": False,
            }
        )
        if clean_text(getattr(row, "pincode_extracted", "")):
            rows.append(
                {
                    "golden_facility_id": row.golden_facility_id,
                    "unique_id": row.unique_id,
                    "source_system": "india_post_pincode_bridge",
                    "source_tier": "A",
                    "source_record_id": clean_text(getattr(row, "pincode_extracted", "")),
                    "source_url": "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month",
                    "match_type": "admin_geography_context",
                    "match_score": getattr(row, "join_confidence", np.nan),
                    "source_agreement_status": "admin_context_only",
                    "source_url_count": 1,
                    "conflict_reason": getattr(row, "join_uncertainty_reason", ""),
                    "can_promote_label": False,
                }
            )
    return pd.DataFrame(rows)


def build_training_set(df: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "golden_facility_id",
        "unique_id",
        "facility_name",
        "facility_name_norm",
        "facilityTypeId",
        "operatorTypeId",
        "address_city",
        "address_city_norm",
        "district_name",
        "state_ut",
        "state_norm",
        "address_zipOrPostcode",
        "pincode_norm",
        "facility_latitude",
        "facility_longitude",
        "h3_res7",
        "h3_res9",
        "evidence_tier",
        "trainable_supervised_label",
        "trust_posture",
        "service_labels",
        "capacity_band",
        "doctor_count_band",
        "recommended_action",
        "abstain_reason",
        "rule_baseline_confidence",
        "first_source_url",
        "source_url_count",
        "claim_text",
    ]
    return df[[col for col in columns if col in df.columns]].copy()


def build_feature_table(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "golden_facility_id": df["golden_facility_id"],
            "unique_id": df["unique_id"],
            "facility_type_raw": df["facilityTypeId"],
            "operator_type_raw": df["operatorTypeId"],
            "lat": df["facility_latitude"],
            "lon": df["facility_longitude"],
            "h3_res7": df["h3_res7"],
            "h3_res9": df["h3_res9"],
            "has_pincode": df["pincode_norm"].astype(str).str.len().eq(6),
            "pincode_is_ambiguous": df.get("pincode_is_ambiguous", False),
            "join_confidence": df["join_confidence"],
            "join_match_score": df["join_match_score"],
            "data_readiness_score": df["data_readiness_score"],
            "semantic_data_quality_score": df["semantic_data_quality_score"],
            "supply_data_confidence_score": df["supply_data_confidence_score"],
            "health_need_score": df["health_need_score"],
            "medical_desert_priority_score": df["medical_desert_priority_score"],
            "source_url_count": df["source_url_count"],
            "has_source_urls": df["has_source_urls"],
            "has_contact_evidence": df["has_contact_evidence"],
            "has_maternity_care_signal": df["has_maternity_care_signal"],
            "has_emergency_care_signal": df["has_emergency_care_signal"],
            "has_diagnostic_signal": df["has_diagnostic_signal"],
            "has_ncd_care_signal": df["has_ncd_care_signal"],
            "capacity_estimate": df["capacity_estimate"],
            "capacity_interval_width": df["capacity_estimate_interval_high"] - df["capacity_estimate_interval_low"],
            "capacity_is_estimated": df["capacity_is_estimated"],
            "doctor_count_estimate": df["doctor_count_estimate"],
            "doctor_count_interval_width": df["doctor_count_estimate_interval_high"] - df["doctor_count_estimate_interval_low"],
            "doctor_count_is_estimated": df["doctor_count_is_estimated"],
            "geo_distance_km_to_pincode_centroid": df["geo_distance_km_to_pincode_centroid"],
            "geo_quality": df["geo_quality"],
            "contradicted_or_geo_invalid_signal": df["contradicted_or_geo_invalid_signal"],
            "needs_human_review": df["needs_human_review"],
        }
    )
    return out


def build_prediction_outputs(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "prediction_id": [
                stable_id(row.golden_facility_id, "rule_proxy_seed_v0", prefix="pred")
                for row in df.itertuples(index=False)
            ],
            "model_version": "rule_proxy_seed_v0",
            "golden_facility_id": df["golden_facility_id"],
            "unique_id": df["unique_id"],
            "predicted_facility_type": df["facilityTypeId"],
            "predicted_service_labels": df["service_labels"],
            "predicted_trust_posture": df["trust_posture"],
            "predicted_capacity_band": df["capacity_band"],
            "predicted_doctor_count_band": df["doctor_count_band"],
            "prediction_confidence": df["rule_baseline_confidence"],
            "evidence_tier": df["evidence_tier"],
            "abstain": ~df["trainable_supervised_label"],
            "abstain_reason": df["abstain_reason"],
            "recommended_action": df["recommended_action"],
            "source_url": df["first_source_url"],
        }
    )
    return out


def load_geo_candidate_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        ids = pd.read_csv(path, usecols=["unique_id"], low_memory=False)["unique_id"]
    except ValueError:
        return set()
    return set(ids.dropna().astype(str))


def report_for(
    df: pd.DataFrame,
    source_matches: pd.DataFrame,
    training_set: pd.DataFrame,
    features: pd.DataFrame,
    predictions: pd.DataFrame,
    geo_candidate_ids: Iterable[str],
) -> dict[str, object]:
    geo_ids = set(geo_candidate_ids)
    return {
        "created_outputs": {
            "source_matches": str(SOURCE_MATCHES_PATH.relative_to(ROOT)),
            "training_set": str(TRAINING_SET_PATH.relative_to(ROOT)),
            "features": str(FEATURES_PATH.relative_to(ROOT)),
            "prediction_outputs": str(PREDICTIONS_PATH.relative_to(ROOT)),
        },
        "row_counts": {
            "cleaned_facilities_input": int(len(df)),
            "source_matches": int(len(source_matches)),
            "training_set": int(len(training_set)),
            "features": int(len(features)),
            "prediction_outputs": int(len(predictions)),
            "geo_validation_candidates_overlap": int(df["unique_id"].astype(str).isin(geo_ids).sum()),
        },
        "label_tier_counts": training_set["evidence_tier"].value_counts(dropna=False).to_dict(),
        "trust_posture_counts": training_set["trust_posture"].value_counts(dropna=False).to_dict(),
        "trainable_supervised_labels": int(training_set["trainable_supervised_label"].sum()),
        "non_trainable_reason": (
            "Seed rows are bronze/conflict only. Promote rows to gold/silver after "
            "HFR/authoritative registry or independent open-data corroboration."
        ),
        "guardrails": [
            "Do not train supervised accuracy metrics from bronze/conflict seed labels.",
            "Do not use Google/Mappls as durable labels without license review.",
            "Use NFHS only as district context, never facility-level truth.",
            "Keep abstain_reason and evidence_tier visible in the app.",
        ],
    }


def main() -> None:
    args = parse_args()
    global SOURCE_MATCHES_PATH, TRAINING_SET_PATH, FEATURES_PATH, PREDICTIONS_PATH, REPORT_PATH
    data_dir = args.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    SOURCE_MATCHES_PATH = data_dir / SOURCE_MATCHES_PATH.name
    TRAINING_SET_PATH = data_dir / TRAINING_SET_PATH.name
    FEATURES_PATH = data_dir / FEATURES_PATH.name
    PREDICTIONS_PATH = data_dir / PREDICTIONS_PATH.name
    REPORT_PATH = data_dir / REPORT_PATH.name

    facilities = load_facilities(args.input, limit=args.limit)
    facilities = add_ids_and_labels(facilities)
    source_matches = build_source_matches(facilities)
    training_set = build_training_set(facilities)
    features = build_feature_table(facilities)
    predictions = build_prediction_outputs(facilities)
    geo_candidate_ids = load_geo_candidate_ids(args.geo_candidates)

    source_matches.to_csv(SOURCE_MATCHES_PATH, index=False)
    training_set.to_csv(TRAINING_SET_PATH, index=False)
    features.to_csv(FEATURES_PATH, index=False)
    predictions.to_csv(PREDICTIONS_PATH, index=False)

    report = report_for(facilities, source_matches, training_set, features, predictions, geo_candidate_ids)
    REPORT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
