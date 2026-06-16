#!/usr/bin/env python3
"""Prepare India geo-validation batches and Databricks AI SQL.

This does not call Google Maps or Mappls. It creates:
- a prioritized CSV of geo-invalid/suspicious facility rows;
- JSONL prompts for row-by-row model-serving experiments;
- Databricks SQL files for the parallel CLI workflow:
  1) summarize current geo failures;
  2) run ai_query as the LLM "janitor" over candidate addresses;
  3) reconcile parsed addresses against the existing PIN/state/district fuzzy signals.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
SQL_DIR = ROOT / "output" / "sql"

FACILITY_CSV = DATA_DIR / "facility_health_cleaned.csv"
UC_FACILITY_TABLE = "workspace.default.hackathon_facility_health_cleaned"
UC_CANDIDATE_TABLE = "workspace.default.hackathon_geo_validation_candidates"
UC_JANITOR_TABLE = "workspace.default.hackathon_geo_address_janitor"
UC_RECONCILIATION_TABLE = "workspace.default.hackathon_geo_fuzzy_reconciliation"

DEFAULT_ENDPOINT = "databricks-gemini-3-5-flash"

USECOLS = [
    "unique_id",
    "facility_name",
    "facilityTypeId",
    "pincode_extracted",
    "pincode_primary_district",
    "pincode_primary_state",
    "pincode_n_districts",
    "pincode_n_states",
    "pincode_is_ambiguous",
    "district_name",
    "state_ut",
    "address_line1",
    "address_line2",
    "address_line3",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "facility_latitude",
    "facility_longitude",
    "geo_quality",
    "geo_distance_km_to_pincode_centroid",
    "contradicted_or_geo_invalid_signal",
    "join_strategy",
    "join_confidence",
    "join_match_score",
    "join_uncertainty_reason",
    "data_readiness_score",
    "health_need_score",
    "semantic_data_quality_score",
    "supply_data_confidence_score",
    "medical_desert_priority_score",
    "source_urls",
]

GEOCODER_PRIORS = [
    {
        "provider_status": "OK",
        "location_type": "ROOFTOP",
        "partial_match": False,
        "proxy_confidence_low": 0.86,
        "proxy_confidence_high": 0.96,
        "planning_uncertainty_radius_km": 0.10,
        "recommended_action": "accept_if_admin_and_pincode_match",
        "explainability_note": "Precise geocode, but still corroborate state/district/PIN against India Post before treating it as facility-level evidence.",
    },
    {
        "provider_status": "OK",
        "location_type": "RANGE_INTERPOLATED",
        "partial_match": False,
        "proxy_confidence_low": 0.68,
        "proxy_confidence_high": 0.84,
        "planning_uncertainty_radius_km": 0.50,
        "recommended_action": "accept_for_planning_if_boundary_checks_pass",
        "explainability_note": "Approximate street-segment geocode; usable for district/H3 planning if it stays inside the expected PIN/district.",
    },
    {
        "provider_status": "OK",
        "location_type": "GEOMETRIC_CENTER",
        "partial_match": False,
        "proxy_confidence_low": 0.48,
        "proxy_confidence_high": 0.68,
        "planning_uncertainty_radius_km": 3.00,
        "recommended_action": "use_for_neighborhood_only_or_retry_with_landmark",
        "explainability_note": "Center of a region/street/polygon rather than a facility doorstep; fine for coarse maps, weak for facility routing.",
    },
    {
        "provider_status": "OK",
        "location_type": "APPROXIMATE",
        "partial_match": False,
        "proxy_confidence_low": 0.20,
        "proxy_confidence_high": 0.48,
        "planning_uncertainty_radius_km": 25.00,
        "recommended_action": "retry_with_landmark_or_alternate_provider",
        "explainability_note": "Approximate result should remain in the uncertainty queue unless another external source corroborates it.",
    },
    {
        "provider_status": "OK",
        "location_type": "ANY",
        "partial_match": True,
        "proxy_confidence_low": 0.18,
        "proxy_confidence_high": 0.60,
        "planning_uncertainty_radius_km": 15.00,
        "recommended_action": "compare_name_admin_pincode_then_queue_if_high_impact",
        "explainability_note": "Partial matches can be right or wrong; the product should explain which address tokens matched and which did not.",
    },
    {
        "provider_status": "ZERO_RESULTS",
        "location_type": "NONE",
        "partial_match": False,
        "proxy_confidence_low": 0.00,
        "proxy_confidence_high": 0.18,
        "planning_uncertainty_radius_km": None,
        "recommended_action": "search_hfr_pmjay_mappls_osm_or_mark_unknown",
        "explainability_note": "No geocoder result is not proof the facility is fake; treat it as missing external evidence.",
    },
]


SYSTEM_PROMPT = """You clean Indian healthcare facility addresses for geocoding.
Return only valid JSON with these keys:
door_or_plot, floor_or_unit, landmark_context, landmark_name, locality, city,
state, pincode, geocoder_query, confidence, notes.

