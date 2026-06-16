#!/usr/bin/env python3
"""Build missing-data remediation and human verification seed artifacts.

The script is local and deterministic: it reads the cleaned facility CSV, uses
only existing columns, makes no network/API/LLM calls, and writes the remediation
summary, seed queue, JSON summary, and workflow doc.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
DOCS_DIR = ROOT / "docs"

FACILITY_PATH = DATA_DIR / "facility_health_cleaned.csv"
REMEDIATION_SUMMARY_PATH = DATA_DIR / "missing_data_remediation_summary.csv"
SEED_QUEUE_PATH = DATA_DIR / "human_verification_seed_queue.csv"
SUMMARY_JSON_PATH = DATA_DIR / "missing_data_seed_summary.json"
WORKFLOW_DOC_PATH = DOCS_DIR / "MISSING_DATA_AND_HUMAN_SEED_WORKFLOW.md"

QUEUE_SIZE_DEFAULT = 150
MIN_QUEUE_SIZE = 50
MAX_QUEUE_SIZE = 200

ACTION_ORDER = [
    "geocode",
    "claims_verification",
    "registry_source_enrichment",
    "phone_email_reachability_review",
    "keep_estimate_with_interval",
    "no_action_low_risk",
]

ACTION_LABELS = {
    "geocode": "geocode",
    "claims_verification": "claims verification",
    "registry_source_enrichment": "registry/source enrichment",
    "phone_email_reachability_review": "phone/email reachability review",
    "keep_estimate_with_interval": "keep estimate with interval",
    "no_action_low_risk": "no action for low-risk rows",
}

CORE_COLUMNS = [
    "unique_id",
    "facility_name",
    "facilityTypeId",
    "operatorTypeId",
    "address_line1",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "pincode_extracted",
    "pincode_primary_district",
    "pincode_primary_state",
    "pincode_n_districts",
    "pincode_n_states",
    "pincode_is_ambiguous",
    "pincode_region_is_ambiguous",
    "facility_latitude",
    "facility_longitude",
    "geo_distance_km_to_pincode_centroid",
    "geo_quality",
    "district_name",
    "state_ut",
    "join_strategy",
    "join_confidence",
    "join_match_score",
    "join_uncertainty_reason",
    "data_readiness_score",
    "medical_desert_priority_score",
    "health_need_score",
    "supply_data_confidence_score",
    "semantic_data_quality_score",
    "semantic_missing_critical_count",
    "critical_supply_gap_flag",
    "needs_human_review",
    "trustworthy_supply_signal",
    "contradicted_or_geo_invalid_signal",
    "capacity_status",
    "capacity_num",
    "capacity_estimate",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "capacity_estimate_source",
    "capacity_estimate_sample_n",
    "capacity_confidence",
    "capacity_is_estimated",
    "doctor_count_status",
    "number_doctors_num",
    "doctor_count_estimate",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
    "doctor_count_estimate_source",
    "doctor_count_estimate_sample_n",
    "doctor_count_confidence",
    "doctor_count_is_estimated",
    "recency_of_page_update",
    "recency_page_update_date",
    "recency_status",
    "recency_confidence",
    "recency_valid_signal",
    "has_description",
    "has_specialties",
    "has_procedure",
    "has_equipment",
    "has_capability",
    "description_status",
    "specialties_status",
    "procedure_status",
    "equipment_status",
    "capability_status",
    "description_item_count",
    "specialties_item_count",
    "procedure_item_count",
    "equipment_item_count",
    "capability_item_count",
    "claim_field_count",
    "has_source_urls",
    "has_contact_evidence",
    "officialWebsite",
    "source_urls",
    "websites",
    "officialPhone",
    "phone_numbers",
    "email",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
    "capacity_num_extreme_outlier",
    "number_doctors_num_extreme_outlier",
    "claim_text",
]

NUMERIC_COLUMNS = [
    "pincode_n_districts",
    "pincode_n_states",
    "facility_latitude",
    "facility_longitude",
    "geo_distance_km_to_pincode_centroid",
    "join_confidence",
    "join_match_score",
    "data_readiness_score",
    "medical_desert_priority_score",
    "health_need_score",
    "supply_data_confidence_score",
    "semantic_data_quality_score",
    "semantic_missing_critical_count",
    "capacity_num",
    "capacity_estimate",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "capacity_estimate_sample_n",
    "number_doctors_num",
    "doctor_count_estimate",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
    "doctor_count_estimate_sample_n",
    "description_item_count",
    "specialties_item_count",
    "procedure_item_count",
    "equipment_item_count",
    "capability_item_count",
    "claim_field_count",
]

BOOLEAN_COLUMNS = [
    "pincode_is_ambiguous",
    "pincode_region_is_ambiguous",
    "critical_supply_gap_flag",
    "needs_human_review",
    "trustworthy_supply_signal",
    "contradicted_or_geo_invalid_signal",
    "capacity_is_estimated",
    "doctor_count_is_estimated",
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
    "capacity_num_extreme_outlier",
    "number_doctors_num_extreme_outlier",
]

HIGH_IMPACT_CLAIM_COLUMNS = [
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
]

STATUS_COLUMNS = [
    "capacity_status",
    "doctor_count_status",
    "recency_status",
    "description_status",
    "specialties_status",
    "procedure_status",
    "equipment_status",
    "capability_status",
    "geo_quality",
    "join_strategy",
    "capacity_confidence",
    "doctor_count_confidence",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=FACILITY_PATH)
    parser.add_argument("--data-dir", type=Path, default=DATA_DIR)
    parser.add_argument("--docs-dir", type=Path, default=DOCS_DIR)
    parser.add_argument(
        "--queue-size",
        type=int,
        default=QUEUE_SIZE_DEFAULT,
        help=f"Seed queue row count, clipped to [{MIN_QUEUE_SIZE}, {MAX_QUEUE_SIZE}].",
    )
    return parser.parse_args()


def load_facilities(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing cleaned facility file: {path}")

    header = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [col for col in CORE_COLUMNS if col in header]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)

    for col in CORE_COLUMNS:
        if col not in df:
            df[col] = pd.NA
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in STATUS_COLUMNS:
        df[col] = df[col].astype("string")
    return df


def clean_text(value: object) -> str:
    if value is None or value is pd.NA:
        return ""
    if isinstance(value, float) and np.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "[]", "{}", "<na>"}:
        return ""
    return text


def compact_text(value: object, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", clean_text(value))
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def first_list_value(raw: object) -> str:
    text = clean_text(raw)
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return text.strip('[]"').split(",")[0].strip()
    if isinstance(parsed, list):
        for item in parsed:
            item_text = clean_text(item)
            if item_text:
                return item_text
        return ""
    return clean_text(parsed)


def list_value_count(raw: object) -> int:
    text = clean_text(raw)
    if not text:
        return 0
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return 1
    if isinstance(parsed, list):
        return sum(1 for item in parsed if clean_text(item))
    return 1 if clean_text(parsed) else 0


def nullable_bool(series: pd.Series) -> pd.Series:
    if str(series.dtype) == "boolean":
        return series
    if series.dtype == bool:
        return series.astype("boolean")

    text = series.astype("string").str.lower().str.strip()
    mapped = pd.Series(pd.NA, index=series.index, dtype="boolean")
    mapped[text.isin({"true", "1", "yes", "y"})] = True
    mapped[text.isin({"false", "0", "no", "n"})] = False
    return mapped


def true_mask(series: pd.Series) -> pd.Series:
    return nullable_bool(series).eq(True).fillna(False)


def false_or_unknown_mask(series: pd.Series) -> pd.Series:
    return nullable_bool(series).ne(True).fillna(True)


def text_missing_mask(series: pd.Series) -> pd.Series:
    return series.map(clean_text).eq("")


def status_not_observed(series: pd.Series, observed: set[str] | None = None) -> pd.Series:
    observed_values = observed or {"observed_valid", "observed_claim"}
    text = series.astype("string").str.strip()
    return text.isna() | ~text.isin(observed_values)


def pct(rows: int, denominator: int) -> float:
    if denominator == 0:
        return float("nan")
    return round(rows / denominator, 6)


def add_summary_row(
    rows: list[dict[str, object]],
    *,
    domain: str,
    issue: str,
    mask: pd.Series,
    remediation_action: str,
    severity: str,
    note: str,
    source_columns: list[str],
    denominator: int,
) -> None:
    count = int(mask.fillna(False).sum())
    rows.append(
        {
            "data_domain": domain,
            "issue": issue,
            "rows": count,
            "denominator": denominator,
            "pct": pct(count, denominator),
            "remediation_action": remediation_action,
            "remediation_action_label": ACTION_LABELS[remediation_action],
            "severity": severity,
            "missing_policy": "unknown_not_false_or_zero",
            "source_columns": json.dumps(source_columns),
            "note": note,
        }
    )


def build_issue_masks(df: pd.DataFrame) -> dict[str, pd.Series]:
    capacity_estimated = true_mask(df["capacity_is_estimated"])
    doctor_estimated = true_mask(df["doctor_count_is_estimated"])
    capacity_incomplete = status_not_observed(df["capacity_status"], {"observed_valid"}) | capacity_estimated
    doctor_incomplete = status_not_observed(df["doctor_count_status"], {"observed_valid"}) | doctor_estimated
    capacity_parse_or_outlier = df["capacity_status"].isin(
        ["present_unparseable", "observed_extreme_outlier"]
    ) | true_mask(df["capacity_num_extreme_outlier"])
    doctor_parse_or_outlier = df["doctor_count_status"].isin(
        ["present_unparseable", "observed_extreme_outlier"]
    ) | true_mask(df["number_doctors_num_extreme_outlier"])
    capacity_low_confidence = df["capacity_confidence"].isin(["low", "low_medium"]) | (
        capacity_estimated & df["capacity_estimate_sample_n"].fillna(0).lt(10)
    )
    doctor_low_confidence = df["doctor_count_confidence"].isin(["low", "low_medium"]) | (
        doctor_estimated & df["doctor_count_estimate_sample_n"].fillna(0).lt(10)
    )

    recency_missing = df["recency_status"].eq("missing_semantic") | df["recency_status"].isna()
    recency_stale_or_invalid = df["recency_status"].isin(
        ["stale_over_2y", "future_date_invalid", "invalid_parse"]
    )
    recency_problem = recency_missing | recency_stale_or_invalid

    lat_missing = df["facility_latitude"].isna()
    lon_missing = df["facility_longitude"].isna()
    coords_missing = lat_missing | lon_missing | df["geo_quality"].eq("missing_coordinates")
    geo_far_or_outside = df["geo_quality"].isin(["far_from_pincode_centroid", "outside_india_bbox"])
    geo_moderate = df["geo_quality"].eq("moderate_distance_from_pincode_centroid")
    severe_geo = coords_missing | geo_far_or_outside
    geo_issue = severe_geo | geo_moderate

    has_source_unknown = false_or_unknown_mask(df["has_source_urls"])
    source_text_missing = text_missing_mask(df["source_urls"])
    source_missing = has_source_unknown | source_text_missing
    official_website_missing = text_missing_mask(df["officialWebsite"]) & text_missing_mask(df["websites"])

    contact_evidence_missing = false_or_unknown_mask(df["has_contact_evidence"])
    phone_missing = text_missing_mask(df["officialPhone"]) & text_missing_mask(df["phone_numbers"])
    email_missing = text_missing_mask(df["email"])
    phone_or_email_missing = phone_missing | email_missing

    specialties_missing = status_not_observed(df["specialties_status"], {"observed_claim"}) | df[
        "specialties_item_count"
    ].fillna(0).le(0)
    procedure_missing = status_not_observed(df["procedure_status"], {"observed_claim"}) | df[
        "procedure_item_count"
    ].fillna(0).le(0)
    equipment_missing = status_not_observed(df["equipment_status"], {"observed_claim"}) | df[
        "equipment_item_count"
    ].fillna(0).le(0)
    capability_missing = status_not_observed(df["capability_status"], {"observed_claim"}) | df[
        "capability_item_count"
    ].fillna(0).le(0)
    missing_service_claim_fields = specialties_missing | procedure_missing | equipment_missing | capability_missing

    join_confidence = df["join_confidence"]
    low_join_confidence = join_confidence.isna() | join_confidence.lt(0.80)
    fuzzy_or_fallback_join = df["join_strategy"].isin(
        [
            "pincode_only_no_health_match",
            "facility_city_state_fallback",
            "no_valid_pincode",
            "pincode_district_state_fuzzy",
            "unjoined",
        ]
    )
    missing_health_district = text_missing_mask(df["district_name"]) | text_missing_mask(df["state_ut"])
    join_issue = low_join_confidence | fuzzy_or_fallback_join | missing_health_district

    pincode_missing = text_missing_mask(df["pincode_extracted"])
    pincode_ambiguous = true_mask(df["pincode_is_ambiguous"]) | true_mask(df["pincode_region_is_ambiguous"])
    pin_issue = pincode_missing | pincode_ambiguous

    high_impact_claim_count = sum(true_mask(df[col]).astype(int) for col in HIGH_IMPACT_CLAIM_COLUMNS)
    high_impact_claim = high_impact_claim_count.gt(0)

    needs_human_review = true_mask(df["needs_human_review"])
    contradicted = true_mask(df["contradicted_or_geo_invalid_signal"])
    outlier_or_conflict = contradicted | capacity_parse_or_outlier | doctor_parse_or_outlier | geo_far_or_outside
    high_impact_claim_needs_review = high_impact_claim & (
        needs_human_review
        | outlier_or_conflict
        | source_missing
        | recency_problem
        | join_issue
        | missing_service_claim_fields
    )

    critical_missing_count = pd.to_numeric(df["semantic_missing_critical_count"], errors="coerce")
    critical_missing_high = critical_missing_count.fillna(0).ge(3)
    critical_supply_gap = true_mask(df["critical_supply_gap_flag"])

    low_risk = (
        ~needs_human_review
        & ~contradicted
        & df["geo_quality"].eq("plausible")
        & df["join_confidence"].ge(0.80).fillna(False)
        & true_mask(df["has_source_urls"])
        & true_mask(df["has_contact_evidence"])
        & ~official_website_missing
        & ~phone_or_email_missing
        & df["recency_status"].eq("observed_valid")
        & df["capacity_status"].eq("observed_valid")
        & df["doctor_count_status"].eq("observed_valid")
        & ~missing_service_claim_fields
        & ~pincode_ambiguous
    )

    return {
        "capacity_incomplete": capacity_incomplete,
        "capacity_parse_or_outlier": capacity_parse_or_outlier,
        "capacity_low_confidence": capacity_low_confidence,
        "doctor_incomplete": doctor_incomplete,
        "doctor_parse_or_outlier": doctor_parse_or_outlier,
        "doctor_low_confidence": doctor_low_confidence,
        "recency_missing": recency_missing,
        "recency_stale_or_invalid": recency_stale_or_invalid,
        "recency_problem": recency_problem,
        "coords_missing": coords_missing,
        "geo_far_or_outside": geo_far_or_outside,
        "geo_moderate": geo_moderate,
        "severe_geo": severe_geo,
        "geo_issue": geo_issue,
        "source_missing": source_missing,
        "official_website_missing": official_website_missing,
        "contact_evidence_missing": contact_evidence_missing,
        "phone_or_email_missing": phone_or_email_missing,
        "specialties_missing": specialties_missing,
        "procedure_missing": procedure_missing,
        "equipment_missing": equipment_missing,
        "capability_missing": capability_missing,
        "missing_service_claim_fields": missing_service_claim_fields,
        "low_join_confidence": low_join_confidence,
        "fuzzy_or_fallback_join": fuzzy_or_fallback_join,
        "missing_health_district": missing_health_district,
        "join_issue": join_issue,
        "pincode_missing": pincode_missing,
        "pincode_ambiguous": pincode_ambiguous,
        "pin_issue": pin_issue,
        "high_impact_claim": high_impact_claim,
        "high_impact_claim_needs_review": high_impact_claim_needs_review,
        "needs_human_review": needs_human_review,
        "contradicted": contradicted,
        "outlier_or_conflict": outlier_or_conflict,
        "critical_missing_high": critical_missing_high,
        "critical_supply_gap": critical_supply_gap,
        "low_risk": low_risk,
        "high_impact_claim_count": high_impact_claim_count,
    }


def build_remediation_summary(df: pd.DataFrame, masks: dict[str, pd.Series]) -> pd.DataFrame:
    denominator = len(df)
    rows: list[dict[str, object]] = []
    add = lambda **kwargs: add_summary_row(rows, denominator=denominator, **kwargs)

    add(
        domain="capacity",
        issue="capacity_missing_unparseable_or_estimated",
        mask=masks["capacity_incomplete"],
        remediation_action="keep_estimate_with_interval",
        severity="medium",
        note="Use capacity_estimate and p10-p90 interval for planning; raw missing remains unknown.",
        source_columns=["capacity_status", "capacity_is_estimated", "capacity_estimate_interval_low", "capacity_estimate_interval_high"],
    )
    add(
        domain="capacity",
        issue="capacity_unparseable_or_extreme_outlier",
        mask=masks["capacity_parse_or_outlier"],
        remediation_action="claims_verification",
        severity="high",
        note="Do not use the parsed capacity claim until source evidence is checked.",
        source_columns=["capacity_status", "capacity_num", "capacity_num_extreme_outlier"],
    )
    add(
        domain="capacity",
        issue="capacity_low_confidence_estimate",
        mask=masks["capacity_low_confidence"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Estimate is available but peer cohort is thin or low confidence.",
        source_columns=["capacity_confidence", "capacity_estimate_sample_n", "capacity_estimate_source"],
    )
    add(
        domain="doctors",
        issue="doctor_count_missing_unparseable_or_estimated",
        mask=masks["doctor_incomplete"],
        remediation_action="keep_estimate_with_interval",
        severity="medium",
        note="Use doctor_count_estimate and p10-p90 interval for planning; raw missing remains unknown.",
        source_columns=["doctor_count_status", "doctor_count_is_estimated", "doctor_count_estimate_interval_low", "doctor_count_estimate_interval_high"],
    )
    add(
        domain="doctors",
        issue="doctor_count_unparseable_or_extreme_outlier",
        mask=masks["doctor_parse_or_outlier"],
        remediation_action="claims_verification",
        severity="high",
        note="Do not use the parsed doctor-count claim until source evidence is checked.",
        source_columns=["doctor_count_status", "number_doctors_num", "number_doctors_num_extreme_outlier"],
    )
    add(
        domain="doctors",
        issue="doctor_count_low_confidence_estimate",
        mask=masks["doctor_low_confidence"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Estimate is available but peer cohort is thin or low confidence.",
        source_columns=["doctor_count_confidence", "doctor_count_estimate_sample_n", "doctor_count_estimate_source"],
    )
    add(
        domain="recency",
        issue="source_recency_missing",
        mask=masks["recency_missing"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Missing recency means the currentness of the source is unknown.",
        source_columns=["recency_status", "recency_of_page_update", "recency_page_update_date"],
    )
    add(
        domain="recency",
        issue="source_recency_stale_or_invalid",
        mask=masks["recency_stale_or_invalid"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Stale, invalid, or future recency values need source refresh before high-stakes use.",
        source_columns=["recency_status", "recency_of_page_update", "recency_page_update_date"],
    )
    add(
        domain="coordinates",
        issue="coordinates_missing",
        mask=masks["coords_missing"],
        remediation_action="geocode",
        severity="high",
        note="Missing coordinates require local address geocoding before map or district use.",
        source_columns=["facility_latitude", "facility_longitude", "geo_quality"],
    )
    add(
        domain="coordinates",
        issue="coordinates_outside_india_or_far_from_pincode",
        mask=masks["geo_far_or_outside"],
        remediation_action="geocode",
        severity="high",
        note="Coordinate conflicts should be resolved before the row informs location-sensitive decisions.",
        source_columns=["facility_latitude", "facility_longitude", "geo_quality", "geo_distance_km_to_pincode_centroid"],
    )
    add(
        domain="coordinates",
        issue="coordinates_moderate_distance_from_pincode",
        mask=masks["geo_moderate"],
        remediation_action="geocode",
        severity="medium",
        note="Moderate distance is not failure, but it is a precision-review candidate.",
        source_columns=["geo_quality", "geo_distance_km_to_pincode_centroid"],
    )
    add(
        domain="contact_evidence",
        issue="contact_evidence_missing_or_unknown",
        mask=masks["contact_evidence_missing"],
        remediation_action="phone_email_reachability_review",
        severity="medium",
        note="Missing contact evidence means reachability is unknown, not unreachable.",
        source_columns=["has_contact_evidence", "officialPhone", "phone_numbers", "email"],
    )
    add(
        domain="contact_evidence",
        issue="phone_or_email_field_missing",
        mask=masks["phone_or_email_missing"],
        remediation_action="phone_email_reachability_review",
        severity="low",
        note="At least one direct phone/email channel is blank and should not be treated as unreachable.",
        source_columns=["officialPhone", "phone_numbers", "email"],
    )
    add(
        domain="source_urls",
        issue="source_urls_missing_or_unknown",
        mask=masks["source_missing"],
        remediation_action="registry_source_enrichment",
        severity="high",
        note="A missing source URL blocks claim traceability.",
        source_columns=["has_source_urls", "source_urls"],
    )
    add(
        domain="source_urls",
        issue="official_website_missing_or_unknown",
        mask=masks["official_website_missing"],
        remediation_action="registry_source_enrichment",
        severity="low",
        note="The facility may still exist; absence of an official website is only a source gap.",
        source_columns=["officialWebsite", "websites"],
    )
    add(
        domain="specialties",
        issue="specialties_missing_or_unknown",
        mask=masks["specialties_missing"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Missing specialties are absent evidence, not absence of specialties.",
        source_columns=["specialties_status", "specialties_item_count", "has_specialties"],
    )
    add(
        domain="procedures",
        issue="procedures_missing_or_unknown",
        mask=masks["procedure_missing"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Missing procedures are absent evidence, not absence of procedures.",
        source_columns=["procedure_status", "procedure_item_count", "has_procedure"],
    )
    add(
        domain="equipment",
        issue="equipment_missing_or_unknown",
        mask=masks["equipment_missing"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Missing equipment is absent evidence, not absence of equipment.",
        source_columns=["equipment_status", "equipment_item_count", "has_equipment"],
    )
    add(
        domain="capabilities",
        issue="capabilities_missing_or_unknown",
        mask=masks["capability_missing"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Missing capabilities are absent evidence, not absence of capabilities.",
        source_columns=["capability_status", "capability_item_count", "has_capability"],
    )
    add(
        domain="claims",
        issue="high_impact_claims_need_human_review",
        mask=masks["high_impact_claim_needs_review"],
        remediation_action="claims_verification",
        severity="high",
        note="Maternity, emergency, diagnostic, or NCD claims need corroboration when evidence is weak or conflicting.",
        source_columns=HIGH_IMPACT_CLAIM_COLUMNS + ["needs_human_review", "claim_text", "source_urls"],
    )
    add(
        domain="district_join_confidence",
        issue="join_confidence_low_or_unknown",
        mask=masks["low_join_confidence"],
        remediation_action="registry_source_enrichment",
        severity="high",
        note="Low or unknown join confidence makes district-level need context uncertain.",
        source_columns=["join_confidence", "join_strategy", "join_uncertainty_reason"],
    )
    add(
        domain="district_join_confidence",
        issue="fuzzy_fallback_or_unjoined_district",
        mask=masks["fuzzy_or_fallback_join"],
        remediation_action="registry_source_enrichment",
        severity="high",
        note="Fallback, fuzzy, or unjoined district mappings should be resolved before district decisions.",
        source_columns=["join_strategy", "join_match_score", "join_uncertainty_reason"],
    )
    add(
        domain="district_join_confidence",
        issue="health_district_missing",
        mask=masks["missing_health_district"],
        remediation_action="registry_source_enrichment",
        severity="high",
        note="Missing joined district/state leaves health context unknown.",
        source_columns=["district_name", "state_ut", "join_strategy"],
    )
    add(
        domain="pin_ambiguity",
        issue="pincode_missing_or_unparseable",
        mask=masks["pincode_missing"],
        remediation_action="registry_source_enrichment",
        severity="high",
        note="No valid PIN means the admin bridge is unknown.",
        source_columns=["address_zipOrPostcode", "pincode_extracted"],
    )
    add(
        domain="pin_ambiguity",
        issue="pincode_maps_to_multiple_admin_areas",
        mask=masks["pincode_ambiguous"],
        remediation_action="registry_source_enrichment",
        severity="medium",
        note="Ambiguous PINs need district/state corroboration; do not force one district as truth.",
        source_columns=["pincode_is_ambiguous", "pincode_region_is_ambiguous", "pincode_n_districts", "pincode_n_states"],
    )
    add(
        domain="overall",
        issue="no_action_low_risk_rows",
        mask=masks["low_risk"],
        remediation_action="no_action_low_risk",
        severity="none",
        note="Rows have observed critical fields, plausible geo, source/contact evidence, and no review/conflict flag.",
        source_columns=["needs_human_review", "geo_quality", "join_confidence", "has_source_urls", "has_contact_evidence"],
    )

    order = {action: i for i, action in enumerate(ACTION_ORDER)}
    out = pd.DataFrame(rows)
    out["action_sort"] = out["remediation_action"].map(order).fillna(99)
    out["severity_sort"] = out["severity"].map({"high": 0, "medium": 1, "low": 2, "none": 3}).fillna(9)
    out = out.sort_values(["severity_sort", "action_sort", "rows", "data_domain", "issue"], ascending=[True, True, False, True, True])
    return out.drop(columns=["action_sort", "severity_sort"]).reset_index(drop=True)


def row_action_lists(df: pd.DataFrame, masks: dict[str, pd.Series]) -> tuple[list[list[str]], list[list[str]]]:
    action_lists: list[list[str]] = []
    reason_lists: list[list[str]] = []

    medical_priority = pd.to_numeric(df["medical_desert_priority_score"], errors="coerce")
    high_medical_threshold = medical_priority.quantile(0.75)

    for idx, row in df.iterrows():
        actions: list[str] = []
        reasons: list[str] = []

        if bool(masks["severe_geo"].loc[idx]) or bool(masks["geo_moderate"].loc[idx]):
            actions.append("geocode")
            if bool(masks["coords_missing"].loc[idx]):
                reasons.append("missing_coordinates")
            elif bool(masks["geo_far_or_outside"].loc[idx]):
                reasons.append("severe_geo_issue")
            else:
                reasons.append("moderate_geo_precision_issue")

        if bool(masks["outlier_or_conflict"].loc[idx]) or bool(masks["high_impact_claim_needs_review"].loc[idx]):
            actions.append("claims_verification")
            if bool(masks["outlier_or_conflict"].loc[idx]):
                reasons.append("conflicting_evidence_or_outlier")
            if bool(masks["high_impact_claim_needs_review"].loc[idx]):
                reasons.append("high_impact_claims_need_review")

        if (
            bool(masks["source_missing"].loc[idx])
            or bool(masks["official_website_missing"].loc[idx])
            or bool(masks["recency_problem"].loc[idx])
            or bool(masks["capacity_low_confidence"].loc[idx])
            or bool(masks["doctor_low_confidence"].loc[idx])
            or bool(masks["missing_service_claim_fields"].loc[idx])
            or bool(masks["join_issue"].loc[idx])
            or bool(masks["pin_issue"].loc[idx])
        ):
            actions.append("registry_source_enrichment")
            if bool(masks["source_missing"].loc[idx]):
                reasons.append("missing_source_urls")
            if bool(masks["recency_problem"].loc[idx]):
                reasons.append("missing_stale_or_invalid_recency")
            if bool(masks["missing_service_claim_fields"].loc[idx]):
                reasons.append("missing_specialty_procedure_equipment_or_capability_evidence")
            if bool(masks["join_issue"].loc[idx]):
                reasons.append("low_confidence_or_unjoined_district")
            if bool(masks["pin_issue"].loc[idx]):
                reasons.append("pin_missing_or_ambiguous")
            if bool(masks["capacity_low_confidence"].loc[idx]) or bool(masks["doctor_low_confidence"].loc[idx]):
                reasons.append("low_confidence_peer_estimate")

        if bool(masks["contact_evidence_missing"].loc[idx]) or bool(masks["phone_or_email_missing"].loc[idx]):
            actions.append("phone_email_reachability_review")
            reasons.append("contact_evidence_missing_or_incomplete")

        if bool(masks["capacity_incomplete"].loc[idx]) or bool(masks["doctor_incomplete"].loc[idx]):
            actions.append("keep_estimate_with_interval")
            if bool(masks["capacity_incomplete"].loc[idx]):
                reasons.append("capacity_missing_or_estimated")
            if bool(masks["doctor_incomplete"].loc[idx]):
                reasons.append("doctor_count_missing_or_estimated")

        if bool(masks["needs_human_review"].loc[idx]):
            reasons.append("needs_human_review")
        if bool(masks["critical_missing_high"].loc[idx]):
            reasons.append("semantic_missing_critical_count_ge_3")
        if pd.notna(medical_priority.loc[idx]) and medical_priority.loc[idx] >= high_medical_threshold:
            reasons.append("high_medical_desert_priority")
        if bool(masks["high_impact_claim"].loc[idx]):
            labels = high_impact_labels(row)
            if labels:
                reasons.append("high_impact_claims:" + ",".join(labels))

        deduped_actions = [action for action in ACTION_ORDER if action in set(actions) and action != "no_action_low_risk"]
        if not deduped_actions:
            deduped_actions = ["no_action_low_risk"]
        deduped_reasons = list(dict.fromkeys(reasons))
        if not deduped_reasons:
            deduped_reasons = ["low_risk_no_missing_data_action"]

        action_lists.append(deduped_actions)
        reason_lists.append(deduped_reasons)

    return action_lists, reason_lists


def high_impact_labels(row: pd.Series) -> list[str]:
    mapping = {
        "has_maternity_care_signal": "maternity",
        "has_emergency_care_signal": "emergency",
        "has_diagnostic_signal": "diagnostic",
        "has_ncd_care_signal": "ncd",
    }
    labels: list[str] = []
    for col, label in mapping.items():
        value = row.get(col, pd.NA)
        if bool(pd.Series([value]).pipe(nullable_bool).eq(True).fillna(False).iloc[0]):
            labels.append(label)
    return labels


def score_seed_candidates(df: pd.DataFrame, masks: dict[str, pd.Series]) -> pd.DataFrame:
    out = df.copy()
    actions, reasons = row_action_lists(df, masks)
    out["remediation_actions"] = [json.dumps(values) for values in actions]
    out["remediation_reasons"] = [json.dumps(values) for values in reasons]
    out["primary_remediation_action"] = [values[0] for values in actions]
    out["primary_remediation_action_label"] = out["primary_remediation_action"].map(ACTION_LABELS)

    medical_priority = pd.to_numeric(out["medical_desert_priority_score"], errors="coerce")
    medical_rank = medical_priority.rank(pct=True, method="average")
    out["medical_desert_priority_percentile"] = medical_rank.round(6)
    out["medical_desert_priority_missing"] = medical_priority.isna()
    medical_component = medical_rank.fillna(0.50)

    critical_count = pd.to_numeric(out["semantic_missing_critical_count"], errors="coerce")
    critical_component = (critical_count.fillna(0) / 5).clip(0, 1)

    join_confidence = pd.to_numeric(out["join_confidence"], errors="coerce")
    join_component = (1 - join_confidence).clip(0, 1).fillna(1)

    evidence_gap_component = (
        masks["source_missing"].astype(float) + masks["contact_evidence_missing"].astype(float)
    ).clip(0, 1)

    out["geo_risk_component"] = np.select(
        [
            masks["geo_far_or_outside"],
            masks["coords_missing"],
            masks["geo_moderate"],
        ],
        [1.00, 0.95, 0.45],
        default=0.00,
    )
    out["missing_critical_component"] = critical_component.round(6)
    out["conflict_component"] = masks["outlier_or_conflict"].astype(float)
    out["needs_review_component"] = masks["needs_human_review"].astype(float)
    out["high_impact_claim_component"] = (
        pd.to_numeric(masks["high_impact_claim_count"], errors="coerce").fillna(0).clip(0, 4) / 4
    )
    out["join_risk_component"] = join_component.round(6)
    out["source_contact_gap_component"] = evidence_gap_component.round(6)

    out["seed_selection_score"] = (
        0.24 * medical_component
        + 0.16 * out["needs_review_component"]
        + 0.16 * out["geo_risk_component"]
        + 0.16 * critical_component
        + 0.12 * out["conflict_component"]
        + 0.10 * out["high_impact_claim_component"]
        + 0.04 * join_component
        + 0.02 * evidence_gap_component
    ).round(6)

    out["high_impact_claim_labels"] = [json.dumps(high_impact_labels(row)) for _, row in out.iterrows()]
    out["source_url_count"] = out["source_urls"].map(list_value_count)
    out["first_source_url"] = out["source_urls"].map(first_list_value)
    out["claim_text_excerpt"] = out["claim_text"].map(compact_text)
    out["verification_task"] = out.apply(verification_task, axis=1)

    return out


def verification_task(row: pd.Series) -> str:
    action = row["primary_remediation_action"]
    if action == "geocode":
        return "Resolve address, coordinate, PIN, and district alignment before location-sensitive use."
    if action == "claims_verification":
        return "Corroborate high-impact service, capacity, doctor, or conflict claim from source evidence."
    if action == "registry_source_enrichment":
        return "Find authoritative or independent source evidence for missing identity, district, recency, or service fields."
    if action == "phone_email_reachability_review":
        return "Check whether listed phone/email evidence exists and is reachable; blank means unknown."
    if action == "keep_estimate_with_interval":
        return "Keep estimate visible with interval and avoid treating the estimated field as observed truth."
    return "No immediate remediation action; keep row in routine monitoring."


def build_seed_queue(scored: pd.DataFrame, queue_size: int) -> pd.DataFrame:
    queue_size = min(MAX_QUEUE_SIZE, max(MIN_QUEUE_SIZE, queue_size))
    candidates = scored[scored["primary_remediation_action"].ne("no_action_low_risk")].copy()
    candidates = candidates.sort_values(
        [
            "seed_selection_score",
            "medical_desert_priority_score",
            "needs_review_component",
            "geo_risk_component",
            "missing_critical_component",
            "unique_id",
        ],
        ascending=[False, False, False, False, False, True],
        na_position="last",
    )
    out = candidates.head(queue_size).copy()
    out.insert(0, "seed_rank", range(1, len(out) + 1))

    cols = [
        "seed_rank",
        "seed_selection_score",
        "primary_remediation_action",
        "primary_remediation_action_label",
        "remediation_actions",
        "remediation_reasons",
        "verification_task",
        "unique_id",
        "facility_name",
        "facilityTypeId",
        "operatorTypeId",
        "address_city",
        "address_stateOrRegion",
        "district_name",
        "state_ut",
        "address_zipOrPostcode",
        "pincode_extracted",
        "pincode_primary_district",
        "pincode_primary_state",
        "pincode_is_ambiguous",
        "facility_latitude",
        "facility_longitude",
        "geo_quality",
        "geo_distance_km_to_pincode_centroid",
        "join_strategy",
        "join_confidence",
        "join_match_score",
        "join_uncertainty_reason",
        "medical_desert_priority_score",
        "medical_desert_priority_percentile",
        "medical_desert_priority_missing",
        "health_need_score",
        "data_readiness_score",
        "semantic_data_quality_score",
        "supply_data_confidence_score",
        "semantic_missing_critical_count",
        "critical_supply_gap_flag",
        "needs_human_review",
        "trustworthy_supply_signal",
        "contradicted_or_geo_invalid_signal",
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
        "recency_status",
        "recency_page_update_date",
        "has_source_urls",
        "source_url_count",
        "first_source_url",
        "has_contact_evidence",
        "officialPhone",
        "phone_numbers",
        "email",
        "specialties_status",
        "procedure_status",
        "equipment_status",
        "capability_status",
        "claim_field_count",
        "high_impact_claim_labels",
        "claim_text_excerpt",
        "geo_risk_component",
        "missing_critical_component",
        "conflict_component",
        "needs_review_component",
        "high_impact_claim_component",
        "join_risk_component",
        "source_contact_gap_component",
    ]
    return out[[col for col in cols if col in out.columns]].reset_index(drop=True)


def counts_from_json_lists(series: pd.Series) -> dict[str, int]:
    counts = {action: 0 for action in ACTION_ORDER}
    for raw in series:
        try:
            values = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(values, list):
            continue
        for value in values:
            if value in counts:
                counts[value] += 1
            else:
                counts[value] = counts.get(value, 0) + 1
    return {key: value for key, value in counts.items() if value}


def top_summary_rows(summary: pd.DataFrame, n: int = 12) -> list[dict[str, object]]:
    cols = ["data_domain", "issue", "rows", "pct", "remediation_action"]
    high = summary[summary["severity"].isin(["high", "medium"])].sort_values(
        ["rows", "data_domain", "issue"], ascending=[False, True, True]
    )
    records: list[dict[str, object]] = []
    for record in high[cols].head(n).to_dict(orient="records"):
        records.append(
            {
                "data_domain": str(record["data_domain"]),
                "issue": str(record["issue"]),
                "rows": int(record["rows"]),
                "pct": float(record["pct"]),
                "remediation_action": str(record["remediation_action"]),
            }
        )
    return records


def build_json_summary(
    df: pd.DataFrame,
    remediation_summary: pd.DataFrame,
    scored: pd.DataFrame,
    seed_queue: pd.DataFrame,
) -> dict[str, object]:
    primary_counts = scored["primary_remediation_action"].value_counts().to_dict()
    seed_primary_counts = seed_queue["primary_remediation_action"].value_counts().to_dict()
    return {
        "script": "scripts/build_missing_data_and_seed_queue.py",
        "source_file": str(FACILITY_PATH.relative_to(ROOT)),
        "created_outputs": {
            "remediation_summary": str(REMEDIATION_SUMMARY_PATH.relative_to(ROOT)),
            "human_verification_seed_queue": str(SEED_QUEUE_PATH.relative_to(ROOT)),
            "json_summary": str(SUMMARY_JSON_PATH.relative_to(ROOT)),
            "workflow_doc": str(WORKFLOW_DOC_PATH.relative_to(ROOT)),
        },
        "row_counts": {
            "facility_rows_input": int(len(df)),
            "remediation_summary_rows": int(len(remediation_summary)),
            "scored_facility_rows": int(len(scored)),
            "human_verification_seed_rows": int(len(seed_queue)),
        },
        "top_remediation_counts_primary": {str(k): int(v) for k, v in primary_counts.items()},
        "assigned_remediation_action_counts": counts_from_json_lists(scored["remediation_actions"]),
        "seed_queue_primary_action_counts": {str(k): int(v) for k, v in seed_primary_counts.items()},
        "seed_queue_assigned_action_counts": counts_from_json_lists(seed_queue["remediation_actions"]),
        "top_missingness_summary_rows": top_summary_rows(remediation_summary),
        "selection_policy": {
            "queue_size_default": QUEUE_SIZE_DEFAULT,
            "queue_size_bounds": [MIN_QUEUE_SIZE, MAX_QUEUE_SIZE],
            "score_components": {
                "medical_desert_priority_percentile": 0.24,
                "needs_human_review": 0.16,
                "geo_risk": 0.16,
                "semantic_missing_critical_count": 0.16,
                "conflicting_evidence": 0.12,
                "high_impact_claims": 0.10,
                "district_join_risk": 0.04,
                "source_or_contact_gap": 0.02,
            },
            "tie_breakers": [
                "seed_selection_score desc",
                "medical_desert_priority_score desc",
                "needs_review_component desc",
                "geo_risk_component desc",
                "missing_critical_component desc",
                "unique_id asc",
            ],
            "missing_policy": "Missing/incomplete values are unknown. They are never converted to false, zero, or proof of absence.",
            "no_network_api_or_llm_calls": True,
        },
    }


def markdown_table(df: pd.DataFrame, columns: list[str]) -> str:
    if df.empty:
        return "_No rows available._"
    clean = df[columns].copy()
    for col in clean.columns:
        clean[col] = clean[col].map(lambda value: "" if pd.isna(value) else str(value).replace("|", "\\|"))
    header = "| " + " | ".join(clean.columns) + " |"
    separator = "| " + " | ".join(["---"] * len(clean.columns)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in clean.to_numpy(dtype=str)]
    return "\n".join([header, separator, *body])


def write_workflow_doc(remediation_summary: pd.DataFrame, summary: dict[str, object], path: Path) -> None:
    action_counts = pd.DataFrame(
        [
            {"remediation_action": key, "rows": value}
            for key, value in summary["top_remediation_counts_primary"].items()
        ]
    )
    if not action_counts.empty:
        action_counts["remediation_action_label"] = action_counts["remediation_action"].map(ACTION_LABELS)
        action_counts = action_counts.sort_values(["rows", "remediation_action"], ascending=[False, True])

    seed_counts = pd.DataFrame(
        [
            {"primary_remediation_action": key, "seed_rows": value}
            for key, value in summary["seed_queue_primary_action_counts"].items()
        ]
    )
    if not seed_counts.empty:
        seed_counts["primary_remediation_action_label"] = seed_counts["primary_remediation_action"].map(ACTION_LABELS)
        seed_counts = seed_counts.sort_values(["seed_rows", "primary_remediation_action"], ascending=[False, True])

    high_summary = remediation_summary[remediation_summary["severity"].isin(["high", "medium"])].sort_values(
        ["rows", "data_domain", "issue"], ascending=[False, True, True]
    )

    text = f"""# Missing Data and Human Seed Workflow

