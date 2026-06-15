#!/usr/bin/env python3
"""Build hackathon EDA artifacts and a cleaned facility-health dataset.

The script deliberately keeps provenance and uncertainty fields in the output.
The hackathon deck frames the facility data as claims extracted from web text,
so cleaned rows should not pretend to be a verified registry.
"""

from __future__ import annotations

import csv
import difflib
import json
import math
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
PLOT_DIR = ROOT / "output" / "plots"
NOTEBOOK_PATH = ROOT / "output" / "jupyter-notebook" / "hackathon_dataset_cleaning_analysis.ipynb"

WAREHOUSE_ID = "1b331b704066b677"
CATALOG = "databricks_virtue_foundation_dataset_dais_2026"
SCHEMA = "virtue_foundation_dataset"

FACILITIES_TABLE = f"`{CATALOG}`.`{SCHEMA}`.`facilities`"
PINCODE_TABLE = f"`{CATALOG}`.`{SCHEMA}`.`india_post_pincode_directory`"
HEALTH_TABLE = f"`{CATALOG}`.`{SCHEMA}`.`nfhs_5_district_health_indicators`"


FACILITY_SQL = f"""
SELECT
  unique_id,
  source_content_id,
  name,
  organization_type,
  phone_numbers,
  officialPhone,
  email,
  websites,
  officialWebsite,
  yearEstablished,
  acceptsVolunteers,
  facebookLink,
  address_line1,
  address_line2,
  address_line3,
  address_city,
  address_stateOrRegion,
  address_zipOrPostcode,
  address_country,
  address_countryCode,
  countries,
  facilityTypeId,
  operatorTypeId,
  affiliationTypeIds,
  description,
  area,
  numberDoctors,
  capacity,
  specialties,
  procedure,
  equipment,
  capability,
  recency_of_page_update,
  distinct_social_media_presence_count,
  affiliated_staff_presence,
  custom_logo_presence,
  number_of_facts_about_the_organization,
  post_metrics_most_recent_social_media_post_date,
  post_metrics_post_count,
  engagement_metrics_n_followers,
  engagement_metrics_n_likes,
  engagement_metrics_n_engagements,
  source,
  coordinates,
  latitude,
  longitude,
  cluster_id,
  source_urls
FROM {FACILITIES_TABLE}
"""

PINCODE_SQL = f"SELECT * FROM {PINCODE_TABLE}"
HEALTH_SQL = f"SELECT * FROM {HEALTH_TABLE}"


KEY_HEALTH_COLUMNS = [
    "district_name",
    "state_ut",
    "households_surveyed",
    "women_15_49_interviewed",
    "men_15_54_interviewed",
    "population_below_age_15_years_pct",
    "hh_member_covered_health_insurance_pct",
    "women_age_15_49_who_are_literate_pct",
    "women_age_15_49_with_10_or_more_years_of_schooling_pct",
    "institutional_birth_5y_pct",
    "institutional_birth_in_public_facility_5y_pct",
    "births_attended_by_skilled_hp_5y_10_pct",
    "births_delivered_by_csection_5y_pct",
    "all_w15_49_who_are_anaemic_pct",
    "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    "women_age_30_49_years_ever_undergone_a_cervical_screen_pct",
    "women_age_30_49_years_ever_undergone_a_breast_exam_pct",
    "women_age_30_49_years_ever_undergone_an_oral_cancer_exam_pct",
]


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


def run_cli_json(args: list[str]) -> dict[str, Any]:
    proc = subprocess.run(args, cwd=str(ROOT), text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"{' '.join(args)}\n\nstdout:\n{proc.stdout}\n\nstderr:\n{proc.stderr}"
        )
    text = proc.stdout.strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON from {' '.join(args)}, got:\n{text[:2000]}") from exc


def rows_from_external_links(external_links: Iterable[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for link_info in external_links:
        link = link_info.get("external_link")
        if not link:
            continue
        with urllib.request.urlopen(link, timeout=180) as handle:
            payload = handle.read()
        chunk_rows = json.loads(payload.decode("utf-8"))
        rows.extend(chunk_rows)
    return rows


def statement_to_frame(statement: str, *, wait_timeout: str = "50s") -> pd.DataFrame:
    payload = {
        "warehouse_id": WAREHOUSE_ID,
        "statement": statement,
        "wait_timeout": wait_timeout,
        "on_wait_timeout": "CONTINUE",
        "format": "JSON_ARRAY",
        "disposition": "EXTERNAL_LINKS",
    }
    response = run_cli_json(
        [
            "databricks",
            "api",
            "post",
            "/api/2.0/sql/statements",
            "--json",
            json.dumps(payload),
            "-o",
            "json",
        ]
    )

    statement_id = response.get("statement_id")
    if not statement_id:
        raise RuntimeError(f"SQL response did not include statement_id: {response}")

    for _ in range(120):
        state = response.get("status", {}).get("state")
        if state == "SUCCEEDED":
            break
        if state in {"FAILED", "CANCELED", "CLOSED"}:
            raise RuntimeError(json.dumps(response.get("status", response), indent=2))
        time.sleep(2)
        response = run_cli_json(
            [
                "databricks",
                "api",
                "get",
                f"/api/2.0/sql/statements/{statement_id}",
                "-o",
                "json",
            ]
        )
    else:
        raise TimeoutError(f"Timed out waiting for SQL statement {statement_id}")

    manifest = response.get("manifest") or {}
    columns = [c["name"] for c in manifest.get("schema", {}).get("columns", [])]
    rows: list[list[Any]] = []

    result = response.get("result") or {}
    if result.get("data_array"):
        rows.extend(result["data_array"])
    if result.get("external_links"):
        rows.extend(rows_from_external_links(result["external_links"]))

    total_chunks = int(manifest.get("total_chunk_count") or 0)
    for chunk_idx in range(1, total_chunks):
        chunk = run_cli_json(
            [
                "databricks",
                "api",
                "get",
                f"/api/2.0/sql/statements/{statement_id}/result/chunks/{chunk_idx}",
                "-o",
                "json",
            ]
        )
        payload_chunk = chunk.get("result", chunk)
        rows.extend(payload_chunk.get("data_array") or [])
        if payload_chunk.get("external_links"):
            rows.extend(rows_from_external_links(payload_chunk["external_links"]))

    return pd.DataFrame(rows, columns=columns)


def normalize_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    value = str(value).strip().lower().replace("&", "and")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def normalize_state(value: Any) -> str:
    raw = normalize_text(value)
    return STATE_ALIASES.get(raw, raw)


def normalize_district(value: Any, state_value: Any = "") -> str:
    state_norm = normalize_state(state_value)
    district_norm = normalize_text(value)
    return DISTRICT_ALIASES.get((state_norm, district_norm), district_norm)


def first_pin(value: Any) -> str | None:
    if pd.isna(value):
        return None
    match = re.search(r"(?<!\d)([1-9]\d{5})(?!\d)", str(value))
    return match.group(1) if match else None


def first_int(value: Any, *, max_value: int | None = None) -> float:
    if pd.isna(value):
        return np.nan
    text = str(value).replace(",", "")
    match = re.search(r"(?<!\d)(\d{1,7})(?!\d)", text)
    if not match:
        return np.nan
    parsed = int(match.group(1))
    if max_value is not None and parsed > max_value:
        return np.nan
    return float(parsed)


def parse_year(value: Any) -> float:
    if pd.isna(value):
        return np.nan
    match = re.search(r"\b(18\d{2}|19\d{2}|20[0-2]\d)\b", str(value))
    if not match:
        return np.nan
    year = int(match.group(1))
    if year < 1800 or year > 2026:
        return np.nan
    return float(year)


def parse_numeric_string(value: Any, *, max_value: int | None = None) -> float:
    if pd.isna(value):
        return np.nan
    text = re.sub(r"[^0-9.]+", "", str(value))
    if not text:
        return np.nan
    try:
        parsed = float(text)
    except ValueError:
        return np.nan
    if max_value is not None and parsed > max_value:
        return np.nan
    return parsed


def nonempty(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().ne("")


def haversine_km(lat1: pd.Series, lon1: pd.Series, lat2: pd.Series, lon2: pd.Series) -> pd.Series:
    radius_km = 6371.0088
    lat1_rad = np.radians(pd.to_numeric(lat1, errors="coerce"))
    lon1_rad = np.radians(pd.to_numeric(lon1, errors="coerce"))
    lat2_rad = np.radians(pd.to_numeric(lat2, errors="coerce"))
    lon2_rad = np.radians(pd.to_numeric(lon2, errors="coerce"))
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon / 2) ** 2
    return 2 * radius_km * np.arcsin(np.sqrt(a))


def wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (np.nan, np.nan)
    p = successes / n
    denom = 1 + (z**2 / n)
    center = (p + z**2 / (2 * n)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2)))) / denom
    return center - margin, center + margin


