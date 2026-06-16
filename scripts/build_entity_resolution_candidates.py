#!/usr/bin/env python3
"""Build deterministic facility entity-resolution review candidates.

This script creates non-destructive candidate pairs and high-confidence review
clusters from the cleaned facility table. It does not call external APIs, does
not call LLMs, and does not modify the canonical facility table.
"""

from __future__ import annotations

import argparse
import csv
import difflib
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"

DEFAULT_INPUT_PATH = DATA_DIR / "facility_health_cleaned.csv"
DEFAULT_PAIR_PATH = DATA_DIR / "entity_resolution_candidate_pairs.csv"
DEFAULT_CLUSTER_PATH = DATA_DIR / "entity_resolution_clusters.csv"
DEFAULT_SUMMARY_PATH = DATA_DIR / "entity_resolution_summary.json"

SCRIPT_VERSION = "1.0"

PIN_RE = re.compile(r"\b(\d{6})\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
NON_WORD_RE = re.compile(r"[^a-z0-9]+")

LEGAL_OR_NOISE_TOKENS = {
    "and",
    "co",
    "company",
    "inc",
    "ltd",
    "limited",
    "llc",
    "llp",
    "pvt",
    "private",
    "the",
}

GENERIC_NAME_TOKENS = {
    "aided",
    "care",
    "center",
    "centre",
    "clinic",
    "clinics",
    "college",
    "diagnostic",
    "diagnostics",
    "dispensary",
    "general",
    "health",
    "healthcare",
    "hosp",
    "hospital",
    "hospitals",
    "institute",
    "institutes",
    "laboratory",
    "medical",
    "multi",
    "nursing",
    "pharmacy",
    "research",
    "service",
    "services",
    "specialist",
    "speciality",
    "specialty",
    "super",
    "trust",
}

PAIR_COLUMNS = [
    "pair_id",
    "match_tier",
    "match_score",
    "review_reasons",
    "blocking_methods",
    "left_unique_id",
    "right_unique_id",
    "left_facility_name",
    "right_facility_name",
    "left_normalized_name",
    "right_normalized_name",
    "name_similarity",
    "left_address",
    "right_address",
    "left_normalized_address",
    "right_normalized_address",
    "address_similarity",
    "left_pincode",
    "right_pincode",
    "pincode_match",
    "left_city",
    "right_city",
    "left_state",
    "right_state",
    "city_state_match",
    "phone_match",
    "email_match",
    "shared_normalized_phones",
    "shared_normalized_emails",
    "left_latitude",
    "left_longitude",
    "right_latitude",
    "right_longitude",
    "geo_distance_km",
    "left_source_duplicate_unique_id",
    "right_source_duplicate_unique_id",
    "left_existing_cluster_id",
    "right_existing_cluster_id",
]

CLUSTER_COLUMNS = [
    "er_cluster_id",
    "cluster_size",
    "canonical_candidate_unique_id",
    "canonical_candidate_name",
    "canonical_candidate_reason",
    "member_unique_ids",
    "member_facility_names",
    "member_city_state",
    "member_pincodes",
    "supporting_pair_ids",
    "supporting_pair_count",
    "best_match_tier",
    "max_match_score",
    "max_name_similarity",
    "max_address_similarity",
    "has_phone_match",
    "has_email_match",
    "min_geo_distance_km",
    "review_reasons",
]

TIER_ORDER = {
    "tier_1_high_confidence": 1,
    "tier_2_review_likely": 2,
    "tier_3_review_possible": 3,
}


@dataclass
class Facility:
    row_number: int
    unique_id: str
    source_duplicate_unique_id: str
    existing_cluster_id: str
    name: str
    normalized_name: str
    name_tokens: tuple[str, ...]
    name_block_key: str
    address: str
    normalized_address: str
    address_tokens: tuple[str, ...]
    city: str
    normalized_city: str
    state: str
    normalized_state: str
    pincode: str
    latitude: float | None
    longitude: float | None
    data_readiness_score: float
    raw_phones: tuple[str, ...]
    raw_emails: tuple[str, ...]
    phones: tuple[str, ...] = field(default_factory=tuple)
    emails: tuple[str, ...] = field(default_factory=tuple)


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, item: str) -> str:
        if item not in self.parent:
            self.parent[item] = item
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if right_root < left_root:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--pairs-output", type=Path, default=DEFAULT_PAIR_PATH)
    parser.add_argument("--clusters-output", type=Path, default=DEFAULT_CLUSTER_PATH)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_PATH)
    parser.add_argument(
        "--max-block-size",
        type=int,
        default=250,
        help="Skip any generated block larger than this row count.",
    )
    parser.add_argument(
        "--max-contact-frequency",
        type=int,
        default=20,
        help="Ignore phone/email values that appear on more than this many rows.",
    )
    return parser.parse_args()


