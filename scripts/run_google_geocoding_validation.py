#!/usr/bin/env python3
"""Run Google Maps Geocoding validation for reconciled facility addresses.

This script intentionally does not print or persist API keys. Local raw outputs
are ignored by .gitignore; the generated SQL contains only sanitized geocoder
metadata needed for the uncertainty workflow.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import subprocess
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
SQL_DIR = ROOT / "output" / "sql"

UC_RECONCILIATION_TABLE = "workspace.default.hackathon_geo_fuzzy_reconciliation"
UC_GOOGLE_RESULTS_TABLE = "workspace.default.hackathon_google_geocoding_results"

DEFAULT_ENV_FILES = [
    Path("/Users/stevenyang/Documents/google-devpost-hackathon/.env"),
    Path("/Users/stevenyang/Documents/google-devpost-hackathon/.env.gcp"),
]


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def api_key_from_env(env_files: list[Path]) -> str:
    merged: dict[str, str] = {}
    for path in env_files:
        merged.update(load_env_file(path))
    merged.update(os.environ)
    return merged.get("GOOGLE_MAPS_API_KEY") or merged.get("GOOGLE_API_KEY") or ""


def databricks_query(sql: str, *, profile: str, warehouse: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [
            "databricks",
            "experimental",
            "aitools",
            "tools",
            "query",
            "--profile",
            profile,
            "--warehouse",
            warehouse,
            sql,
            "-o",
            "json",
        ],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
    return json.loads(proc.stdout or "[]")


def fetch_candidates(*, profile: str, warehouse: str, status: str, limit: int) -> list[dict[str, Any]]:
    sql = f"""
SELECT
  unique_id,
  facility_name,
  raw_india_address,
  parsed_address.geocoder_query AS geocoder_query,
  pincode_extracted_clean AS expected_pincode,
  parsed_address.city AS parsed_city,
  parsed_address.state AS parsed_state,
  parsed_address.pincode AS parsed_pincode,
  address_city,
  address_stateOrRegion,
  geo_quality,
  facility_latitude,
  facility_longitude,
  geo_distance_km_to_pincode_centroid,
  fuzzy_precheck_status,
  reconciliation_status,
  external_validation_action
FROM {UC_RECONCILIATION_TABLE}
WHERE reconciliation_status = '{sql_escape(status)}'
  AND parsed_address.geocoder_query IS NOT NULL
ORDER BY
  CASE WHEN lower(geo_quality) RLIKE 'outside|far|missing' THEN 1 ELSE 0 END DESC,
  coalesce(geo_distance_km_to_pincode_centroid, 0) DESC