Rules:
- Do not invent coordinates.
- Preserve useful landmarks such as Near, Opposite, Behind, Next to.
- Remove floor/room/delivery instructions from geocoder_query unless needed.
- Use a 6 digit Indian PIN only if present in the source text.
- Always keep the query India-specific.
- confidence is 0.0 to 1.0.
"""

STATE_ALIASES = {
    "andamanandnicobarislands": "andamannicobar",
    "andamannicobarislands": "andamannicobar",
    "andhrapradesh": "andhrapradesh",
    "arunachalpradesh": "arunachalpradesh",
    "assam": "assam",
    "bihar": "bihar",
    "chandigarh": "chandigarh",
    "chattisgarh": "chhattisgarh",
    "chhattisgarh": "chhattisgarh",
    "dadraandnagarhaveli": "dadranagarhaveli",
    "dadraandnagarhavelianddamananddiu": "dadranagarhavelidamandiu",
    "damananddiu": "damandiu",
    "delhi": "delhi",
    "nctofdelhi": "delhi",
    "goa": "goa",
    "gujarat": "gujarat",
    "haryana": "haryana",
    "himachalpradesh": "himachalpradesh",
    "jammuandkashmir": "jammukashmir",
    "jammukashmir": "jammukashmir",
    "jharkhand": "jharkhand",
    "karnataka": "karnataka",
    "kerala": "kerala",
    "ladakh": "ladakh",
    "lakshadweep": "lakshadweep",
    "madhyapradesh": "madhyapradesh",
    "maharastra": "maharashtra",
    "maharashtra": "maharashtra",
    "manipur": "manipur",
    "meghalaya": "meghalaya",
    "mizoram": "mizoram",
    "nagaland": "nagaland",
    "odisha": "odisha",
    "orissa": "odisha",
    "puducherry": "puducherry",
    "pondicherry": "puducherry",
    "punjab": "punjab",
    "rajasthan": "rajasthan",
    "sikkim": "sikkim",
    "tamilnadu": "tamilnadu",
    "telangana": "telangana",
    "tripura": "tripura",
    "uttarpradesh": "uttarpradesh",
    "uttarakhand": "uttarakhand",
    "uttaranchal": "uttarakhand",
    "westbengal": "westbengal",
}

DISTRICT_ALIASES = {
    ("assam", "kamrupmetro"): "kamrupmetropolitan",
    ("haryana", "gurugram"): "gurgaon",
    ("jharkhand", "eastsinghbhum"): "purbisinghbhum",
    ("jharkhand", "seraikelakharsawan"): "saraikelakharsawan",
    ("jharkhand", "westsinghbhum"): "pashchimisinghbhum",
    ("karnataka", "ballari"): "bellary",
    ("karnataka", "belagavi"): "belgaum",
    ("karnataka", "bengaluru"): "bangalore",
    ("karnataka", "bengalururural"): "bangalorerural",
    ("karnataka", "bengaluruurban"): "bangalore",
    ("karnataka", "bangaloreurban"): "bangalore",
    ("maharashtra", "ahmednagar"): "ahmadnagar",
    ("maharashtra", "beed"): "bid",
    ("maharashtra", "raigad"): "raigarh",
    ("punjab", "sasnagar"): "sahibzadaajitsinghnagar",
    ("uttarpradesh", "prayagraj"): "allahabad",
    ("westbengal", "24paraganasnorth"): "northtwentyfourpargana",
    ("westbengal", "24paraganassouth"): "southtwentyfourpargana",
    ("westbengal", "coochbehar"): "kochbihar",
    ("westbengal", "darjeeling"): "darjiling",
    ("westbengal", "hooghly"): "hugli",
    ("westbengal", "howrah"): "haora",
    ("westbengal", "malda"): "maldah",
    ("westbengal", "north24parganas"): "northtwentyfourpargana",
    ("westbengal", "paschimbardhaman"): "paschimbarddhaman",
    ("westbengal", "purulia"): "puruliya",
    ("westbengal", "south24parganas"): "southtwentyfourpargana",
}


def clean_value(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "—"}:
        return ""
    return text


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip().lower().replace("&", "and")
    return re.sub(r"[^a-z0-9]+", "", value)


def normalize_state(value) -> str:
    raw = normalize_text(value)
    return STATE_ALIASES.get(raw, raw)


def normalize_district(value, state_value="") -> str:
    state_norm = normalize_state(state_value)
    district_norm = normalize_text(value)
    return DISTRICT_ALIASES.get((state_norm, district_norm), district_norm)


def first_pin(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    match = re.search(r"(?<!\d)([1-9]\d{5})(?!\d)", text)
    if match:
        return match.group(1)
    try:
        parsed = int(float(text))
    except ValueError:
        return ""
    parsed_text = str(parsed)
    return parsed_text if re.fullmatch(r"[1-9]\d{5}", parsed_text) else ""


def boolish(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y"}


def district_similarity(row: pd.Series) -> float | None:
    facility_city = normalize_district(row.get("address_city"), row.get("address_stateOrRegion"))
    pin_district = normalize_district(row.get("pincode_primary_district"), row.get("pincode_primary_state"))
    if not facility_city or not pin_district:
        return None
    return round(difflib.SequenceMatcher(None, facility_city, pin_district).ratio(), 3)


def state_match(row: pd.Series) -> str:
    facility_state = normalize_state(row.get("address_stateOrRegion"))
    pin_state = normalize_state(row.get("pincode_primary_state"))
    if not facility_state or not pin_state:
        return "missing"
    return "match" if facility_state == pin_state else "conflict"


def fuzzy_precheck_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if not row.get("pincode_extracted_clean"):
        reasons.append("missing_or_unparseable_pin")
    if bool(row.get("pincode_is_ambiguous_bool")):
        reasons.append("ambiguous_pin_bridge")
    if row.get("state_pincode_state_match") == "conflict":
        reasons.append("state_pin_conflict")
    similarity = row.get("city_pincode_district_similarity")
    if pd.notna(similarity) and similarity < 0.72:
        reasons.append("city_pin_district_conflict")
    join_confidence = pd.to_numeric(pd.Series([row.get("join_confidence")]), errors="coerce").iloc[0]
    if pd.notna(join_confidence) and join_confidence < 0.8:
        reasons.append("weak_health_join")
    return reasons


def geocoder_review_hint(reasons: list[str]) -> str:
    if "state_pin_conflict" in reasons:
        return "Do not trust existing coordinates until geocoder result agrees with the PIN/state."
    if "city_pin_district_conflict" in reasons:
        return "Try landmark + locality + city first; then compare returned district to the PIN bridge."
    if "ambiguous_pin_bridge" in reasons:
        return "Accept only if geocoder state/district matches the facility address or authoritative registry."
    if "missing_or_unparseable_pin" in reasons:
        return "Use geocoder plus external registry because PIN cannot anchor the address."
    if "weak_health_join" in reasons:
        return "Geo may be usable, but downstream district health join should remain uncertain."
    return "Run India-restricted geocoder and accept only precise or locality-consistent results."


def raw_address(row: pd.Series) -> str:
    pieces = []
    seen = set()
    for col in [
        "facility_name",
        "address_line1",
        "address_line2",
        "address_line3",
        "address_city",
        "address_stateOrRegion",
        "address_zipOrPostcode",
    ]:
        value = clean_value(row.get(col))
        key = value.lower()
        if value and key not in seen:
            pieces.append(value)
            seen.add(key)
    pieces.append("India")
    return ", ".join(pieces)


def geo_reason(row: pd.Series) -> str:
    geo = clean_value(row.get("geo_quality")).lower()
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


def geo_uncertainty_band(row: pd.Series) -> tuple[float, float]:
    """Heuristic planning band for current coordinate disagreement.

    This is not calibrated geocoder accuracy. It makes the size of the current
    geo problem visible before Google/Mappls or registry evidence is attached.
    """

    geo = clean_value(row.get("geo_quality")).lower()
    distance = pd.to_numeric(row.get("geo_distance_km_to_pincode_centroid"), errors="coerce")
    if pd.isna(distance):
        distance = 0.0
    distance = float(max(distance, 0.0))
    if "outside" in geo:
        return 50.0, round(min(max(distance, 250.0), 5000.0), 1)
    if "far" in geo:
        return 10.0, round(min(max(distance, 50.0), 2500.0), 1)
    if "moderate" in geo:
        return 2.0, round(min(max(distance, 10.0), 250.0), 1)
    if "missing" in geo:
        return 10.0, 250.0
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return 5.0, round(min(max(distance, 25.0), 1000.0), 1)
    return 0.1, 5.0


def external_validation_action(row: pd.Series) -> str:
    geo = clean_value(row.get("geo_quality")).lower()
    high_impact = pd.to_numeric(row.get("medical_desert_priority_score"), errors="coerce")
    high_impact = 0 if pd.isna(high_impact) else float(high_impact)
    if "outside" in geo:
        return "replace_coordinate_with_external_geocode"
    if "missing" in geo:
        return "geocode_missing_coordinate"
    if "far" in geo:
        return "geocode_and_compare_pincode_district"
    if "moderate" in geo and high_impact >= 0.6:
        return "high_impact_geocode_precision_check"
    if "moderate" in geo:
        return "batch_geocode_precision_check"
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        return "external_source_contradiction_check"
    return "monitor"


def geocoder_acceptance_rule(row: pd.Series) -> str:
    action = external_validation_action(row)
    if action == "replace_coordinate_with_external_geocode":
        return "Accept only ROOFTOP/RANGE_INTERPOLATED with India + expected state/PIN match; otherwise keep contradicted."
    if action == "geocode_missing_coordinate":
        return "Use geocoder result as candidate coordinate; require formatted address or registry source before calling it passed checks."
    if action == "geocode_and_compare_pincode_district":
        return "Accept if geocoded coordinate is inside expected pincode/district envelope or explains the current mismatch."
    if action == "high_impact_geocode_precision_check":
        return "Require ROOFTOP/RANGE_INTERPOLATED or independent registry/Mappls agreement before reducing uncertainty."
    if action == "batch_geocode_precision_check":
        return "Use GEOMETRIC_CENTER only for district/H3 maps; keep facility-level routing uncertainty visible."
    return "Compare name, state, district, PIN, and provider metadata before changing trust posture."


def external_evidence_sources(row: pd.Series) -> str:
    sources = ["Google Geocoding API", "India Post pincode bridge"]
    geo = clean_value(row.get("geo_quality")).lower()
    if "far" in geo or "outside" in geo or "missing" in geo:
        sources.append("Mappls/MapmyIndia fallback")
    if clean_value(row.get("facilityTypeId")).lower() in {"hospital", "clinic"}:
        sources.extend(["ABDM/HFR registry", "PM-JAY empanelled hospitals"])
    sources.append("OSM/Overture POI cross-check")
    return json.dumps(sources, ensure_ascii=True)


def external_reason_codes(row: pd.Series) -> str:
    distance = pd.to_numeric(row.get("geo_distance_km_to_pincode_centroid"), errors="coerce")
    join_conf = pd.to_numeric(row.get("join_confidence"), errors="coerce")
    readiness = pd.to_numeric(row.get("data_readiness_score"), errors="coerce")
    medical_desert = pd.to_numeric(row.get("medical_desert_priority_score"), errors="coerce")
    geo = clean_value(row.get("geo_quality")).lower()
    reasons = []
    if "outside" in geo:
        reasons.append("current_coordinate_outside_india")
    if "missing" in geo:
        reasons.append("missing_coordinate")
    if "far" in geo:
        reasons.append("far_from_pincode_centroid")
    if "moderate" in geo:
        reasons.append("moderate_distance_from_pincode_centroid")
    if pd.notna(distance) and distance >= 50:
        reasons.append("large_coordinate_pincode_disagreement")
    if bool(row.get("contradicted_or_geo_invalid_signal", False)):
        reasons.append("existing_contradiction_flag")
    if pd.notna(join_conf) and join_conf < 0.8:
        reasons.append("low_join_confidence")
    if pd.notna(readiness) and readiness < 0.7:
        reasons.append("low_data_readiness")
    if pd.notna(medical_desert) and medical_desert >= 0.6:
        reasons.append("high_decision_impact")
    return json.dumps(reasons, ensure_ascii=True, sort_keys=True)


def add_external_uncertainty_fields(out: pd.DataFrame) -> pd.DataFrame:
    bands = out.apply(geo_uncertainty_band, axis=1, result_type="expand")
    out["pre_geocode_uncertainty_band_low_km"] = bands[0]
    out["pre_geocode_uncertainty_band_high_km"] = bands[1]
    out["external_validation_action"] = out.apply(external_validation_action, axis=1)
    out["geocoder_expected_precision_after_success"] = out["external_validation_action"].map(
        {
            "replace_coordinate_with_external_geocode": "rooftop_or_range_interpolated_required",
            "geocode_missing_coordinate": "rooftop_or_range_interpolated_preferred",
            "geocode_and_compare_pincode_district": "range_interpolated_or_better",
            "high_impact_geocode_precision_check": "rooftop_or_independent_source_agreement",
            "batch_geocode_precision_check": "geometric_center_ok_for_h3_only",
            "external_source_contradiction_check": "independent_source_agreement_required",
            "monitor": "no_external_geocode_required",
        }
    )
    out["geocoder_acceptance_rule"] = out.apply(geocoder_acceptance_rule, axis=1)
    out["external_evidence_sources_to_check"] = out.apply(external_evidence_sources, axis=1)
    out["external_uncertainty_reason_codes"] = out.apply(external_reason_codes, axis=1)
    out["google_response_fields_to_store"] = json.dumps(
        [
            "status",
            "formatted_address",
            "place_id",
            "geometry.location.lat",
            "geometry.location.lng",
            "geometry.location_type",
            "partial_match",
            "plus_code",
        ],
        ensure_ascii=True,
    )
    readiness_gap = 1 - pd.to_numeric(out.get("data_readiness_score"), errors="coerce").fillna(0.5).clip(0, 1)
    health_need = pd.to_numeric(out.get("health_need_score"), errors="coerce").fillna(0.5).clip(0, 1)
    geo_score = pd.to_numeric(out["geo_review_score"], errors="coerce").fillna(0)
    geo_score = (geo_score / max(float(geo_score.max()), 1.0)).clip(0, 1)
    out["external_validation_priority_score"] = (
        0.55 * geo_score
        + 0.20 * pd.to_numeric(out["medical_desert_priority_score"], errors="coerce").fillna(0).clip(0, 1)
        + 0.15 * health_need
        + 0.10 * readiness_gap
    ).clip(0, 1).round(4)
    out["external_validation_note"] = (
        "External evidence reduces location uncertainty only when provider metadata agrees with India Post/NFHS admin geography; "
        "otherwise keep the row in the active uncertainty queue."
    )
    return out


def build_candidates(limit: int, exclude_ids: set[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(FACILITY_CSV, usecols=USECOLS, low_memory=False)
    for col in [
        "facility_latitude",
        "facility_longitude",
        "geo_distance_km_to_pincode_centroid",
        "pincode_n_districts",
        "pincode_n_states",
        "join_confidence",
        "join_match_score",
        "data_readiness_score",
        "health_need_score",
        "semantic_data_quality_score",
        "supply_data_confidence_score",
        "medical_desert_priority_score",
    ]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["contradicted_or_geo_invalid_signal"] = (
        df["contradicted_or_geo_invalid_signal"].astype("boolean").fillna(False).astype(bool)
    )
    df["pincode_is_ambiguous_bool"] = df["pincode_is_ambiguous"].map(boolish)
    df["address_pincode_clean"] = df["address_zipOrPostcode"].map(first_pin)
    df["pincode_extracted_clean"] = df["pincode_extracted"].map(first_pin)
    df["pincode_extracted_clean"] = df["pincode_extracted_clean"].where(
        df["pincode_extracted_clean"].ne(""),
        df["address_pincode_clean"],
    )
    df["facility_state_norm_review"] = df["address_stateOrRegion"].map(normalize_state)
    df["facility_city_norm_review"] = df.apply(
        lambda row: normalize_district(row["address_city"], row["address_stateOrRegion"]),
        axis=1,
    )
    df["pincode_state_norm_review"] = df["pincode_primary_state"].map(normalize_state)
    df["pincode_district_norm_review"] = df.apply(
        lambda row: normalize_district(row["pincode_primary_district"], row["pincode_primary_state"]),
        axis=1,
    )
    df["state_pincode_state_match"] = df.apply(state_match, axis=1)
    df["city_pincode_district_similarity"] = df.apply(district_similarity, axis=1)
    df["address_pin_matches_bridge_pin"] = (
        df["address_pincode_clean"].ne("")
        & df["pincode_extracted_clean"].ne("")
        & df["address_pincode_clean"].eq(df["pincode_extracted_clean"])
    )

    geo = df["geo_quality"].astype(str).str.lower()
    mask = (
        df["contradicted_or_geo_invalid_signal"]
        | geo.str.contains("outside|far|moderate|missing", na=False)
        | df["facility_latitude"].isna()
        | df["facility_longitude"].isna()
    )
    out = df[mask].copy()
    if exclude_ids:
        out = out[~out["unique_id"].astype(str).isin(exclude_ids)].copy()
    distance = out["geo_distance_km_to_pincode_centroid"].fillna(-1)
    out["geo_review_reason"] = out.apply(geo_reason, axis=1)
    out["raw_india_address"] = out.apply(raw_address, axis=1)
    out["geocoder_query"] = out["raw_india_address"]
    out["_fuzzy_reasons"] = out.apply(fuzzy_precheck_reasons, axis=1)
    out["fuzzy_precheck_status"] = out["_fuzzy_reasons"].map(lambda reasons: reasons[0] if reasons else "fuzzy_ok")
    out["fuzzy_precheck_reasons"] = out["_fuzzy_reasons"].map(lambda reasons: ";".join(reasons) if reasons else "fuzzy_ok")
    out["geocoder_review_hint"] = out["_fuzzy_reasons"].map(geocoder_review_hint)
    out["google_geocode_url_template"] = out["geocoder_query"].map(
        lambda q: "https://maps.googleapis.com/maps/api/geocode/json"
        f"?address={quote_plus(q)}&components=country:IN&key=$GOOGLE_MAPS_API_KEY"
    )
    state_conflict = out["state_pincode_state_match"].eq("conflict")
    city_conflict = out["city_pincode_district_similarity"].lt(0.72).fillna(False)
    weak_join = out["join_confidence"].fillna(0).lt(0.8)
    out["geo_review_score"] = (
        out["contradicted_or_geo_invalid_signal"].astype(float) * 50
        + geo[mask].str.contains("outside", na=False).astype(float) * 35
        + geo[mask].str.contains("far", na=False).astype(float) * 25
        + geo[mask].str.contains("moderate", na=False).astype(float) * 12
        + state_conflict.astype(float) * 25
        + city_conflict.astype(float) * 10
        + out["pincode_is_ambiguous_bool"].astype(float) * 8
        + out["pincode_extracted_clean"].eq("").astype(float) * 12
        + weak_join.astype(float) * 6
        + distance.clip(lower=0, upper=5000) / 100
        + out["medical_desert_priority_score"].fillna(0.0).clip(0, 1) * 8
    ).round(1)
    out = add_external_uncertainty_fields(out)
    out = out.drop(columns=["_fuzzy_reasons"])
    return out.sort_values("geo_review_score", ascending=False).head(limit).reset_index(drop=True)


def read_exclude_ids(path: Path | None) -> set[str]:
    if path is None:
        return set()
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, usecols=["unique_id"])
    return set(frame["unique_id"].dropna().astype(str))


def write_geocoder_priors(path: Path) -> None:
    pd.DataFrame(GEOCODER_PRIORS).to_csv(path, index=False)


def write_prompts(candidates: pd.DataFrame, path: Path, endpoint: str) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for _, row in candidates.iterrows():
            payload = {
                "unique_id": row["unique_id"],
                "endpoint": endpoint,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Address text: {row['raw_india_address']}"},
                ],
                "temperature": 0,
                "max_tokens": 300,
            }
            fh.write(json.dumps(payload, ensure_ascii=True) + "\n")


def sql_escape(text: str) -> str:
    return text.replace("'", "''")


def write_sql(endpoint: str, limit: int) -> None:
    SQL_DIR.mkdir(parents=True, exist_ok=True)
    summary_sql = SQL_DIR / "geo_validation_summary.sql"
    summary_sql.write_text(
        f"""-- Read-only geo-quality summary.