def ascii_fold(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii", "ignore")
    )


def normalize_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = ascii_fold(text).lower().replace("&", " and ")
    text = NON_WORD_RE.sub(" ", text)
    return " ".join(text.split())


def tokenize(value: str, *, remove_noise: bool = False) -> tuple[str, ...]:
    tokens = tuple(token for token in normalize_text(value).split() if token)
    if not remove_noise:
        return tokens
    return tuple(token for token in tokens if token not in LEGAL_OR_NOISE_TOKENS)


def name_block_key(tokens: tuple[str, ...]) -> str:
    significant = [
        token
        for token in tokens
        if token not in LEGAL_OR_NOISE_TOKENS and token not in GENERIC_NAME_TOKENS
    ]
    if significant:
        return "-".join(significant[:2])
    if tokens:
        return "-".join(tokens[:2])
    return ""


def normalize_pin(*values: object) -> str:
    for value in values:
        text = "" if value is None else str(value)
        match = PIN_RE.search(text)
        if match:
            return match.group(1)
    return ""


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        result = float(text)
    except ValueError:
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def parse_bool(value: object) -> bool:
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def plausible_india_coordinate(latitude: float | None, longitude: float | None, in_bbox: object) -> bool:
    if latitude is None or longitude is None:
        return False
    if parse_bool(in_bbox):
        return True
    return 5.0 <= latitude <= 40.0 and 60.0 <= longitude <= 100.0


def extract_phones(*values: object) -> tuple[str, ...]:
    phones: set[str] = set()
    for value in values:
        text = "" if value is None else str(value)
        for match in PHONE_RE.findall(text):
            digits = re.sub(r"\D", "", match)
            if digits.startswith("00"):
                digits = digits[2:]
            if len(digits) > 10:
                digits = digits[-10:]
            if len(digits) < 8:
                continue
            if len(set(digits)) <= 2:
                continue
            phones.add(digits)
    return tuple(sorted(phones))


def extract_emails(*values: object) -> tuple[str, ...]:
    emails: set[str] = set()
    for value in values:
        text = "" if value is None else str(value)
        for email in EMAIL_RE.findall(text):
            emails.add(email.lower())
    return tuple(sorted(emails))


def combine_address(row: dict[str, str]) -> str:
    parts = [
        row.get("address_line1", ""),
        row.get("address_line2", ""),
        row.get("address_line3", ""),
        row.get("address_city", ""),
        row.get("address_stateOrRegion", ""),
        row.get("address_zipOrPostcode", ""),
    ]
    return ", ".join(str(part).strip() for part in parts if str(part).strip())