This workflow is generated by `scripts/build_missing_data_and_seed_queue.py`.

## Purpose

The cleaned facility table is evidence-bearing planning data, not a verified
facility registry. Missing values are handled as unknown, never as false, zero,
or proof that a facility lacks a service.

The script reads `output/data/facility_health_cleaned.csv` and writes:

- `output/data/missing_data_remediation_summary.csv`
- `output/data/human_verification_seed_queue.csv`
- `output/data/missing_data_seed_summary.json`
- `docs/MISSING_DATA_AND_HUMAN_SEED_WORKFLOW.md`

The script makes no web calls, API calls, or LLM calls.

## Remediation Categories

| Category | Use |
| --- | --- |
| `geocode` | Missing, impossible, far-from-PIN, or precision-sensitive coordinates. |
| `registry_source_enrichment` | Missing source URLs, stale recency, weak district join, PIN ambiguity, or missing service evidence. |
| `phone_email_reachability_review` | Missing or incomplete phone/email/contact evidence. |
| `claims_verification` | High-impact medical claims, parsed outliers, or conflicting evidence. |
| `keep_estimate_with_interval` | Capacity or doctor counts are missing/incomplete but planning estimates and intervals exist. |
| `no_action_low_risk` | Observed critical fields, plausible geography, source/contact evidence, and no conflict/review flag. |