SELECT
  geo_quality,
  contradicted_or_geo_invalid_signal,
  COUNT(*) AS rows,
  ROUND(AVG(geo_distance_km_to_pincode_centroid), 1) AS avg_distance_km,
  ROUND(MAX(geo_distance_km_to_pincode_centroid), 1) AS max_distance_km
FROM {UC_FACILITY_TABLE}
GROUP BY geo_quality, contradicted_or_geo_invalid_signal
ORDER BY rows DESC;
	""",
        encoding="utf-8",
    )

    reconciliation_sql = SQL_DIR / "geo_fuzzy_reconciliation.sql"
    reconciliation_sql.write_text(
        f"""-- Reconciles LLM-parsed addresses with the existing pincode/district fuzzy signals.
-- Run after output/sql/geo_address_janitor_ai_query.sql.

CREATE OR REPLACE TABLE {UC_RECONCILIATION_TABLE} AS
WITH joined AS (
  SELECT
    c.*,
    j.model_response,
    j.parsed_address,
    regexp_replace(lower(coalesce(j.parsed_address.city, '')), '[^a-z0-9]+', '') AS parsed_city_norm,
    regexp_replace(lower(coalesce(j.parsed_address.state, '')), '[^a-z0-9]+', '') AS parsed_state_norm,
    regexp_extract(cast(j.parsed_address.pincode AS STRING), '([1-9][0-9]{{5}})', 1) AS parsed_pincode_clean
  FROM {UC_CANDIDATE_TABLE} c
  LEFT JOIN {UC_JANITOR_TABLE} j USING (unique_id)
),
scored AS (
  SELECT
    *,
    CASE
      WHEN parsed_city_norm = '' OR pincode_district_norm_review = '' THEN NULL
      ELSE ROUND(
        1.0 - (
          levenshtein(parsed_city_norm, pincode_district_norm_review)
          / CAST(greatest(length(parsed_city_norm), length(pincode_district_norm_review), 1) AS DOUBLE)
        ),
        3
      )
    END AS parsed_city_pincode_district_similarity,
    CASE
      WHEN parsed_state_norm = '' OR pincode_state_norm_review = '' THEN 'missing'
      WHEN parsed_state_norm = pincode_state_norm_review THEN 'match'
      ELSE 'conflict'
    END AS parsed_state_pincode_state_match,
    CASE
      WHEN coalesce(parsed_pincode_clean, '') = '' OR coalesce(pincode_extracted_clean, '') = '' THEN 'missing'
      WHEN parsed_pincode_clean = pincode_extracted_clean THEN 'match'
      ELSE 'conflict'
    END AS parsed_pin_match
  FROM joined
)
SELECT
  *,
  CASE
    WHEN parsed_address IS NULL OR parsed_address.geocoder_query IS NULL OR parsed_address.confidence IS NULL THEN 'llm_parse_missing'
    WHEN parsed_pin_match = 'conflict' THEN 'parsed_pin_conflict'
    WHEN parsed_state_pincode_state_match = 'conflict' THEN 'parsed_state_conflict'
    WHEN parsed_city_pincode_district_similarity < 0.72 THEN 'parsed_city_district_conflict'
    WHEN coalesce(parsed_address.confidence, 0) < 0.65 THEN 'low_llm_parse_confidence'
    WHEN fuzzy_precheck_status != 'fuzzy_ok' THEN 'pre_geocoder_review'
    ELSE 'ready_for_geocoder'
  END AS reconciliation_status,
  concat(
    'https://maps.googleapis.com/maps/api/geocode/json?address=',
    url_encode(coalesce(parsed_address.geocoder_query, raw_india_address)),
    '&components=country:IN&key=$GOOGLE_MAPS_API_KEY'
  ) AS cleaned_google_geocode_url_template