def load_facilities(path: Path, max_contact_frequency: int) -> tuple[list[Facility], dict[str, int]]:
    facilities: list[Facility] = []
    phone_counts: Counter[str] = Counter()
    email_counts: Counter[str] = Counter()

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            unique_id = row.get("unique_id", "").strip()
            if not unique_id:
                unique_id = f"row_{row_number}"

            name = row.get("facility_name", "").strip()
            normalized_name = normalize_text(name)
            name_tokens = tokenize(name, remove_noise=True)
            address = combine_address(row)
            normalized_address = normalize_text(address)
            address_tokens = tokenize(address, remove_noise=True)

            latitude = parse_float(row.get("facility_latitude"))
            longitude = parse_float(row.get("facility_longitude"))
            if not plausible_india_coordinate(latitude, longitude, row.get("geo_in_india_bbox")):
                latitude = None
                longitude = None

            raw_phones = extract_phones(row.get("officialPhone"), row.get("phone_numbers"))
            raw_emails = extract_emails(row.get("email"))
            phone_counts.update(raw_phones)
            email_counts.update(raw_emails)

            facilities.append(
                Facility(
                    row_number=row_number,
                    unique_id=unique_id,
                    source_duplicate_unique_id=row.get("source_duplicate_unique_id", "").strip(),
                    existing_cluster_id=row.get("cluster_id", "").strip(),
                    name=name,
                    normalized_name=normalized_name,
                    name_tokens=name_tokens,
                    name_block_key=name_block_key(name_tokens),
                    address=address,
                    normalized_address=normalized_address,
                    address_tokens=address_tokens,
                    city=row.get("address_city", "").strip(),
                    normalized_city=normalize_text(row.get("address_city", "")),
                    state=row.get("address_stateOrRegion", "").strip(),
                    normalized_state=normalize_text(row.get("address_stateOrRegion", "")),
                    pincode=normalize_pin(row.get("pincode_extracted"), row.get("address_zipOrPostcode")),
                    latitude=latitude,
                    longitude=longitude,
                    data_readiness_score=parse_float(row.get("data_readiness_score")) or 0.0,
                    raw_phones=raw_phones,
                    raw_emails=raw_emails,
                )
            )

    ignored_phones = {value for value, count in phone_counts.items() if count > max_contact_frequency}
    ignored_emails = {value for value, count in email_counts.items() if count > max_contact_frequency}

    for facility in facilities:
        facility.phones = tuple(
            value
            for value in facility.raw_phones
            if phone_counts[value] > 1 and value not in ignored_phones
        )
        facility.emails = tuple(
            value
            for value in facility.raw_emails
            if email_counts[value] > 1 and value not in ignored_emails
        )

    filter_stats = {
        "distinct_normalized_phones": len(phone_counts),
        "distinct_normalized_emails": len(email_counts),
        "ignored_high_frequency_phones": len(ignored_phones),
        "ignored_high_frequency_emails": len(ignored_emails),
    }
    return facilities, filter_stats


def add_block(blocks: dict[str, set[int]], key: str, index: int) -> None:
    if key:
        blocks[key].add(index)


def coord_bucket(value: float, size: float) -> int:
    return math.floor(value / size)


def build_blocks(facilities: list[Facility]) -> dict[str, set[int]]:
    blocks: dict[str, set[int]] = defaultdict(set)
    for index, facility in enumerate(facilities):
        if facility.pincode:
            add_block(blocks, f"pin:{facility.pincode}", index)

        if facility.normalized_city and facility.normalized_state and facility.name_block_key:
            add_block(
                blocks,
                f"city_state_name:{facility.normalized_state}:{facility.normalized_city}:{facility.name_block_key}",
                index,
            )

        for phone in facility.phones:
            add_block(blocks, f"phone:{phone}", index)

        for email in facility.emails:
            add_block(blocks, f"email:{email}", index)

        if facility.latitude is not None and facility.longitude is not None:
            add_block(
                blocks,
                f"geo_0.01:{coord_bucket(facility.latitude, 0.01)}:{coord_bucket(facility.longitude, 0.01)}",
                index,
            )
            if facility.name_block_key:
                add_block(
                    blocks,
                    (
                        "geo_0.02_name:"
                        f"{coord_bucket(facility.latitude, 0.02)}:"
                        f"{coord_bucket(facility.longitude, 0.02)}:"
                        f"{facility.name_block_key}"
                    ),
                    index,
                )
    return blocks


