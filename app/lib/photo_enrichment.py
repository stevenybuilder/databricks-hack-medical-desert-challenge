"""Optional, safe facility photo metadata lookup.

Google Places should be resolved by an offline/server-side enrichment job, not
inside Streamlit render loops. This module only reads sanitized match metadata:
place IDs, display names, attribution notes, and optional static preview URLs
provided by that enrichment layer. API keys are never read here.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import config


def _metadata_paths() -> list[Path]:
    configured = os.environ.get("GOOGLE_PLACE_PHOTO_METADATA")
    paths = [Path(configured)] if configured else []
    paths.extend([
        config.data_dir() / "google_places_photo_metadata.json",
        config.data_dir() / "google_places_photo_metadata.jsonl",
    ])
    return paths


def _clean(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text


def _norm(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _keys(record: dict[str, Any]) -> list[str]:
    values = [
        _clean(record.get("unique_id")),
        _clean(record.get("facility_name")),
        _clean(record.get("facility_name_norm")),
        "|".join([
            _clean(record.get("facility_name")),
            _clean(record.get("address_city")) or _clean(record.get("district_name")),
            _clean(record.get("address_stateOrRegion")) or _clean(record.get("state_ut")),
        ]),
    ]
    return [_norm(value) for value in values if _norm(value)]


def _records_from_path(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        if path.suffix == ".jsonl":
            return [
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            rows = payload.get("records")
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
            return [payload]
    except Exception:
        return []
    return []


@lru_cache(maxsize=1)
def _metadata_index() -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for path in _metadata_paths():
        for record in _records_from_path(path):
            meta = {
                "place_id": _clean(record.get("place_id") or record.get("google_place_id")),
                "place_name": _clean(record.get("place_name") or record.get("google_place_name")),
                "photo_uri": _clean(record.get("photo_uri") or record.get("preview_url")),
                "attribution": _clean(record.get("attribution")) or "Google Maps",
                "match_label": _clean(record.get("match_label")) or "Google Maps match",
            }
            if not (meta["place_id"] or meta["photo_uri"]):
                continue
            for key in _keys(record):
                index[key] = meta
    return index


def facility_photo(facility: dict[str, Any]) -> dict[str, str]:
    """Return sanitized photo metadata, or `{}` if no pre-enriched match exists."""
    if os.environ.get("CAREGAP_PLACES_PHOTOS_ENABLED", "").lower() not in {"1", "true", "yes"}:
        return {}
    index = _metadata_index()
    for key in _keys(facility):
        meta = index.get(key)
        if meta:
            return meta
    return {}
