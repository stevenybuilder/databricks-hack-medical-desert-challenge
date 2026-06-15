"""Data loading and H3 hex-binning for the map.

Backend logic (trust signals, geo quality, need/gap scores, service signals)
is already computed in the project's cleaned tables; this module only loads,
filters, and aggregates for display.
"""
from __future__ import annotations

import json
import os

import h3
import numpy as np
import pandas as pd

from . import config

# Unity Catalog — canonical cleaned tables (teammate's, in workspace.default).
UC_FACILITY_TABLE = "workspace.default.hackathon_facility_health_cleaned"
UC_DISTRICT_TABLE = "workspace.default.hackathon_district_health_facility_cleaned"

# Columns we actually need for Phase 1 (keep the 49MB read fast).
_USECOLS = [
    "unique_id",
    "source_unique_id_occurrences",
    "source_duplicate_unique_id",
    "facility_name",
    "facilityTypeId",
    "address_line1",
    "address_line2",
    "address_line3",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "pincode_extracted",
    "pincode_is_ambiguous",
    "pincode_region_is_ambiguous",
    "district_name",
    "state_ut",
    "join_strategy",
    "join_uncertainty_reason",
    "facility_latitude",
    "facility_longitude",
    "geo_in_india_bbox",
    "geo_distance_km_to_pincode_centroid",
    "geo_quality",
    "medical_desert_priority_score",
    "health_need_score",
    "join_confidence",
    "join_match_score",
    "data_readiness_score",
    "semantic_data_quality_score",
    "supply_data_confidence_score",
    "capacity_status",
    "capacity_estimate",
    "capacity_display_value",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "capacity_estimate_source",
    "capacity_confidence",
    "capacity_is_estimated",
    "doctor_count_status",
    "doctor_count_estimate",
    "doctor_count_display_value",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
    "doctor_count_estimate_source",
    "doctor_count_confidence",
    "doctor_count_is_estimated",
    "recency_status",
    "description_status",
    "specialties_status",
    "procedure_status",
    "equipment_status",
    "capability_status",
    "semantic_missing_critical_count",
    "trustworthy_supply_signal",
    "needs_human_review",
    "contradicted_or_geo_invalid_signal",
    "has_source_urls",
    "has_contact_evidence",
    "has_maternity_care_signal",
    "has_emergency_care_signal",
    "has_diagnostic_signal",
    "has_ncd_care_signal",
    "capacity_num_extreme_outlier",
    "number_doctors_num_extreme_outlier",
    "source_urls",
    "officialWebsite",
    "officialPhone",
    "email",
    "claim_text",
]


_NUM_COLS = [
    "facility_latitude",
    "facility_longitude",
    "medical_desert_priority_score",
    "health_need_score",
    "geo_distance_km_to_pincode_centroid",
    "join_confidence",
    "join_match_score",
    "data_readiness_score",
    "semantic_data_quality_score",
    "supply_data_confidence_score",
    "source_unique_id_occurrences",
    "capacity_estimate",
    "capacity_display_value",
    "capacity_estimate_interval_low",
    "capacity_estimate_interval_high",
    "doctor_count_estimate",
    "doctor_count_display_value",
    "doctor_count_estimate_interval_low",
    "doctor_count_estimate_interval_high",
    "semantic_missing_critical_count",
]
_BOOL_COLS = ["trustworthy_supply_signal", "needs_human_review",
              "contradicted_or_geo_invalid_signal", "geo_in_india_bbox",
              "source_duplicate_unique_id", "has_source_urls",
              "has_contact_evidence", "capacity_num_extreme_outlier",
              "number_doctors_num_extreme_outlier",
              "capacity_is_estimated", "doctor_count_is_estimated",
              "pincode_is_ambiguous", "pincode_region_is_ambiguous",
              "has_maternity_care_signal", "has_emergency_care_signal",
              "has_diagnostic_signal", "has_ncd_care_signal"]