def block_method(block_key: str) -> str:
    return block_key.split(":", 1)[0]


def collect_blocked_pairs(
    blocks: dict[str, set[int]], max_block_size: int
) -> tuple[dict[tuple[int, int], set[str]], dict[str, int]]:
    pair_methods: dict[tuple[int, int], set[str]] = defaultdict(set)
    skipped_blocks = 0
    used_blocks = 0
    generated_pair_mentions = 0

    for block_key in sorted(blocks):
        members = sorted(blocks[block_key])
        if len(members) < 2:
            continue
        if len(members) > max_block_size:
            skipped_blocks += 1
            continue
        used_blocks += 1
        method = block_method(block_key)
        for left_pos, left in enumerate(members):
            for right in members[left_pos + 1 :]:
                pair_methods[(left, right)].add(method)
                generated_pair_mentions += 1

    stats = {
        "generated_blocks": len(blocks),
        "used_blocks": used_blocks,
        "skipped_blocks_over_max_size": skipped_blocks,
        "unique_blocked_pairs": len(pair_methods),
        "generated_pair_mentions": generated_pair_mentions,
    }
    return pair_methods, stats


def token_similarity(left: tuple[str, ...], right: tuple[str, ...]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    containment = intersection / min(len(left_set), len(right_set))
    jaccard = intersection / union
    return (0.65 * containment) + (0.35 * jaccard)


def text_similarity(
    left_text: str,
    right_text: str,
    left_tokens: tuple[str, ...],
    right_tokens: tuple[str, ...],
) -> float:
    if not left_text or not right_text:
        return 0.0
    direct = difflib.SequenceMatcher(None, left_text, right_text).ratio()
    left_sorted = " ".join(sorted(left_tokens))
    right_sorted = " ".join(sorted(right_tokens))
    sorted_ratio = difflib.SequenceMatcher(None, left_sorted, right_sorted).ratio()
    overlap = token_similarity(left_tokens, right_tokens)
    return round(max(direct, sorted_ratio, overlap), 6)


def haversine_km(
    left_lat: float | None,
    left_lon: float | None,
    right_lat: float | None,
    right_lon: float | None,
) -> float | None:
    if None in {left_lat, left_lon, right_lat, right_lon}:
        return None
    assert left_lat is not None
    assert left_lon is not None
    assert right_lat is not None
    assert right_lon is not None
    radius_km = 6371.0088
    lat1 = math.radians(left_lat)
    lat2 = math.radians(right_lat)
    delta_lat = math.radians(right_lat - left_lat)
    delta_lon = math.radians(right_lon - left_lon)
    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return round(radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 6)


def geo_within(geo_distance_km: float | None, threshold: float) -> bool:
    return geo_distance_km is not None and geo_distance_km <= threshold


def score_pair(
    name_similarity: float,
    address_similarity: float,
    phone_match: bool,
    email_match: bool,
    pincode_match: bool,
    city_state_match: bool,
    geo_distance_km: float | None,
) -> float:
    geo_score = 0.0
    if geo_distance_km is not None:
        if geo_distance_km <= 0.2:
            geo_score = 1.0
        elif geo_distance_km <= 1.0:
            geo_score = 0.85
        elif geo_distance_km <= 5.0:
            geo_score = 0.65
        elif geo_distance_km <= 10.0:
            geo_score = 0.4
    score = (
        0.42 * name_similarity
        + 0.24 * address_similarity
        + 0.12 * float(phone_match)
        + 0.12 * float(email_match)
        + 0.04 * float(pincode_match)
        + 0.03 * float(city_state_match)
        + 0.03 * geo_score
    )
    return round(min(score, 1.0), 6)


def assign_tier(
    name_similarity: float,
    address_similarity: float,
    phone_match: bool,
    email_match: bool,
    pincode_match: bool,
    city_state_match: bool,
    geo_distance_km: float | None,
) -> str:
    locality_match = pincode_match or city_state_match or geo_within(geo_distance_km, 5.0)
    strong_locality_match = pincode_match or city_state_match or geo_within(geo_distance_km, 1.0)

    if (
        phone_match
        and email_match
        and name_similarity >= 0.70
        and (
            address_similarity >= 0.82
            or geo_within(geo_distance_km, 0.5)
            or (strong_locality_match and address_similarity >= 0.45)
        )
    ):
        return "tier_1_high_confidence"
    if email_match and name_similarity >= 0.80 and (
        address_similarity >= 0.82
        or geo_within(geo_distance_km, 0.5)
        or (strong_locality_match and address_similarity >= 0.45)
    ):
        return "tier_1_high_confidence"
    if phone_match and name_similarity >= 0.84 and (
        address_similarity >= 0.82
        or geo_within(geo_distance_km, 0.5)
        or (strong_locality_match and address_similarity >= 0.50)
    ):
        return "tier_1_high_confidence"
    if name_similarity >= 0.94 and address_similarity >= 0.82 and locality_match:
        return "tier_1_high_confidence"
    if name_similarity >= 0.92 and geo_within(geo_distance_km, 0.2) and (
        address_similarity >= 0.50 or pincode_match or city_state_match
    ):
        return "tier_1_high_confidence"

    if (phone_match or email_match) and name_similarity >= 0.70 and (
        address_similarity >= 0.35 or pincode_match or city_state_match or geo_within(geo_distance_km, 10.0)
    ):
        return "tier_2_review_likely"
    if name_similarity >= 0.88 and address_similarity >= 0.65 and locality_match:
        return "tier_2_review_likely"
    if name_similarity >= 0.86 and geo_within(geo_distance_km, 0.5) and (
        pincode_match or city_state_match or address_similarity >= 0.45
    ):
        return "tier_2_review_likely"
    if name_similarity >= 0.88 and pincode_match and address_similarity >= 0.55:
        return "tier_2_review_likely"

    if name_similarity >= 0.78 and address_similarity >= 0.50 and (pincode_match or city_state_match):
        return "tier_3_review_possible"
    if name_similarity >= 0.80 and geo_within(geo_distance_km, 1.0):
        return "tier_3_review_possible"
    if (phone_match or email_match) and name_similarity >= 0.55 and address_similarity >= 0.30:
        return "tier_3_review_possible"

    return ""


def compact_json(values: Iterable[str]) -> str:
    return json.dumps(list(values), ensure_ascii=True, separators=(",", ":"))


def review_reasons(
    *,
    name_similarity: float,
    address_similarity: float,
    phone_match: bool,
    email_match: bool,
    shared_phones: list[str],
    shared_emails: list[str],
    pincode_match: bool,
    city_state_match: bool,
    geo_distance_km: float | None,
) -> list[str]:
    reasons: list[str] = []
    if email_match:
        reasons.append(f"shared_email={','.join(shared_emails[:3])}")
    if phone_match:
        reasons.append(f"shared_phone={','.join(shared_phones[:3])}")
    if name_similarity >= 0.94:
        reasons.append(f"very_high_name_similarity={name_similarity:.3f}")
    elif name_similarity >= 0.86:
        reasons.append(f"high_name_similarity={name_similarity:.3f}")
    elif name_similarity >= 0.78:
        reasons.append(f"moderate_name_similarity={name_similarity:.3f}")
    if address_similarity >= 0.82:
        reasons.append(f"very_high_address_similarity={address_similarity:.3f}")
    elif address_similarity >= 0.65:
        reasons.append(f"high_address_similarity={address_similarity:.3f}")
    elif address_similarity >= 0.50:
        reasons.append(f"moderate_address_similarity={address_similarity:.3f}")
    if pincode_match:
        reasons.append("same_pincode")
    if city_state_match:
        reasons.append("same_city_state")
    if geo_distance_km is not None:
        if geo_distance_km <= 0.2:
            reasons.append(f"coordinates_within_0.2km={geo_distance_km:.3f}")
        elif geo_distance_km <= 1.0:
            reasons.append(f"coordinates_within_1km={geo_distance_km:.3f}")
        elif geo_distance_km <= 5.0:
            reasons.append(f"coordinates_within_5km={geo_distance_km:.3f}")
    return reasons


def evaluate_pairs(
    facilities: list[Facility],
    pair_methods: dict[tuple[int, int], set[str]],
) -> list[dict[str, object]]:
    candidate_rows: list[dict[str, object]] = []

    for left_index, right_index in sorted(pair_methods):
        left = facilities[left_index]
        right = facilities[right_index]
        if left.unique_id == right.unique_id:
            continue

        shared_phones = sorted(set(left.phones) & set(right.phones))
        shared_emails = sorted(set(left.emails) & set(right.emails))
        phone_match = bool(shared_phones)
        email_match = bool(shared_emails)
        pincode_match = bool(left.pincode and left.pincode == right.pincode)
        city_state_match = bool(
            left.normalized_city
            and left.normalized_state
            and left.normalized_city == right.normalized_city
            and left.normalized_state == right.normalized_state
        )
        name_similarity = text_similarity(
            left.normalized_name,
            right.normalized_name,
            left.name_tokens,
            right.name_tokens,
        )
        geo_distance_km = haversine_km(
            left.latitude,
            left.longitude,
            right.latitude,
            right.longitude,
        )

        if phone_match or email_match:
            if name_similarity < 0.55:
                continue
        elif name_similarity < 0.78:
            continue

        address_similarity = text_similarity(
            left.normalized_address,
            right.normalized_address,
            left.address_tokens,
            right.address_tokens,
        )
        tier = assign_tier(
            name_similarity,
            address_similarity,
            phone_match,
            email_match,
            pincode_match,
            city_state_match,
            geo_distance_km,
        )
        if not tier:
            continue

        match_score = score_pair(
            name_similarity,
            address_similarity,
            phone_match,
            email_match,
            pincode_match,
            city_state_match,
            geo_distance_km,
        )
        reasons = review_reasons(
            name_similarity=name_similarity,
            address_similarity=address_similarity,
            phone_match=phone_match,
            email_match=email_match,
            shared_phones=shared_phones,
            shared_emails=shared_emails,
            pincode_match=pincode_match,
            city_state_match=city_state_match,
            geo_distance_km=geo_distance_km,
        )

        candidate_rows.append(
            {
                "match_tier": tier,
                "match_score": match_score,
                "review_reasons": "; ".join(reasons),
                "blocking_methods": ";".join(sorted(pair_methods[(left_index, right_index)])),
                "left_unique_id": left.unique_id,
                "right_unique_id": right.unique_id,
                "left_facility_name": left.name,
                "right_facility_name": right.name,
                "left_normalized_name": left.normalized_name,
                "right_normalized_name": right.normalized_name,
                "name_similarity": name_similarity,
                "left_address": left.address,
                "right_address": right.address,
                "left_normalized_address": left.normalized_address,
                "right_normalized_address": right.normalized_address,
                "address_similarity": address_similarity,
                "left_pincode": left.pincode,
                "right_pincode": right.pincode,
                "pincode_match": pincode_match,
                "left_city": left.city,
                "right_city": right.city,
                "left_state": left.state,
                "right_state": right.state,
                "city_state_match": city_state_match,
                "phone_match": phone_match,
                "email_match": email_match,
                "shared_normalized_phones": compact_json(shared_phones),
                "shared_normalized_emails": compact_json(shared_emails),
                "left_latitude": left.latitude if left.latitude is not None else "",
                "left_longitude": left.longitude if left.longitude is not None else "",
                "right_latitude": right.latitude if right.latitude is not None else "",
                "right_longitude": right.longitude if right.longitude is not None else "",
                "geo_distance_km": geo_distance_km if geo_distance_km is not None else "",
                "left_source_duplicate_unique_id": left.source_duplicate_unique_id,
                "right_source_duplicate_unique_id": right.source_duplicate_unique_id,
                "left_existing_cluster_id": left.existing_cluster_id,
                "right_existing_cluster_id": right.existing_cluster_id,
            }
        )

    candidate_rows.sort(
        key=lambda row: (
            TIER_ORDER[str(row["match_tier"])],
            -float(row["match_score"]),
            str(row["left_unique_id"]),
            str(row["right_unique_id"]),
        )
    )
    for index, row in enumerate(candidate_rows, start=1):
        row["pair_id"] = f"er_pair_{index:06d}"
    return candidate_rows


def completeness_score(facility: Facility) -> int:
    return sum(
        [
            bool(facility.name),
            bool(facility.address),
            bool(facility.pincode),
            bool(facility.normalized_city and facility.normalized_state),
            bool(facility.latitude is not None and facility.longitude is not None),
            bool(facility.raw_phones),
            bool(facility.raw_emails),
        ]
    )


def choose_canonical_candidate(members: list[Facility]) -> Facility:
    return sorted(
        members,
        key=lambda facility: (
            -facility.data_readiness_score,
            -completeness_score(facility),
            -len(facility.name),
            facility.unique_id,
        ),
    )[0]


def build_clusters(
    facilities: list[Facility], candidate_rows: list[dict[str, object]]
) -> list[dict[str, object]]:
    high_pairs = [row for row in candidate_rows if row["match_tier"] == "tier_1_high_confidence"]
    by_id = {facility.unique_id: facility for facility in facilities}

    union_find = UnionFind()
    for row in high_pairs:
        union_find.union(str(row["left_unique_id"]), str(row["right_unique_id"]))

    components: dict[str, set[str]] = defaultdict(set)
    for row in high_pairs:
        left_id = str(row["left_unique_id"])
        right_id = str(row["right_unique_id"])
        root = union_find.find(left_id)
        components[root].update([left_id, right_id])

    high_pair_by_component: dict[str, list[dict[str, object]]] = defaultdict(list)
    for row in high_pairs:
        root = union_find.find(str(row["left_unique_id"]))
        high_pair_by_component[root].append(row)

    cluster_rows: list[dict[str, object]] = []
    sorted_components = sorted(
        [sorted(member_ids) for member_ids in components.values() if len(member_ids) >= 2],
        key=lambda member_ids: member_ids[0],
    )

    for cluster_index, member_ids in enumerate(sorted_components, start=1):
        members = [by_id[member_id] for member_id in member_ids if member_id in by_id]
        if len(members) < 2:
            continue
        root = union_find.find(member_ids[0])
        supporting_pairs = sorted(
            high_pair_by_component[root],
            key=lambda row: str(row["pair_id"]),
        )
        canonical = choose_canonical_candidate(members)
        geo_distances = [
            float(row["geo_distance_km"])
            for row in supporting_pairs
            if str(row["geo_distance_km"]).strip()
        ]
        cluster_reasons = sorted(
            {
                reason.strip()
                for row in supporting_pairs
                for reason in str(row["review_reasons"]).split(";")
                if reason.strip()
            }
        )
        city_state = sorted(
            {
                f"{member.city}, {member.state}".strip(", ")
                for member in members
                if member.city or member.state
            }
        )
        cluster_rows.append(
            {
                "er_cluster_id": f"er_cluster_{cluster_index:06d}",
                "cluster_size": len(members),
                "canonical_candidate_unique_id": canonical.unique_id,
                "canonical_candidate_name": canonical.name,
                "canonical_candidate_reason": (
                    "Highest data_readiness_score, then contact/address completeness, then deterministic ID tie-break."
                ),
                "member_unique_ids": compact_json(member_ids),
                "member_facility_names": compact_json(member.name for member in members),
                "member_city_state": compact_json(city_state),
                "member_pincodes": compact_json(sorted({member.pincode for member in members if member.pincode})),
                "supporting_pair_ids": compact_json(str(row["pair_id"]) for row in supporting_pairs),
                "supporting_pair_count": len(supporting_pairs),
                "best_match_tier": "tier_1_high_confidence",
                "max_match_score": round(max(float(row["match_score"]) for row in supporting_pairs), 6),
                "max_name_similarity": round(max(float(row["name_similarity"]) for row in supporting_pairs), 6),
                "max_address_similarity": round(max(float(row["address_similarity"]) for row in supporting_pairs), 6),
                "has_phone_match": any(parse_bool(row["phone_match"]) for row in supporting_pairs),
                "has_email_match": any(parse_bool(row["email_match"]) for row in supporting_pairs),
                "min_geo_distance_km": min(geo_distances) if geo_distances else "",
                "review_reasons": "; ".join(cluster_reasons),
            }
        )
    return cluster_rows


def write_csv(path: Path, rows: list[dict[str, object]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in columns})


def write_summary(
    path: Path,
    *,
    args: argparse.Namespace,
    facilities: list[Facility],
    candidate_rows: list[dict[str, object]],
    cluster_rows: list[dict[str, object]],
    block_stats: dict[str, int],
    filter_stats: dict[str, int],
) -> dict[str, object]:
    tier_counts = Counter(str(row["match_tier"]) for row in candidate_rows)
    clustered_facility_rows = sum(int(row["cluster_size"]) for row in cluster_rows)
    summary: dict[str, object] = {
        "script_version": SCRIPT_VERSION,
        "source_file": str(args.input.relative_to(ROOT) if args.input.is_relative_to(ROOT) else args.input),
        "source_rows": len(facilities),
        "candidate_pair_rows": len(candidate_rows),
        "cluster_rows": len(cluster_rows),
        "clustered_facility_rows": clustered_facility_rows,
        "tier_counts": {tier: tier_counts.get(tier, 0) for tier in TIER_ORDER},
        "blocking": {
            **block_stats,
            "max_block_size": args.max_block_size,
            "blocking_methods": [
                "exact PIN",
                "city/state plus significant normalized name token",
                "frequency-filtered normalized phone",
                "frequency-filtered normalized email",
                "0.01 degree coordinate bucket",
                "0.02 degree coordinate bucket plus significant normalized name token",
            ],
        },
        "contact_frequency_filter": {
            **filter_stats,
            "max_contact_frequency": args.max_contact_frequency,
            "note": "Phone/email values above the frequency cap are ignored for blocking and match flags.",
        },
        "cluster_policy": (
            "Clusters are connected components of tier_1_high_confidence candidate pairs only. "
            "They are review aids and do not modify the canonical facility table."
        ),
        "outputs": {
            "candidate_pairs": str(
                args.pairs_output.relative_to(ROOT)
                if args.pairs_output.is_relative_to(ROOT)
                else args.pairs_output
            ),
            "clusters": str(
                args.clusters_output.relative_to(ROOT)
                if args.clusters_output.is_relative_to(ROOT)
                else args.clusters_output
            ),
            "summary": str(
                args.summary_output.relative_to(ROOT)
                if args.summary_output.is_relative_to(ROOT)
                else args.summary_output
            ),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return summary


def main() -> int:
    args = parse_args()
    facilities, filter_stats = load_facilities(args.input, args.max_contact_frequency)
    blocks = build_blocks(facilities)
    pair_methods, block_stats = collect_blocked_pairs(blocks, args.max_block_size)
    candidate_rows = evaluate_pairs(facilities, pair_methods)
    cluster_rows = build_clusters(facilities, candidate_rows)

    write_csv(args.pairs_output, candidate_rows, PAIR_COLUMNS)
    write_csv(args.clusters_output, cluster_rows, CLUSTER_COLUMNS)
    summary = write_summary(
        args.summary_output,
        args=args,
        facilities=facilities,
        candidate_rows=candidate_rows,
        cluster_rows=cluster_rows,
        block_stats=block_stats,
        filter_stats=filter_stats,
    )

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