FROM scored;
""",
        encoding="utf-8",
    )

    lakeflow_sql = SQL_DIR / "lakeflow_geo_validation_pipeline.sql"
    lakeflow_sql.write_text(
        f"""-- Lakeflow/DLT production template for the geo validation workflow.
-- Do not run this file through a SQL warehouse. Use it as the SQL source for a
-- Lakeflow Declarative Pipeline when this becomes a scheduled data-quality job.

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_validation_candidates_mv
COMMENT 'Geo validation candidates using the same pincode/fuzzy triage logic as the hackathon batch.'
AS
SELECT *
FROM {UC_CANDIDATE_TABLE};

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_address_janitor_mv
COMMENT 'LLM parsed Indian addresses ready for geocoder validation.'
AS
SELECT *
FROM {UC_JANITOR_TABLE};

CREATE OR REFRESH MATERIALIZED VIEW workspace.default.hackathon_geo_fuzzy_reconciliation_mv
COMMENT 'Parsed address reconciliation against pincode, state, district, and join confidence signals.'
AS
SELECT *
FROM {UC_RECONCILIATION_TABLE};
""",
        encoding="utf-8",
    )

    candidate_sql = SQL_DIR / "geo_validation_candidates_create.sql"
    candidate_sql.write_text(
        f"""-- Creates the candidate table for geo validation.