_WAREHOUSE_FALLBACKS = {
    "capacity_status": "CASE WHEN capacity_num IS NOT NULL AND NOT coalesce(capacity_num_extreme_outlier, false) THEN 'observed_valid' ELSE 'missing_semantic' END",
    "capacity_estimate": "CAST(NULL AS DOUBLE)",
    "capacity_estimate_interval_low": "CAST(NULL AS DOUBLE)",
    "capacity_estimate_interval_high": "CAST(NULL AS DOUBLE)",
    "capacity_estimate_source": "''",
    "capacity_confidence": "CASE WHEN capacity_num IS NOT NULL AND NOT coalesce(capacity_num_extreme_outlier, false) THEN 'observed' ELSE 'low' END",
    "capacity_is_estimated": "capacity_num IS NULL OR coalesce(capacity_num_extreme_outlier, false)",
    "doctor_count_status": "CASE WHEN number_doctors_num IS NOT NULL AND NOT coalesce(number_doctors_num_extreme_outlier, false) THEN 'observed_valid' ELSE 'missing_semantic' END",
    "doctor_count_estimate": "CAST(NULL AS DOUBLE)",
    "doctor_count_estimate_interval_low": "CAST(NULL AS DOUBLE)",
    "doctor_count_estimate_interval_high": "CAST(NULL AS DOUBLE)",
    "doctor_count_estimate_source": "''",
    "doctor_count_confidence": "CASE WHEN number_doctors_num IS NOT NULL AND NOT coalesce(number_doctors_num_extreme_outlier, false) THEN 'observed' ELSE 'low' END",
    "doctor_count_is_estimated": "number_doctors_num IS NULL OR coalesce(number_doctors_num_extreme_outlier, false)",
    "recency_status": "CASE WHEN recency_of_page_update IS NOT NULL AND trim(recency_of_page_update) != '' THEN 'observed_valid' ELSE 'missing_semantic' END",
    "description_status": "CASE WHEN coalesce(has_description, false) THEN 'observed_claim' ELSE 'missing_semantic' END",
    "specialties_status": "CASE WHEN coalesce(has_specialties, false) THEN 'observed_claim' ELSE 'missing_semantic' END",
    "procedure_status": "CASE WHEN coalesce(has_procedure, false) THEN 'observed_claim' ELSE 'missing_semantic' END",
    "equipment_status": "CASE WHEN coalesce(has_equipment, false) THEN 'observed_claim' ELSE 'missing_semantic' END",
    "capability_status": "CASE WHEN coalesce(has_capability, false) THEN 'observed_claim' ELSE 'missing_semantic' END",
    "semantic_missing_critical_count": (
        "CAST((CASE WHEN capacity_num IS NULL OR coalesce(capacity_num_extreme_outlier, false) THEN 1 ELSE 0 END) + "
        "(CASE WHEN number_doctors_num IS NULL OR coalesce(number_doctors_num_extreme_outlier, false) THEN 1 ELSE 0 END) + "
        "(CASE WHEN NOT coalesce(has_equipment, false) THEN 1 ELSE 0 END) + "
        "(CASE WHEN NOT coalesce(has_specialties, false) THEN 1 ELSE 0 END) + "
        "(CASE WHEN NOT coalesce(has_procedure, false) THEN 1 ELSE 0 END) AS INT)"
    ),
    "pincode_extracted": "regexp_extract(coalesce(address_zipOrPostcode, ''), '([1-9][0-9]{5})', 1)",
    "pincode_is_ambiguous": "false",
    "pincode_region_is_ambiguous": "false",
    "join_uncertainty_reason": "''",
    "semantic_data_quality_score": "CAST(NULL AS DOUBLE)",
    "supply_data_confidence_score": "CAST(NULL AS DOUBLE)",
    "capacity_display_value": "CAST(NULL AS DOUBLE)",
    "doctor_count_display_value": "CAST(NULL AS DOUBLE)",
}


def _coerce(df: pd.DataFrame) -> pd.DataFrame:
    for col in _NUM_COLS:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in _BOOL_COLS:
        if col in df:
            df[col] = df[col].astype("boolean").fillna(False).astype(bool)
    return df


def load_facilities() -> pd.DataFrame:
    """Load the cleaned facility table.

    DATA_BACKEND=warehouse reads from Unity Catalog (deployed Databricks App);
    otherwise reads the local cleaned CSV (fast local dev). Same columns either way.
    """
    if os.environ.get("DATA_BACKEND", "csv").lower() == "warehouse":
        return _coerce(_load_from_warehouse())
    df = pd.read_csv(config.facility_table_path(), usecols=_USECOLS, low_memory=False)
    return _coerce(df)