## Current Row Counts

| Metric | Rows |
| --- | --- |
| Facility rows input | {summary["row_counts"]["facility_rows_input"]} |
| Remediation summary rows | {summary["row_counts"]["remediation_summary_rows"]} |
| Human verification seed rows | {summary["row_counts"]["human_verification_seed_rows"]} |

## Primary Remediation Counts

{markdown_table(action_counts, ["remediation_action", "remediation_action_label", "rows"]) if not action_counts.empty else "_No rows available._"}

## Seed Queue Primary Counts

{markdown_table(seed_counts, ["primary_remediation_action", "primary_remediation_action_label", "seed_rows"]) if not seed_counts.empty else "_No rows available._"}

## Largest Missing Or Incomplete Signals

{markdown_table(high_summary.head(15), ["data_domain", "issue", "rows", "pct", "remediation_action", "severity"])}

## Seed Selection Policy

The seed queue is capped to 50-200 rows and defaults to 150 rows. Rows with
`no_action_low_risk` as the primary action are excluded from the seed queue.

The deterministic score is:

```text
0.24 * medical_desert_priority_percentile
+ 0.16 * needs_human_review
+ 0.16 * geo_risk
+ 0.16 * semantic_missing_critical_count_component
+ 0.12 * conflicting_evidence
+ 0.10 * high_impact_claims
+ 0.04 * district_join_risk
+ 0.02 * source_or_contact_gap
```