-- Run with:
-- databricks experimental aitools tools query --profile 7474647301321645 \\
--   --warehouse 1b331b704066b677 --file output/sql/geo_validation_candidates_create.sql

CREATE OR REPLACE TABLE {UC_CANDIDATE_TABLE} AS
WITH base AS (
  SELECT
    unique_id,
    facility_name,
    facilityTypeId,
    pincode_extracted,
    pincode_primary_district,
    pincode_primary_state,
    pincode_n_districts,
    pincode_n_states,
    pincode_is_ambiguous,
    district_name,
    state_ut,
    address_line1,
    address_line2,
    address_line3,
    address_city,
    address_stateOrRegion,
    address_zipOrPostcode,
    facility_latitude,
    facility_longitude,
    geo_quality,
    geo_distance_km_to_pincode_centroid,
    contradicted_or_geo_invalid_signal,
    join_strategy,
    join_confidence,
    join_match_score,
    join_uncertainty_reason,
    data_readiness_score,
    health_need_score,
    CAST(NULL AS DOUBLE) AS semantic_data_quality_score,
    CAST(NULL AS DOUBLE) AS supply_data_confidence_score,
    medical_desert_priority_score,
    regexp_extract(concat(coalesce(cast(pincode_extracted AS STRING), ''), ' ', coalesce(address_zipOrPostcode, '')), '([1-9][0-9]{{5}})', 1) AS pincode_extracted_clean,
    regexp_replace(lower(coalesce(address_city, '')), '[^a-z0-9]+', '') AS facility_city_norm_review,
    regexp_replace(lower(coalesce(address_stateOrRegion, '')), '[^a-z0-9]+', '') AS facility_state_norm_review,
    regexp_replace(lower(coalesce(pincode_primary_district, '')), '[^a-z0-9]+', '') AS pincode_district_norm_review,
    regexp_replace(lower(coalesce(pincode_primary_state, '')), '[^a-z0-9]+', '') AS pincode_state_norm_review,
    concat_ws(', ',
      facility_name,
      address_line1,
      address_line2,
      address_line3,
      address_city,
      address_stateOrRegion,
      address_zipOrPostcode,
      'India'
    ) AS raw_india_address
  FROM {UC_FACILITY_TABLE}
  WHERE contradicted_or_geo_invalid_signal
     OR lower(geo_quality) RLIKE 'outside|far|moderate|missing'
     OR facility_latitude IS NULL
     OR facility_longitude IS NULL
  ORDER BY
    CASE WHEN contradicted_or_geo_invalid_signal THEN 1 ELSE 0 END DESC,
    coalesce(geo_distance_km_to_pincode_centroid, 0) DESC
  LIMIT {limit}
),
scored AS (
  SELECT
    *,
    CASE
      WHEN facility_state_norm_review = '' OR pincode_state_norm_review = '' THEN 'missing'
      WHEN facility_state_norm_review = pincode_state_norm_review THEN 'match'
      ELSE 'conflict'
    END AS state_pincode_state_match,
    CASE
      WHEN facility_city_norm_review = '' OR pincode_district_norm_review = '' THEN NULL
      ELSE ROUND(
        1.0 - (
          levenshtein(facility_city_norm_review, pincode_district_norm_review)
          / CAST(greatest(length(facility_city_norm_review), length(pincode_district_norm_review), 1) AS DOUBLE)
        ),
        3
      )
    END AS city_pincode_district_similarity
  FROM base
)
SELECT
  *,
  concat_ws(';',
    CASE WHEN pincode_extracted_clean = '' THEN 'missing_or_unparseable_pin' END,
    CASE WHEN coalesce(pincode_is_ambiguous, false) THEN 'ambiguous_pin_bridge' END,
    CASE WHEN state_pincode_state_match = 'conflict' THEN 'state_pin_conflict' END,
    CASE WHEN city_pincode_district_similarity < 0.72 THEN 'city_pin_district_conflict' END,
    CASE WHEN coalesce(join_confidence, 0) < 0.8 THEN 'weak_health_join' END
  ) AS fuzzy_precheck_reasons,
  CASE
    WHEN pincode_extracted_clean = '' THEN 'missing_or_unparseable_pin'
    WHEN coalesce(pincode_is_ambiguous, false) THEN 'ambiguous_pin_bridge'
    WHEN state_pincode_state_match = 'conflict' THEN 'state_pin_conflict'
    WHEN city_pincode_district_similarity < 0.72 THEN 'city_pin_district_conflict'
    WHEN coalesce(join_confidence, 0) < 0.8 THEN 'weak_health_join'
    ELSE 'fuzzy_ok'
  END AS fuzzy_precheck_status,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN 'replace_coordinate_with_external_geocode'
    WHEN lower(geo_quality) LIKE '%missing%' THEN 'geocode_missing_coordinate'
    WHEN lower(geo_quality) LIKE '%far%' THEN 'geocode_and_compare_pincode_district'
    WHEN lower(geo_quality) LIKE '%moderate%' AND coalesce(medical_desert_priority_score, 0) >= 0.6 THEN 'high_impact_geocode_precision_check'
    WHEN lower(geo_quality) LIKE '%moderate%' THEN 'batch_geocode_precision_check'
    WHEN contradicted_or_geo_invalid_signal THEN 'external_source_contradiction_check'
    ELSE 'monitor'
  END AS external_validation_action,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN 50.0
    WHEN lower(geo_quality) LIKE '%far%' THEN 10.0
    WHEN lower(geo_quality) LIKE '%moderate%' THEN 2.0
    WHEN lower(geo_quality) LIKE '%missing%' THEN 10.0
    WHEN contradicted_or_geo_invalid_signal THEN 5.0
    ELSE 0.1
  END AS pre_geocode_uncertainty_band_low_km,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 250.0), 250.0), 5000.0)
    WHEN lower(geo_quality) LIKE '%far%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 50.0), 50.0), 2500.0)
    WHEN lower(geo_quality) LIKE '%moderate%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 10.0), 10.0), 250.0)
    WHEN lower(geo_quality) LIKE '%missing%' THEN 250.0
    WHEN contradicted_or_geo_invalid_signal THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 25.0), 25.0), 1000.0)
    ELSE 5.0
  END AS pre_geocode_uncertainty_band_high_km,
  'Store status, formatted_address, place_id, geometry.location, geometry.location_type, partial_match, plus_code, provider, and timestamp.' AS google_response_fields_to_store,
  concat(
    'https://maps.googleapis.com/maps/api/geocode/json?address=',
    url_encode(raw_india_address),
    '&components=country:IN&key=$GOOGLE_MAPS_API_KEY'
  ) AS google_geocode_url_template
