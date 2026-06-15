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
from datetime import date
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
CURRENT_DATE = pd.Timestamp(date(2026, 6, 15))

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


NULLISH_TOKENS = {
    "",
    "null",
    "none",
    "nan",
    "na",
    "n/a",
    "not available",
    "not applicable",
    "unknown",
    "nil",
    "[]",
    "[\"\"]",
    "['']",
}

NO_EVIDENCE_PATTERNS = [
    re.compile(r"^no\s+(specific\s+)?(equipment|procedure|specialt(y|ies)|capabilit(y|ies)|details?)\s+(details?\s+)?(provided|listed|available|mentioned)", re.I),
    re.compile(r"^(equipment|procedure|specialt(y|ies)|capabilit(y|ies)|details?)\s+(not\s+)?(provided|listed|available|mentioned|specified)$", re.I),
    re.compile(r"^(not\s+provided|not\s+specified|not\s+available|unknown|none|nil|n/?a)$", re.I),
]


def clean_text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def is_nullish_scalar(value: Any) -> bool:
    text = clean_text(value)
    if not text:
        return True
    compact = text.lower()
    return compact in NULLISH_TOKENS


def is_no_evidence_text(value: Any) -> bool:
    text = clean_text(value)
    if is_nullish_scalar(text):
        return True
    return any(pattern.search(text) for pattern in NO_EVIDENCE_PATTERNS)


def semantic_items(value: Any) -> list[str]:
    """Return meaningful items from a scalar or JSON-ish array field.

    FDR fields often contain strings such as "null", "[]", [""] or
    "No equipment details provided". These are semantically missing even when
    the raw string is non-empty.
    """

    if pd.isna(value):
        return []
    text = clean_text(value)
    if is_nullish_scalar(text):
        return []

    candidates: list[Any]
    if text.startswith("[") or text.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            candidates = parsed
        elif isinstance(parsed, dict):
            candidates = list(parsed.values())
        else:
            candidates = [text]
    else:
        candidates = [text]

    items: list[str] = []
    for candidate in candidates:
        if isinstance(candidate, (list, tuple)):
            nested = candidate
        else:
            nested = [candidate]
        for item in nested:
            item_text = clean_text(item)
            if not item_text or is_no_evidence_text(item_text):
                continue
            items.append(item_text)
    return items


def has_semantic_evidence(value: Any) -> bool:
    return len(semantic_items(value)) > 0


def semantic_nonempty(series: pd.Series) -> pd.Series:
    return series.map(has_semantic_evidence)


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


def parse_recency_status(series: pd.Series) -> tuple[pd.Series, pd.Series, pd.Series]:
    raw_missing = ~semantic_nonempty(series)
    parsed = pd.to_datetime(series.where(~raw_missing), errors="coerce")
    status = pd.Series("observed_valid", index=series.index, dtype=object)
    status[raw_missing] = "missing_semantic"
    status[~raw_missing & parsed.isna()] = "invalid_parse"
    status[parsed.notna() & parsed.gt(CURRENT_DATE)] = "future_date_invalid"
    status[parsed.notna() & parsed.le(CURRENT_DATE - pd.Timedelta(days=730))] = "stale_over_2y"
    confidence = pd.Series("high", index=series.index, dtype=object)
    confidence[status.eq("stale_over_2y")] = "medium"
    confidence[status.isin(["missing_semantic", "invalid_parse", "future_date_invalid"])] = "low"
    return parsed.dt.strftime("%Y-%m-%d"), status, confidence


def build_group_stats(
    frame: pd.DataFrame,
    value_col: str,
    valid_mask: pd.Series,
    group_cols: list[str],
    *,
    min_n: int,
) -> dict[tuple[Any, ...], dict[str, float]]:
    stats: dict[tuple[Any, ...], dict[str, float]] = {}
    subset = frame[valid_mask & frame[group_cols].notna().all(axis=1)].copy()
    if subset.empty:
        return stats
    for key, group in subset.groupby(group_cols, dropna=True):
        values = pd.to_numeric(group[value_col], errors="coerce").dropna()
        if len(values) < min_n:
            continue
        if not isinstance(key, tuple):
            key = (key,)
        stats[key] = {
            "n": float(len(values)),
            "median": float(values.median()),
            "p10": float(values.quantile(0.10)),
            "p90": float(values.quantile(0.90)),
        }
    return stats