def _load_from_warehouse() -> pd.DataFrame:
    """Query the cleaned facility table from the SQL warehouse.

    In a deployed Databricks App these env vars come from the attached SQL
    warehouse resource. Requires `databricks-sql-connector` (in requirements.txt).
    """
    from databricks import sql  # lazy import; only needed when deployed

    with sql.connect(
        server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
        http_path=os.environ["DATABRICKS_HTTP_PATH"],
        access_token=os.environ.get("DATABRICKS_TOKEN"),
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(f"DESCRIBE TABLE {UC_FACILITY_TABLE}")
            schema = cur.fetchall_arrow().to_pandas()
            available = set(schema["col_name"].astype(str))
            select_exprs = []
            for col in _USECOLS:
                if col in available:
                    select_exprs.append(col)
                elif col in _WAREHOUSE_FALLBACKS:
                    select_exprs.append(f"{_WAREHOUSE_FALLBACKS[col]} AS {col}")
                else:
                    select_exprs.append(f"CAST(NULL AS STRING) AS {col}")
            cols = ", ".join(select_exprs)
            cur.execute(f"SELECT {cols} FROM {UC_FACILITY_TABLE}")
            return cur.fetchall_arrow().to_pandas()


# --- Districts (Phase 2: leaderboard + region detail) ------------------------

# specialty -> (district service-signal column, NFHS condition columns to profile)
SPECIALTY_DISTRICT: dict[str, tuple[str | None, list[str]]] = {
    "All specialties": (None, [
        "institutional_birth_5y_pct", "all_w15_49_who_are_anaemic_pct",
        "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
        "women_age_30_49_years_ever_undergone_a_cervical_screen_pct",
        "hh_member_covered_health_insurance_pct"]),
    "Maternity / OB-GYN": ("maternity_signal_rate", [
        "institutional_birth_5y_pct", "births_attended_by_skilled_hp_5y_10_pct",
        "births_delivered_by_csection_5y_pct", "all_w15_49_who_are_anaemic_pct"]),
    "Emergency / Surgery": ("emergency_signal_rate", [
        "institutional_birth_5y_pct", "hh_member_covered_health_insurance_pct",
        "all_w15_49_who_are_anaemic_pct",
        "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"]),
    "Diagnostics / Imaging": ("diagnostic_signal_rate", [
        "women_age_30_49_years_ever_undergone_a_cervical_screen_pct",
        "women_age_30_49_years_ever_undergone_a_breast_exam_pct",
        "women_age_30_49_years_ever_undergone_an_oral_cancer_exam_pct"]),
    "Chronic disease (NCD)": ("ncd_signal_rate", [
        "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
        "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
        "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
        "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct"]),
}

COND_LABELS = {
    "institutional_birth_5y_pct": "Institutional births",
    "births_attended_by_skilled_hp_5y_10_pct": "Skilled birth attendance",
    "births_delivered_by_csection_5y_pct": "C-section deliveries",
    "all_w15_49_who_are_anaemic_pct": "Women 15-49 anaemic",
    "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct": "Women high BP",
    "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct": "Men high BP",
    "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct": "Women high blood sugar",
    "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct": "Men high blood sugar",
    "women_age_30_49_years_ever_undergone_a_cervical_screen_pct": "Cervical screening",
    "women_age_30_49_years_ever_undergone_a_breast_exam_pct": "Breast exam",
    "women_age_30_49_years_ever_undergone_an_oral_cancer_exam_pct": "Oral cancer exam",
    "hh_member_covered_health_insurance_pct": "Health insurance coverage",
}

# planning_category -> (chip label, recommendation sentence)
PLANNING = {
    "real_desert_candidate": ("🚑 Deploy / build",
        "Genuine unmet need with little trustworthy supply — strongest case to deploy."),
    "phantom_desert_or_verification_gap": ("🔎 Verify first",
        "Looks empty, but the few records are unverified — verify before acting."),
    "supply_record_quality_problem": ("🛠 Fix records",
        "Facilities likely exist but records are broken — fix data before planning."),
    "referral_or_capacity_candidate": ("➡️ Refer (capacity exists)",
        "Trustworthy capacity is present — route patients here."),
    "mixed_or_monitor": ("👁 Monitor",
        "Mixed signals — monitor; no single clear action."),
}


VALIDATION_SOURCES = pd.DataFrame([
    {
        "Tier": "A/B",
        "Source": "Google Maps / Mappls geocoding",
        "Best use": "Address existence, coordinate candidate, place ID, location_type, partial_match",
        "Role in labels": "Source-agreement signal; narrows geo band only when admin geography also agrees",
        "URL": "https://developers.google.com/maps/documentation/geocoding",
    },
    {
        "Tier": "A",
        "Source": "ABDM Health Facility Registry",
        "Best use": "Facility existence, facility type, official identity, location",
        "Role in labels": "Positive match, official ID, location corroboration",
        "URL": "https://facility.abdm.gov.in/",
    },
    {
        "Tier": "A",
        "Source": "PM-JAY empanelled hospitals",
        "Best use": "Hospital existence and empanelled specialty/service signal",
        "Role in labels": "Positive match for active hospital network facilities",
        "URL": "https://hospitals.pmjay.gov.in/Search/",
    },
    {
        "Tier": "A",
        "Source": "India Post PIN directory via data.gov.in",
        "Best use": "PIN-to-district/state bridge, ambiguity counts, centroid checks",
        "Role in labels": "Admin geography validator; never proves facility existence alone",
        "URL": "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month",
    },
    {
        "Tier": "B",
        "Source": "Overture Maps Places",
        "Best use": "Independent POI name, category, coordinates, confidence, contacts",
        "Role in labels": "Independent geo/name corroboration",
        "URL": "https://docs.overturemaps.org/guides/places/",
    },
    {
        "Tier": "B",
        "Source": "OpenStreetMap / Overpass / Healthsites",
        "Best use": "Community-mapped health facilities and coordinates",
        "Role in labels": "Independent open-data corroboration",
        "URL": "https://www.healthsites.io/",
    },
    {
        "Tier": "B",
        "Source": "National Health Portal / data.gov.in health datasets",
        "Best use": "Legacy hospital names, contacts, specialties, public directories",
        "Role in labels": "Corroborating registry; useful but may be stale",
        "URL": "https://data.gov.in/keywords/healthcare",
    },
    {
        "Tier": "C",
        "Source": "geoBoundaries / district boundary files",
        "Best use": "State/district containment, boundary-crossing checks, map joins",
        "Role in labels": "Spatial QA for coordinates and district assignment",
        "URL": "https://www.geoboundaries.org/",
    },
    {
        "Tier": "C",
        "Source": "HMIS / NHSRC district indicators",
        "Best use": "District/block service context and plausibility checks",
        "Role in labels": "Context only; not proof of individual facility claims",
        "URL": "https://nhsrcindia.org/hmis-data-analysis",
    },
    {
        "Tier": "C",
        "Source": "NFHS-5 district fact sheets",
        "Best use": "Need-side health indicators for ranking care gaps",
        "Role in labels": "Need context only; not facility ground truth",
        "URL": "https://dhsprogram.com/publications/publication-OF43-Other-Fact-Sheets.cfm",
    },
    {
        "Tier": "C",
        "Source": "Facility website / source URL / phone or email",
        "Best use": "Current service claims, contact route, human follow-up",
        "Role in labels": "Evidence citation; not enough alone for high-risk claims",
        "URL": "",
    },
])


VERIFICATION_CHECKS = pd.DataFrame([
    {
        "Priority": 1,
        "Question": "Does the facility exist and operate at this location?",
        "Evidence": "HFR/PM-JAY/NHP match, Overture/OSM match, phone confirmation",
        "Why it matters": "Prevents phantom coverage from hiding a real desert",
    },
    {
        "Priority": 2,
        "Question": "Is the district/PIN/coordinate assignment correct?",
        "Evidence": "India Post PIN bridge, distance to PIN centroid, external POI coordinate",
        "Why it matters": "A facility in the wrong district changes the care-gap ranking",
    },
    {
        "Priority": 3,
        "Question": "Is the facility reachable?",
        "Evidence": "Answered phone, working email, current website, reachable source page",
        "Why it matters": "Contact evidence is not the same thing as contact reachability",
    },
    {
        "Priority": 4,
        "Question": "Which critical services are really available?",
        "Evidence": "Official registry specialties, facility staff confirmation, cited website text",
        "Why it matters": "Specialty-specific care gaps depend on service truth, not generic existence",
    },
    {
        "Priority": 5,
        "Question": "Are capacity/equipment/doctor-count claims plausible?",
        "Evidence": "Registry fields, hospital confirmation, outlier checks, source text",
        "Why it matters": "The raw operational fields are sparse and heavy-tailed",
    },
])


GEO_VALIDATION_STEPS = pd.DataFrame([
    {
        "Step": "1. LLM janitor",
        "Tool": "Databricks ai_query or serving-endpoints query",
        "Output": "Structured Indian address JSON: plot/door, landmark, locality, city, state, PIN, geocode query",
        "Decision": "Parser only; never treat model coordinates as truth",
    },
    {
        "Step": "2. Geocoder surveyor",
        "Tool": "Google Maps Geocoding API with components=country:IN",
        "Output": "lat/lon, formatted address, place_id, plus_code, partial_match, location_type",
        "Decision": "Validator; confirms whether the cleaned address exists",
    },
    {
        "Step": "3. India fallback",
        "Tool": "Retry landmark + locality + city; optionally Mappls for India-specific coverage",
        "Output": "fallback lat/lon and provider metadata",
        "Decision": "Use only when first pass is APPROXIMATE/ZERO_RESULTS",
    },
    {
        "Step": "4. H3 smoothing",
        "Tool": "Databricks SQL H3 functions or Python h3",
        "Output": "H3 neighborhood cell at resolution 9/10",
        "Decision": "Compare neighborhoods, not exact points, when geocoder precision is fuzzy",
    },
    {
        "Step": "5. Review queue",
        "Tool": "Uncertainty tab + persisted Delta outcomes",
        "Output": "keep, corrected_geo, approximate_review, not_found, provider_conflict",
        "Decision": "Manual review only for ambiguous API outcomes",
    },
])


GEO_QUALITY_RULES = pd.DataFrame([
    {
        "Geocoder metadata": "ROOFTOP",
        "India interpretation": "Exact building/premise match",
        "Action": "Accept as high-quality correction",
    },
    {
        "Geocoder metadata": "RANGE_INTERPOLATED",
        "India interpretation": "Address approximated along a road segment",
        "Action": "Accept unless it crosses district/PIN boundary",
    },
    {
        "Geocoder metadata": "GEOMETRIC_CENTER + premise/sublocality",
        "India interpretation": "Often a colony/nagar/locality center",
        "Action": "Accept for neighborhood/H3 analysis; flag if facility-level precision matters",
    },
    {
        "Geocoder metadata": "APPROXIMATE",
        "India interpretation": "Likely city/PIN centroid; street or facility was not resolved",
        "Action": "Retry with landmark/locality query, then send to review",
    },
    {
        "Geocoder metadata": "ZERO_RESULTS / provider conflict",
        "India interpretation": "Address not found or sources disagree",
        "Action": "Search HFR/PM-JAY/Mappls and send to manual review",
    },
])


MISSING_DATA_METHODS = pd.DataFrame([
    {
        "Gap": "Missing or suspicious coordinates",
        "Current signal": "`geo_quality`, PIN-centroid distance, India bbox, contradiction flag",
        "Treatment": "LLM parses address; Google/Mappls validates; H3 used for neighborhood-level uncertainty",
        "Not allowed": "Do not ask an LLM for coordinates or treat approximate geocodes as facility-level truth",
    },
    {
        "Gap": "Missing facility identity/existence evidence",
        "Current signal": "No source URL, weak digital footprint, duplicate/merged names",
        "Treatment": "Match to HFR, PM-JAY, NHP/data.gov, Overture, OSM/Healthsites; keep unmatched as unknown",
        "Not allowed": "Do not collapse unmatched into fake or closed",
    },
    {
        "Gap": "Incomplete district/PIN join",
        "Current signal": "`join_strategy`, `join_confidence`, PIN ambiguity, fuzzy match score",
        "Treatment": "Normalize aliases, use same-state fuzzy matching, flag ambiguous PINs and weak joins",
        "Not allowed": "Do not use district-level NFHS facts as facility facts",
    },
    {
        "Gap": "Missing capacity or doctor count",
        "Current signal": "`capacity_status`, `doctor_count_status`, outlier flags",
        "Treatment": "Estimate from facility-type/operator/state peer groups with p10-p90 intervals and confidence labels",
        "Not allowed": "Do not rank facility capacity without showing estimate/source/interval",
    },
    {
        "Gap": "Missing equipment/procedure/specialty claims",
        "Current signal": "Semantic status fields for description, specialties, procedure, equipment, capability",
        "Treatment": "Treat as absent evidence, enrich from registries/source pages, route high-impact rows to review",
        "Not allowed": "Do not interpret blank as no service",
    },
    {
        "Gap": "Missing or stale contact/reachability",
        "Current signal": "Phone/email/site/source presence and recency status",
        "Treatment": "Use source URL, official site, registry contact, and optional call/email outcome as evidence",
        "Not allowed": "Do not equate a phone field with reachable facility",
    },
])


def validation_sources() -> pd.DataFrame:
    return VALIDATION_SOURCES.copy()


def verification_checks() -> pd.DataFrame:
    return VERIFICATION_CHECKS.copy()


def geo_validation_steps() -> pd.DataFrame:
    return GEO_VALIDATION_STEPS.copy()


def geo_quality_rules() -> pd.DataFrame:
    return GEO_QUALITY_RULES.copy()


def missing_data_methods() -> pd.DataFrame:
    return MISSING_DATA_METHODS.copy()


def golden_seed_report() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load the generated golden facility seed report for the app report card."""
    path = config.golden_facility_seed_report_path()
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame(), {}

    report = json.loads(path.read_text(encoding="utf-8"))
    counts = report.get("row_counts", {})
    tiers = report.get("label_tier_counts", {})
    posture = report.get("trust_posture_counts", {})

    summary_rows = [
        {"Metric": "Cleaned facility rows", "Value": counts.get("cleaned_facilities_input", 0)},
        {"Metric": "Golden seed rows", "Value": counts.get("training_set", 0)},
        {"Metric": "Source/context match rows", "Value": counts.get("source_matches", 0)},
        {"Metric": "Prediction feature rows", "Value": counts.get("features", 0)},
        {"Metric": "Rule-baseline prediction rows", "Value": counts.get("prediction_outputs", 0)},
        {"Metric": "Geo-validation overlap", "Value": counts.get("geo_validation_candidates_overlap", 0)},
        {"Metric": "Trainable supervised labels", "Value": report.get("trainable_supervised_labels", 0)},
    ]
    tier_rows = (
        [{"Group": "Evidence tier", "Name": key, "Rows": value} for key, value in tiers.items()]
        + [{"Group": "Trust posture", "Name": key, "Rows": value} for key, value in posture.items()]
    )
    return pd.DataFrame(summary_rows), pd.DataFrame(tier_rows), report


def supervised_model_report() -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Load the supervised model trainer report, if it has been generated."""
    path = config.facility_prediction_model_report_path()
    if not path.exists():
        return pd.DataFrame(), pd.DataFrame(), {}

    report = json.loads(path.read_text(encoding="utf-8"))
    policy = report.get("model_policy", {})
    summary = pd.DataFrame(
        [
            {"Metric": "Primary model", "Value": policy.get("primary_model", "")},
            {"Metric": "Input rows", "Value": report.get("input_rows", 0)},
            {"Metric": "Trainable rows", "Value": report.get("trainable_rows", 0)},
            {"Metric": "Trained tasks", "Value": report.get("trained_tasks", 0)},
            {"Metric": "Skipped tasks", "Value": report.get("skipped_tasks", 0)},
            {"Metric": "Abstention rule", "Value": policy.get("abstention_rule", "")},
        ]
    )
    task_rows = []
    for task in report.get("tasks", []):
        row = {
            "Task": task.get("task"),
            "Status": task.get("status"),
            "Reason / metric": task.get("reason", ""),
        }
        metrics = task.get("metrics", {})
        if metrics:
            row["Reason / metric"] = (
                f"accuracy={metrics.get('accuracy')}; "
                f"balanced_accuracy={metrics.get('balanced_accuracy')}; "
                f"f1_macro={metrics.get('f1_macro')}"
            )
        task_rows.append(row)
    return summary, pd.DataFrame(task_rows), report


def load_districts() -> pd.DataFrame:
    """Load the cleaned district table (CSV or warehouse, same as facilities)."""
    if os.environ.get("DATA_BACKEND", "csv").lower() == "warehouse":
        from databricks import sql
        with sql.connect(
            server_hostname=os.environ["DATABRICKS_SERVER_HOSTNAME"],
            http_path=os.environ["DATABRICKS_HTTP_PATH"],
            access_token=os.environ.get("DATABRICKS_TOKEN"),
        ) as conn, conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {UC_DISTRICT_TABLE}")
            d = cur.fetchall_arrow().to_pandas()
    else:
        d = pd.read_csv(config.district_table_path(), low_memory=False)
    d["district_name"] = d["district_name"].astype(str).str.strip()
    d["state_ut"] = d["state_ut"].astype(str).str.strip()
    return d


def leaderboard(districts: pd.DataFrame, specialty: str, top_n: int = 15):
    """Rank districts by a (specialty-aware) care-gap score. Returns (df, gap_label)."""
    d = districts.copy()
    sig, _ = SPECIALTY_DISTRICT.get(specialty, (None, []))
    need = pd.to_numeric(d.get("health_need_score"), errors="coerce")
    if sig and sig in d.columns:
        rate = pd.to_numeric(d[sig], errors="coerce").fillna(0.0)
        d["gap"] = (need.fillna(0) * (1.0 - rate)).round(3)
        gap_label = f"{specialty.split(' /')[0]} gap"
    else:
        d["gap"] = pd.to_numeric(d.get("care_gap_score"), errors="coerce")
        gap_label = "Care-gap score"
    d = d[d["observed_facility_rows"].notna()] if "observed_facility_rows" in d else d
    return d.sort_values("gap", ascending=False).head(top_n).reset_index(drop=True), gap_label


def filter_facilities(df: pd.DataFrame, specialty: str, include_geo_flagged: bool) -> pd.DataFrame:
    """Filter to mappable rows for the selected specialty."""
    out = df.dropna(subset=["facility_latitude", "facility_longitude"]).copy()
    if not include_geo_flagged:
        out = out[out["geo_in_india_bbox"]]
    signal_col = config.SPECIALTIES.get(specialty)
    if signal_col:
        out = out[out[signal_col]]
    return out


def quality_snapshot(facilities: pd.DataFrame, districts: pd.DataFrame) -> dict[str, float | int]:
    """Top-line quality metrics for the verification workflow."""
    total = len(facilities)
    district_total = len(districts)
    far_or_bad_geo = facilities["geo_quality"].astype(str).str.contains(
        "far|outside|missing|moderate", case=False, na=False
    ).sum()
    outside_india = facilities["geo_quality"].astype(str).str.contains(
        "outside", case=False, na=False
    ).sum()
    extreme_supply = (
        facilities.get("capacity_num_extreme_outlier", False)
        | facilities.get("number_doctors_num_extreme_outlier", False)
    ).sum()
    return {
        "facility_rows": total,
        "district_rows": district_total,
        "needs_human_review": int(facilities["needs_human_review"].sum()),
        "trustworthy_supply": int(facilities["trustworthy_supply_signal"].sum()),
        "contradicted_or_geo_invalid": int(facilities["contradicted_or_geo_invalid_signal"].sum()),
        "source_url_rows": int(facilities["has_source_urls"].sum()),
        "contact_evidence_rows": int(facilities["has_contact_evidence"].sum()),
        "far_or_bad_geo_rows": int(far_or_bad_geo),
        "outside_india_rows": int(outside_india),
        "extreme_supply_rows": int(extreme_supply),
        "higher_uncertainty_districts": int(
            districts["district_uncertainty_level"].astype(str).str.lower().eq("higher").sum()
        ),
        "avg_data_readiness": float(facilities["data_readiness_score"].mean()),
    }


def messiness_breakdown(facilities: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    """Human-readable explanation of the main failure modes."""
    q = quality_snapshot(facilities, districts)
    total = max(q["facility_rows"], 1)
    district_total = max(q["district_rows"], 1)
    rows = [
        {
            "Failure mode": "Claim pipeline, not registry truth",
            "Observed signal": "Web crawl -> GenAI extraction -> entity resolution",
            "Impact": "Treat facility fields as claims until externally corroborated",
        },
        {
            "Failure mode": "Manual review burden",
            "Observed signal": f"{q['needs_human_review']:,} rows ({q['needs_human_review']/total:.0%})",
            "Impact": "The product must route records to verification, not hide uncertainty",
        },
        {
            "Failure mode": "Geography can be wrong",
            "Observed signal": f"{q['far_or_bad_geo_rows']:,} suspicious geo rows; "
                               f"{q['outside_india_rows']:,} outside India",
            "Impact": "Bad coordinates can make supply appear in the wrong district",
        },
        {
            "Failure mode": "Operational fields are sparse/outlier-prone",
            "Observed signal": f"{q['extreme_supply_rows']:,} capacity/doctor-count outlier rows",
            "Impact": "Use robust checks and source confirmation before ranking on capacity",
        },
        {
            "Failure mode": "Contact evidence is not reachability",
            "Observed signal": f"{q['contact_evidence_rows']:,} rows have a phone/email/site field",
            "Impact": "Reachability needs a call/email outcome, ideally in local language",
        },
        {
            "Failure mode": "District uncertainty remains material",
            "Observed signal": f"{q['higher_uncertainty_districts']:,} of {district_total:,} districts are higher uncertainty",
            "Impact": "Show confidence alongside every care-gap recommendation",
        },
    ]
    return pd.DataFrame(rows)


def missingness_summary(facilities: pd.DataFrame) -> pd.DataFrame:
    """Volume and handling plan for missing or incomplete fields."""
    total = max(len(facilities), 1)

    def status_not_observed(col: str) -> pd.Series:
        if col not in facilities:
            return pd.Series(False, index=facilities.index)
        return facilities[col].fillna("").astype(str).str.lower().ne("observed_valid") & facilities[col].fillna("").astype(str).str.lower().ne("observed_claim")

    rows = [
        {
            "Incomplete area": "Capacity / beds",
            "Rows": int(facilities.get("capacity_is_estimated", pd.Series(False, index=facilities.index)).sum()),
            "Handling": "Use peer-group median estimate, p10-p90 interval, confidence label; keep estimate flag visible",
        },
        {
            "Incomplete area": "Doctor count",
            "Rows": int(facilities.get("doctor_count_is_estimated", pd.Series(False, index=facilities.index)).sum()),
            "Handling": "Use peer-group median estimate, p10-p90 interval, confidence label; do not call it observed",
        },
        {
            "Incomplete area": "Equipment",
            "Rows": int(status_not_observed("equipment_status").sum()),
            "Handling": "Treat as missing evidence; enrich from registry/source pages or send high-impact rows to review",
        },
        {
            "Incomplete area": "Procedure / specialty / capability text",
            "Rows": int(
                (
                    status_not_observed("procedure_status")
                    | status_not_observed("specialties_status")
                    | status_not_observed("capability_status")
                ).sum()
            ),
            "Handling": "Do not infer services from blanks; use semantic claim extraction plus external corroboration",
        },
        {
            "Incomplete area": "Recency",
            "Rows": int(status_not_observed("recency_status").sum()),
            "Handling": "Downweight stale/invalid source pages; prioritize current registry or reachable facility source",
        },
        {
            "Incomplete area": "Contact/reachability",
            "Rows": int((~facilities["has_contact_evidence"]).sum()),
            "Handling": "Enrich phone/email/site from HFR, PM-JAY, source URL, Overture/OSM; reachability remains separate",
        },
        {
            "Incomplete area": "Source citation",
            "Rows": int((~facilities["has_source_urls"]).sum()),
            "Handling": "Search authoritative/open sources; keep uncited records in lower trust posture",
        },
        {
            "Incomplete area": "Coordinates",
            "Rows": int(facilities["geo_quality"].astype(str).str.contains("missing", case=False, na=False).sum()),
            "Handling": "LLM address parser plus India-restricted geocoder; ambiguous results stay in uncertainty queue",
        },
    ]
    out = pd.DataFrame(rows)
    out["Pct of records"] = (out["Rows"] / total).map(lambda value: f"{value:.1%}")
    return out.sort_values("Rows", ascending=False).reset_index(drop=True)


def _service_label(row: pd.Series) -> str:
    signals = []
    if row.get("has_maternity_care_signal", False):
        signals.append("maternity")
    if row.get("has_emergency_care_signal", False):
        signals.append("emergency")
    if row.get("has_diagnostic_signal", False):
        signals.append("diagnostics")
    if row.get("has_ncd_care_signal", False):
        signals.append("NCD")
    return ", ".join(signals) if signals else "general"


def _primary_concern(row: pd.Series) -> str:
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "Contradicted or invalid geography"
    geo = str(row.get("geo_quality", "")).lower()
    if "outside" in geo:
        return "Coordinates outside India"
    if "far" in geo or "moderate" in geo:
        return "Coordinates far from PIN centroid"
    if pd.to_numeric(row.get("join_confidence"), errors="coerce") < 0.75:
        return "Weak district/PIN join"
    if bool(row.get("capacity_num_extreme_outlier", False)) or bool(
        row.get("number_doctors_num_extreme_outlier", False)
    ):
        return "Implausible capacity or doctor count"
    if not bool(row.get("has_source_urls", False)):
        return "No source URL citation"
    if not bool(row.get("has_contact_evidence", False)):
        return "No contact evidence"
    if bool(row.get("needs_human_review", False)):
        return "Manual review flag"
    return "Positive control candidate"


def _verification_channel(row: pd.Series) -> str:
    if str(row.get("officialPhone", "") or "").strip():
        return "Call first"
    if str(row.get("email", "") or "").strip():
        return "Email first"
    if str(row.get("officialWebsite", "") or "").strip():
        return "Check website"
    if str(row.get("source_urls", "") or "").strip():
        return "Check source page"
    return "Search HFR/PM-JAY"


def _label_seed(row: pd.Series) -> str:
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "contradicted_seed"
    if bool(row.get("trustworthy_supply_signal", False)) and not bool(
        row.get("needs_human_review", False)
    ):
        return "verified_seed_candidate"
    if bool(row.get("needs_human_review", False)):
        return "review_seed"
    return "unverified_seed"


def _address_parts(row: pd.Series) -> list[str]:
    parts = []
    for col in [
        "facility_name", "address_line1", "address_line2", "address_line3",
        "address_city", "address_stateOrRegion", "address_zipOrPostcode",
    ]:
        value = str(row.get(col, "") or "").strip()
        if value and value.lower() not in {"nan", "none", "—"}:
            parts.append(value)
    parts.append("India")
    return parts


def _raw_address(row: pd.Series) -> str:
    seen = set()
    out = []
    for part in _address_parts(row):
        key = part.lower()
        if key not in seen:
            seen.add(key)
            out.append(part)
    return ", ".join(out)


def _geo_reason(row: pd.Series) -> str:
    geo = str(row.get("geo_quality", "") or "").lower()
    if "outside" in geo:
        return "outside_india_bbox"
    if "far" in geo:
        return "far_from_pincode_centroid"
    if "moderate" in geo:
        return "moderate_distance_from_pincode_centroid"
    if "missing" in geo:
        return "missing_coordinates"
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "contradicted_geo_signal"
    return "geo_review_candidate"


def geo_validation_candidates(facilities: pd.DataFrame, top_n: int = 100) -> pd.DataFrame:
    """Rows that should go through LLM parsing + geocoder validation."""
    d = facilities.copy()
    geo_text = d["geo_quality"].astype(str).str.lower()
    mask = (
        d["contradicted_or_geo_invalid_signal"]
        | geo_text.str.contains("outside|far|moderate|missing", na=False)
        | d["facility_latitude"].isna()
        | d["facility_longitude"].isna()
    )
    d = d[mask].copy()
    if d.empty:
        return pd.DataFrame()

    distance = d["geo_distance_km_to_pincode_centroid"].fillna(-1)
    d["geo_review_score"] = (
        d["contradicted_or_geo_invalid_signal"].astype(float) * 50
        + geo_text.str.contains("outside", na=False).astype(float) * 35
        + geo_text.str.contains("far", na=False).astype(float) * 25
        + geo_text.str.contains("moderate", na=False).astype(float) * 12
        + distance.clip(lower=0, upper=5000) / 100
        + d["medical_desert_priority_score"].fillna(0.0).clip(0, 1) * 8
    ).round(1)
    d["geo_review_reason"] = d.apply(_geo_reason, axis=1)
    d["raw_india_address"] = d.apply(_raw_address, axis=1)
    d["geocoder_query"] = d["raw_india_address"]
    d["current_coordinates"] = (
        d["facility_latitude"].round(6).astype(str)
        + ", "
        + d["facility_longitude"].round(6).astype(str)
    )

    cols = [
        "facility_name", "facilityTypeId", "geo_review_reason", "geo_review_score",
        "geo_quality", "geo_distance_km_to_pincode_centroid", "current_coordinates",
        "address_city", "address_stateOrRegion", "address_zipOrPostcode",
        "raw_india_address", "geocoder_query", "source_urls",
    ]
    return d[[c for c in cols if c in d.columns]].sort_values(
        "geo_review_score", ascending=False
    ).head(top_n).reset_index(drop=True)


def verification_queue(
    facilities: pd.DataFrame,
    specialty: str,
    focus: str,
    top_n: int = 75,
) -> pd.DataFrame:
    """Build a prioritized facility queue for external/human verification."""
    d = filter_facilities(facilities, specialty, include_geo_flagged=True).copy()
    if d.empty:
        return pd.DataFrame()

    score = pd.Series(0.0, index=d.index)
    score += d["contradicted_or_geo_invalid_signal"].astype(float) * 35
    score += d["needs_human_review"].astype(float) * 25
    score += (1.0 - d["data_readiness_score"].fillna(0.0)).clip(0, 1) * 20
    score += (1.0 - d["join_confidence"].fillna(0.0)).clip(0, 1) * 15
    score += d["medical_desert_priority_score"].fillna(0.0).clip(0, 1) * 12
    score += (~d["has_contact_evidence"]).astype(float) * 8
    score += (~d["has_source_urls"]).astype(float) * 6
    score += d["source_duplicate_unique_id"].astype(float) * 6
    score += (
        d["capacity_num_extreme_outlier"] | d["number_doctors_num_extreme_outlier"]
    ).astype(float) * 10
    d["review_priority"] = score.round(1)
    d["primary_concern"] = d.apply(_primary_concern, axis=1)
    d["verification_channel"] = d.apply(_verification_channel, axis=1)
    d["service_signal"] = d.apply(_service_label, axis=1)
    d["label_seed"] = d.apply(_label_seed, axis=1)
    d["first_source_url"] = d["source_urls"].map(_first_url)

    if focus == "Positive controls":
        d = d[d["label_seed"].eq("verified_seed_candidate")]
        d = d.sort_values(["data_readiness_score", "join_confidence"], ascending=False)
    elif focus == "Contradictions and geo failures":
        d = d[d["label_seed"].eq("contradicted_seed")]
        d = d.sort_values("review_priority", ascending=False)
    elif focus == "Manual review queue":
        d = d[d["needs_human_review"]]
        d = d.sort_values("review_priority", ascending=False)
    else:
        d = d.sort_values("review_priority", ascending=False)

    cols = [
        "facility_name", "facilityTypeId", "address_city", "district_name", "state_ut",
        "service_signal", "primary_concern", "verification_channel", "label_seed",
        "review_priority", "data_readiness_score", "join_confidence", "geo_quality",
        "officialPhone", "email", "officialWebsite", "first_source_url", "claim_text",
    ]
    return d[[c for c in cols if c in d.columns]].head(top_n).reset_index(drop=True)


_COLOR_UNKNOWN = [203, 213, 225]  # light slate for cells with no score


def _lerp(a: tuple, b: tuple, t: float) -> list[int]:
    return [int(round(a[i] + (b[i] - a[i]) * t)) for i in range(3)]


def _ramp(t: float, higher_is_worse: bool) -> list[int]:
    """3-stop ramp good->mid->bad through an amber midpoint. NaN -> slate."""
    if t is None or (isinstance(t, float) and np.isnan(t)):
        return list(_COLOR_UNKNOWN)
    t = float(np.clip(t, 0.0, 1.0))
    if not higher_is_worse:
        t = 1.0 - t  # invert so "more is better" reads green
    if t <= 0.5:
        return _lerp(config.COLOR_GOOD, config.COLOR_MID, t / 0.5)
    return _lerp(config.COLOR_MID, config.COLOR_BAD, (t - 0.5) / 0.5)


# Facility status -> point color (RGBA).
_STATUS_COLOR = {
    "Contradicted / geo-invalid": [229, 57, 53, 230],
    "Needs review": [255, 170, 0, 220],
    "Passed checks": [38, 166, 154, 220],
    "Unknown": [148, 163, 184, 200],
}


def _first_url(raw) -> str:
    """Pull the first usable URL from the source_urls JSON-ish string."""
    if not isinstance(raw, str) or not raw.strip():
        return ""
    import json
    try:
        items = json.loads(raw)
        for u in items:
            if u:
                return str(u)
    except Exception:
        pass
    return raw.strip().strip('[]"').split(",")[0]


def facility_points(df: pd.DataFrame) -> pd.DataFrame:
    """Slim, display-ready per-facility points for the scatter layer + detail card."""
    d = df.dropna(subset=["facility_latitude", "facility_longitude"]).copy()
    if d.empty:
        return d

    status = np.select(
        [d["contradicted_or_geo_invalid_signal"], d["needs_human_review"],
         d["trustworthy_supply_signal"]],
        ["Contradicted / geo-invalid", "Needs review", "Passed checks"],
        default="Unknown",
    )
    out = pd.DataFrame({
        "facility_name": d["facility_name"].fillna("Unnamed facility"),
        "facility_type": d["facilityTypeId"].fillna("—"),
        "city": d["address_city"].fillna("—"),
        "state": d["address_stateOrRegion"].fillna("—"),
        "district": d["district_name"].fillna("—"),
        "geo_quality": d["geo_quality"].fillna("—"),
        "status": status,
        "lat": d["facility_latitude"],
        "lon": d["facility_longitude"],
        "source_url": d["source_urls"].map(_first_url),
        "evidence": d["claim_text"].fillna("").str.slice(0, 260),
    })
    out["point_color"] = out["status"].map(_STATUS_COLOR)
    out["tip"] = "<b>" + out["facility_name"] + "</b><br/>" + out["status"] + " · " + out["city"]
    return out


def hexbin(df: pd.DataFrame, metric_label: str, resolution: int) -> pd.DataFrame:
    """Aggregate facilities into H3 cells and attach a fill color + tooltip text."""
    col, agg, higher_is_worse = config.METRICS[metric_label]

    if df.empty:
        return pd.DataFrame(columns=["h3", "value", "fill_color", "n",
                                     "metric_label", "value_str", "trust_str"])

    work = df.copy()
    work["h3"] = [
        h3.latlng_to_cell(lat, lng, resolution)
        for lat, lng in zip(work["facility_latitude"], work["facility_longitude"])
    ]

    grouped = work.groupby("h3")
    cells = pd.DataFrame({
        "n": grouped.size(),
        "trustworthy": grouped["trustworthy_supply_signal"].sum(),
        "need_mean": grouped["health_need_score"].mean(),
        "gap_mean": grouped["medical_desert_priority_score"].mean(),
    }).reset_index()

    # The displayed metric value per cell.
    if agg == "count":
        cells["value"] = cells["n"]
    elif agg == "sum":
        cells["value"] = cells["trustworthy"]
    else:  # mean of the chosen score column
        cells["value"] = grouped[col].mean().values

    # Normalize for coloring.
    vmin, vmax = cells["value"].min(), cells["value"].max()
    span = (vmax - vmin) or 1.0
    cells["fill_color"] = [
        _ramp((v - vmin) / span, higher_is_worse) + [config.HEX_ALPHA]
        for v in cells["value"]
    ]

    # Tooltip strings.
    cells["metric_label"] = metric_label
    cells["value_str"] = cells["value"].round(2).astype(str)
    cells["trust_str"] = (cells["trustworthy"].astype(int).astype(str)
                          + " / " + cells["n"].astype(int).astype(str))
    cells["tip"] = ("<b>" + cells["n"].astype(int).astype(str) + " facilities</b><br/>"
                    + metric_label + ": " + cells["value_str"]
                    + "<br/>Passed checks: " + cells["trust_str"])
    return cells