FROM scored;
""",
        encoding="utf-8",
    )

    janitor_sql = SQL_DIR / "geo_address_janitor_ai_query.sql"
    prompt = sql_escape(SYSTEM_PROMPT)
    janitor_sql.write_text(
        f"""-- Creates a Databricks AI "janitor" table for geo validation.
-- Run after output/sql/geo_validation_candidates_create.sql.

CREATE OR REPLACE TABLE {UC_JANITOR_TABLE} AS
WITH model_raw AS (
  SELECT
    unique_id,
    facility_name,
    raw_india_address,
    ai_query(
      '{endpoint}',
      concat('{prompt}\\nAddress text: ', raw_india_address)
    ) AS model_response
  FROM {UC_CANDIDATE_TABLE}
),
json_ready AS (
  SELECT
    *,
    coalesce(
      nullif(regexp_extract(model_response, '(?s)(\\\\{{.*\\\\}})', 1), ''),
      model_response
    ) AS model_response_json
  FROM model_raw
)
SELECT
  unique_id,
  facility_name,
  raw_india_address,
  model_response,
  model_response_json,
  from_json(
    model_response_json,
    'door_or_plot STRING, floor_or_unit STRING, landmark_context STRING, landmark_name STRING, locality STRING, city STRING, state STRING, pincode STRING, geocoder_query STRING, confidence DOUBLE, notes STRING'
  ) AS parsed_address