def add_numeric_estimates(
    frame: pd.DataFrame,
    *,
    raw_col: str,
    value_col: str,
    outlier_col: str,
    prefix: str,
) -> pd.DataFrame:
    result = frame.copy()
    raw_missing = ~semantic_nonempty(result[raw_col])
    valid_observed = result[value_col].notna() & ~result[outlier_col].fillna(False)
    present_unparseable = ~raw_missing & result[value_col].isna()
    observed_outlier = result[outlier_col].fillna(False)

    status = pd.Series("observed_valid", index=result.index, dtype=object)
    status[raw_missing] = "missing_semantic"
    status[present_unparseable] = "present_unparseable"
    status[observed_outlier] = "observed_extreme_outlier"
    result[f"{prefix}_status"] = status

    group_specs = [
        (["facilityTypeId", "operatorTypeId", "pincode_primary_state"], 5, "facility_type_operator_state"),
        (["facilityTypeId", "operatorTypeId"], 10, "facility_type_operator"),
        (["facilityTypeId"], 10, "facility_type"),
        (["operatorTypeId"], 10, "operator_type"),
    ]
    grouped_stats = [
        (cols, label, build_group_stats(result, value_col, valid_observed, cols, min_n=min_n))
        for cols, min_n, label in group_specs
    ]
    global_values = pd.to_numeric(result.loc[valid_observed, value_col], errors="coerce").dropna()
    global_stats = {
        "n": float(len(global_values)),
        "median": float(global_values.median()) if len(global_values) else np.nan,
        "p10": float(global_values.quantile(0.10)) if len(global_values) else np.nan,
        "p90": float(global_values.quantile(0.90)) if len(global_values) else np.nan,
    }

    estimates: list[float] = []
    lows: list[float] = []
    highs: list[float] = []
    sources: list[str] = []
    sample_ns: list[float] = []
    confidences: list[str] = []

    for idx, row in result.iterrows():
        if valid_observed.loc[idx]:
            value = float(row[value_col])
            estimates.append(value)
            lows.append(value)
            highs.append(value)
            sources.append("observed_extracted_claim")
            sample_ns.append(1.0)
            confidences.append("observed")
            continue

        chosen: dict[str, float] | None = None
        source = "global_median"
        for cols, label, stats in grouped_stats:
            if row[cols].isna().any():
                continue
            key = tuple(row[col] for col in cols)
            if key in stats:
                chosen = stats[key]
                source = label
                break
        if chosen is None:
            chosen = global_stats

        estimates.append(chosen["median"])
        lows.append(chosen["p10"])
        highs.append(chosen["p90"])
        sources.append(source)
        sample_ns.append(chosen["n"])
        if chosen["n"] >= 50:
            confidences.append("medium")
        elif chosen["n"] >= 10:
            confidences.append("low_medium")
        else:
            confidences.append("low")

    result[f"{prefix}_estimate"] = estimates
    result[f"{prefix}_estimate_interval_low"] = lows
    result[f"{prefix}_estimate_interval_high"] = highs
    result[f"{prefix}_estimate_source"] = sources
    result[f"{prefix}_estimate_sample_n"] = sample_ns
    result[f"{prefix}_confidence"] = confidences
    result[f"{prefix}_is_estimated"] = ~valid_observed
    result[f"{prefix}_display_value"] = np.where(
        valid_observed,
        result[value_col],
        result[f"{prefix}_estimate"],
    )
    return result


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
    if "regionname" in pin.columns:
        pin["pincode_region_norm"] = pin["regionname"].map(normalize_text)
    else:
        pin["pincode_region_norm"] = ""

    grouped = (
        pin.groupby("pincode_extracted", dropna=False)
        .agg(
            pincode_primary_district=("district", weighted_mode),
            pincode_primary_state=("statename", weighted_mode),
            pincode_primary_region=("regionname", weighted_mode) if "regionname" in pin.columns else ("pincode_region_norm", weighted_mode),
            pincode_n_offices=("officename", "count"),
            pincode_n_districts=("pincode_district_norm", pd.Series.nunique),
            pincode_n_states=("pincode_state_norm", pd.Series.nunique),
            pincode_n_regions=("pincode_region_norm", pd.Series.nunique),
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
    grouped["pincode_region_is_ambiguous"] = grouped["pincode_n_regions"] > 1
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
    fac["capacity_raw_semantic_missing"] = ~semantic_nonempty(fac["capacity"])
    fac["number_doctors_raw_semantic_missing"] = ~semantic_nonempty(fac["numberDoctors"])
    fac["year_established_raw_semantic_missing"] = ~semantic_nonempty(fac["yearEstablished"])
    fac["year_established_status"] = np.select(
        [
            fac["year_established_num"].notna(),
            fac["year_established_raw_semantic_missing"],
        ],
        ["observed_valid", "missing_semantic"],
        default="present_unparseable",
    )
    fac["year_established_confidence"] = np.select(
        [
            fac["year_established_status"].eq("observed_valid"),
            fac["year_established_status"].eq("present_unparseable"),
        ],
        ["high", "low"],
        default="low",
    )
    (
        fac["recency_page_update_date"],
        fac["recency_status"],
        fac["recency_confidence"],
    ) = parse_recency_status(fac["recency_of_page_update"])

    claim_cols = ["description", "specialties", "procedure", "equipment", "capability"]
    for col in claim_cols:
        fac[f"has_{col}"] = semantic_nonempty(fac[col])
        fac[f"{col}_item_count"] = fac[col].map(lambda value: len(semantic_items(value)))
        fac[f"{col}_len"] = fac[col].fillna("").astype(str).str.len()
        fac[f"{col}_status"] = np.where(fac[f"has_{col}"], "observed_claim", "missing_semantic")
    fac["equipment_confidence"] = np.where(fac["has_equipment"], "medium_claim", "low_no_evidence")
    fac["claim_field_count"] = fac[[f"has_{c}" for c in claim_cols]].sum(axis=1)
    fac["has_source_urls"] = semantic_nonempty(fac["source_urls"])
    fac["has_contact_evidence"] = semantic_nonempty(fac["officialPhone"]) | semantic_nonempty(fac["phone_numbers"]) | semantic_nonempty(fac["email"])
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

    clean = add_numeric_estimates(
        clean,
        raw_col="capacity",
        value_col="capacity_num",
        outlier_col="capacity_num_extreme_outlier",
        prefix="capacity",
    )
    clean = add_numeric_estimates(
        clean,
        raw_col="numberDoctors",
        value_col="number_doctors_num",
        outlier_col="number_doctors_num_extreme_outlier",
        prefix="doctor_count",
    )
    clean["recency_valid_signal"] = clean["recency_status"].isin(["observed_valid", "stale_over_2y"])
    clean["recency_invalid_signal"] = clean["recency_status"].isin(["invalid_parse", "future_date_invalid"])
    clean["semantic_missing_critical_count"] = (
        clean["capacity_status"].ne("observed_valid").astype(int)
        + clean["doctor_count_status"].ne("observed_valid").astype(int)
        + clean["year_established_status"].ne("observed_valid").astype(int)
        + clean["recency_status"].ne("observed_valid").astype(int)
        + clean["equipment_status"].ne("observed_claim").astype(int)
    )
    clean["critical_supply_gap_flag"] = clean["semantic_missing_critical_count"].ge(3) | clean[
        ["capacity_num_extreme_outlier", "number_doctors_num_extreme_outlier", "recency_invalid_signal"]
    ].any(axis=1)
    clean["supply_data_confidence_score"] = (
        0.24 * clean["capacity_confidence"].isin(["observed", "medium"]).astype(float)
        + 0.24 * clean["doctor_count_confidence"].isin(["observed", "medium"]).astype(float)
        + 0.18 * clean["has_equipment"].astype(float)
        + 0.14 * clean["recency_valid_signal"].astype(float)
        + 0.10 * clean["year_established_status"].eq("observed_valid").astype(float)
        + 0.10 * clean["has_source_urls"].astype(float)
    ).round(3)
    clean["semantic_data_quality_score"] = (
        0.45 * clean["supply_data_confidence_score"]
        + 0.25 * (1 - clean["semantic_missing_critical_count"] / 5)
        + 0.15 * clean["has_source_urls"].astype(float)
        + 0.15 * clean["has_contact_evidence"].astype(float)
    ).clip(0, 1).round(3)
    clean["data_readiness_score"] = (
        0.70 * clean["data_readiness_score"] + 0.30 * clean["semantic_data_quality_score"]
    ).round(3)

    clean["needs_human_review"] = (
        clean["data_readiness_score"].lt(0.65)
        | clean["semantic_data_quality_score"].lt(0.45)
        | clean["critical_supply_gap_flag"]
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
        & clean["supply_data_confidence_score"].ge(0.65)
        & ~clean["capacity_num_extreme_outlier"]
        & ~clean["number_doctors_num_extreme_outlier"]
        & ~clean["recency_invalid_signal"]
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
        "pincode_primary_region",
        "pincode_n_offices",
        "pincode_n_districts",
        "pincode_n_states",
        "pincode_n_regions",
        "pincode_is_ambiguous",
        "pincode_region_is_ambiguous",
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
        "year_established_status",
        "year_established_confidence",
        "capacity",
        "capacity_num",
        "capacity_status",
        "capacity_estimate",
        "capacity_estimate_interval_low",
        "capacity_estimate_interval_high",
        "capacity_estimate_source",
        "capacity_estimate_sample_n",
        "capacity_confidence",
        "capacity_is_estimated",
        "capacity_display_value",
        "numberDoctors",
        "number_doctors_num",
        "doctor_count_status",
        "doctor_count_estimate",
        "doctor_count_estimate_interval_low",
        "doctor_count_estimate_interval_high",
        "doctor_count_estimate_source",
        "doctor_count_estimate_sample_n",
        "doctor_count_confidence",
        "doctor_count_is_estimated",
        "doctor_count_display_value",
        "recency_of_page_update",
        "recency_page_update_date",
        "recency_status",
        "recency_confidence",
        "recency_valid_signal",
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
        "description_item_count",
        "specialties_item_count",
        "procedure_item_count",
        "equipment_item_count",
        "capability_item_count",
        "description_status",
        "specialties_status",
        "procedure_status",
        "equipment_status",
        "equipment_confidence",
        "capability_status",
        "description_len",
        "specialties_len",
        "procedure_len",
        "equipment_len",
        "capability_len",
        "has_source_urls",
        "has_contact_evidence",
        "supply_data_confidence_score",
        "semantic_data_quality_score",
        "semantic_missing_critical_count",
        "critical_supply_gap_flag",
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
        "pincode_region_is_ambiguous",
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
        "recency_valid_signal",
        "critical_supply_gap_flag",
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
        pincode_region_ambiguous_rows=("pincode_region_is_ambiguous", "sum"),
        exact_join_rows=("join_strategy", lambda s: int(s.eq("pincode_district_state_exact").sum())),
        fuzzy_join_rows=("join_strategy", lambda s: int(s.eq("pincode_district_state_fuzzy").sum())),
        city_fallback_rows=("join_strategy", lambda s: int(s.eq("facility_city_state_fallback").sum())),
        avg_join_confidence=("join_confidence", "mean"),
        avg_data_readiness_score=("data_readiness_score", "mean"),
        avg_semantic_data_quality_score=("semantic_data_quality_score", "mean"),
        avg_supply_data_confidence_score=("supply_data_confidence_score", "mean"),
        avg_semantic_missing_critical_count=("semantic_missing_critical_count", "mean"),
        median_data_readiness_score=("data_readiness_score", "median"),
        needs_human_review_rows=("needs_human_review", "sum"),
        critical_supply_gap_rows=("critical_supply_gap_flag", "sum"),
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
        capacity_observed_rows=("capacity_status", lambda s: int(s.eq("observed_valid").sum())),
        capacity_estimated_rows=("capacity_is_estimated", "sum"),
        capacity_low_confidence_rows=("capacity_confidence", lambda s: int(s.isin(["low", "low_medium"]).sum())),
        observed_capacity_sum=("capacity_num", "sum"),
        observed_capacity_median=("capacity_num", "median"),
        observed_capacity_p95=("capacity_num", lambda s: float(s.dropna().quantile(0.95)) if s.notna().any() else np.nan),
        observed_capacity_max=("capacity_num", "max"),
        estimated_capacity_sum=("capacity_display_value", "sum"),
        estimated_capacity_median=("capacity_display_value", "median"),
        parsed_doctor_rows=("number_doctors_num", lambda s: int(s.notna().sum())),
        doctor_observed_rows=("doctor_count_status", lambda s: int(s.eq("observed_valid").sum())),
        doctor_estimated_rows=("doctor_count_is_estimated", "sum"),
        doctor_low_confidence_rows=("doctor_count_confidence", lambda s: int(s.isin(["low", "low_medium"]).sum())),
        observed_doctors_sum=("number_doctors_num", "sum"),
        observed_doctors_median=("number_doctors_num", "median"),
        observed_doctors_p95=("number_doctors_num", lambda s: float(s.dropna().quantile(0.95)) if s.notna().any() else np.nan),
        observed_doctors_max=("number_doctors_num", "max"),
        estimated_doctors_sum=("doctor_count_display_value", "sum"),
        estimated_doctors_median=("doctor_count_display_value", "median"),
        valid_recency_rows=("recency_valid_signal", "sum"),
        future_recency_rows=("recency_status", lambda s: int(s.eq("future_date_invalid").sum())),
        stale_recency_rows=("recency_status", lambda s: int(s.eq("stale_over_2y").sum())),
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
    district["pincode_region_ambiguity_rate"] = district["pincode_region_ambiguous_rows"] / count
    district["needs_human_review_rate"] = district["needs_human_review_rows"] / count
    district["critical_supply_gap_rate"] = district["critical_supply_gap_rows"] / count
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
    district["capacity_observed_rate"] = district["capacity_observed_rows"] / count
    district["capacity_estimated_rate"] = district["capacity_estimated_rows"] / count
    district["capacity_low_confidence_rate"] = district["capacity_low_confidence_rows"] / count
    district["doctor_parse_rate"] = district["parsed_doctor_rows"] / count
    district["doctor_observed_rate"] = district["doctor_observed_rows"] / count
    district["doctor_estimated_rate"] = district["doctor_estimated_rows"] / count
    district["doctor_low_confidence_rate"] = district["doctor_low_confidence_rows"] / count
    district["recency_valid_rate"] = district["valid_recency_rows"] / count
    district["future_recency_rate"] = district["future_recency_rows"] / count
    district["stale_recency_rate"] = district["stale_recency_rows"] / count
    district["exact_join_rate"] = district["exact_join_rows"] / count

    for stem, success_col in [
        ("needs_human_review", "needs_human_review_rows"),
        ("critical_supply_gap", "critical_supply_gap_rows"),
        ("plausible_geo", "plausible_geo_rows"),
        ("source_url", "source_url_rows"),
        ("trustworthy_supply", "trustworthy_supply_rows"),
        ("exact_join", "exact_join_rows"),
        ("capacity_observed", "capacity_observed_rows"),
        ("doctor_observed", "doctor_observed_rows"),
        ("equipment", "equipment_rows"),
        ("recency_valid", "valid_recency_rows"),
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
        + 0.25 * district["needs_human_review_rate"].fillna(1)
        + 0.20 * district["critical_supply_gap_rate"].fillna(1)
        + 0.10 * district["contradicted_or_geo_invalid_rate"].fillna(0)
    ).clip(0, 1)
    district["district_data_quality_score"] = (
        0.22 * district["avg_data_readiness_score"].fillna(0)
        + 0.20 * district["avg_semantic_data_quality_score"].fillna(0)
        + 0.18 * district["avg_join_confidence"].fillna(0)
        + 0.15 * district["plausible_geo_rate"].fillna(0)
        + 0.10 * district["source_url_rate"].fillna(0)
        + 0.10 * (1 - district["critical_supply_gap_rate"].fillna(1))
        + 0.05 * (1 - district["needs_human_review_rate"].fillna(1))
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
        "avg_semantic_data_quality_score",
        "avg_supply_data_confidence_score",
        "avg_semantic_missing_critical_count",
        "median_data_readiness_score",
        "exact_join_rows",
        "fuzzy_join_rows",
        "city_fallback_rows",
        "exact_join_rate",
        "exact_join_rate_ci_low",
        "exact_join_rate_ci_high",
        "pincode_ambiguous_rows",
        "pincode_ambiguity_rate",
        "pincode_region_ambiguous_rows",
        "pincode_region_ambiguity_rate",
        "needs_human_review_rows",
        "needs_human_review_rate",
        "needs_human_review_rate_ci_low",
        "needs_human_review_rate_ci_high",
        "critical_supply_gap_rows",
        "critical_supply_gap_rate",
        "critical_supply_gap_rate_ci_low",
        "critical_supply_gap_rate_ci_high",
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
        "equipment_rate_ci_low",
        "equipment_rate_ci_high",
        "capability_rate",
        "parsed_capacity_rows",
        "capacity_parse_rate",
        "capacity_observed_rows",
        "capacity_observed_rate",
        "capacity_observed_rate_ci_low",
        "capacity_observed_rate_ci_high",
        "capacity_estimated_rows",
        "capacity_estimated_rate",
        "capacity_low_confidence_rows",
        "capacity_low_confidence_rate",
        "observed_capacity_sum",
        "observed_capacity_median",
        "observed_capacity_p95",
        "observed_capacity_max",
        "estimated_capacity_sum",
        "estimated_capacity_median",
        "parsed_doctor_rows",
        "doctor_parse_rate",
        "doctor_observed_rows",
        "doctor_observed_rate",
        "doctor_observed_rate_ci_low",
        "doctor_observed_rate_ci_high",
        "doctor_estimated_rows",
        "doctor_estimated_rate",
        "doctor_low_confidence_rows",
        "doctor_low_confidence_rate",
        "observed_doctors_sum",
        "observed_doctors_median",
        "observed_doctors_p95",
        "observed_doctors_max",
        "estimated_doctors_sum",
        "estimated_doctors_median",
        "valid_recency_rows",
        "recency_valid_rate",
        "recency_valid_rate_ci_low",
        "recency_valid_rate_ci_high",
        "future_recency_rows",
        "future_recency_rate",
        "stale_recency_rows",
        "stale_recency_rate",
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
            "present_pct": [100 * semantic_nonempty(facilities[c]).mean() if c in facilities else np.nan for c in key_fields],
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

    geo_candidates_path = DATA_DIR / "geo_validation_candidates.csv"
    if geo_candidates_path.exists():
        geo_candidates = pd.read_csv(geo_candidates_path, low_memory=False)
        required = {"external_validation_action", "external_validation_priority_score", "geo_review_reason"}
        if not geo_candidates.empty and required.issubset(geo_candidates.columns):
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))
            action_counts = geo_candidates["external_validation_action"].value_counts().sort_values()
            sns.barplot(
                x=action_counts.values,
                y=action_counts.index,
                ax=axes[0],
                color="#3c6e71",
            )
            axes[0].set_title("External Validation Actions")
            axes[0].set_xlabel("Candidate rows")
            axes[0].set_ylabel("")

            reason_priority = (
                geo_candidates.groupby("geo_review_reason")["external_validation_priority_score"]
                .mean()
                .sort_values()
            )
            sns.barplot(
                x=reason_priority.values,
                y=reason_priority.index,
                ax=axes[1],
                color="#d98c3a",
            )
            axes[1].set_title("Mean Source-Enrichment Priority")
            axes[1].set_xlabel("Priority score")
            axes[1].set_ylabel("")
            plt.tight_layout()
            path = PLOT_DIR / "geo_external_validation_actions.png"
            plt.savefig(path, dpi=160)
            plt.close()
            plot_paths["geo_external_validation_actions"] = str(path.relative_to(ROOT))

        scatter_required = {
            "geo_distance_km_to_pincode_centroid",
            "external_validation_priority_score",
            "geo_review_reason",
        }
        if not geo_candidates.empty and scatter_required.issubset(geo_candidates.columns):
            plot_df = geo_candidates.copy()
            plot_df["distance_for_plot_km"] = pd.to_numeric(
                plot_df["geo_distance_km_to_pincode_centroid"], errors="coerce"
            ).clip(lower=0, upper=2500)
            plot_df["external_validation_priority_score"] = pd.to_numeric(
                plot_df["external_validation_priority_score"], errors="coerce"
            )
            plot_df = plot_df.dropna(subset=["distance_for_plot_km", "external_validation_priority_score"])
            if not plot_df.empty:
                plt.figure(figsize=(10, 6))
                sns.scatterplot(
                    data=plot_df,
                    x="distance_for_plot_km",
                    y="external_validation_priority_score",
                    hue="geo_review_reason",
                    s=48,
                    alpha=0.75,
                )
                plt.xscale("symlog", linthresh=10)
                plt.xlabel("Distance from India Post PIN centroid, km (capped at 2,500)")
                plt.ylabel("External validation priority score")
                plt.title("Geo Failures Prioritized for External API Calls")
                plt.grid(alpha=0.25)
                plt.tight_layout()
                path = PLOT_DIR / "geo_external_priority_scatter.png"
                plt.savefig(path, dpi=160)
                plt.close()
                plot_paths["geo_external_priority_scatter"] = str(path.relative_to(ROOT))

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
        "semantic_data_quality_score": "Score over semantic missingness for supply fields such as capacity, doctors, recency, equipment, source URLs, and contact evidence.",
        "supply_data_confidence_score": "Confidence score for facility supply planning fields: capacity, doctors, equipment, recency, year, and source URLs.",
        "semantic_missing_critical_count": "Count of critical fields that are semantically missing, invalid, or unobserved: capacity, doctors, year, recency, equipment.",
        "critical_supply_gap_flag": "True when supply planning fields have multiple semantic gaps or invalid/outlier values.",
        "capacity_status": "Observed/semantic-missing/unparseable/outlier status for raw capacity.",
        "capacity_estimate": "Capacity value for planning when missing, estimated from facility/operator/state cohorts with fallback to broader medians.",
        "capacity_estimate_interval_low": "Empirical 10th percentile of the cohort used for capacity estimate; prediction interval, not verified truth.",
        "capacity_estimate_interval_high": "Empirical 90th percentile of the cohort used for capacity estimate; prediction interval, not verified truth.",
        "capacity_confidence": "Observed/medium/low-medium/low confidence label based on whether capacity was observed and the estimation cohort sample size.",
        "doctor_count_status": "Observed/semantic-missing/unparseable/outlier status for raw numberDoctors.",
        "doctor_count_estimate": "Doctor-count value for planning when missing, estimated from facility/operator/state cohorts with fallback to broader medians.",
        "doctor_count_confidence": "Observed/medium/low-medium/low confidence label based on whether doctor count was observed and the estimation cohort sample size.",
        "recency_status": "Semantic status for recency_of_page_update: observed_valid, stale_over_2y, future_date_invalid, invalid_parse, or missing_semantic.",
        "equipment_status": "Semantic status for equipment claim field after removing empty arrays, blank strings, nulls, and no-evidence phrases.",
        "medical_desert_priority_score": "Planner proxy: high district health need plus low facility count in the joined sample.",
        "health_need_score": "Percentile composite over adverse NFHS indicators. It is district-level context, not a facility label.",
        "claim_text": "Truncated concatenation of raw extracted text fields used as claim evidence.",
        "needs_human_review": "Legacy flag for rows needing uncertainty review due to low readiness, low join confidence, geography issues, sparse evidence, or extreme parsed numerics.",
    }
    district_descriptions = {
        "observed_facility_rows": "Number of FDR facility rows joined into this district. This is not a verified facility census.",
        "health_need_score": "Percentile composite over adverse NFHS district indicators.",
        "district_medical_desert_priority_score": "Proxy score: high health need plus low observed FDR facility count percentile.",
        "district_data_quality_score": "Composite quality score from readiness, join confidence, geography, source URLs, and review rate.",
        "district_uncertainty_level": "Lower/medium/higher uncertainty based on district quality score and observed row count.",
        "exact_join_rate": "Share of facility rows that joined through exact pincode district/state match.",
        "needs_human_review_rate": "Share of facility rows in the district flagged for uncertainty review.",
        "critical_supply_gap_rate": "Share of facility rows with multiple critical supply-field semantic gaps or invalid values.",
        "plausible_geo_rate": "Share of facility rows with plausible India coordinates and pincode centroid distance.",
        "source_url_rate": "Share of facility rows with source URLs for evidence citation.",
        "capacity_parse_rate": "Share of facility rows where capacity could be parsed into a number.",
        "capacity_observed_rate": "Share of facility rows with observed non-outlier capacity values.",
        "capacity_estimated_rate": "Share of facility rows using estimated capacity values.",
        "doctor_parse_rate": "Share of facility rows where numberDoctors could be parsed into a number.",
        "doctor_observed_rate": "Share of facility rows with observed non-outlier doctor-count values.",
        "doctor_estimated_rate": "Share of facility rows using estimated doctor-count values.",
        "recency_valid_rate": "Share of facility rows with parseable, non-future recency dates.",
        "pincode_region_ambiguity_rate": "Share of facility rows whose PIN maps to multiple India Post region names, based on duplicate pincode rows.",
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


def write_semantic_missingness_summary(clean: pd.DataFrame) -> pd.DataFrame:
    specs = [
        {
            "field": "capacity",
            "status_col": "capacity_status",
            "valid_statuses": ["observed_valid"],
            "estimated_col": "capacity_is_estimated",
            "confidence_col": "capacity_confidence",
            "why_it_matters": "Beds/capacity planning and referral routing.",
        },
        {
            "field": "numberDoctors",
            "status_col": "doctor_count_status",
            "valid_statuses": ["observed_valid"],
            "estimated_col": "doctor_count_is_estimated",
            "confidence_col": "doctor_count_confidence",
            "why_it_matters": "Staffing gaps, beds-per-doctor ratios, and care availability.",
        },
        {
            "field": "yearEstablished",
            "status_col": "year_established_status",
            "valid_statuses": ["observed_valid"],
            "estimated_col": None,
            "confidence_col": "year_established_confidence",
            "why_it_matters": "Trust signal for established facilities.",
        },
        {
            "field": "recency_of_page_update",
            "status_col": "recency_status",
            "valid_statuses": ["observed_valid", "stale_over_2y"],
            "estimated_col": None,
            "confidence_col": "recency_confidence",
            "why_it_matters": "Freshness signal for extracted web evidence.",
        },
        {
            "field": "equipment",
            "status_col": "equipment_status",
            "valid_statuses": ["observed_claim"],
            "estimated_col": None,
            "confidence_col": "equipment_confidence",
            "why_it_matters": "Referral routing for diagnostics, dialysis, imaging, and specialty services.",
        },
    ]
    rows: list[dict[str, Any]] = []
    n = len(clean)
    for spec in specs:
        status = clean[spec["status_col"]].fillna("missing_semantic")
        valid = status.isin(spec["valid_statuses"])
        ci_low, ci_high = wilson_interval(int(valid.sum()), n)
        estimated_rows = int(clean[spec["estimated_col"]].sum()) if spec["estimated_col"] else 0
        low_confidence_rows = (
            int(clean[spec["confidence_col"]].fillna("").isin(["low", "low_medium", "low_no_evidence"]).sum())
            if spec["confidence_col"]
            else 0
        )
        rows.append(
            {
                "field": spec["field"],
                "rows": n,
                "semantic_valid_rows": int(valid.sum()),
                "semantic_valid_pct": float(100 * valid.mean()),
                "semantic_valid_rate_ci_low": ci_low,
                "semantic_valid_rate_ci_high": ci_high,
                "semantic_missing_or_invalid_rows": int((~valid).sum()),
                "semantic_missing_or_invalid_pct": float(100 * (~valid).mean()),
                "estimated_rows": estimated_rows,
                "low_confidence_rows": low_confidence_rows,
                "status_counts": json.dumps(status.value_counts(dropna=False).to_dict(), sort_keys=True),
                "why_it_matters": spec["why_it_matters"],
            }
        )
    summary = pd.DataFrame(rows)
    summary.to_csv(DATA_DIR / "semantic_missingness_summary.csv", index=False)
    return summary


def _series_01(series: pd.Series, default: float = 0.0) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce")
    if numeric.notna().sum() == 0:
        return pd.Series(default, index=series.index, dtype=float)
    filled = numeric.fillna(numeric.median()).astype(float)
    lo = filled.min()
    hi = filled.max()
    if not np.isfinite(lo) or not np.isfinite(hi) or math.isclose(lo, hi):
        return pd.Series(default, index=series.index, dtype=float)
    return ((filled - lo) / (hi - lo)).clip(0, 1)


def _boolish(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    return series.astype(str).str.lower().isin(["true", "1", "yes"])


def _relative_interval_width(low: pd.Series, high: pd.Series, point: pd.Series) -> pd.Series:
    low_num = pd.to_numeric(low, errors="coerce")
    high_num = pd.to_numeric(high, errors="coerce")
    point_num = pd.to_numeric(point, errors="coerce").abs().replace(0, np.nan)
    width = ((high_num - low_num).abs() / point_num).replace([np.inf, -np.inf], np.nan)
    return (width / (1 + width)).fillna(0).clip(0, 1)


def _json_reasons(row: pd.Series, checks: list[tuple[str, bool]]) -> str:
    return json.dumps([reason for reason, include in checks if include], sort_keys=True)


def _geo_uncertainty_bands(
    geo_quality: pd.Series,
    distance_km: pd.Series,
    contradicted: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Planning uncertainty bands for coordinates before external geocoding.

    These are heuristic evidence-quality bands, not measured geocoder error.
    They make the current coordinate disagreement visible for triage and UI copy.
    """

    geo_text = geo_quality.fillna("").astype(str).str.lower()
    distance = pd.to_numeric(distance_km, errors="coerce").fillna(0).clip(lower=0)
    contradicted_bool = _boolish(contradicted)
    low = pd.Series(0.1, index=geo_quality.index, dtype=float)
    high = pd.Series(5.0, index=geo_quality.index, dtype=float)

    outside = geo_text.str.contains("outside", na=False)
    far = geo_text.str.contains("far", na=False)
    moderate = geo_text.str.contains("moderate", na=False)
    missing = geo_text.str.contains("missing", na=False)
    contradiction_only = contradicted_bool & ~(outside | far | moderate | missing)

    low[outside] = 50.0
    high[outside] = distance[outside].clip(lower=250.0, upper=5000.0)
    low[far] = 10.0
    high[far] = distance[far].clip(lower=50.0, upper=2500.0)
    low[moderate] = 2.0
    high[moderate] = distance[moderate].clip(lower=10.0, upper=250.0)
    low[missing] = 10.0
    high[missing] = 250.0
    low[contradiction_only] = 5.0
    high[contradiction_only] = distance[contradiction_only].clip(lower=25.0, upper=1000.0)

    distance_score = (distance.clip(upper=250.0) / 250.0).clip(0, 1)
    quality_score = pd.Series(0.0, index=geo_quality.index, dtype=float)
    quality_score[moderate] = 0.35
    quality_score[far] = 0.75
    quality_score[outside | missing] = 1.0
    quality_score[contradiction_only] = 0.65
    geo_uncertainty_score = (0.68 * quality_score + 0.32 * distance_score).clip(0, 1)
    return low.round(2), high.round(2), geo_uncertainty_score.round(4)


def build_active_learning_queues(clean: pd.DataFrame, district: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Rank records where more evidence would most reduce planning uncertainty.

    This is active-learning inspired, but without a human-oracle assumption. The
    queue identifies rows/districts for source enrichment, sensitivity analysis,
    and cautious UI surfacing. Scores are triage heuristics, not measured accuracy.
    """

    fac = clean.copy()
    segment_cols = ["facilityTypeId", "operatorTypeId", "pincode_primary_state"]
    for col in segment_cols:
        if col not in fac:
            fac[col] = ""
    segment_n = fac.groupby(segment_cols, dropna=False)["unique_id"].transform("count")
    segment_rarity_score = (1 - (segment_n.clip(upper=50) / 50)).fillna(0).clip(0, 1)

    capacity_width = _relative_interval_width(
        fac["capacity_estimate_interval_low"],
        fac["capacity_estimate_interval_high"],
        fac["capacity_display_value"],
    )
    doctor_width = _relative_interval_width(
        fac["doctor_count_estimate_interval_low"],
        fac["doctor_count_estimate_interval_high"],
        fac["doctor_count_display_value"],
    )
    capacity_estimated = _boolish(fac["capacity_is_estimated"])
    doctor_estimated = _boolish(fac["doctor_count_is_estimated"])
    critical_gap = _boolish(fac["critical_supply_gap_flag"])
    geo_risk = fac["geo_quality"].fillna("").ne("plausible")
    geo_band_low, geo_band_high, external_geo_uncertainty_score = _geo_uncertainty_bands(
        fac["geo_quality"],
        fac["geo_distance_km_to_pincode_centroid"],
        fac["contradicted_or_geo_invalid_signal"],
    )
    low_join = pd.to_numeric(fac["join_confidence"], errors="coerce").fillna(0).lt(0.8)
    pincode_ambiguous = _boolish(fac["pincode_is_ambiguous"]) | _boolish(fac["pincode_region_is_ambiguous"])
    no_contact = ~_boolish(fac["has_contact_evidence"])
    no_source = ~_boolish(fac["has_source_urls"])
    outlier = _boolish(fac["capacity_num_extreme_outlier"]) | _boolish(fac["number_doctors_num_extreme_outlier"])
    recency_invalid = fac["recency_status"].fillna("").isin(["invalid_parse", "future_date_invalid", "missing_semantic"])

    clinical_impact = _series_01(fac["health_need_score"], default=0.5)
    medical_desert = _series_01(fac["medical_desert_priority_score"], default=0.5)
    data_quality_gap = (1 - pd.to_numeric(fac["semantic_data_quality_score"], errors="coerce").fillna(0)).clip(0, 1)

    uncertainty_score = (
        0.22 * data_quality_gap
        + 0.15 * capacity_estimated.astype(float)
        + 0.15 * doctor_estimated.astype(float)
        + 0.12 * capacity_width
        + 0.12 * doctor_width
        + 0.10 * critical_gap.astype(float)
        + 0.08 * low_join.astype(float)
        + 0.06 * recency_invalid.astype(float)
    ).clip(0, 1)
    contradiction_risk_score = (
        0.35 * external_geo_uncertainty_score
        + 0.25 * outlier.astype(float)
        + 0.15 * pincode_ambiguous.astype(float)
        + 0.15 * low_join.astype(float)
        + 0.10 * recency_invalid.astype(float)
    ).clip(0, 1)
    decision_leverage_score = (
        0.45 * medical_desert
        + 0.25 * clinical_impact
        + 0.20 * (1 - pd.to_numeric(fac["supply_data_confidence_score"], errors="coerce").fillna(0)).clip(0, 1)
        + 0.10 * _boolish(fac["needs_human_review"]).astype(float)
    ).clip(0, 1)

    fac["active_uncertainty_score"] = (
        0.30 * clinical_impact
        + 0.30 * uncertainty_score
        + 0.18 * contradiction_risk_score
        + 0.14 * decision_leverage_score
        + 0.08 * segment_rarity_score
    ).clip(0, 1).round(4)
    fac["active_uncertainty_rank"] = fac["active_uncertainty_score"].rank(
        method="first", ascending=False
    ).astype(int)
    fac["uncertainty_score"] = uncertainty_score.round(4)
    fac["contradiction_risk_score"] = contradiction_risk_score.round(4)
    fac["decision_leverage_score"] = decision_leverage_score.round(4)
    fac["segment_rarity_score"] = segment_rarity_score.round(4)
    fac["external_geo_uncertainty_score"] = external_geo_uncertainty_score
    fac["pre_geocode_uncertainty_band_low_km"] = geo_band_low
    fac["pre_geocode_uncertainty_band_high_km"] = geo_band_high
    fac["capacity_relative_interval_width"] = capacity_width.round(4)
    fac["doctor_count_relative_interval_width"] = doctor_width.round(4)
    fac["proxy_trust_score"] = pd.to_numeric(fac["semantic_data_quality_score"], errors="coerce").fillna(0).clip(0, 1)
    proxy_width = (0.12 + 0.28 * uncertainty_score + 0.16 * contradiction_risk_score).clip(0.12, 0.56)
    fac["proxy_trust_interval_low"] = (fac["proxy_trust_score"] - proxy_width / 2).clip(0, 1).round(4)
    fac["proxy_trust_interval_high"] = (fac["proxy_trust_score"] + proxy_width / 2).clip(0, 1).round(4)
    fac["active_learning_action"] = np.select(
        [
            outlier | fac["geo_quality"].fillna("").isin(["outside_india_bbox", "far_from_pincode_centroid"]),
            critical_gap,
            low_join | pincode_ambiguous,
            clinical_impact.ge(0.75) & uncertainty_score.ge(0.45),
            segment_rarity_score.ge(0.75),
        ],
        [
            "contradiction_audit",
            "semantic_missingness_enrichment",
            "join_bridge_enrichment",
            "high_impact_uncertainty_reduction",
            "sparse_segment_coverage",
        ],
        default="uncertainty_monitor",
    )
    geo_text = fac["geo_quality"].fillna("").astype(str).str.lower()
    fac["external_validation_action"] = np.select(
        [
            geo_text.str.contains("outside", na=False),
            geo_text.str.contains("missing", na=False),
            geo_text.str.contains("far", na=False),
            geo_text.str.contains("moderate", na=False) & medical_desert.ge(0.6),
            geo_text.str.contains("moderate", na=False),
            _boolish(fac["contradicted_or_geo_invalid_signal"]),
        ],
        [
            "replace_coordinate_with_external_geocode",
            "geocode_missing_coordinate",
            "geocode_and_compare_pincode_district",
            "high_impact_geocode_precision_check",
            "batch_geocode_precision_check",
            "external_source_contradiction_check",
        ],
        default="no_external_geocode_required",
    )
    fac["external_evidence_sources_to_check"] = np.where(
        fac["external_validation_action"].ne("no_external_geocode_required"),
        '["Google Geocoding API", "India Post pincode bridge", "Mappls/MapmyIndia fallback", "ABDM/HFR registry", "PM-JAY empanelled hospitals", "OSM/Overture POI cross-check"]',
        '["India Post pincode bridge", "source_urls"]',
    )

    top_fac = fac.sort_values("active_uncertainty_score", ascending=False).head(500).copy()
    top_fac["active_learning_reasons"] = top_fac.apply(
        lambda row: _json_reasons(
            row,
            [
                ("high_health_need", pd.notna(row.get("health_need_score")) and row.get("health_need_score", 0) >= 0.6),
                ("capacity_estimated_or_missing", bool(row.get("capacity_is_estimated"))),
                ("doctor_count_estimated_or_missing", bool(row.get("doctor_count_is_estimated"))),
                ("wide_capacity_interval", row.get("capacity_relative_interval_width", 0) >= 0.4),
                ("wide_doctor_interval", row.get("doctor_count_relative_interval_width", 0) >= 0.4),
                ("critical_supply_gap", bool(row.get("critical_supply_gap_flag"))),
                ("low_join_confidence", row.get("join_confidence", 0) < 0.8),
                ("non_plausible_geo", row.get("geo_quality") != "plausible"),
                ("external_geocode_needed", row.get("external_validation_action") != "no_external_geocode_required"),
                ("wide_geo_uncertainty_band", row.get("pre_geocode_uncertainty_band_high_km", 0) >= 50),
                ("ambiguous_pincode_or_region", bool(row.get("pincode_is_ambiguous")) or bool(row.get("pincode_region_is_ambiguous"))),
                ("missing_contact_evidence", not bool(row.get("has_contact_evidence"))),
                ("missing_source_urls", not bool(row.get("has_source_urls"))),
                ("sparse_segment", row.get("segment_rarity_score", 0) >= 0.75),
            ],
        ),
        axis=1,
    )
    facility_cols = [
        "active_uncertainty_rank",
        "active_uncertainty_score",
        "active_learning_action",
        "active_learning_reasons",
        "unique_id",
        "facility_name",
        "state_ut",
        "district_name",
        "pincode_extracted",
        "facilityTypeId",
        "operatorTypeId",
        "health_need_score",
        "medical_desert_priority_score",
        "data_readiness_score",
        "semantic_data_quality_score",
        "supply_data_confidence_score",
        "proxy_trust_score",
        "proxy_trust_interval_low",
        "proxy_trust_interval_high",
        "uncertainty_score",
        "contradiction_risk_score",
        "decision_leverage_score",
        "segment_rarity_score",
        "external_geo_uncertainty_score",
        "external_validation_action",
        "external_evidence_sources_to_check",
        "pre_geocode_uncertainty_band_low_km",
        "pre_geocode_uncertainty_band_high_km",
        "capacity_status",
        "capacity_display_value",
        "capacity_estimate_interval_low",
        "capacity_estimate_interval_high",
        "capacity_relative_interval_width",
        "doctor_count_status",
        "doctor_count_display_value",
        "doctor_count_estimate_interval_low",
        "doctor_count_estimate_interval_high",
        "doctor_count_relative_interval_width",
        "recency_status",
        "equipment_status",
        "semantic_missing_critical_count",
        "critical_supply_gap_flag",
        "join_strategy",
        "join_confidence",
        "geo_quality",
        "geo_distance_km_to_pincode_centroid",
        "pincode_is_ambiguous",
        "pincode_region_is_ambiguous",
        "has_source_urls",
        "has_contact_evidence",
        "claim_text",
        "source_urls",
    ]
    facility_queue = top_fac[[c for c in facility_cols if c in top_fac.columns]].copy()

    dist = district.copy()
    ci_width_cols = [
        ("needs_human_review_rate_ci_low", "needs_human_review_rate_ci_high"),
        ("critical_supply_gap_rate_ci_low", "critical_supply_gap_rate_ci_high"),
        ("trustworthy_supply_rate_ci_low", "trustworthy_supply_rate_ci_high"),
        ("capacity_observed_rate_ci_low", "capacity_observed_rate_ci_high"),
        ("doctor_observed_rate_ci_low", "doctor_observed_rate_ci_high"),
    ]
    ci_widths = []
    for low_col, high_col in ci_width_cols:
        if low_col in dist and high_col in dist:
            ci_widths.append((dist[high_col] - dist[low_col]).abs())
    aggregate_ci_width = pd.concat(ci_widths, axis=1).mean(axis=1).fillna(0) if ci_widths else pd.Series(0, index=dist.index)
    sample_uncertainty = (1 - (pd.to_numeric(dist["observed_facility_rows"], errors="coerce").fillna(0).clip(upper=20) / 20)).clip(0, 1)
    uncertainty_level_score = dist["district_uncertainty_level"].map({"lower": 0.1, "medium": 0.55, "higher": 1.0}).fillna(1)
    dist["aggregate_ci_width"] = aggregate_ci_width.round(4)
    dist["sample_size_uncertainty_score"] = sample_uncertainty.round(4)
    dist["active_uncertainty_score"] = (
        0.24 * pd.to_numeric(dist["care_gap_score"], errors="coerce").fillna(0)
        + 0.22 * pd.to_numeric(dist["trust_gap_score"], errors="coerce").fillna(0)
        + 0.18 * pd.to_numeric(dist["health_need_score"], errors="coerce").fillna(0)
        + 0.14 * aggregate_ci_width.clip(0, 1)
        + 0.12 * uncertainty_level_score
        + 0.10 * sample_uncertainty
    ).clip(0, 1).round(4)
    dist["active_uncertainty_rank"] = dist["active_uncertainty_score"].rank(
        method="first", ascending=False
    ).astype(int)
    top_dist = dist.sort_values("active_uncertainty_score", ascending=False).head(250).copy()
    top_dist["active_learning_action"] = np.select(
        [
            top_dist["planning_category"].eq("real_desert_candidate"),
            top_dist["district_uncertainty_level"].eq("higher"),
            top_dist["critical_supply_gap_rate"].fillna(0).ge(0.5),
            top_dist["aggregate_ci_width"].fillna(0).ge(0.25),
        ],
        [
            "stress_test_desert_call",
            "uncertainty_band_reduction",
            "semantic_gap_enrichment",
            "rate_ci_reduction",
        ],
        default="monitor",
    )
    top_dist["active_learning_reasons"] = top_dist.apply(
        lambda row: _json_reasons(
            row,
            [
                ("high_care_gap", row.get("care_gap_score", 0) >= 0.65),
                ("high_health_need", row.get("health_need_score", 0) >= 0.6),
                ("high_trust_gap", row.get("trust_gap_score", 0) >= 0.65),
                ("higher_uncertainty_level", row.get("district_uncertainty_level") == "higher"),
                ("wide_rate_confidence_intervals", row.get("aggregate_ci_width", 0) >= 0.25),
                ("small_observed_facility_sample", row.get("observed_facility_rows", 0) < 5),
                ("high_critical_supply_gap_rate", row.get("critical_supply_gap_rate", 0) >= 0.5),
            ],
        ),
        axis=1,
    )
    district_cols = [
        "active_uncertainty_rank",
        "active_uncertainty_score",
        "active_learning_action",
        "active_learning_reasons",
        "state_ut",
        "district_name",
        "planning_category",
        "observed_facility_rows",
        "health_need_score",
        "care_gap_score",
        "trust_gap_score",
        "district_medical_desert_priority_score",
        "district_data_quality_score",
        "district_uncertainty_level",
        "aggregate_ci_width",
        "sample_size_uncertainty_score",
        "needs_human_review_rate",
        "needs_human_review_rate_ci_low",
        "needs_human_review_rate_ci_high",
        "critical_supply_gap_rate",
        "critical_supply_gap_rate_ci_low",
        "critical_supply_gap_rate_ci_high",
        "trustworthy_supply_rate",
        "trustworthy_supply_rate_ci_low",
        "trustworthy_supply_rate_ci_high",
        "capacity_observed_rate",
        "capacity_observed_rate_ci_low",
        "capacity_observed_rate_ci_high",
        "doctor_observed_rate",
        "doctor_observed_rate_ci_low",
        "doctor_observed_rate_ci_high",
        "sample_facility_names",
        "sample_claim_evidence",
        "sample_source_urls",
    ]
    district_queue = top_dist[[c for c in district_cols if c in top_dist.columns]].copy()

    facility_queue.to_csv(DATA_DIR / "active_learning_facility_queue.csv", index=False)
    district_queue.to_csv(DATA_DIR / "active_learning_district_queue.csv", index=False)
    return facility_queue, district_queue


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
            "present_rows": int(semantic_nonempty(facilities[col]).sum()),
            "present_pct": float(100 * semantic_nonempty(facilities[col]).mean()),
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
        "critical_supply_gap_rate",
        "plausible_geo_rate",
        "capacity_parse_rate",
        "doctor_parse_rate",
        "capacity_observed_rate",
        "doctor_observed_rate",
        "recency_valid_rate",
        "avg_semantic_data_quality_score",
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
                "Distribution analysis, confidence intervals, active-learning-style uncertainty triage, and sensitivity analysis were suggested directions.",
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
            "Active-learning-style uncertainty queues for facility and district records that would benefit most from source enrichment or stress testing.",
            "External-evidence uncertainty scoring for geocoding candidates: Google/Mappls metadata, India Post admin agreement, and registry corroboration reduce or widen proxy bands.",
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

This notebook follows the hackathon warning from the screenshots: the facility fields are extracted claims from open web text, not verified ground truth. The cleaning step therefore keeps claim evidence, join strategy, confidence, and uncertainty-review flags.
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
- Prior notes: merging records creates uncertainty; useful analysis includes distributions, confidence intervals, Boolean indicators, Bayesian-style confidence, active-learning-style uncertainty triage, and sensitivity analysis without pretending proxy labels are ground truth.
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
for candidate in [ROOT, *ROOT.parents]:
    if (candidate / "output" / "data" / "facility_health_cleaned.csv").exists():
        ROOT = candidate
        break
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

The readiness score is deliberately conservative. It rewards parseable pincode, health join, plausible coordinates, non-ambiguous PIN bridge, source URLs, claim-text coverage, and contact evidence. Rows below the threshold or with outlier flags are marked `needs_human_review`, which now means uncertainty review rather than manual verification.
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
## Active Uncertainty Queue

Without human verification labels, active learning becomes active uncertainty triage. The queue ranks facilities and districts where source enrichment, stress testing, or cautious UI treatment would most reduce decision uncertainty. The scores are not measured accuracy; they combine clinical impact, semantic missingness, contradiction risk, decision leverage, sparse-segment coverage, geocoding uncertainty, and confidence/prediction-interval width.
"""
        )
    )
    cells.append(
        code(
            """
facility_queue = pd.read_csv(DATA_DIR / "active_learning_facility_queue.csv")
district_queue = pd.read_csv(DATA_DIR / "active_learning_district_queue.csv")

facility_queue[
    [
        "active_uncertainty_rank",
        "active_uncertainty_score",
        "active_learning_action",
        "facility_name",
        "state_ut",
        "district_name",
        "proxy_trust_interval_low",
        "proxy_trust_interval_high",
        "external_validation_action",
        "pre_geocode_uncertainty_band_low_km",
        "pre_geocode_uncertainty_band_high_km",
        "capacity_estimate_interval_low",
        "capacity_estimate_interval_high",
        "doctor_count_estimate_interval_low",
        "doctor_count_estimate_interval_high",
    ]
].head(15)
"""
        )
    )
    cells.append(
        md(
            """
## External Evidence and Geocoding Uncertainty

The parallel geocoding work addresses the garbage-in/garbage-out problem by turning Google Maps, Mappls, India Post, and registry evidence into uncertainty explanations. A geocoder result is not treated as truth by itself. It only reduces uncertainty when its `status`, `location_type`, `partial_match`, formatted address, place ID, and coordinates agree with the expected state, district, pincode, and facility name.

The active-learning idea here is value-of-information triage: spend external API calls and registry lookups on rows where location disagreement is large and the district decision would change.
"""
        )
    )
    if "geo_external_validation_actions" in plot:
        cells.append(md(f"![Geo external validation actions](../../{plot['geo_external_validation_actions']})"))
    if "geo_external_priority_scatter" in plot:
        cells.append(md(f"![Geo external validation priority scatter](../../{plot['geo_external_priority_scatter']})"))
    cells.append(
        code(
            """
geo_candidates_path = DATA_DIR / "geo_validation_candidates.csv"
geocoder_priors_path = DATA_DIR / "geocoder_uncertainty_priors.csv"

geo_candidates = pd.read_csv(geo_candidates_path) if geo_candidates_path.exists() else pd.DataFrame()
geocoder_priors = pd.read_csv(geocoder_priors_path) if geocoder_priors_path.exists() else pd.DataFrame()

if geo_candidates.empty:
    print("No geo validation candidate file found yet. Run scripts/prepare_geo_validation_batch.py to generate it.")
else:
    display(
        geo_candidates[
            [
                "facility_name",
                "state_ut",
                "district_name",
                "geo_review_reason",
                "external_validation_action",
                "external_validation_priority_score",
                "geo_distance_km_to_pincode_centroid",
                "pre_geocode_uncertainty_band_low_km",
                "pre_geocode_uncertainty_band_high_km",
                "geocoder_expected_precision_after_success",
            ]
        ].head(15)
    )
"""
        )
    )
    cells.append(
        code(
            """
if not geocoder_priors.empty:
    display(geocoder_priors)
"""
        )
    )
    cells.append(
        code(
            """
if not geo_candidates.empty:
    fig, axes = plt.subplots(1, 2, figsize=(15, 5))

    geo_candidates["external_validation_action"].value_counts().sort_values().plot(
        kind="barh", ax=axes[0], color="#3c6e71"
    )
    axes[0].set_title("External validation actions")
    axes[0].set_xlabel("Candidate rows")
    axes[0].set_ylabel("")

    by_reason = (
        geo_candidates.groupby("geo_review_reason")["external_validation_priority_score"]
        .mean()
        .sort_values()
    )
    by_reason.plot(kind="barh", ax=axes[1], color="#d98c3a")
    axes[1].set_title("Mean source-enrichment priority")
    axes[1].set_xlabel("Priority score")
    axes[1].set_ylabel("")

    plt.tight_layout()
    plt.show()
"""
        )
    )
    cells.append(
        code(
            """
if not geo_candidates.empty:
    plot_df = geo_candidates.copy()
    plot_df["distance_for_plot_km"] = pd.to_numeric(
        plot_df["geo_distance_km_to_pincode_centroid"], errors="coerce"
    ).clip(lower=0, upper=2500)
    plot_df["external_validation_priority_score"] = pd.to_numeric(
        plot_df["external_validation_priority_score"], errors="coerce"
    )

    fig, ax = plt.subplots(figsize=(11, 6))
    for reason, group in plot_df.groupby("geo_review_reason"):
        ax.scatter(
            group["distance_for_plot_km"],
            group["external_validation_priority_score"],
            label=reason,
            alpha=0.72,
            s=42,
        )
    ax.set_xscale("symlog", linthresh=10)
    ax.set_xlabel("Distance from India Post PIN centroid, km (capped at 2,500)")
    ax.set_ylabel("External validation priority score")
    ax.set_title("Which geo failures should use external API calls first?")
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.25)
    plt.tight_layout()
    plt.show()
"""
        )
    )
    cells.append(
        code(
            """
if not geo_candidates.empty:
    interval_df = geo_candidates.copy()
    interval_df["uncertainty_band_width_km"] = (
        pd.to_numeric(interval_df["pre_geocode_uncertainty_band_high_km"], errors="coerce")
        - pd.to_numeric(interval_df["pre_geocode_uncertainty_band_low_km"], errors="coerce")
    ).clip(lower=0)
    top_intervals = interval_df.nlargest(15, "uncertainty_band_width_km")[
        [
            "facility_name",
            "state_ut",
            "district_name",
            "geo_review_reason",
            "external_validation_action",
            "uncertainty_band_width_km",
            "geocoder_acceptance_rule",
        ]
    ]
    display(top_intervals)
"""
        )
    )
    cells.append(
        code(
            """
district_queue[
    [
        "active_uncertainty_rank",
        "active_uncertainty_score",
        "active_learning_action",
        "state_ut",
        "district_name",
        "care_gap_score",
        "trust_gap_score",
        "needs_human_review_rate_ci_low",
        "needs_human_review_rate_ci_high",
        "critical_supply_gap_rate_ci_low",
        "critical_supply_gap_rate_ci_high",
        "trustworthy_supply_rate_ci_low",
        "trustworthy_supply_rate_ci_high",
    ]
].head(15)
"""
        )
    )
    cells.append(
        md(
            """
## Exported Artifacts

- `output/data/facility_health_cleaned.csv`
- `output/data/district_health_facility_cleaned.csv` (primary cleaned dataset)
- `output/data/district_unmatched_pincode_facility_counts.csv`
- `output/data/active_learning_facility_queue.csv`
- `output/data/active_learning_district_queue.csv`
- `output/data/geo_validation_candidates.csv`
- `output/data/geocoder_uncertainty_priors.csv`
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
    semantic_missingness = write_semantic_missingness_summary(clean)
    facility_active_queue, district_active_queue = build_active_learning_queues(clean, district_clean)
    plot_paths = plot_outputs(clean, district_clean, facilities)
    summary = make_summary(facilities, pincode, health, clean, district_clean, unmatched_districts, pin_bridge, plot_paths)
    summary["semantic_missingness"] = semantic_missingness.to_dict(orient="records")
    summary["active_learning_uncertainty"] = {
        "facility_queue_rows": int(len(facility_active_queue)),
        "district_queue_rows": int(len(district_active_queue)),
        "facility_queue_path": str(DATA_DIR / "active_learning_facility_queue.csv"),
        "district_queue_path": str(DATA_DIR / "active_learning_district_queue.csv"),
        "method_note": (
            "Active-learning inspired uncertainty triage without human-oracle labels. "
            "Scores prioritize source enrichment, external geocoding checks, and stress testing, not measured truth."
        ),
        "top_facility_rows": facility_active_queue.head(10).to_dict(orient="records"),
        "top_district_rows": district_active_queue.head(10).to_dict(orient="records"),
    }
    geo_candidate_path = DATA_DIR / "geo_validation_candidates.csv"
    if geo_candidate_path.exists():
        geo_candidates = pd.read_csv(geo_candidate_path, low_memory=False)
        summary["external_geocoding_uncertainty"] = {
            "candidate_rows": int(len(geo_candidates)),
            "candidate_path": str(geo_candidate_path),
            "geocoder_priors_path": str(DATA_DIR / "geocoder_uncertainty_priors.csv"),
            "action_counts": (
                geo_candidates.get("external_validation_action", pd.Series(dtype=object))
                .value_counts(dropna=False)
                .to_dict()
            ),
            "method_note": (
                "Google/Mappls geocoder metadata and external registries are treated as evidence signals. "
                "They reduce uncertainty only when address, pincode, district/state, and facility-name checks agree."
            ),
        }
    (DATA_DIR / "analysis_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_notebook(summary)

    print(f"cleaned: {clean.shape}")
    print(f"district cleaned: {district_clean.shape}")
    print(f"unmatched pincode districts: {unmatched_districts.shape}")
    print(f"notebook: {NOTEBOOK_PATH}")
    print(f"summary: {DATA_DIR / 'analysis_summary.json'}")


if __name__ == "__main__":
    main()
