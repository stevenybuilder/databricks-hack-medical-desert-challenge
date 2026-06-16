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

# Governed gold layer (materialized by DB-2). Catalog/schema are env-overridable so
# the same app code runs against Free-Edition `workspace.caregap_gold` or any clone.
CAREGAP_CATALOG = os.environ.get("CAREGAP_CATALOG", "workspace")
CAREGAP_GOLD_SCHEMA = os.environ.get("CAREGAP_GOLD_SCHEMA", "caregap_gold")


def _gold(name: str) -> str:
    """Fully-qualified gold table/view name, e.g. workspace.caregap_gold.<name>."""
    return f"{CAREGAP_CATALOG}.{CAREGAP_GOLD_SCHEMA}.{name}"


def _is_warehouse() -> bool:
    return os.environ.get("DATA_BACKEND", "csv").lower() == "warehouse"

# Columns we actually need for Phase 1 (keep the 49MB read fast).
_USECOLS = [
    "unique_id",
    "trust_tier",
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


def _wh_connect():
    """Open a SQL-warehouse connection.

    Works both with a static token (local/dev: ``DATABRICKS_TOKEN`` set) and with
    Databricks Apps OAuth (no token in env — auth comes from the deployed app's
    service principal via the Databricks SDK). Accepts ``DATABRICKS_SERVER_HOSTNAME``
    or the app-injected ``DATABRICKS_HOST`` (URL form) for the hostname.
    """
    from databricks import sql  # lazy import; only needed when deployed

    host = (
        os.environ.get("DATABRICKS_SERVER_HOSTNAME")
        or os.environ.get("DATABRICKS_HOST", "")
    ).replace("https://", "").replace("http://", "").strip("/")
    http_path = os.environ["DATABRICKS_HTTP_PATH"]
    token = os.environ.get("DATABRICKS_TOKEN")
    # use_cloud_fetch=False forces inline Arrow results. Databricks Apps egress
    # cannot reach the external CloudFetch storage host
    # (*.storage.cloud.databricks.com), so cloud fetch hangs/fails; inline avoids it.
    if token:
        return sql.connect(server_hostname=host, http_path=http_path,
                           access_token=token, use_cloud_fetch=False)
    # Databricks Apps: authenticate as the app's service principal via the SDK.
    from databricks.sdk.core import Config
    cfg = Config()
    return sql.connect(
        server_hostname=host,
        http_path=http_path,
        credentials_provider=lambda: cfg.authenticate,
        use_cloud_fetch=False,
    )


def _load_from_warehouse() -> pd.DataFrame:
    """Query the cleaned facility table from the SQL warehouse.

    In a deployed Databricks App auth comes from the attached SQL warehouse
    resource. Requires `databricks-sql-connector` (in requirements.txt).
    """
    with _wh_connect() as conn:
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


# --- Governed gold decision tables (DB-2's caregap_gold) ---------------------
#
# When DATA_BACKEND=warehouse these read the governed gold tables/views; in every
# other case (local dev, or any warehouse failure) they fall back to the local CSV
# artifacts in output/data/. They NEVER raise to the UI — an empty DataFrame is the
# worst case, so the app degrades gracefully when a gold object is missing.


def _warehouse_query(query: str) -> pd.DataFrame:
    """Run a read query against the SQL warehouse, returning a pandas DataFrame.

    Raises on connection/SQL failure; callers wrap this and fall back to CSV.
    """
    with _wh_connect() as conn, conn.cursor() as cur:
        cur.execute(query)
        return cur.fetchall_arrow().to_pandas()


def _load_gold(table_or_view: str, fallback_path) -> pd.DataFrame:
    """Generic gold reader: warehouse SELECT * when in warehouse mode, else CSV.

    On ANY warehouse error (missing object, auth, network) we fall back to the local
    CSV artifact. If that is also absent we return an empty DataFrame. Never raises.
    """
    if _is_warehouse():
        try:
            df = _warehouse_query(f"SELECT * FROM {_gold(table_or_view)}")
            return _coerce_known_numeric(df)
        except Exception:
            # Fall through to the local artifact so the UI still renders.
            pass
    try:
        df = _read_optional_csv(fallback_path)
        return _coerce_known_numeric(df) if not df.empty else df
    except Exception:
        return pd.DataFrame()


def load_gold_interventions() -> pd.DataFrame:
    """Intervention recommendations.

    Warehouse: view `v_intervention_recommender` (falls back to table
    `intervention_recommendations`). Local: output/data/intervention_recommendations.csv.
    """
    if _is_warehouse():
        for obj in ("v_intervention_recommender", "intervention_recommendations"):
            try:
                return _coerce_known_numeric(_warehouse_query(f"SELECT * FROM {_gold(obj)}"))
            except Exception:
                continue
    return _load_gold(
        "intervention_recommendations",
        config.data_dir() / "intervention_recommendations.csv",
    )


def load_gold_provider_confidence() -> pd.DataFrame:
    """Provider confidence.

    Warehouse: view `v_provider_confidence` (falls back to table `provider_confidence`).
    Local: output/data/conformal_facility_sets.csv (the closest available trust artifact).
    """
    if _is_warehouse():
        for obj in ("v_provider_confidence", "provider_confidence"):
            try:
                return _coerce_known_numeric(_warehouse_query(f"SELECT * FROM {_gold(obj)}"))
            except Exception:
                continue
    return _load_gold(
        "provider_confidence",
        config.data_dir() / "conformal_facility_sets.csv",
    )


def load_gold_scenario_simulations() -> pd.DataFrame:
    """What-if scenario simulations.

    Warehouse: view `v_scenario_simulator` (falls back to table `scenario_simulations`).
    Local: output/data/scenario_simulations.csv if present, else empty.
    """
    if _is_warehouse():
        for obj in ("v_scenario_simulator", "scenario_simulations"):
            try:
                return _coerce_known_numeric(_warehouse_query(f"SELECT * FROM {_gold(obj)}"))
            except Exception:
                continue
    return _load_gold(
        "scenario_simulations",
        config.data_dir() / "scenario_simulations.csv",
    )


def load_medical_desert_scores() -> pd.DataFrame:
    """Medical desert risk scores.

    Warehouse: view `v_risk_map` (falls back to table `medical_desert_scores`).
    Local: output/data/medical_desert_scores.csv if present, else empty.
    """
    if _is_warehouse():
        for obj in ("v_risk_map", "medical_desert_scores"):
            try:
                return _coerce_known_numeric(_warehouse_query(f"SELECT * FROM {_gold(obj)}"))
            except Exception:
                continue
    return _load_gold(
        "medical_desert_scores",
        config.data_dir() / "medical_desert_scores.csv",
    )


# --- Monitoring / feedback write-back ----------------------------------------
#
# These tie the app's local SQLite decisions module to the governed cloud tables in
# caregap_gold. When DATA_BACKEND=warehouse they INSERT (parameterized); otherwise
# they no-op so local dev never needs a warehouse. They never raise to the UI.

DEFAULT_POLICY_VERSION = os.environ.get("CAREGAP_POLICY_VERSION", "v0")


def _warehouse_insert(table: str, columns: list[str], values: list) -> bool:
    """Parameterized INSERT into a gold table. Returns True on success, never raises."""
    if not _is_warehouse():
        return False
    try:
        placeholders = ", ".join(["?"] * len(columns))
        col_list = ", ".join(columns)
        stmt = f"INSERT INTO {_gold(table)} ({col_list}) VALUES ({placeholders})"
        with _wh_connect() as conn, conn.cursor() as cur:
            cur.execute(stmt, values)
        return True
    except Exception:
        # Governed write-back is best-effort; failures must not break the UI.
        return False


def append_reviewer_feedback(
    geography_id: str,
    feedback_type: str,
    notes: str = "",
    reviewer: str | None = None,
    payload: str = "",
    status: str = "pending",
    policy_version: str | None = None,
) -> bool:
    """Append a reviewer feedback row to caregap_gold.reviewer_feedback.

    Warehouse mode: parameterized INSERT (returns True on success). Otherwise no-op
    returning False. `feedback_type` is one of the architecture doc's feedback types
    (e.g. provider_correction, recommendation_override, outcome_data, data_quality_flag).
    """
    columns = [
        "geography_id", "feedback_type", "payload", "notes",
        "reviewer", "status", "policy_version", "created_at",
    ]
    values = [
        str(geography_id), str(feedback_type), str(payload), str(notes),
        reviewer or os.environ.get("CAREGAP_REVIEWER", "app"),
        str(status), policy_version or DEFAULT_POLICY_VERSION,
        pd.Timestamp.utcnow().isoformat(),
    ]
    return _warehouse_insert("reviewer_feedback", columns, values)


def append_recommendation_override(
    geography_id: str,
    original_intervention: str,
    chosen_intervention: str,
    notes: str = "",
    reviewer: str | None = None,
    status: str = "pending",
    policy_version: str | None = None,
) -> bool:
    """Append a recommendation override to caregap_gold.recommendation_overrides.

    Warehouse mode: parameterized INSERT. Otherwise no-op returning False.
    """
    columns = [
        "geography_id", "original_intervention", "chosen_intervention",
        "notes", "reviewer", "status", "policy_version", "created_at",
    ]
    values = [
        str(geography_id), str(original_intervention), str(chosen_intervention),
        str(notes), reviewer or os.environ.get("CAREGAP_REVIEWER", "app"),
        str(status), policy_version or DEFAULT_POLICY_VERSION,
        pd.Timestamp.utcnow().isoformat(),
    ]
    return _warehouse_insert("recommendation_overrides", columns, values)


def append_scenario_decision(
    geography_id: str,
    assumptions: str,
    notes: str = "",
    reviewer: str | None = None,
    status: str = "saved",
    policy_version: str | None = None,
) -> bool:
    """Append a saved what-if scenario to caregap_gold.scenario_decisions.

    Warehouse mode: parameterized INSERT (returns True on success). Otherwise no-op
    returning False. `assumptions` is a serialized payload (e.g. JSON) describing the
    scenario levers/planning values the planner chose for this geography.
    """
    columns = [
        "geography_id", "assumptions", "notes",
        "reviewer", "status", "policy_version", "created_at",
    ]
    values = [
        str(geography_id), str(assumptions), str(notes),
        reviewer or os.environ.get("CAREGAP_REVIEWER", "app"),
        str(status), policy_version or DEFAULT_POLICY_VERSION,
        pd.Timestamp.utcnow().isoformat(),
    ]
    return _warehouse_insert("scenario_decisions", columns, values)


def load_reviewer_feedback(geography_id: str | None = None) -> pd.DataFrame:
    """Read persisted reviewer feedback from caregap_gold.reviewer_feedback.

    Warehouse-only governed read. Returns an empty DataFrame on any error, on a
    missing table, or when not in warehouse mode (local persistence lives in
    SQLite). Never raises.
    """
    if not _is_warehouse():
        return pd.DataFrame()
    try:
        where = ""
        if geography_id is not None:
            safe = str(geography_id).replace("'", "''")
            where = f" WHERE geography_id = '{safe}'"
        return _warehouse_query(
            f"SELECT * FROM {_gold('reviewer_feedback')}{where} ORDER BY created_at DESC"
        )
    except Exception:
        return pd.DataFrame()


def load_scenario_decisions(geography_id: str | None = None) -> pd.DataFrame:
    """Read persisted scenarios from caregap_gold.scenario_decisions.

    Warehouse-only governed read. Returns an empty DataFrame on any error, on a
    missing table, or when not in warehouse mode. Never raises.
    """
    if not _is_warehouse():
        return pd.DataFrame()
    try:
        where = ""
        if geography_id is not None:
            safe = str(geography_id).replace("'", "''")
            where = f" WHERE geography_id = '{safe}'"
        return _warehouse_query(
            f"SELECT * FROM {_gold('scenario_decisions')}{where} ORDER BY created_at DESC"
        )
    except Exception:
        return pd.DataFrame()


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
    "real_desert_candidate": ("Deploy / build",
        "Genuine unmet need with little trustworthy supply — strongest case to deploy."),
    "phantom_desert_or_verification_gap": ("Verify first",
        "Looks empty, but the few records are unverified — verify before acting."),
    "supply_record_quality_problem": ("Fix records",
        "Facilities likely exist but records are broken — fix data before planning."),
    "referral_or_capacity_candidate": ("Refer (capacity exists)",
        "Trustworthy capacity is present — route patients here."),
    "mixed_or_monitor": ("Monitor",
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
        "Step": "5. Uncertainty queue",
        "Tool": "Uncertainty tab + persisted Delta outcomes",
        "Output": "keep, corrected_geo, approximate_review, not_found, provider_conflict",
        "Decision": "Keep ambiguous API outcomes visible as unresolved uncertainty",
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
            {"Metric": "Input rows", "Value": f"{report.get('input_rows', 0):,}"},
            {"Metric": "Trainable rows", "Value": f"{report.get('trainable_rows', 0):,}"},
            {"Metric": "Trained tasks", "Value": f"{report.get('trained_tasks', 0):,}"},
            {"Metric": "Skipped tasks", "Value": f"{report.get('skipped_tasks', 0):,}"},
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


def _read_optional_csv(path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, low_memory=False)


def _coerce_known_numeric(df: pd.DataFrame) -> pd.DataFrame:
    numeric_fragments = [
        "_score", "_rate", "_ci_low", "_ci_high", "_rows", "_rank", "_width",
        "_km", "_value", "_low", "_high", "_n", "confidence",
        "pct", "denominator", "wilson", "bayes",
    ]
    for col in df.columns:
        if any(fragment in col for fragment in numeric_fragments):
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().any():
                df[col] = converted
    return df


def statistical_decision_report() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    """Load category volumes and statistical decision policy artifacts."""
    volume = _read_optional_csv(config.decision_category_volume_summary_path())
    policy_path = config.statistical_decision_policy_report_path()
    policy = json.loads(policy_path.read_text(encoding="utf-8")) if policy_path.exists() else {}

    if not volume.empty:
        volume = _coerce_known_numeric(volume)
        volume["Pct"] = volume["pct"].map(lambda value: _pct(value, digits=1))
        volume["Wilson 95%"] = volume.apply(
            lambda row: f"{_pct(row.get('wilson_95_low'), digits=1)} to {_pct(row.get('wilson_95_high'), digits=1)}",
            axis=1,
        )
        volume["Bayes 95%"] = volume.apply(
            lambda row: f"{_pct(row.get('bayes_95_low'), digits=1)} to {_pct(row.get('bayes_95_high'), digits=1)}",
            axis=1,
        )

    concepts = pd.DataFrame(policy.get("concepts", []))
    if not concepts.empty:
        concepts = concepts.rename(
            columns={
                "concept": "Concept",
                "use_now": "Use now",
                "where_applied": "Where applied",
                "why_relevant": "Why relevant",
            }
        )
        concepts["Use now"] = concepts["Use now"].map(lambda value: "Yes" if bool(value) else "Not yet")

    rules = pd.DataFrame(policy.get("decision_rules_already_in_pipeline", []))
    if not rules.empty:
        rules = rules.rename(
            columns={
                "decision": "Decision",
                "rule": "Rule",
                "statistical_role": "Statistical role",
            }
        )

    return volume, concepts, rules, policy


def _json_list(raw) -> list[str]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    text = str(raw).strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            return [str(item) for item in parsed if str(item).strip()]
    except Exception:
        pass
    if ";" in text:
        return [item.strip() for item in text.split(";") if item.strip()]
    if "," in text and text.startswith("["):
        return [item.strip().strip('"') for item in text.strip("[]").split(",") if item.strip()]
    return [text]


_REASON_LABELS = {
    "high_health_need": "High district health need",
    "capacity_estimated_or_missing": "Capacity is estimated or missing",
    "doctor_count_estimated_or_missing": "Doctor count is estimated or missing",
    "wide_capacity_interval": "Wide capacity prediction interval",
    "wide_doctor_interval": "Wide doctor-count prediction interval",
    "critical_supply_gap": "Multiple supply fields are missing or weak",
    "low_join_confidence": "District/PIN join confidence is low",
    "non_plausible_geo": "Coordinates are not plausible",
    "external_geocode_needed": "External geocoding/source agreement needed",
    "wide_geo_uncertainty_band": "Large pre-geocode uncertainty band",
    "ambiguous_pincode_or_region": "PIN maps ambiguously in India Post",
    "missing_contact_evidence": "No phone/email/site evidence",
    "missing_source_urls": "No source URL citation",
    "sparse_segment": "Sparse facility/operator/state segment",
    "high_care_gap": "High care-gap score",
    "high_trust_gap": "Low trustworthy supply relative to need",
    "higher_uncertainty_level": "District is marked higher uncertainty",
    "wide_rate_confidence_intervals": "Rate confidence intervals are wide",
    "small_observed_facility_sample": "Small observed facility sample",
    "high_critical_supply_gap_rate": "High share of critical supply gaps",
    "current_coordinate_outside_india": "Current coordinate is outside India",
    "large_coordinate_pincode_disagreement": "Coordinate is far from PIN centroid",
    "existing_contradiction_flag": "Existing contradiction flag is set",
    "missing_coordinate": "Missing coordinate",
    "far_from_pincode_centroid": "Far from PIN centroid",
    "moderate_distance_from_pincode_centroid": "Moderate distance from PIN centroid",
    "high_decision_impact": "High planning impact if wrong",
    "low_data_readiness": "Low data readiness",
}


def reason_labels(raw) -> list[str]:
    return [_REASON_LABELS.get(reason, reason.replace("_", " ").title()) for reason in _json_list(raw)]


def active_facility_queue() -> pd.DataFrame:
    df = _read_optional_csv(config.active_facility_queue_path())
    if df.empty:
        return df
    df = _coerce_known_numeric(df)
    if "source_urls" in df:
        df["first_source_url"] = df["source_urls"].map(_first_url)
    return df


def active_district_queue() -> pd.DataFrame:
    df = _read_optional_csv(config.active_district_queue_path())
    return _coerce_known_numeric(df) if not df.empty else df


def geocoder_uncertainty_priors() -> pd.DataFrame:
    return _read_optional_csv(config.geocoder_uncertainty_priors_path())


def explainability_model_card() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Layer": "Need context",
                "Evidence used": "NFHS district indicators",
                "What the app can say": "This district has high patient burden for a specialty.",
                "What it cannot say": "A specific facility has those patients or outcomes.",
            },
            {
                "Layer": "Facility supply",
                "Evidence used": "FDR extracted claims, service signals, source URLs",
                "What the app can say": "The dataset contains claimed facilities and service evidence.",
                "What it cannot say": "The claim is true without corroboration.",
            },
            {
                "Layer": "Uncertainty bands",
                "Evidence used": "Wilson CIs, empirical p10-p90 intervals, proxy trust bands",
                "What the app can say": "The recommendation is robust or fragile under finite evidence.",
                "What it cannot say": "Measured model accuracy without gold labels.",
            },
            {
                "Layer": "External source agreement",
                "Evidence used": "Google/Mappls metadata, India Post, HFR/ABDM, PM-JAY, OSM/Overture",
                "What the app can say": "Independent sources agree or conflict on identity/location.",
                "What it cannot say": "A single geocoder hit proves facility truth.",
            },
        ]
    )