FROM json_ready;
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=250)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--exclude-ids-file", type=Path)
    parser.add_argument("--output-prefix", default="geo_validation")
    parser.add_argument("--skip-sql", action="store_true")
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQL_DIR.mkdir(parents=True, exist_ok=True)

    exclude_ids = read_exclude_ids(args.exclude_ids_file)
    candidates = build_candidates(args.limit, exclude_ids=exclude_ids)
    candidate_csv = DATA_DIR / f"{args.output_prefix}_candidates.csv"
    prompt_jsonl = DATA_DIR / f"{args.output_prefix}_ai_prompts.jsonl"
    geocoder_priors_csv = DATA_DIR / "geocoder_uncertainty_priors.csv"
    candidates.to_csv(candidate_csv, index=False)
    write_geocoder_priors(geocoder_priors_csv)
    write_prompts(candidates, prompt_jsonl, args.endpoint)
    if not args.skip_sql:
        write_sql(args.endpoint, args.limit)

    print(f"Wrote {candidate_csv.relative_to(ROOT)} ({len(candidates)} rows)")
    print(f"Wrote {geocoder_priors_csv.relative_to(ROOT)}")
    print(f"Wrote {prompt_jsonl.relative_to(ROOT)}")
    if not args.skip_sql:
        print(f"Wrote {SQL_DIR.relative_to(ROOT)}/geo_validation_summary.sql")
        print(f"Wrote {SQL_DIR.relative_to(ROOT)}/geo_validation_candidates_create.sql")
        print(f"Wrote {SQL_DIR.relative_to(ROOT)}/geo_address_janitor_ai_query.sql")
        print(f"Wrote {SQL_DIR.relative_to(ROOT)}/geo_fuzzy_reconciliation.sql")
        print(f"Wrote {SQL_DIR.relative_to(ROOT)}/lakeflow_geo_validation_pipeline.sql")


if __name__ == "__main__":
    main()