def weighted_mode(values: pd.Series) -> str:
    vc = values.fillna("").astype(str).str.strip()
    vc = vc[vc.ne("")]
    if vc.empty:
        return ""
    counts = vc.value_counts()
    return str(counts.index[0])


def build_pincode_bridge(pincode: pd.DataFrame) -> pd.DataFrame:
    pin = pincode.copy()
    pin["pincode_extracted"] = pin["pincode"].astype(str).str.extract(r"(\d{6})")[0]
    pin["post_latitude"] = pd.to_numeric(pin["latitude"], errors="coerce")
    pin["post_longitude"] = pd.to_numeric(pin["longitude"], errors="coerce")
    pin["pincode_state_norm"] = pin["statename"].map(normalize_state)
    pin["pincode_district_norm"] = pin.apply(
        lambda row: normalize_district(row["district"], row["statename"]),
        axis=1,
    )

    grouped = (
        pin.groupby("pincode_extracted", dropna=False)
        .agg(
            pincode_primary_district=("district", weighted_mode),
            pincode_primary_state=("statename", weighted_mode),
            pincode_n_offices=("officename", "count"),
            pincode_n_districts=("pincode_district_norm", pd.Series.nunique),
            pincode_n_states=("pincode_state_norm", pd.Series.nunique),
            pincode_centroid_latitude=("post_latitude", "mean"),
            pincode_centroid_longitude=("post_longitude", "mean"),
        )
        .reset_index()
    )
    grouped["pincode_state_norm"] = grouped["pincode_primary_state"].map(normalize_state)
    grouped["pincode_district_norm"] = grouped.apply(
        lambda row: normalize_district(row["pincode_primary_district"], row["pincode_primary_state"]),
        axis=1,
    )
    grouped["pincode_is_ambiguous"] = (grouped["pincode_n_districts"] > 1) | (grouped["pincode_n_states"] > 1)
    return grouped[grouped["pincode_extracted"].notna()].copy()


def fuzzy_join_health(row: pd.Series, health_keys: dict[tuple[str, str], int], health_by_state: dict[str, list[str]]) -> tuple[int | None, float]:
    state = row.get("join_state_norm", "")
    district = row.get("join_district_norm", "")
    if not state or not district or state not in health_by_state:
        return None, np.nan
    if (state, district) in health_keys:
        return health_keys[(state, district)], 1.0
    candidates = health_by_state[state]
    if not candidates:
        return None, np.nan
    best = max(candidates, key=lambda cand: difflib.SequenceMatcher(None, district, cand).ratio())
    score = difflib.SequenceMatcher(None, district, best).ratio()
    if score >= 0.92:
        return health_keys[(state, best)], score
    return None, score