LIMIT {int(limit)}
"""
    return databricks_query(sql, profile=profile, warehouse=warehouse)


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return "".join(ch.lower() for ch in str(value) if ch.isalnum())


def haversine_km(lat1: Any, lon1: Any, lat2: Any, lon2: Any) -> float | None:
    try:
        lat1f = float(lat1)
        lon1f = float(lon1)
        lat2f = float(lat2)
        lon2f = float(lon2)
    except (TypeError, ValueError):
        return None
    radius_km = 6371.0088
    dlat = math.radians(lat2f - lat1f)
    dlon = math.radians(lon2f - lon1f)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1f))
        * math.cos(math.radians(lat2f))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * radius_km * math.asin(math.sqrt(a))


def call_google_geocode(address: str, api_key: str, timeout: int) -> dict[str, Any]:
    params = {
        "address": address,
        "components": "country:IN",
        "region": "in",
        "key": api_key,
    }
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urlencode(params)
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def should_retry_google_response(response: dict[str, Any]) -> bool:
    status = str(response.get("status") or "")
    error_message = str(response.get("error_message") or "").lower()
    return status == "REQUEST_DENIED" and "expired" in error_message


def first_result_payload(row: dict[str, Any], response: dict[str, Any]) -> dict[str, Any]:
    results = response.get("results") or []
    first = results[0] if results else {}
    geometry = first.get("geometry") or {}
    location = geometry.get("location") or {}
    plus_code = first.get("plus_code") or response.get("plus_code") or {}

    formatted = str(first.get("formatted_address") or "")
    expected_pin = str(row.get("expected_pincode") or "").strip()
    expected_state = str(row.get("parsed_state") or row.get("address_stateOrRegion") or "").strip()
    expected_city = str(row.get("parsed_city") or row.get("address_city") or "").strip()

    formatted_norm = normalize_text(formatted)
    pincode_match = bool(expected_pin and expected_pin in formatted)
    state_match = bool(expected_state and normalize_text(expected_state) in formatted_norm)
    city_match = bool(expected_city and normalize_text(expected_city) in formatted_norm)
    partial_match = bool(first.get("partial_match", False))
    location_type = str(geometry.get("location_type") or "")
    status = str(response.get("status") or "")

    validation_status = classify_google_result(
        status=status,
        result_count=len(results),
        location_type=location_type,
        partial_match=partial_match,
        pincode_match=pincode_match,
        state_match=state_match,
    )

    distance = haversine_km(
        row.get("facility_latitude"),
        row.get("facility_longitude"),
        location.get("lat"),
        location.get("lng"),
    )

    return {
        "unique_id": row.get("unique_id", ""),
        "facility_name": row.get("facility_name", ""),
        "requested_address": row.get("geocoder_query", ""),
        "google_status": status,
        "google_error_message": response.get("error_message", ""),
        "google_result_count": len(results),
        "formatted_address": formatted,
        "place_id": first.get("place_id", ""),
        "location_type": location_type,
        "partial_match": partial_match,
        "google_latitude": location.get("lat"),
        "google_longitude": location.get("lng"),
        "google_types": ",".join(first.get("types") or []),
        "plus_code_global": plus_code.get("global_code", ""),
        "plus_code_compound": plus_code.get("compound_code", ""),
        "expected_pincode": expected_pin,
        "expected_state": expected_state,
        "expected_city": expected_city,
        "pincode_match": pincode_match,
        "state_match": state_match,
        "city_match": city_match,
        "distance_km_current_to_google": round(distance, 3) if distance is not None else None,
        "prior_geo_quality": row.get("geo_quality", ""),
        "prior_fuzzy_precheck_status": row.get("fuzzy_precheck_status", ""),
        "prior_reconciliation_status": row.get("reconciliation_status", ""),
        "external_validation_action": row.get("external_validation_action", ""),
        "google_validation_status": validation_status,
    }


def classify_google_result(
    *,
    status: str,
    result_count: int,
    location_type: str,
    partial_match: bool,
    pincode_match: bool,
    state_match: bool,
) -> str:
    if status == "ZERO_RESULTS":
        return "zero_results_review"
    if status != "OK" or result_count == 0:
        return f"api_{status.lower() or 'unknown'}_review"
    if partial_match:
        return "partial_match_review"
    if not state_match:
        return "state_mismatch_review"
    if not pincode_match:
        return "pincode_mismatch_review"
    if location_type in {"ROOFTOP", "RANGE_INTERPOLATED"}:
        return "accept_coordinate_candidate"
    if location_type == "GEOMETRIC_CENTER":
        return "neighborhood_candidate_h3_only"
    if location_type == "APPROXIMATE":
        return "approximate_review"
    return "provider_metadata_review"


def sql_escape(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("'", "''")


def sql_literal(value: Any) -> str:
    if value is None or value == "":
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return f"'{sql_escape(value)}'"


def write_outputs(rows: list[dict[str, Any]], raw_rows: list[dict[str, Any]]) -> tuple[Path, Path, Path]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SQL_DIR.mkdir(parents=True, exist_ok=True)

    csv_path = DATA_DIR / "google_geocoding_results.csv"
    raw_path = DATA_DIR / "google_geocoding_raw.jsonl"
    sql_path = SQL_DIR / "google_geocoding_results_generated.sql"

    fieldnames = list(rows[0].keys()) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    with raw_path.open("w", encoding="utf-8") as fh:
        for item in raw_rows:
            fh.write(json.dumps(item, ensure_ascii=True) + "\n")

    columns = fieldnames
    values = []
    for row in rows:
        values.append("(" + ", ".join(sql_literal(row.get(col)) for col in columns) + ")")
    if values:
        sql = (
            f"CREATE OR REPLACE TABLE {UC_GOOGLE_RESULTS_TABLE} AS\n"
            "SELECT * FROM VALUES\n"
            + ",\n".join(values)
            + "\nAS t("
            + ", ".join(columns)
            + ");\n"
        )
    else:
        sql = f"-- No rows to write for {UC_GOOGLE_RESULTS_TABLE}.\n"
    sql_path.write_text(sql, encoding="utf-8")
    return csv_path, raw_path, sql_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="7474647301321645")
    parser.add_argument("--warehouse", default="1b331b704066b677")
    parser.add_argument("--status", default="ready_for_geocoder")
    parser.add_argument("--limit", type=int, default=138)
    parser.add_argument("--sleep", type=float, default=0.05)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--retry-sleep", type=float, default=2.0)
    parser.add_argument("--env-file", action="append", type=Path, default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    env_files = args.env_file or DEFAULT_ENV_FILES
    api_key = api_key_from_env(env_files)
    if not api_key and not args.dry_run:
        raise SystemExit("No GOOGLE_MAPS_API_KEY or GOOGLE_API_KEY found in env or env files.")

    candidates = fetch_candidates(
        profile=args.profile,
        warehouse=args.warehouse,
        status=args.status,
        limit=args.limit,
    )
    if args.dry_run:
        print(f"Would geocode {len(candidates)} rows with status={args.status}.")
        for row in candidates[:5]:
            print(f"- {row.get('facility_name')}: {row.get('geocoder_query')}")
        return

    results: list[dict[str, Any]] = []
    raw_results: list[dict[str, Any]] = []
    for idx, row in enumerate(candidates, start=1):
        address = str(row.get("geocoder_query") or "").strip()
        if not address:
            continue
        response = call_google_geocode(address, api_key, args.timeout)
        for attempt in range(args.retries):
            if not should_retry_google_response(response):
                break
            time.sleep(args.retry_sleep * (attempt + 1))
            response = call_google_geocode(address, api_key, args.timeout)
        results.append(first_result_payload(row, response))
        raw_results.append(
            {
                "unique_id": row.get("unique_id"),
                "facility_name": row.get("facility_name"),
                "requested_address": address,
                "response": response,
            }
        )
        if idx % 25 == 0:
            print(f"Geocoded {idx}/{len(candidates)} rows", flush=True)
        time.sleep(args.sleep)

    csv_path, raw_path, sql_path = write_outputs(results, raw_results)
    print(f"Wrote {csv_path.relative_to(ROOT)} ({len(results)} rows)", flush=True)
    print(f"Wrote {raw_path.relative_to(ROOT)}", flush=True)
    print(f"Wrote {sql_path.relative_to(ROOT)}", flush=True)

    counts: dict[str, int] = {}
    for row in results:
        key = str(row.get("google_validation_status"))
        counts[key] = counts.get(key, 0) + 1
    print(json.dumps(counts, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