def _pct(value, digits: int = 0) -> str:
    try:
        if pd.isna(value):
            return "unknown"
        return f"{float(value) * 100:.{digits}f}%"
    except Exception:
        return "unknown"


def _score(value, digits: int = 2) -> str:
    try:
        if pd.isna(value):
            return "unknown"
        return f"{float(value):.{digits}f}"
    except Exception:
        return "unknown"


def _int_count(value) -> int:
    num = pd.to_numeric(value, errors="coerce")
    return 0 if pd.isna(num) else int(num)


def _ci_text(row: pd.Series, low_col: str, high_col: str, *, digits: int = 0) -> str:
    lo = row.get(low_col)
    hi = row.get(high_col)
    if pd.isna(pd.to_numeric(lo, errors="coerce")) or pd.isna(pd.to_numeric(hi, errors="coerce")):
        return "unknown interval"
    return f"{_pct(lo, digits)} to {_pct(hi, digits)}"


def active_district_match(row: pd.Series) -> pd.Series | None:
    queue = active_district_queue()
    if queue.empty:
        return None
    state = str(row.get("state_ut", "")).strip().lower()
    district = str(row.get("district_name", "")).strip().lower()
    match = queue[
        queue["state_ut"].astype(str).str.strip().str.lower().eq(state)
        & queue["district_name"].astype(str).str.strip().str.lower().eq(district)
    ]
    return None if match.empty else match.iloc[0]