def add_health_need_scores(health: pd.DataFrame) -> pd.DataFrame:
    health = health.copy()
    for col in KEY_HEALTH_COLUMNS:
        if col in health.columns and col not in {"district_name", "state_ut"}:
            health[col] = pd.to_numeric(health[col], errors="coerce")

    # Percentile ranks keep bounded percentage indicators comparable without
    # assuming Gaussian distributions.
    high_bad = [
        "all_w15_49_who_are_anaemic_pct",
        "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
        "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
        "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
        "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    ]
    low_bad = [
        "hh_member_covered_health_insurance_pct",
        "women_age_15_49_who_are_literate_pct",
        "institutional_birth_5y_pct",
        "births_attended_by_skilled_hp_5y_10_pct",
        "women_age_30_49_years_ever_undergone_a_cervical_screen_pct",
        "women_age_30_49_years_ever_undergone_a_breast_exam_pct",
        "women_age_30_49_years_ever_undergone_an_oral_cancer_exam_pct",
    ]
    score_parts = []
    for col in high_bad:
        if col in health.columns:
            score_parts.append(health[col].rank(pct=True))
    for col in low_bad:
        if col in health.columns:
            score_parts.append(1 - health[col].rank(pct=True))
    health["health_need_score"] = pd.concat(score_parts, axis=1).mean(axis=1)
    health["health_need_score"] = health["health_need_score"].clip(0, 1)
    return health


def clean_and_join(facilities: pd.DataFrame, pincode: pd.DataFrame, health: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    fac = facilities.copy()
    for col in fac.columns:
        if fac[col].dtype == object:
            fac[col] = fac[col].replace({"": np.nan})
    fac["source_unique_id_occurrences"] = fac.groupby("unique_id", dropna=False)["unique_id"].transform("size")
    fac["source_duplicate_unique_id"] = fac["source_unique_id_occurrences"].gt(1)
    fac = fac.drop_duplicates("unique_id", keep="first").copy()

    fac["facility_name"] = fac["name"].fillna("").astype(str).str.strip()
    fac["facility_latitude"] = pd.to_numeric(fac["latitude"], errors="coerce")
    fac["facility_longitude"] = pd.to_numeric(fac["longitude"], errors="coerce")
    fac["geo_in_india_bbox"] = fac["facility_latitude"].between(6, 38) & fac["facility_longitude"].between(68, 98)
    fac["pincode_extracted"] = fac["address_zipOrPostcode"].map(first_pin)
    fac["facility_state_norm"] = fac["address_stateOrRegion"].map(normalize_state)
    fac["facility_city_norm"] = fac.apply(
        lambda row: normalize_district(row["address_city"], row["address_stateOrRegion"]),
        axis=1,
    )

    fac["year_established_num"] = fac["yearEstablished"].map(parse_year)
    fac["capacity_num"] = fac["capacity"].map(lambda v: first_int(v, max_value=100000))
    fac["number_doctors_num"] = fac["numberDoctors"].map(lambda v: first_int(v, max_value=50000))
    fac["social_media_presence_count_num"] = fac["distinct_social_media_presence_count"].map(lambda v: first_int(v, max_value=50))
    fac["post_count_num"] = fac["post_metrics_post_count"].map(lambda v: first_int(v, max_value=1000000))
    fac["followers_num"] = fac["engagement_metrics_n_followers"].map(lambda v: parse_numeric_string(v, max_value=50000000))
    fac["likes_num"] = fac["engagement_metrics_n_likes"].map(lambda v: parse_numeric_string(v, max_value=50000000))
    fac["engagements_num"] = fac["engagement_metrics_n_engagements"].map(lambda v: parse_numeric_string(v, max_value=50000000))

    claim_cols = ["description", "specialties", "procedure", "equipment", "capability"]
    for col in claim_cols:
        fac[f"has_{col}"] = nonempty(fac[col])
        fac[f"{col}_len"] = fac[col].fillna("").astype(str).str.len()
    fac["claim_field_count"] = fac[[f"has_{c}" for c in claim_cols]].sum(axis=1)
    fac["has_source_urls"] = nonempty(fac["source_urls"])
    fac["has_contact_evidence"] = nonempty(fac["officialPhone"]) | nonempty(fac["phone_numbers"]) | nonempty(fac["email"])
    fac["claim_text"] = (
        fac[claim_cols]
        .fillna("")
        .astype(str)
        .agg(" | ".join, axis=1)
        .str.replace(r"\s+", " ", regex=True)
        .str.slice(0, 1800)
    )
    claim_lower = fac["claim_text"].str.lower()
    fac["has_maternity_care_signal"] = claim_lower.str.contains(
        r"maternity|maternal|obstetric|gynae|gynec|delivery|labou?r|nicu|neonat|paediatric|pediatric",
        regex=True,
        na=False,
    )
    fac["has_emergency_care_signal"] = claim_lower.str.contains(
        r"emergency|trauma|icu|critical care|casualty|ambulance|urgent",
        regex=True,
        na=False,
    )
    fac["has_diagnostic_signal"] = claim_lower.str.contains(
        r"diagnostic|pathology|radiology|imaging|laborator|lab test|scan|x-?ray|mri|ct scan|ultrasound",
        regex=True,
        na=False,
    )
    fac["has_ncd_care_signal"] = claim_lower.str.contains(
        r"cardiac|cardiology|diabetes|hypertension|oncology|cancer|dialysis|nephrology|stroke",
        regex=True,
        na=False,
    )

    pin_bridge = build_pincode_bridge(pincode)
    joined = fac.merge(pin_bridge, on="pincode_extracted", how="left", validate="m:1")
    joined["pincode_matched"] = joined["pincode_primary_district"].notna()
    joined["join_state_norm"] = joined["pincode_state_norm"].where(joined["pincode_matched"], joined["facility_state_norm"])
    joined["join_district_norm"] = joined["pincode_district_norm"].where(joined["pincode_matched"], joined["facility_city_norm"])

    health = add_health_need_scores(health)
    health["_health_row_id"] = np.arange(len(health))
    health["health_state_norm"] = health["state_ut"].map(normalize_state)
    health["health_district_norm"] = health.apply(
        lambda row: normalize_district(row["district_name"], row["state_ut"]),
        axis=1,
    )
    health_keys = {
        (str(row["health_state_norm"]), str(row["health_district_norm"])): int(row["_health_row_id"])
        for _, row in health.iterrows()
        if row["health_state_norm"] and row["health_district_norm"]
    }
    health_by_state: dict[str, list[str]] = {}
    for state, group in health.groupby("health_state_norm"):
        health_by_state[state] = sorted(group["health_district_norm"].dropna().unique().tolist())

    match_info = joined.apply(lambda row: fuzzy_join_health(row, health_keys, health_by_state), axis=1)
    joined["_health_row_id"] = [m[0] for m in match_info]
    joined["join_match_score"] = [m[1] for m in match_info]
    joined["_health_row_id"] = pd.to_numeric(joined["_health_row_id"], errors="coerce")

    health_subset_cols = [c for c in KEY_HEALTH_COLUMNS if c in health.columns]
    health_merge = health[["_health_row_id", "health_state_norm", "health_district_norm", "health_need_score", *health_subset_cols]].copy()
    clean = joined.merge(health_merge, on="_health_row_id", how="left", suffixes=("", "_health"))

    exact_health = clean["_health_row_id"].notna() & clean["join_match_score"].eq(1.0)
    fuzzy_health = clean["_health_row_id"].notna() & clean["join_match_score"].lt(1.0)
    city_fallback = ~clean["pincode_matched"] & clean["_health_row_id"].notna()
    clean["join_strategy"] = np.select(
        [
            exact_health & clean["pincode_matched"],
            fuzzy_health & clean["pincode_matched"],
            city_fallback,
            clean["pincode_matched"] & clean["_health_row_id"].isna(),
            clean["pincode_extracted"].isna(),
        ],
        [
            "pincode_district_state_exact",
            "pincode_district_state_fuzzy",
            "facility_city_state_fallback",
            "pincode_only_no_health_match",
            "no_valid_pincode",
        ],
        default="unjoined",
    )
    clean["join_confidence"] = np.select(
        [
            clean["join_strategy"].eq("pincode_district_state_exact") & ~clean["pincode_is_ambiguous"].fillna(False),
            clean["join_strategy"].eq("pincode_district_state_exact") & clean["pincode_is_ambiguous"].fillna(False),
            clean["join_strategy"].eq("pincode_district_state_fuzzy"),
            clean["join_strategy"].eq("facility_city_state_fallback"),
        ],
        [0.95, 0.82, 0.72, 0.55],
        default=0.0,
    )
    clean["join_uncertainty_reason"] = np.select(
        [
            clean["join_strategy"].eq("no_valid_pincode"),
            clean["join_strategy"].eq("pincode_only_no_health_match"),
            clean["pincode_is_ambiguous"].fillna(False),
            clean["join_strategy"].eq("pincode_district_state_fuzzy"),
            clean["join_strategy"].eq("facility_city_state_fallback"),
        ],
        [
            "No parseable six-digit Indian PIN code.",
            "PIN code matched India Post but no district/state match in NFHS.",
            "PIN code maps to multiple districts or states in India Post.",
            "District spelling required fuzzy matching within the same state.",
            "No PIN bridge; used facility city/state as district/state proxy.",
        ],
        default="Exact PIN-to-district-to-health join.",
    )

    clean["geo_distance_km_to_pincode_centroid"] = haversine_km(
        clean["facility_latitude"],
        clean["facility_longitude"],
        clean["pincode_centroid_latitude"],
        clean["pincode_centroid_longitude"],
    )
    clean["geo_quality"] = np.select(
        [
            clean["facility_latitude"].isna() | clean["facility_longitude"].isna(),
            ~clean["geo_in_india_bbox"],
            clean["geo_distance_km_to_pincode_centroid"].gt(250),
            clean["geo_distance_km_to_pincode_centroid"].between(50, 250, inclusive="right"),
        ],
        ["missing_coordinates", "outside_india_bbox", "far_from_pincode_centroid", "moderate_distance_from_pincode_centroid"],
        default="plausible",
    )

    health_joined = clean["_health_row_id"].notna()
    district_counts = clean[health_joined].groupby("_health_row_id")["unique_id"].transform("count")
    clean["facility_count_in_joined_district_sample"] = district_counts
    count_rank = clean[health_joined].drop_duplicates("_health_row_id")[
        ["_health_row_id", "facility_count_in_joined_district_sample"]
    ].copy()
    count_rank["district_facility_count_percentile_in_sample"] = count_rank[
        "facility_count_in_joined_district_sample"
    ].rank(pct=True)
    clean = clean.merge(count_rank[["_health_row_id", "district_facility_count_percentile_in_sample"]], on="_health_row_id", how="left")
    clean["medical_desert_priority_score"] = (
        0.65 * clean["health_need_score"] + 0.35 * (1 - clean["district_facility_count_percentile_in_sample"])
    ).where(health_joined)
    clean["medical_desert_priority_score"] = clean["medical_desert_priority_score"].clip(0, 1)

    # Score components deliberately mirror the visual EDA findings:
    # geography and join quality dominated uncertainty, while raw claim text
    # coverage was high but unverified.
    clean["data_readiness_score"] = (
        0.18 * clean["pincode_extracted"].notna().astype(float)
        + 0.22 * health_joined.astype(float)
        + 0.14 * clean["geo_in_india_bbox"].astype(float)
        + 0.08 * (~clean["pincode_is_ambiguous"].fillna(True)).astype(float)
        + 0.12 * clean["has_source_urls"].astype(float)
        + 0.16 * (clean["claim_field_count"] >= 3).astype(float)
        + 0.10 * clean["has_contact_evidence"].astype(float)
    ).round(3)

    for col, max_reasonable in [
        ("capacity_num", 5000),
        ("number_doctors_num", 5000),
        ("followers_num", 1000000),
        ("post_count_num", 100000),
    ]:
        clean[f"{col}_extreme_outlier"] = clean[col].gt(max_reasonable).fillna(False)

    clean["needs_human_review"] = (
        clean["data_readiness_score"].lt(0.65)
        | clean["join_confidence"].lt(0.8)
        | clean["geo_quality"].ne("plausible")
        | clean["capacity_num_extreme_outlier"]
        | clean["number_doctors_num_extreme_outlier"]
        | clean["claim_field_count"].lt(2)
    )
    clean["trustworthy_supply_signal"] = (
        clean["data_readiness_score"].ge(0.8)
        & clean["join_confidence"].ge(0.8)
        & clean["geo_quality"].eq("plausible")
        & clean["has_source_urls"]
        & clean["claim_field_count"].ge(3)
        & ~clean["capacity_num_extreme_outlier"]
        & ~clean["number_doctors_num_extreme_outlier"]
    )
    clean["contradicted_or_geo_invalid_signal"] = (
        clean["geo_quality"].isin(["outside_india_bbox", "far_from_pincode_centroid"])
        | clean["capacity_num_extreme_outlier"]
        | clean["number_doctors_num_extreme_outlier"]
    )

    ordered_cols = [
        "unique_id",
        "source_unique_id_occurrences",
        "source_duplicate_unique_id",
        "facility_name",
        "organization_type",
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
        "pincode_n_offices",
        "pincode_n_districts",
        "pincode_n_states",
        "pincode_is_ambiguous",
        "facility_latitude",
        "facility_longitude",
        "geo_in_india_bbox",
        "pincode_centroid_latitude",
        "pincode_centroid_longitude",
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
        "facility_count_in_joined_district_sample",
        "district_facility_count_percentile_in_sample",
        "yearEstablished",
        "year_established_num",
        "capacity",
        "capacity_num",
        "numberDoctors",
        "number_doctors_num",
        "recency_of_page_update",
        "social_media_presence_count_num",
        "post_count_num",
        "followers_num",
        "likes_num",
        "engagements_num",
        "claim_field_count",
        "has_description",
        "has_specialties",
        "has_procedure",
        "has_equipment",
        "has_capability",
        "description_len",
        "specialties_len",
        "procedure_len",
        "equipment_len",
        "capability_len",
        "has_source_urls",
        "has_contact_evidence",
        "needs_human_review",
        "trustworthy_supply_signal",
        "contradicted_or_geo_invalid_signal",
        "has_maternity_care_signal",
        "has_emergency_care_signal",
        "has_diagnostic_signal",
        "has_ncd_care_signal",
        "capacity_num_extreme_outlier",
        "number_doctors_num_extreme_outlier",
        "followers_num_extreme_outlier",
        "post_count_num_extreme_outlier",
        "claim_text",
        "source_urls",
        "officialWebsite",
        "websites",
        "officialPhone",
        "phone_numbers",
        "email",
        "source_content_id",
        "cluster_id",
    ]
    ordered_cols.extend([c for c in KEY_HEALTH_COLUMNS if c in clean.columns and c not in ordered_cols])
    clean = clean[[c for c in ordered_cols if c in clean.columns]].copy()
    return clean, pin_bridge


def sample_values(values: pd.Series, limit: int = 8, max_chars: int = 500) -> str:
    seen: list[str] = []
    for value in values.dropna().astype(str):
        value = re.sub(r"\s+", " ", value).strip()
        if not value or value in seen:
            continue
        seen.append(value)
        if len(seen) >= limit:
            break
    result = "; ".join(seen)
    return result[:max_chars]


def mode_or_blank(values: pd.Series) -> str:
    values = values.dropna().astype(str).str.strip()
    values = values[values.ne("")]
    if values.empty:
        return ""
    return str(values.value_counts().index[0])


def rate_ci_from_counts(successes: float, n: float) -> tuple[float, float]:
    if pd.isna(successes) or pd.isna(n) or int(n) <= 0:
        return (np.nan, np.nan)
    return wilson_interval(int(successes), int(n))


def build_district_dataset(clean: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    joined = clean[clean["state_ut"].notna() & clean["district_name"].notna()].copy()
    bool_cols = [
        "pincode_is_ambiguous",
        "geo_in_india_bbox",
        "has_source_urls",
        "has_contact_evidence",
        "has_description",
        "has_specialties",
        "has_procedure",
        "has_equipment",
        "has_capability",
        "needs_human_review",
        "trustworthy_supply_signal",
        "contradicted_or_geo_invalid_signal",
        "has_maternity_care_signal",
        "has_emergency_care_signal",
        "has_diagnostic_signal",
        "has_ncd_care_signal",
    ]
    for col in bool_cols:
        if col in joined.columns:
            joined[col] = joined[col].fillna(False).astype(bool)

    health_cols = [c for c in KEY_HEALTH_COLUMNS if c in joined.columns and c not in {"district_name", "state_ut"}]
    health_first = (
        joined.groupby(["state_ut", "district_name"], dropna=False)[["health_need_score", *health_cols]]
        .first()
        .reset_index()
    )

    grouped = joined.groupby(["state_ut", "district_name"], dropna=False)
    metrics = grouped.agg(
        observed_facility_rows=("unique_id", "count"),
        unique_facility_ids=("unique_id", pd.Series.nunique),
        unique_pincodes_observed=("pincode_extracted", pd.Series.nunique),
        pincode_ambiguous_rows=("pincode_is_ambiguous", "sum"),
        exact_join_rows=("join_strategy", lambda s: int(s.eq("pincode_district_state_exact").sum())),
        fuzzy_join_rows=("join_strategy", lambda s: int(s.eq("pincode_district_state_fuzzy").sum())),
        city_fallback_rows=("join_strategy", lambda s: int(s.eq("facility_city_state_fallback").sum())),
        avg_join_confidence=("join_confidence", "mean"),
        avg_data_readiness_score=("data_readiness_score", "mean"),
        median_data_readiness_score=("data_readiness_score", "median"),
        needs_human_review_rows=("needs_human_review", "sum"),
        plausible_geo_rows=("geo_quality", lambda s: int(s.eq("plausible").sum())),
        far_geo_rows=("geo_quality", lambda s: int(s.isin(["far_from_pincode_centroid", "outside_india_bbox"]).sum())),
        source_url_rows=("has_source_urls", "sum"),
        contact_evidence_rows=("has_contact_evidence", "sum"),
        trustworthy_supply_rows=("trustworthy_supply_signal", "sum"),
        contradicted_or_geo_invalid_rows=("contradicted_or_geo_invalid_signal", "sum"),
        maternity_signal_rows=("has_maternity_care_signal", "sum"),
        emergency_signal_rows=("has_emergency_care_signal", "sum"),
        diagnostic_signal_rows=("has_diagnostic_signal", "sum"),
        ncd_signal_rows=("has_ncd_care_signal", "sum"),
        description_rows=("has_description", "sum"),
        procedure_rows=("has_procedure", "sum"),
        equipment_rows=("has_equipment", "sum"),
        capability_rows=("has_capability", "sum"),
        parsed_capacity_rows=("capacity_num", lambda s: int(s.notna().sum())),
        observed_capacity_sum=("capacity_num", "sum"),
        observed_capacity_median=("capacity_num", "median"),
        observed_capacity_p95=("capacity_num", lambda s: float(s.dropna().quantile(0.95)) if s.notna().any() else np.nan),
        observed_capacity_max=("capacity_num", "max"),
        parsed_doctor_rows=("number_doctors_num", lambda s: int(s.notna().sum())),
        observed_doctors_sum=("number_doctors_num", "sum"),
        observed_doctors_median=("number_doctors_num", "median"),
        observed_doctors_p95=("number_doctors_num", lambda s: float(s.dropna().quantile(0.95)) if s.notna().any() else np.nan),
        observed_doctors_max=("number_doctors_num", "max"),
        median_followers=("followers_num", "median"),
        p95_followers=("followers_num", lambda s: float(s.dropna().quantile(0.95)) if s.notna().any() else np.nan),
        predominant_geo_quality=("geo_quality", mode_or_blank),
        predominant_join_uncertainty=("join_uncertainty_reason", mode_or_blank),
        sample_facility_names=("facility_name", sample_values),
        sample_claim_evidence=("claim_text", lambda s: sample_values(s, limit=3, max_chars=900)),
        sample_source_urls=("source_urls", lambda s: sample_values(s, limit=3, max_chars=900)),
    ).reset_index()

    district = health_first.merge(metrics, on=["state_ut", "district_name"], how="left", validate="1:1")
    count = district["observed_facility_rows"].replace(0, np.nan)
    district["pincode_ambiguity_rate"] = district["pincode_ambiguous_rows"] / count
    district["needs_human_review_rate"] = district["needs_human_review_rows"] / count
    district["plausible_geo_rate"] = district["plausible_geo_rows"] / count
    district["source_url_rate"] = district["source_url_rows"] / count
    district["contact_evidence_rate"] = district["contact_evidence_rows"] / count
    district["trustworthy_supply_rate"] = district["trustworthy_supply_rows"] / count
    district["contradicted_or_geo_invalid_rate"] = district["contradicted_or_geo_invalid_rows"] / count
    district["maternity_signal_rate"] = district["maternity_signal_rows"] / count
    district["emergency_signal_rate"] = district["emergency_signal_rows"] / count
    district["diagnostic_signal_rate"] = district["diagnostic_signal_rows"] / count
    district["ncd_signal_rate"] = district["ncd_signal_rows"] / count
    district["description_rate"] = district["description_rows"] / count
    district["procedure_rate"] = district["procedure_rows"] / count
    district["equipment_rate"] = district["equipment_rows"] / count
    district["capability_rate"] = district["capability_rows"] / count
    district["capacity_parse_rate"] = district["parsed_capacity_rows"] / count
    district["doctor_parse_rate"] = district["parsed_doctor_rows"] / count
    district["exact_join_rate"] = district["exact_join_rows"] / count

    for stem, success_col in [
        ("needs_human_review", "needs_human_review_rows"),
        ("plausible_geo", "plausible_geo_rows"),
        ("source_url", "source_url_rows"),
        ("trustworthy_supply", "trustworthy_supply_rows"),
        ("exact_join", "exact_join_rows"),
    ]:
        cis = district.apply(lambda row: rate_ci_from_counts(row[success_col], row["observed_facility_rows"]), axis=1)
        district[f"{stem}_rate_ci_low"] = [ci[0] for ci in cis]
        district[f"{stem}_rate_ci_high"] = [ci[1] for ci in cis]

    district["observed_facility_count_percentile"] = district["observed_facility_rows"].rank(pct=True)
    district["district_medical_desert_priority_score"] = (
        0.65 * district["health_need_score"] + 0.35 * (1 - district["observed_facility_count_percentile"])
    ).clip(0, 1)
    district["care_gap_score"] = (
        0.55 * district["health_need_score"]
        + 0.25 * (1 - district["observed_facility_count_percentile"])
        + 0.20 * (1 - district["trustworthy_supply_rate"].fillna(0))
    ).clip(0, 1)
    district["trust_gap_score"] = (
        0.45 * (1 - district["trustworthy_supply_rate"].fillna(0))
        + 0.30 * district["needs_human_review_rate"].fillna(1)
        + 0.25 * district["contradicted_or_geo_invalid_rate"].fillna(0)
    ).clip(0, 1)
    district["district_data_quality_score"] = (
        0.30 * district["avg_data_readiness_score"].fillna(0)
        + 0.25 * district["avg_join_confidence"].fillna(0)
        + 0.20 * district["plausible_geo_rate"].fillna(0)
        + 0.15 * district["source_url_rate"].fillna(0)
        + 0.10 * (1 - district["needs_human_review_rate"].fillna(1))
    ).round(3)
    district["best_care_signal_score"] = (
        0.40 * (1 - district["health_need_score"])
        + 0.30 * district["trustworthy_supply_rate"].fillna(0)
        + 0.20 * district["district_data_quality_score"].fillna(0)
        + 0.10 * district["observed_facility_count_percentile"].fillna(0)
    ).clip(0, 1)
    district["district_uncertainty_level"] = np.select(
        [
            district["district_data_quality_score"].ge(0.85) & district["observed_facility_rows"].ge(5),
            district["district_data_quality_score"].ge(0.70) & district["observed_facility_rows"].ge(3),
        ],
        ["lower", "medium"],
        default="higher",
    )
    district["planning_category"] = np.select(
        [
            district["care_gap_score"].ge(0.70)
            & district["health_need_score"].ge(district["health_need_score"].quantile(0.75))
            & district["trustworthy_supply_rows"].le(2),
            district["health_need_score"].ge(district["health_need_score"].quantile(0.75))
            & district["observed_facility_rows"].ge(district["observed_facility_rows"].median())
            & district["trustworthy_supply_rate"].lt(0.60),
            district["contradicted_or_geo_invalid_rate"].ge(0.25),
            district["best_care_signal_score"].ge(district["best_care_signal_score"].quantile(0.80))
            & district["district_data_quality_score"].ge(0.75),
        ],
        [
            "real_desert_candidate",
            "phantom_desert_or_verification_gap",
            "supply_record_quality_problem",
            "referral_or_capacity_candidate",
        ],
        default="mixed_or_monitor",
    )
    district["dataset_grain"] = "district"
    district["facility_supply_warning"] = "Observed FDR facility rows are not a verified census of facilities."

    ordered = [
        "state_ut",
        "district_name",
        "dataset_grain",
        "observed_facility_rows",
        "unique_facility_ids",
        "unique_pincodes_observed",
        "observed_facility_count_percentile",
        "health_need_score",
        "district_medical_desert_priority_score",
        "care_gap_score",
        "trust_gap_score",
        "best_care_signal_score",
        "planning_category",
        "district_data_quality_score",
        "district_uncertainty_level",
        "avg_join_confidence",
        "avg_data_readiness_score",
        "median_data_readiness_score",
        "exact_join_rows",
        "fuzzy_join_rows",
        "city_fallback_rows",
        "exact_join_rate",
        "exact_join_rate_ci_low",
        "exact_join_rate_ci_high",
        "pincode_ambiguous_rows",
        "pincode_ambiguity_rate",
        "needs_human_review_rows",
        "needs_human_review_rate",
        "needs_human_review_rate_ci_low",
        "needs_human_review_rate_ci_high",
        "plausible_geo_rows",
        "plausible_geo_rate",
        "plausible_geo_rate_ci_low",
        "plausible_geo_rate_ci_high",
        "far_geo_rows",
        "source_url_rows",
        "source_url_rate",
        "source_url_rate_ci_low",
        "source_url_rate_ci_high",
        "contact_evidence_rows",
        "contact_evidence_rate",
        "trustworthy_supply_rows",
        "trustworthy_supply_rate",
        "trustworthy_supply_rate_ci_low",
        "trustworthy_supply_rate_ci_high",
        "contradicted_or_geo_invalid_rows",
        "contradicted_or_geo_invalid_rate",
        "maternity_signal_rows",
        "maternity_signal_rate",
        "emergency_signal_rows",
        "emergency_signal_rate",
        "diagnostic_signal_rows",
        "diagnostic_signal_rate",
        "ncd_signal_rows",
        "ncd_signal_rate",
        "description_rate",
        "procedure_rate",
        "equipment_rate",
        "capability_rate",
        "parsed_capacity_rows",
        "capacity_parse_rate",
        "observed_capacity_sum",
        "observed_capacity_median",
        "observed_capacity_p95",
        "observed_capacity_max",
        "parsed_doctor_rows",
        "doctor_parse_rate",
        "observed_doctors_sum",
        "observed_doctors_median",
        "observed_doctors_p95",
        "observed_doctors_max",
        "median_followers",
        "p95_followers",
        "predominant_geo_quality",
        "predominant_join_uncertainty",
        "sample_facility_names",
        "sample_claim_evidence",
        "sample_source_urls",
        "facility_supply_warning",
    ]
    ordered.extend([c for c in KEY_HEALTH_COLUMNS if c in district.columns and c not in ordered])
    district = district[[c for c in ordered if c in district.columns]].sort_values(
        ["district_medical_desert_priority_score", "observed_facility_rows"],
        ascending=[False, True],
    )

    unmatched = clean[clean["state_ut"].isna() & clean["pincode_primary_district"].notna()].copy()
    unmatched_grouped = (
        unmatched.groupby(["pincode_primary_state", "pincode_primary_district"], dropna=False)
        .agg(
            observed_facility_rows=("unique_id", "count"),
            unique_pincodes_observed=("pincode_extracted", pd.Series.nunique),
            sample_facility_names=("facility_name", sample_values),
            predominant_join_uncertainty=("join_uncertainty_reason", mode_or_blank),
        )
        .reset_index()
        .sort_values("observed_facility_rows", ascending=False)
    )
    return district, unmatched_grouped


def describe_distribution(series: pd.Series) -> dict[str, Any]:
    x = pd.to_numeric(series, errors="coerce").dropna()
    if x.empty:
        return {"n": 0}
    result: dict[str, Any] = {
        "n": int(x.size),
        "mean": float(x.mean()),
        "median": float(x.median()),
        "std": float(x.std(ddof=1)) if x.size > 1 else 0.0,
        "min": float(x.min()),
        "p25": float(x.quantile(0.25)),
        "p75": float(x.quantile(0.75)),
        "p95": float(x.quantile(0.95)),
        "max": float(x.max()),
        "skew": float(stats.skew(x, nan_policy="omit")) if x.size > 2 else np.nan,
        "kurtosis": float(stats.kurtosis(x, nan_policy="omit")) if x.size > 3 else np.nan,
    }
    sample = x.sample(min(5000, x.size), random_state=42)
    if sample.nunique() >= 8 and sample.size >= 20:
        normaltest = stats.normaltest(sample)
        result["normaltest_k2"] = float(normaltest.statistic)
        result["normaltest_pvalue"] = float(normaltest.pvalue)
        positive = sample[sample > 0]
        if positive.size >= 20 and positive.nunique() >= 8:
            logtest = stats.normaltest(np.log1p(positive))
            result["log1p_normaltest_pvalue"] = float(logtest.pvalue)
    return result


def plot_outputs(clean: pd.DataFrame, district_clean: pd.DataFrame, facilities: pd.DataFrame) -> dict[str, str]:
    sns.set_theme(style="whitegrid", context="notebook")
    plot_paths: dict[str, str] = {}

    key_fields = [
        "name",
        "address_zipOrPostcode",
        "latitude",
        "longitude",
        "yearEstablished",
        "capacity",
        "numberDoctors",
        "description",
        "procedure",
        "equipment",
        "capability",
        "source_urls",
    ]
    missing = pd.DataFrame(
        {
            "field": key_fields,
            "present_pct": [100 * nonempty(facilities[c]).mean() if c in facilities else np.nan for c in key_fields],
        }
    ).sort_values("present_pct")
    plt.figure(figsize=(10, 5.8))
    sns.barplot(data=missing, x="present_pct", y="field", color="#4c78a8")
    plt.xlim(0, 100)
    plt.xlabel("Present rows (%)")
    plt.ylabel("")
    plt.title("Field Coverage: Evidence Fields Are Present, But Not Verified")
    plt.tight_layout()
    path = PLOT_DIR / "field_coverage.png"
    plt.savefig(path, dpi=160)
    plt.close()
    plot_paths["field_coverage"] = str(path.relative_to(ROOT))

    join_counts = clean["join_strategy"].value_counts().rename_axis("join_strategy").reset_index(name="rows")
    plt.figure(figsize=(10, 5.5))
    sns.barplot(data=join_counts, x="rows", y="join_strategy", color="#59a14f")
    plt.xlabel("Rows")
    plt.ylabel("")
    plt.title("Join Strategy Distribution")
    plt.tight_layout()
    path = PLOT_DIR / "join_strategy_distribution.png"
    plt.savefig(path, dpi=160)
    plt.close()
    plot_paths["join_strategy"] = str(path.relative_to(ROOT))

    plt.figure(figsize=(9, 5.5))
    sns.histplot(clean["data_readiness_score"], bins=20, color="#f28e2b")
    plt.xlabel("Data readiness score")
    plt.ylabel("Facility rows")
    plt.title("Cleaned Dataset Readiness Score")
    plt.tight_layout()
    path = PLOT_DIR / "data_readiness_distribution.png"
    plt.savefig(path, dpi=160)
    plt.close()
    plot_paths["data_readiness"] = str(path.relative_to(ROOT))

    plt.figure(figsize=(9, 5.5))
    sns.histplot(district_clean["district_data_quality_score"], bins=20, color="#f28e2b")
    plt.xlabel("District data quality score")
    plt.ylabel("District rows")
    plt.title("District-Level Data Quality Score")
    plt.tight_layout()
    path = PLOT_DIR / "district_data_quality_distribution.png"
    plt.savefig(path, dpi=160)
    plt.close()
    plot_paths["district_data_quality"] = str(path.relative_to(ROOT))

    numeric_cols = ["capacity_num", "number_doctors_num", "followers_num", "post_count_num"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 8))
    for ax, col in zip(axes.flat, numeric_cols):
        x = clean[col].dropna()
        if x.empty:
            ax.text(0.5, 0.5, "No parsed values", ha="center", va="center")
        else:
            sns.histplot(np.log1p(x), bins=35, ax=ax, color="#b07aa1")
            ax.set_xlabel(f"log1p({col})")
        ax.set_title(col)
    fig.suptitle("Numeric-Looking Facility Fields Are Heavy-Tailed After Parsing", y=1.02)
    plt.tight_layout()
    path = PLOT_DIR / "numeric_distributions_log.png"
    plt.savefig(path, dpi=160, bbox_inches="tight")
    plt.close()
    plot_paths["numeric_distributions"] = str(path.relative_to(ROOT))

    state_counts = (
        clean.groupby("pincode_primary_state", dropna=False)["unique_id"]
        .count()
        .sort_values(ascending=False)
        .head(15)
        .rename_axis("state")
        .reset_index(name="facilities")
    )
    plt.figure(figsize=(10, 6))
    sns.barplot(data=state_counts, x="facilities", y="state", color="#e15759")
    plt.xlabel("Facility rows in this dataset")
    plt.ylabel("")
    plt.title("Facility Rows by Pincode-Inferred State, Top 15")
    plt.tight_layout()
    path = PLOT_DIR / "facility_counts_by_state.png"
    plt.savefig(path, dpi=160)
    plt.close()
    plot_paths["state_counts"] = str(path.relative_to(ROOT))

    district = district_clean.dropna(
        subset=["observed_facility_rows", "health_need_score", "district_medical_desert_priority_score"]
    ).copy()
    if not district.empty:
        plt.figure(figsize=(9, 6))
        sns.scatterplot(
            data=district,
            x="observed_facility_rows",
            y="health_need_score",
            hue="district_medical_desert_priority_score",
            palette="viridis",
            size="district_medical_desert_priority_score",
            sizes=(20, 180),
            legend="brief",
        )
        plt.xscale("log")
        plt.xlabel("Facility rows in joined district sample (log scale)")
        plt.ylabel("Health need score")
        plt.title("Medical Desert Proxy: High Need + Low Observed Facility Coverage")
        plt.tight_layout()
        path = PLOT_DIR / "medical_desert_proxy_scatter.png"
        plt.savefig(path, dpi=160)
        plt.close()
        plot_paths["medical_desert_proxy"] = str(path.relative_to(ROOT))

    geo_sample = clean.dropna(subset=["facility_latitude", "facility_longitude"]).copy()
    if not geo_sample.empty:
        plt.figure(figsize=(8, 8))
        sns.scatterplot(
            data=geo_sample.sample(min(len(geo_sample), 6000), random_state=42),
            x="facility_longitude",
            y="facility_latitude",
            hue="geo_quality",
            s=14,
            linewidth=0,
            alpha=0.7,
        )
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        plt.title("Facility Coordinates Include Off-India Outliers")
        plt.tight_layout()
        path = PLOT_DIR / "geo_quality_scatter.png"
        plt.savefig(path, dpi=160)
        plt.close()
        plot_paths["geo_quality"] = str(path.relative_to(ROOT))

    return plot_paths


def write_data_dictionary(clean: pd.DataFrame, district_clean: pd.DataFrame) -> None:
    facility_descriptions = {
        "pincode_extracted": "First valid six-digit Indian PIN parsed from address_zipOrPostcode.",
        "pincode_primary_district": "Modal India Post district for the parsed PIN code.",
        "pincode_is_ambiguous": "True when the PIN maps to multiple districts or states in India Post.",
        "geo_quality": "Coordinate quality class informed by India bounding box and PIN centroid distance.",
        "join_strategy": "How the row was joined to NFHS district health indicators.",
        "join_confidence": "Heuristic confidence score for the facility -> pincode -> health join.",
        "join_uncertainty_reason": "Human-readable reason why the join may be uncertain.",
        "data_readiness_score": "Weighted score for pincode, health join, geography, source URLs, claim field coverage, and contact evidence.",
        "medical_desert_priority_score": "Planner proxy: high district health need plus low facility count in the joined sample.",
        "health_need_score": "Percentile composite over adverse NFHS indicators. It is district-level context, not a facility label.",
        "claim_text": "Truncated concatenation of raw extracted text fields used as claim evidence.",
        "needs_human_review": "Flag for low readiness, low join confidence, geography issues, sparse evidence, or extreme parsed numerics.",
    }
    district_descriptions = {
        "observed_facility_rows": "Number of FDR facility rows joined into this district. This is not a verified facility census.",
        "health_need_score": "Percentile composite over adverse NFHS district indicators.",
        "district_medical_desert_priority_score": "Proxy score: high health need plus low observed FDR facility count percentile.",
        "district_data_quality_score": "Composite quality score from readiness, join confidence, geography, source URLs, and review rate.",
        "district_uncertainty_level": "Lower/medium/higher uncertainty based on district quality score and observed row count.",
        "exact_join_rate": "Share of facility rows that joined through exact pincode district/state match.",
        "needs_human_review_rate": "Share of facility rows in the district flagged for human review.",
        "plausible_geo_rate": "Share of facility rows with plausible India coordinates and pincode centroid distance.",
        "source_url_rate": "Share of facility rows with source URLs for evidence citation.",
        "capacity_parse_rate": "Share of facility rows where capacity could be parsed into a number.",
        "doctor_parse_rate": "Share of facility rows where numberDoctors could be parsed into a number.",
        "sample_claim_evidence": "Small sample of raw extracted claim text from facility rows in the district.",
        "facility_supply_warning": "Reminder that observed FDR counts are not a ground-truth supply registry.",
    }

    def rows_for(df: pd.DataFrame, descriptions: dict[str, str]) -> list[dict[str, Any]]:
        rows = []
        for col in df.columns:
            rows.append(
                {
                    "column": col,
                    "dtype": str(df[col].dtype),
                    "non_null_rows": int(df[col].notna().sum()),
                    "description": descriptions.get(col, ""),
                }
            )
        return rows

    facility_rows = rows_for(clean, facility_descriptions)
    district_rows = rows_for(district_clean, district_descriptions)
    pd.DataFrame(facility_rows).to_csv(DATA_DIR / "facility_health_cleaned_data_dictionary.csv", index=False)
    pd.DataFrame(district_rows).to_csv(DATA_DIR / "district_health_facility_cleaned_data_dictionary.csv", index=False)


def load_raw_or_query(name: str, sql: str) -> pd.DataFrame:
    path = DATA_DIR / name
    if path.exists():
        print(f"Loading cached {name}...")
        return pd.read_csv(path, low_memory=False)
    frame = statement_to_frame(sql)
    frame.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL)
    return frame


def make_summary(
    facilities: pd.DataFrame,
    pincode: pd.DataFrame,
    health: pd.DataFrame,
    clean: pd.DataFrame,
    district_clean: pd.DataFrame,
    unmatched_districts: pd.DataFrame,
    pin_bridge: pd.DataFrame,
    plot_paths: dict[str, str],
) -> dict[str, Any]:
    coverage_cols = [
        "name",
        "address_zipOrPostcode",
        "latitude",
        "longitude",
        "yearEstablished",
        "capacity",
        "numberDoctors",
        "description",
        "procedure",
        "equipment",
        "capability",
        "source_urls",
    ]
    coverage = {
        col: {
            "present_rows": int(nonempty(facilities[col]).sum()),
            "present_pct": float(100 * nonempty(facilities[col]).mean()),
        }
        for col in coverage_cols
        if col in facilities.columns
    }
    n = len(clean)
    joined_n = int(clean["district_name"].notna().sum())
    valid_pin_n = int(clean["pincode_extracted"].notna().sum())
    geo_valid_n = int(clean["geo_in_india_bbox"].sum())
    review_n = int(clean["needs_human_review"].sum())
    intervals = {
        "valid_pin_rate_95ci": wilson_interval(valid_pin_n, n),
        "health_join_rate_95ci": wilson_interval(joined_n, n),
        "geo_in_india_bbox_rate_95ci": wilson_interval(geo_valid_n, n),
        "needs_review_rate_95ci": wilson_interval(review_n, n),
    }

    dist_cols = [
        "capacity_num",
        "number_doctors_num",
        "followers_num",
        "post_count_num",
        "data_readiness_score",
        "medical_desert_priority_score",
        "health_need_score",
        "facility_count_in_joined_district_sample",
    ]
    distributions = {col: describe_distribution(clean[col]) for col in dist_cols if col in clean}
    district_dist_cols = [
        "observed_facility_rows",
        "district_medical_desert_priority_score",
        "district_data_quality_score",
        "health_need_score",
        "needs_human_review_rate",
        "plausible_geo_rate",
        "capacity_parse_rate",
        "doctor_parse_rate",
    ]
    district_distributions = {
        col: describe_distribution(district_clean[col]) for col in district_dist_cols if col in district_clean
    }

    normality_notes = {
        col: (
            "not_gaussian"
            if details.get("normaltest_pvalue", 1.0) < 0.05
            else "insufficient_evidence_against_gaussian"
        )
        for col, details in distributions.items()
        if details.get("n", 0) >= 20
    }

    top_district_cols = [
        "district_name",
        "state_ut",
        "observed_facility_rows",
        "health_need_score",
        "district_medical_desert_priority_score",
        "district_data_quality_score",
        "district_uncertainty_level",
        "sample_facility_names",
        "predominant_join_uncertainty",
    ]
    top_district_priority = (
        district_clean.sort_values(
            ["district_medical_desert_priority_score", "district_data_quality_score"],
            ascending=[False, False],
        )
        .head(15)[top_district_cols]
        .to_dict(orient="records")
    )

    return {
        "workspace": "https://dbc-54942fa9-145a.cloud.databricks.com",
        "warehouse_id": WAREHOUSE_ID,
        "source_tables": {
            "facilities": {"rows": int(len(facilities)), "columns": int(facilities.shape[1])},
            "india_post_pincode_directory": {"rows": int(len(pincode)), "columns": int(pincode.shape[1])},
            "nfhs_5_district_health_indicators": {"rows": int(len(health)), "columns": int(health.shape[1])},
        },
        "cleaned_rows": int(len(clean)),
        "cleaned_columns": int(clean.shape[1]),
        "district_cleaned_rows": int(len(district_clean)),
        "district_cleaned_columns": int(district_clean.shape[1]),
        "unmatched_pincode_district_rows": int(len(unmatched_districts)),
        "pincode_bridge_rows": int(len(pin_bridge)),
        "join_strategy_counts": clean["join_strategy"].value_counts(dropna=False).to_dict(),
        "geo_quality_counts": clean["geo_quality"].value_counts(dropna=False).to_dict(),
        "district_uncertainty_counts": district_clean["district_uncertainty_level"].value_counts(dropna=False).to_dict(),
        "needs_human_review_rows": review_n,
        "needs_human_review_pct": float(100 * review_n / n),
        "field_coverage": coverage,
        "confidence_intervals": intervals,
        "distribution_profiles": distributions,
        "district_distribution_profiles": district_distributions,
        "normality_notes": normality_notes,
        "top_district_medical_desert_priority_rows": top_district_priority,
        "plots": plot_paths,
        "screenshot_context": {
            "problem": "10,000 messy healthcare facility records across India; extracted structured fields plus uneven free-text claims.",
            "requirements": [
                "Use the provided facility dataset.",
                "Cite underlying facility text for important claims, recommendations, scores, or rankings.",
                "Communicate uncertainty rather than treating weak evidence as fact.",
                "Persist actions such as notes, overrides, shortlists, scenarios, or review decisions.",
            ],
            "data_warning": "FDR turns open-web text into structured data through GenAI extraction and entity resolution; field coverage should be treated as claims to verify, not ground truth.",
            "prior_notes": [
                "Target users include doctors/medical staff and government researchers/planners.",
                "A quality dataset should be reusable and open-source friendly.",
                "Merging records can create inaccuracy, so joins need explicit uncertainty.",
                "Distribution analysis, confidence intervals, Bayesian-style confidence updates, and supervised learning from a golden dataset were suggested directions.",
            ],
        },
        "statistical_methods": [
            "Field missingness/coverage profiling.",
            "Regex-based type parsing with parse-failure and extreme-outlier flags.",
            "India bounding-box and pincode-centroid distance checks for geospatial outliers.",
            "Modal pincode bridge with ambiguity counts before joining to NFHS districts.",
            "Exact and high-threshold fuzzy district matching within state; match strategy and score retained.",
            "Wilson 95% confidence intervals for rates such as pincode validity, join success, and review flags.",
            "Skew/kurtosis and D'Agostino normality tests on parsed numeric fields.",
            "Log1p visualizations for heavy-tailed facility numeric fields.",
            "Percentile-rank health need scoring to avoid Gaussian assumptions on bounded NFHS percentages.",
            "Planner proxy score combining district health need and inverse sample facility coverage.",
            "District-level aggregation to align facility evidence with the NFHS district grain.",
        ],
    }


def write_notebook(summary: dict[str, Any]) -> None:
    plot = summary["plots"]
    cells = []

    def md(text: str) -> dict[str, Any]:
        return {"cell_type": "markdown", "metadata": {}, "source": text.strip() + "\n"}

    def code(text: str) -> dict[str, Any]:
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": text.strip() + "\n",
        }

    cells.append(
        md(
            """
# Hackathon Dataset Cleaning and Join Analysis

Objective: turn the FDR healthcare-facility data into a cleaner, uncertainty-aware dataset for non-technical planners, medical staff, and researchers.

This notebook follows the hackathon warning from the screenshots: the facility fields are extracted claims from open web text, not verified ground truth. The cleaning step therefore keeps claim evidence, join strategy, confidence, and human-review flags.
"""
        )
    )
    cells.append(
        md(
            """
## Screenshot-Derived Context

- Source pipeline: web crawl -> GenAI extraction -> entity resolution -> FDR dataset.
- Dataset: roughly 10k India-focused facility records with 51 facility columns.
- Required behavior: cite underlying facility text, communicate uncertainty honestly, and persist review decisions.
- Prior notes: merging records creates uncertainty; useful analysis includes distributions, confidence intervals, Boolean indicators, Bayesian-style confidence, and eventually supervised learning from a reviewed golden set.
"""
        )
    )
    cells.append(
        code(
            """
from pathlib import Path
import json
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import Image, display

ROOT = Path.cwd()
DATA_DIR = ROOT / "output" / "data"
PLOT_DIR = ROOT / "output" / "plots"

facility_clean = pd.read_csv(DATA_DIR / "facility_health_cleaned.csv")
district_clean = pd.read_csv(DATA_DIR / "district_health_facility_cleaned.csv")
unmatched_pincode_districts = pd.read_csv(DATA_DIR / "district_unmatched_pincode_facility_counts.csv")
summary = json.loads((DATA_DIR / "analysis_summary.json").read_text())
clean = facility_clean  # Alias used by the facility QA cells below.
district_clean.shape, facility_clean.shape, summary["source_tables"]
"""
        )
    )
    cells.append(
        md(
            """
## Primary Output: District-Level Dataset

District is the safer analytic grain. NFHS health indicators are district-level, India Post lets us bridge PIN codes to district/state, and facility rows are noisy web-extracted claims. The district dataset aggregates facility evidence and quality signals without pretending that each facility record is fully verified.
"""
        )
    )
    cells.append(
        code(
            """
district_cols = [
    "state_ut", "district_name", "observed_facility_rows",
    "health_need_score", "district_medical_desert_priority_score",
    "district_data_quality_score", "district_uncertainty_level",
    "source_url_rate", "needs_human_review_rate", "sample_facility_names"
]
district_clean[district_cols].head(20)
"""
        )
    )
    cells.append(
        md(
            """
## Join Strategy

Facilities do not carry a reliable district field. The defensible join path is:

1. Extract a six-digit Indian PIN from `address_zipOrPostcode`.
2. Join the PIN to India Post.
3. Collapse India Post rows to the modal district/state for each PIN while preserving ambiguity counts.
4. Normalize state and district names.
5. Join to NFHS district health indicators on normalized state + district.
6. Use facility city/state only as a low-confidence fallback when PIN is missing.

The cleaned dataset keeps `join_strategy`, `join_confidence`, `join_match_score`, and `join_uncertainty_reason` so downstream users can filter or review risky rows.
"""
        )
    )
    cells.append(code('clean["join_strategy"].value_counts(dropna=False).to_frame("rows")'))
    cells.append(md(f"![Join strategy distribution](../../{plot['join_strategy']})"))
    cells.append(
        md(
            """
## Field Coverage and Claim Risk

High field coverage is useful but not equivalent to truth. Description, procedure, equipment, and capability text can be used as evidence snippets, but the scores/rankings should cite those fields and disclose that they are extracted claims.
"""
        )
    )
    cells.append(md(f"![Field coverage](../../{plot['field_coverage']})"))
    cells.append(
        code(
            """
coverage = pd.DataFrame(summary["field_coverage"]).T
coverage.sort_values("present_pct")
"""
        )
    )
    cells.append(
        md(
            """
## Distribution Findings

The facility numeric fields are not Gaussian. They are sparse, parsed from text, and heavy-tailed. For ranking and cleaning, the pipeline uses log-scale plots, percentile ranks, and outlier flags instead of deleting high values.
"""
        )
    )
    cells.append(md(f"![Numeric distributions](../../{plot['numeric_distributions']})"))
    cells.append(code('pd.DataFrame(summary["distribution_profiles"]).T'))
    cells.append(
        md(
            """
## Geography and Join Uncertainty

Coordinates include off-India values and rows far from their pincode centroid. Those rows are flagged rather than silently dropped because they may reflect extraction errors, entity-resolution mistakes, or facilities with international web artifacts.
"""
        )
    )
    if "geo_quality" in plot:
        cells.append(md(f"![Geo quality scatter](../../{plot['geo_quality']})"))
    cells.append(code('clean["geo_quality"].value_counts(dropna=False).to_frame("rows")'))
    cells.append(
        md(
            """
## Medical Desert Proxy

Without true catchment population or verified facility supply, this is a proxy, not a definitive desert label. The score combines:

- NFHS district-level health need percentile.
- Inverse percentile of facility count observed in the joined FDR sample.

Use this to prioritize review and planning questions, not to make final policy claims.
"""
        )
    )
    if "medical_desert_proxy" in plot:
        cells.append(md(f"![Medical desert proxy](../../{plot['medical_desert_proxy']})"))
    cells.append(
        code(
            """
cols = [
    "state_ut", "district_name", "observed_facility_rows",
    "health_need_score", "district_medical_desert_priority_score",
    "district_data_quality_score", "district_uncertainty_level",
    "predominant_join_uncertainty", "sample_facility_names"
]
district_clean.sort_values("district_medical_desert_priority_score", ascending=False)[cols].head(20)
"""
        )
    )
    cells.append(
        md(
            """
## Data Readiness

The readiness score is deliberately conservative. It rewards parseable pincode, health join, plausible coordinates, non-ambiguous PIN bridge, source URLs, claim-text coverage, and contact evidence. Rows below the threshold or with outlier flags are marked `needs_human_review`.
"""
        )
    )
    cells.append(md(f"![Data readiness distribution](../../{plot['data_readiness']})"))
    if "district_data_quality" in plot:
        cells.append(md(f"![District data quality distribution](../../{plot['district_data_quality']})"))
    cells.append(code('clean["needs_human_review"].value_counts(dropna=False).to_frame("rows")'))
    cells.append(
        md(
            """
## Exported Artifacts

- `output/data/facility_health_cleaned.csv`
- `output/data/district_health_facility_cleaned.csv` (primary cleaned dataset)
- `output/data/district_unmatched_pincode_facility_counts.csv`
- `output/data/facility_health_cleaned_data_dictionary.csv`
- `output/data/district_health_facility_cleaned_data_dictionary.csv`
- `output/data/analysis_summary.json`
- `output/plots/*.png`
"""
        )
    )
    cells.append(
        code(
            """
district_path = DATA_DIR / "district_health_facility_cleaned.csv"
facility_audit_path = DATA_DIR / "facility_health_cleaned.csv"
dictionary_path = DATA_DIR / "district_health_facility_cleaned_data_dictionary.csv"
district_path, facility_audit_path, dictionary_path
"""
        )
    )

    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {
                "name": "python",
                "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    NOTEBOOK_PATH.write_text(json.dumps(notebook, indent=2), encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    print("Loading/querying facilities...")
    facilities = load_raw_or_query("raw_facilities_selected.csv", FACILITY_SQL)
    print(f"facilities: {facilities.shape}")

    print("Loading/querying pincode directory...")
    pincode = load_raw_or_query("raw_india_post_pincode_directory.csv", PINCODE_SQL)
    print(f"pincode: {pincode.shape}")

    print("Loading/querying NFHS health indicators...")
    health = load_raw_or_query("raw_nfhs_5_district_health_indicators.csv", HEALTH_SQL)
    print(f"health: {health.shape}")

    clean, pin_bridge = clean_and_join(facilities, pincode, health)
    district_clean, unmatched_districts = build_district_dataset(clean)
    clean.to_csv(DATA_DIR / "facility_health_cleaned.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    district_clean.to_csv(DATA_DIR / "district_health_facility_cleaned.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    unmatched_districts.to_csv(
        DATA_DIR / "district_unmatched_pincode_facility_counts.csv",
        index=False,
        quoting=csv.QUOTE_MINIMAL,
    )
    pin_bridge.to_csv(DATA_DIR / "pincode_bridge.csv", index=False, quoting=csv.QUOTE_MINIMAL)
    try:
        clean.to_parquet(DATA_DIR / "facility_health_cleaned.parquet", index=False)
    except Exception as exc:
        print(f"Parquet export skipped: {exc}")

    write_data_dictionary(clean, district_clean)
    plot_paths = plot_outputs(clean, district_clean, facilities)
    summary = make_summary(facilities, pincode, health, clean, district_clean, unmatched_districts, pin_bridge, plot_paths)
    (DATA_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_notebook(summary)

    print(f"cleaned: {clean.shape}")
    print(f"district cleaned: {district_clean.shape}")
    print(f"unmatched pincode districts: {unmatched_districts.shape}")
    print(f"notebook: {NOTEBOOK_PATH}")
    print(f"summary: {DATA_DIR / 'analysis_summary.json'}")


if __name__ == "__main__":
    main()
