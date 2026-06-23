#!/usr/bin/env python3
"""Map facility claims to Google Place IDs and photo availability metadata.

The script is intentionally dry-run by default. It never prints API keys and it
does not persist Google photo names, photo URLs, or image bytes. Durable output
is limited to match metadata such as place IDs, confidence labels, and whether a
matched listing reports photos. The Streamlit app can then decide whether to
request/display photos through an approved server-side path.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"
DEFAULT_INPUT = DATA_DIR / "facility_health_cleaned.csv"
DEFAULT_OUTPUT = DATA_DIR / "google_places_photo_metadata.jsonl"
DEFAULT_RAW = DATA_DIR / "google_places_text_search_raw.jsonl"
DEFAULT_ENV_FILES = [ROOT / ".env", ROOT / ".env.gcp"]

TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
TEXT_SEARCH_FIELDS = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.photos,"
    "places.types"
)


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def api_key(env_files: list[Path]) -> str:
    merged: dict[str, str] = {}
    for path in env_files:
        merged.update(load_env_file(path))
    merged.update(os.environ)
    return (
        merged.get("GOOGLE_PLACES_API_KEY")
        or merged.get("GOOGLE_MAPS_API_KEY")
        or merged.get("GOOGLE_API_KEY")
        or ""
    )


def clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def norm(value: Any) -> str:
    return "".join(ch.lower() for ch in clean(value) if ch.isalnum())


def tokens(value: Any) -> set[str]:
    return {norm(part) for part in re.split(r"\W+", clean(value)) if norm(part)}


def query_for(row: dict[str, Any]) -> str:
    parts = [
        clean(row.get("facility_name")),
        clean(row.get("address_city")) or clean(row.get("district_name")),
        clean(row.get("address_stateOrRegion")) or clean(row.get("state_ut")),
        clean(row.get("pincode_extracted_clean")) or clean(row.get("pincode")),
        "India",
    ]
    return " ".join(part for part in parts if part)


def text_search(query: str, key: str, timeout: int) -> dict[str, Any]:
    payload = json.dumps({"textQuery": query, "includedType": "hospital"}).encode("utf-8")
    request = Request(
        TEXT_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": TEXT_SEARCH_FIELDS,
        },
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def match_score(row: dict[str, Any], place: dict[str, Any]) -> tuple[float, str]:
    facility_name = clean(row.get("facility_name"))
    place_name = clean((place.get("displayName") or {}).get("text"))
    address = clean(place.get("formattedAddress"))
    state = clean(row.get("address_stateOrRegion")) or clean(row.get("state_ut"))
    city = clean(row.get("address_city")) or clean(row.get("district_name"))

    name_match = 1.0 if norm(facility_name) and norm(facility_name) in norm(place_name) else 0.0
    if not name_match:
        left = tokens(facility_name)
        right = tokens(place_name)
        name_match = len(left & right) / max(len(left), 1) if left else 0.0
    state_match = 1.0 if state and norm(state) in norm(address) else 0.0
    city_match = 1.0 if city and norm(city) in norm(address) else 0.0
    score = 0.70 * name_match + 0.18 * state_match + 0.12 * city_match
    if score >= 0.82:
        label = "high"
    elif score >= 0.62:
        label = "medium"
    else:
        label = "low"
    return round(score, 3), label


def result_payload(row: dict[str, Any], response: dict[str, Any], query: str) -> dict[str, Any]:
    places = response.get("places") or []
    best = places[0] if places else {}
    score, label = match_score(row, best) if best else (0.0, "no_match")
    photos = best.get("photos") or []
    return {
        "unique_id": clean(row.get("unique_id")),
        "facility_name": clean(row.get("facility_name")),
        "address_city": clean(row.get("address_city")) or clean(row.get("district_name")),
        "address_stateOrRegion": clean(row.get("address_stateOrRegion")) or clean(row.get("state_ut")),
        "query": query,
        "place_id": clean(best.get("id")),
        "place_name": clean((best.get("displayName") or {}).get("text")),
        "formatted_address": clean(best.get("formattedAddress")),
        "match_score": score,
        "match_label": label,
        "has_google_photos": bool(photos),
        "photo_count": len(photos),
        "provider": "google_places",
        "enrichment_note": (
            "Stores place ID and photo availability only. Do not persist Google photo "
            "names, URLs, or image bytes."
        ),
    }


def rows_from_csv(path: Path, limit: int) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if limit:
        rows = rows[:limit]
    return rows


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--raw-output", type=Path, default=DEFAULT_RAW)
    parser.add_argument("--env-file", type=Path, action="append", default=[])
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--sleep", type=float, default=0.15)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--execute", action="store_true", help="Call Google Places. Default only prints planned queries.")
    parser.add_argument("--write-raw", action="store_true", help="Write raw API responses to ignored local output for debugging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = rows_from_csv(args.input, args.limit)
    env_files = [*DEFAULT_ENV_FILES, *args.env_file]
    key = api_key(env_files)

    if not args.execute:
        print(f"Dry run: would enrich {len(rows)} facility rows.")
        for row in rows[:10]:
            print(f"- {clean(row.get('facility_name'))}: {query_for(row)}")
        print("Run with --execute after setting GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY.")
        return
    if not key:
        raise SystemExit("Missing GOOGLE_PLACES_API_KEY or GOOGLE_MAPS_API_KEY.")

    records: list[dict[str, Any]] = []
    raw_records: list[dict[str, Any]] = []
    for idx, row in enumerate(rows, start=1):
        query = query_for(row)
        if not query:
            continue
        try:
            response = text_search(query, key, args.timeout)
        except Exception as exc:
            response = {"error": type(exc).__name__, "message": str(exc)}
        records.append(result_payload(row, response, query))
        if args.write_raw:
            raw_records.append({
                "unique_id": clean(row.get("unique_id")),
                "facility_name": clean(row.get("facility_name")),
                "query": query,
                "response": response,
            })
        print(f"[{idx}/{len(rows)}] {clean(row.get('facility_name'))}: {records[-1]['match_label']} {records[-1]['match_score']}")
        time.sleep(max(0.0, args.sleep))

    write_jsonl(args.output, records)
    print(f"Wrote sanitized metadata: {args.output.relative_to(ROOT)}")
    if args.write_raw:
        write_jsonl(args.raw_output, raw_records)
        print(f"Wrote ignored raw debug responses: {args.raw_output.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