Missing `medical_desert_priority_score` gets a neutral rank component for queue
ordering only; the original score remains blank and unknown in the output.

Tie-breakers are deterministic: score descending, medical desert priority
descending, review flag descending, geo risk descending, missing-critical
component descending, then `unique_id` ascending.

## Human Verification Lane

Use `human_verification_seed_queue.csv` as the small review lane. Reviewers
should update downstream labels only after they can cite stronger evidence.
The queue includes the primary action, all applicable actions, reason codes,
first source URL, contact fields, interval fields, and a claim-text excerpt.

Verification should preserve these rules:

- Blank contact fields mean reachability is unknown, not unreachable.
- Blank specialties, procedures, equipment, or capabilities mean absent
  evidence, not absent services.
- Estimated capacity and doctor counts can support planning only with their
  intervals visible.
- District joins and PIN mappings remain uncertain when join confidence is low,
  the PIN is missing, or the PIN maps to multiple admin areas.
- High-impact maternity, emergency, diagnostic, and NCD claims need corroborated
  source evidence before operational use.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    queue_size = min(MAX_QUEUE_SIZE, max(MIN_QUEUE_SIZE, args.queue_size))

    global DATA_DIR, DOCS_DIR, FACILITY_PATH, REMEDIATION_SUMMARY_PATH, SEED_QUEUE_PATH, SUMMARY_JSON_PATH, WORKFLOW_DOC_PATH
    DATA_DIR = args.data_dir
    DOCS_DIR = args.docs_dir
    FACILITY_PATH = args.input
    REMEDIATION_SUMMARY_PATH = DATA_DIR / REMEDIATION_SUMMARY_PATH.name
    SEED_QUEUE_PATH = DATA_DIR / SEED_QUEUE_PATH.name
    SUMMARY_JSON_PATH = DATA_DIR / SUMMARY_JSON_PATH.name
    WORKFLOW_DOC_PATH = DOCS_DIR / WORKFLOW_DOC_PATH.name

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    facilities = load_facilities(FACILITY_PATH)
    masks = build_issue_masks(facilities)
    remediation_summary = build_remediation_summary(facilities, masks)
    scored = score_seed_candidates(facilities, masks)
    seed_queue = build_seed_queue(scored, queue_size)
    summary = build_json_summary(facilities, remediation_summary, scored, seed_queue)

    remediation_summary.to_csv(REMEDIATION_SUMMARY_PATH, index=False)
    seed_queue.to_csv(SEED_QUEUE_PATH, index=False)
    SUMMARY_JSON_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_workflow_doc(remediation_summary, summary, WORKFLOW_DOC_PATH)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