def district_explanation(row: pd.Series, specialty: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    queue_row = active_district_match(row)
    sig, _ = SPECIALTY_DISTRICT.get(specialty, (None, []))
    service_value = row.get(sig) if sig else row.get("trustworthy_supply_rate")
    service_name = sig.replace("_", " ") if sig else "trustworthy supply rate"

    drivers = [
        {
            "Signal": "Health need",
            "Value": _score(row.get("health_need_score")),
            "Interpretation": "Percentile-style burden score from district NFHS indicators.",
        },
        {
            "Signal": "Care gap",
            "Value": _score(row.get("care_gap_score")),
            "Interpretation": "High need combined with limited trustworthy/service-specific supply.",
        },
        {
            "Signal": service_name,
            "Value": _pct(service_value),
            "Interpretation": "Observed FDR rows with the relevant service signal; not a facility census.",
        },
        {
            "Signal": "Trustworthy supply rate",
            "Value": f"{_pct(row.get('trustworthy_supply_rate'))} ({_ci_text(row, 'trustworthy_supply_rate_ci_low', 'trustworthy_supply_rate_ci_high')})",
            "Interpretation": "Wilson interval over observed facility rows; wide bands mean fragile evidence.",
        },
        {
            "Signal": "Needs-review rate",
            "Value": f"{_pct(row.get('needs_human_review_rate'))} ({_ci_text(row, 'needs_human_review_rate_ci_low', 'needs_human_review_rate_ci_high')})",
            "Interpretation": "Rows needing uncertainty review due to weak joins, geo issues, missingness, or contradictions.",
        },
        {
            "Signal": "Critical supply-gap rate",
            "Value": f"{_pct(row.get('critical_supply_gap_rate'))} ({_ci_text(row, 'critical_supply_gap_rate_ci_low', 'critical_supply_gap_rate_ci_high')})",
            "Interpretation": "Share of rows with multiple missing/estimated supply fields.",
        },
        {
            "Signal": "Observed facility sample",
            "Value": f"{_int_count(row.get('observed_facility_rows'))} rows",
            "Interpretation": "Small samples produce wider intervals and more fragile recommendations.",
        },
        {
            "Signal": "District data quality",
            "Value": f"{_score(row.get('district_data_quality_score'))} / {str(row.get('district_uncertainty_level', 'unknown')).title()}",
            "Interpretation": "Composite of readiness, join confidence, geography, source URLs, and review burden.",
        },
    ]
    if queue_row is not None:
        drivers.insert(
            0,
            {
                "Signal": "Active uncertainty rank",
                "Value": f"#{int(queue_row.get('active_uncertainty_rank'))} · {_score(queue_row.get('active_uncertainty_score'))}",
                "Interpretation": f"Action: {str(queue_row.get('active_learning_action')).replace('_', ' ')}.",
            },
        )

    reasons = pd.DataFrame(
        {
            "Reason": reason_labels(queue_row.get("active_learning_reasons") if queue_row is not None else ""),
        }
    )
    return pd.DataFrame(drivers), reasons


def care_gap_breakdown(row: pd.Series) -> tuple[pd.DataFrame, float, bool]:
    """Decompose the care-gap score into its additive contributions.

    Mirrors the exact builder formula so the demo can SHOW the math behind the score:
        care_gap = 0.55*health_need + 0.25*(1 - facility_percentile) + 0.20*(1 - trust_rate)
    Returns (breakdown_df, total, is_zero_facility_desert).
    """
    def _f(v: Any) -> float:
        n = pd.to_numeric(v, errors="coerce")
        return 0.0 if pd.isna(n) else float(n)

    hn = _f(row.get("health_need_score"))
    pct = _f(row.get("observed_facility_count_percentile"))
    tsr = _f(row.get("trustworthy_supply_rate"))
    comps = [
        ("Health need (NFHS burden)", 0.55, hn),
        ("Supply scarcity (few/no facilities)", 0.25, 1 - pct),
        ("Low trustworthy supply", 0.20, 1 - tsr),
    ]
    breakdown = pd.DataFrame([
        {"Component": name, "Weight × factor": f"{w:.2f} × {factor:.2f}",
         "Contribution": round(w * factor, 3)}
        for name, w, factor in comps
    ])
    total = min(sum(w * factor for _, w, factor in comps), 1.0)
    is_desert = bool(row.get("zero_facility_desert", False))
    return breakdown, total, is_desert


# Condition direction: higher value = worse burden, vs lower value = worse access gap.
_COND_HIGH_BAD = {
    "all_w15_49_who_are_anaemic_pct",
    "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
}
# Everything else in COND_LABELS is an access/screening metric where LOWER = worse.


def _national_condition_medians(districts: pd.DataFrame) -> dict:
    out = {}
    if districts is None:
        return out
    for col in COND_LABELS:
        if col in districts.columns:
            med = pd.to_numeric(districts[col], errors="coerce").median()
            if pd.notna(med):
                out[col] = float(med)
    return out


def district_top_conditions(row: pd.Series, districts: pd.DataFrame, n: int = 6) -> pd.DataFrame:
    """The district's worst medical-condition gaps vs the national median.

    Tableau-style drill-down (think "Top 5 Cities" nested view): each condition gets
    its district value, the national median, and a signed Δ where **positive = worse
    than national**. Sorted by severity; only conditions worse than national surface.
    """
    nat = _national_condition_medians(districts)
    rows = []
    for col, label in COND_LABELS.items():
        if col not in row.index:
            continue
        val = pd.to_numeric(row.get(col), errors="coerce")
        if pd.isna(val):
            continue
        national = nat.get(col, float("nan"))
        high_bad = col in _COND_HIGH_BAD
        # Severity: how much WORSE than national, in percentage points.
        if pd.isna(national):
            severity = 0.0
            delta = float("nan")
        elif high_bad:
            delta = val - national          # higher burden than national = worse
            severity = delta
        else:
            delta = national - val          # lower access than national = worse (report as +)
            severity = delta
        rows.append({
            "Condition": label,
            "District %": round(float(val), 1),
            "National %": None if pd.isna(national) else round(float(national), 1),
            "Δ vs national": None if pd.isna(delta) else round(float(delta), 1),
            "kind": "burden" if high_bad else "access",
            "_sev": severity,
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # Surface the worst gaps first (most worse-than-national).
    df = df.sort_values("_sev", ascending=False).head(n).drop(columns=["_sev"]).reset_index(drop=True)
    return df


def facility_explanation(row: pd.Series) -> pd.DataFrame:
    sources = ", ".join(_json_list(row.get("external_evidence_sources_to_check"))) or "Source URLs / registry search"
    return pd.DataFrame(
        [
            {
                "Signal": "Active uncertainty",
                "Value": f"#{int(row.get('active_uncertainty_rank', 0))} · {_score(row.get('active_uncertainty_score'))}",
                "Interpretation": f"Action: {str(row.get('active_learning_action', '')).replace('_', ' ')}.",
            },
            {
                "Signal": "Proxy trust band",
                "Value": f"{_score(row.get('proxy_trust_interval_low'))} to {_score(row.get('proxy_trust_interval_high'))}",
                "Interpretation": "Heuristic evidence-quality band, not measured accuracy.",
            },
            {
                "Signal": "External geo uncertainty",
                "Value": f"{_score(row.get('external_geo_uncertainty_score'))}; {row.get('pre_geocode_uncertainty_band_low_km', 'unknown')} to {row.get('pre_geocode_uncertainty_band_high_km', 'unknown')} km",
                "Interpretation": str(row.get("external_validation_action", "")).replace("_", " "),
            },
            {
                "Signal": "Capacity estimate",
                "Value": f"{row.get('capacity_display_value', 'unknown')} ({row.get('capacity_estimate_interval_low', 'unknown')} to {row.get('capacity_estimate_interval_high', 'unknown')})",
                "Interpretation": f"{row.get('capacity_status', 'unknown')} with interval width {_score(row.get('capacity_relative_interval_width'))}.",
            },
            {
                "Signal": "Doctor estimate",
                "Value": f"{row.get('doctor_count_display_value', 'unknown')} ({row.get('doctor_count_estimate_interval_low', 'unknown')} to {row.get('doctor_count_estimate_interval_high', 'unknown')})",
                "Interpretation": f"{row.get('doctor_count_status', 'unknown')} with interval width {_score(row.get('doctor_count_relative_interval_width'))}.",
            },
            {
                "Signal": "Join and geo",
                "Value": f"join {_score(row.get('join_confidence'))}; {row.get('geo_quality', 'unknown')}",
                "Interpretation": "Facility-to-district health context depends on this join quality.",
            },
            {
                "Signal": "Evidence to check",
                "Value": sources,
                "Interpretation": "Independent agreement can narrow uncertainty; conflicts keep the row fragile.",
            },
        ]
    )


def geo_candidate_explanation(row: pd.Series) -> tuple[pd.DataFrame, pd.DataFrame]:
    checks = pd.DataFrame(
        [
            {
                "Check": "Current geo failure",
                "Value": str(row.get("geo_review_reason", "unknown")).replace("_", " "),
                "Why it matters": "Wrong coordinates can make supply appear in the wrong district.",
            },
            {
                "Check": "Pre-geocode uncertainty band",
                "Value": f"{row.get('pre_geocode_uncertainty_band_low_km', 'unknown')} to {row.get('pre_geocode_uncertainty_band_high_km', 'unknown')} km",
                "Why it matters": "This is the planning uncertainty before Google/Mappls or registry evidence.",
            },
            {
                "Check": "Fuzzy precheck",
                "Value": str(row.get("fuzzy_precheck_status", "unknown")).replace("_", " "),
                "Why it matters": str(row.get("fuzzy_precheck_reasons", "") or "No precheck conflict recorded."),
            },
            {
                "Check": "External validation action",
                "Value": str(row.get("external_validation_action", "unknown")).replace("_", " "),
                "Why it matters": str(row.get("geocoder_acceptance_rule", "") or "Compare geocoder metadata with admin geography."),
            },
            {
                "Check": "Expected precision",
                "Value": str(row.get("geocoder_expected_precision_after_success", "unknown")).replace("_", " "),
                "Why it matters": "Facility routing requires stronger precision than district/H3 planning.",
            },
        ]
    )
    reasons = pd.DataFrame(
        {
            "Reason code": reason_labels(row.get("external_uncertainty_reason_codes")),
        }
    )
    return checks, reasons


def load_districts() -> pd.DataFrame:
    """Load the cleaned district table (CSV or warehouse, same as facilities)."""
    if os.environ.get("DATA_BACKEND", "csv").lower() == "warehouse":
        with _wh_connect() as conn, conn.cursor() as cur:
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


def filter_facilities_to_districts(facilities: pd.DataFrame, districts: pd.DataFrame) -> pd.DataFrame:
    """Restrict facility rows to a district subset without dropping non-mappable rows."""
    if facilities is None:
        return pd.DataFrame()
    if districts is None or districts.empty or facilities.empty:
        return pd.DataFrame(columns=facilities.columns)
    join_cols = ["district_name", "state_ut"]
    if not set(join_cols).issubset(facilities.columns) or not set(join_cols).issubset(districts.columns):
        return facilities.copy()
    keys = districts[join_cols].dropna().drop_duplicates().copy()
    if keys.empty:
        return pd.DataFrame(columns=facilities.columns)
    f = facilities.copy()
    f["_district_scope_key"] = f["district_name"].astype(str).str.strip().str.casefold()
    f["_state_scope_key"] = f["state_ut"].astype(str).str.strip().str.casefold()
    keys["_district_scope_key"] = keys["district_name"].astype(str).str.strip().str.casefold()
    keys["_state_scope_key"] = keys["state_ut"].astype(str).str.strip().str.casefold()
    scoped = f.merge(
        keys[["_district_scope_key", "_state_scope_key"]].drop_duplicates(),
        on=["_district_scope_key", "_state_scope_key"],
        how="inner",
    )
    return scoped.drop(columns=["_district_scope_key", "_state_scope_key"], errors="ignore")


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
            "Failure mode": "Uncertainty review burden",
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
    artifact = _read_optional_csv(config.geo_validation_candidates_path())
    if not artifact.empty:
        artifact = _coerce_known_numeric(artifact)
        if "current_coordinates" not in artifact and {"facility_latitude", "facility_longitude"}.issubset(artifact.columns):
            artifact["current_coordinates"] = (
                pd.to_numeric(artifact["facility_latitude"], errors="coerce").round(6).astype(str)
                + ", "
                + pd.to_numeric(artifact["facility_longitude"], errors="coerce").round(6).astype(str)
            )
        if "first_source_url" not in artifact and "source_urls" in artifact:
            artifact["first_source_url"] = artifact["source_urls"].map(_first_url)
        sort_col = "external_validation_priority_score"
        if sort_col not in artifact:
            sort_col = "geo_review_score" if "geo_review_score" in artifact else artifact.columns[0]
        return artifact.sort_values(sort_col, ascending=False).head(top_n).reset_index(drop=True)

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
    """Build a prioritized facility queue for source enrichment and uncertainty review."""
    d = facilities.copy()
    signal_col = config.SPECIALTIES.get(specialty)
    if signal_col and signal_col in d.columns:
        d = d[d[signal_col].fillna(False).astype(bool)].copy()
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
    elif focus in {"Manual review queue", "Uncertainty review queue"}:
        d = d[d["needs_human_review"]]
        d = d.sort_values("review_priority", ascending=False)
    else:
        d = d.sort_values("review_priority", ascending=False)

    cols = [
        "unique_id", "facility_name", "facilityTypeId", "address_city", "district_name", "state_ut",
        "facility_latitude", "facility_longitude",
        "service_signal", "primary_concern", "verification_channel", "label_seed",
        "review_priority", "data_readiness_score", "join_confidence", "geo_quality",
        "officialPhone", "email", "officialWebsite", "first_source_url", "claim_text", "source_urls",
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
        "unique_id": d["unique_id"].fillna(""),
        "facility_name": d["facility_name"].fillna("Unnamed facility"),
        "facility_type": d["facilityTypeId"].fillna("—"),
        "city": d["address_city"].fillna("—"),
        "state": d["address_stateOrRegion"].fillna("—"),
        "district": d["district_name"].fillna("—"),
        "pincode": d.get("pincode_extracted", pd.Series("", index=d.index)).fillna(""),
        "geo_quality": d["geo_quality"].fillna("—"),
        "geo_distance_km_to_pincode_centroid": d["geo_distance_km_to_pincode_centroid"],
        "join_strategy": d.get("join_strategy", pd.Series("", index=d.index)).fillna(""),
        "join_confidence": d.get("join_confidence", pd.Series(np.nan, index=d.index)),
        "join_uncertainty_reason": d.get("join_uncertainty_reason", pd.Series("", index=d.index)).fillna(""),
        "data_readiness_score": d.get("data_readiness_score", pd.Series(np.nan, index=d.index)),
        "semantic_data_quality_score": d.get("semantic_data_quality_score", pd.Series(np.nan, index=d.index)),
        "supply_data_confidence_score": d.get("supply_data_confidence_score", pd.Series(np.nan, index=d.index)),
        "capacity_display_value": d.get("capacity_display_value", d.get("capacity_estimate", pd.Series(np.nan, index=d.index))),
        "capacity_estimate_interval_low": d.get("capacity_estimate_interval_low", pd.Series(np.nan, index=d.index)),
        "capacity_estimate_interval_high": d.get("capacity_estimate_interval_high", pd.Series(np.nan, index=d.index)),
        "capacity_confidence": d.get("capacity_confidence", pd.Series("", index=d.index)).fillna(""),
        "capacity_is_estimated": d.get("capacity_is_estimated", pd.Series(False, index=d.index)),
        "doctor_count_display_value": d.get("doctor_count_display_value", d.get("doctor_count_estimate", pd.Series(np.nan, index=d.index))),
        "doctor_count_estimate_interval_low": d.get("doctor_count_estimate_interval_low", pd.Series(np.nan, index=d.index)),
        "doctor_count_estimate_interval_high": d.get("doctor_count_estimate_interval_high", pd.Series(np.nan, index=d.index)),
        "doctor_count_confidence": d.get("doctor_count_confidence", pd.Series("", index=d.index)).fillna(""),
        "doctor_count_is_estimated": d.get("doctor_count_is_estimated", pd.Series(False, index=d.index)),
        "semantic_missing_critical_count": d.get("semantic_missing_critical_count", pd.Series(np.nan, index=d.index)),
        "has_source_urls": d["has_source_urls"],
        "has_contact_evidence": d["has_contact_evidence"],
        "pincode_is_ambiguous": d.get("pincode_is_ambiguous", pd.Series(False, index=d.index)),
        "pincode_region_is_ambiguous": d.get("pincode_region_is_ambiguous", pd.Series(False, index=d.index)),
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


def district_hexes(districts: pd.DataFrame, resolution: int = 5) -> pd.DataFrame:
    """One care-gap hex per district centroid (incl. zero-facility deserts).

    Mirrors VF Match's "medical deserts" layer: green (low gap / good coverage) →
    red (high gap / desert). This is how the 212 zero-facility deserts finally
    appear on the map. Colored by care_gap_score, normalized across districts.
    """
    cols = ["h3", "fill_color", "district_name", "state_ut", "care_gap_score",
            "health_need_score", "trustworthy_supply_rate", "observed_facility_rows",
            "zero_facility_desert", "lat", "lon", "tip"]
    if districts is None or districts.empty:
        return pd.DataFrame(columns=cols)
    d = districts.dropna(subset=["district_latitude", "district_longitude"]).copy()
    if d.empty:
        return pd.DataFrame(columns=cols)

    gap = pd.to_numeric(d["care_gap_score"], errors="coerce")
    vmin, vmax = float(gap.min()), float(gap.max())
    span = (vmax - vmin) or 1.0
    d["h3"] = [h3.latlng_to_cell(la, lo, resolution)
               for la, lo in zip(d["district_latitude"], d["district_longitude"])]
    # If two district centroids collide in one cell, keep the worse (higher) gap.
    d = d.sort_values("care_gap_score", ascending=False).drop_duplicates("h3")

    desert = d.get("zero_facility_desert", pd.Series(False, index=d.index)).fillna(False).astype(bool)
    d["fill_color"] = [
        _ramp((float(g) - vmin) / span, higher_is_worse=True) + [220]
        if pd.notna(g) else list(_COLOR_UNKNOWN)
        for g in gap.loc[d.index]
    ]
    obs = pd.to_numeric(d["observed_facility_rows"], errors="coerce").fillna(0).astype(int)
    tsr = pd.to_numeric(d["trustworthy_supply_rate"], errors="coerce")
    tag = np.where(desert, "🏜️ Zero mapped facilities", obs.astype(str) + " facilities")
    d["tip"] = ("<b>" + d["district_name"].fillna("—") + ", " + d["state_ut"].fillna("—") + "</b><br/>"
                + "Care gap: " + gap.loc[d.index].round(2).astype(str)
                + " · Need: " + pd.to_numeric(d["health_need_score"], errors="coerce").round(2).astype(str)
                + "<br/>" + tag)
    out = d.rename(columns={"district_latitude": "lat", "district_longitude": "lon"})
    out["zero_facility_desert"] = desert.values
    return out[cols]
