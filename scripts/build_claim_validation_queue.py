#!/usr/bin/env python3
"""Build a local facility-claim validation queue from cleaned facility claims."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "output" / "data"

DEFAULT_INPUT = DATA_DIR / "facility_health_cleaned.csv"
DEFAULT_QUEUE_OUTPUT = DATA_DIR / "claim_validation_queue.csv"
DEFAULT_SUMMARY_OUTPUT = DATA_DIR / "claim_validation_summary.json"

LANE_VERSION = "claim_validation_rules_v1"

ADDRESS_COLUMNS = [
    "address_line1",
    "address_line2",
    "address_line3",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "pincode_extracted",
    "district_name",
    "state_ut",
]

INPUT_COLUMNS = [
    "unique_id",
    "facility_name",
    "facilityTypeId",
    "operatorTypeId",
    *ADDRESS_COLUMNS,
    "claim_text",
    "source_urls",
    "officialWebsite",
    "websites",
    "officialPhone",
    "phone_numbers",
    "email",
    "has_source_urls",
    "has_contact_evidence",
    "description_status",
    "specialties_status",
    "procedure_status",
    "equipment_status",
    "equipment_confidence",
    "capability_status",
    "description_item_count",
    "specialties_item_count",
    "procedure_item_count",
    "equipment_item_count",
    "capability_item_count",
    "description_len",
    "specialties_len",
    "procedure_len",
    "equipment_len",
    "capability_len",
    "semantic_data_quality_score",
    "semantic_missing_critical_count",
    "needs_human_review",
    "trustworthy_supply_signal",
    "medical_desert_priority_score",
    "health_need_score",
]

NUMERIC_COLUMNS = [
    "description_item_count",
    "specialties_item_count",
    "procedure_item_count",
    "equipment_item_count",
    "capability_item_count",
    "description_len",
    "specialties_len",
    "procedure_len",
    "equipment_len",
    "capability_len",
    "semantic_data_quality_score",
    "semantic_missing_critical_count",
    "medical_desert_priority_score",
    "health_need_score",
]

BOOLEAN_COLUMNS = [
    "has_source_urls",
    "has_contact_evidence",
    "needs_human_review",
    "trustworthy_supply_signal",
]

CLAIM_SECTIONS = ["description", "specialties", "procedure", "equipment", "capability"]

FIELD_STATUS_COLUMNS = {
    "description": "description_status",
    "specialties": "specialties_status",
    "procedure": "procedure_status",
    "equipment": "equipment_status",
    "capability": "capability_status",
}

FIELD_COUNT_COLUMNS = {
    "description": "description_item_count",
    "specialties": "specialties_item_count",
    "procedure": "procedure_item_count",
    "equipment": "equipment_item_count",
    "capability": "capability_item_count",
}

BROAD_SOURCE_PATTERNS = [
    ("all_specialty_services", r"\ball (specialty|speciality|specialties|specialities) services?\b"),
    ("multi_specialty_generic", r"\b(multi\s*super\s*specialty|multi\s*specialty|multispecialty|multi\s*speciality|super\s*specialty|quaternary care)\b"),
    ("directory_listing", r"\b(listed among|listed as|top hospitals?|top clinics?|hospital in .{0,80} offering)\b"),
    ("indirect_affiliation", r"\b(affiliated (with|organization|to)|mentioned as|outside the state listed|referral hospital)\b"),
    ("academic_or_article_context", r"\b(mbbs|medical college|approved and recognized|journal article|pubmed article|article '|research collaboration)\b"),
    ("generic_full_service", r"\b(complete|comprehensive|full range|wide range)\b.{0,40}\b(services?|care|specialties|specialities|facilities)\b"),
]


@dataclass(frozen=True)
class CategoryRule:
    category: str
    impact_level: str
    impact_weight: float
    related_fields: tuple[str, ...]
    patterns: tuple[tuple[str, str], ...]
    generic_keywords: frozenset[str] = frozenset()


def terms(*items: str) -> tuple[tuple[str, str], ...]:
    return tuple((item, rf"\b{re.escape(item)}\b") for item in items)


CATEGORY_RULES = [
    CategoryRule(
        category="maternity",
        impact_level="critical",
        impact_weight=1.0,
        related_fields=("specialties", "procedure", "capability"),
        patterns=terms(
            "maternity",
            "maternal",
            "obstetrics",
            "obstetric",
            "gynecology",
            "gynaecology",
            "normal delivery",
            "caesarean",
            "cesarean",
            "c section",
            "labour room",
            "labor room",
            "neonatology",
            "neonatal",
            "perinatal",
            "fetal",
            "foetal",
            "ivf",
            "infertility",
            "reproductive",
        ),
    ),
    CategoryRule(
        category="emergency",
        impact_level="critical",
        impact_weight=1.0,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "emergency",
            "emergency medicine",
            "pediatric emergency",
            "paediatric emergency",
            "trauma",
            "casualty",
            "urgent care",
            "accident",
            "ambulance",
            "disaster response",
        ),
    ),
    CategoryRule(
        category="diagnostic",
        impact_level="high",
        impact_weight=0.85,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "diagnostic",
            "diagnostics",
            "screening",
            "ct scan",
            "mri",
            "pet ct",
            "ultrasound",
            "sonography",
            "x ray",
            "xray",
            "endoscopy",
            "biopsy",
            "echo",
            "tmt",
            "ecg",
            "ekg",
        ),
        generic_keywords=frozenset({"diagnostic", "diagnostics", "screening"}),
    ),
    CategoryRule(
        category="surgery",
        impact_level="high",
        impact_weight=0.85,
        related_fields=("specialties", "procedure", "capability"),
        patterns=terms(
            "surgery",
            "surgical",
            "operating theatre",
            "operation theatre",
            "operating room",
            "ot",
            "laparoscopic",
            "robotic surgery",
            "transplant",
            "reconstruction",
            "hysterectomy",
            "cholecystectomy",
            "hernia repair",
            "craniotomy",
            "laminectomy",
            "angioplasty",
        ),
        generic_keywords=frozenset({"surgery", "surgical", "ot"}),
    ),
    CategoryRule(
        category="cardiology",
        impact_level="high",
        impact_weight=0.8,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "cardiology",
            "cardiac",
            "cardiothoracic",
            "heart",
            "coronary",
            "angioplasty",
            "angiogram",
            "cath lab",
            "echocardiography",
            "echo",
            "tmt",
            "ecg",
            "ekg",
        ),
    ),
    CategoryRule(
        category="oncology",
        impact_level="high",
        impact_weight=0.82,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "oncology",
            "oncological",
            "onco",
            "cancer",
            "tumor",
            "tumour",
            "radiotherapy",
            "radiation therapy",
            "chemotherapy",
            "bone marrow transplant",
            "bmt",
            "hematology oncology",
            "haematology oncology",
        ),
    ),
    CategoryRule(
        category="ophthalmology",
        impact_level="standard",
        impact_weight=0.55,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "ophthalmology",
            "eye",
            "cataract",
            "cornea",
            "retina",
            "vitreoretinal",
            "glaucoma",
            "oculoplastics",
            "orbital surgery",
        ),
    ),
    CategoryRule(
        category="dental",
        impact_level="standard",
        impact_weight=0.5,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "dental",
            "dentistry",
            "dentist",
            "oral medicine",
            "oral and maxillofacial",
            "orthodontics",
            "periodontics",
            "endodontics",
            "prosthodontics",
            "implantology",
        ),
    ),
    CategoryRule(
        category="pharmacy",
        impact_level="standard",
        impact_weight=0.5,
        related_fields=("equipment", "capability"),
        patterns=terms(
            "pharmacy",
            "pharmaceutical",
            "drug store",
            "dispensary",
            "medicines",
            "medication",
            "drug dispensing",
        ),
        generic_keywords=frozenset({"medicines", "medication"}),
    ),
    CategoryRule(
        category="lab/imaging",
        impact_level="high",
        impact_weight=0.8,
        related_fields=("specialties", "procedure", "equipment", "capability"),
        patterns=terms(
            "laboratory",
            "lab",
            "pathology",
            "radiology",
            "imaging",
            "diagnostic radiology",
            "ct scan",
            "mri",
            "pet ct",
            "ultrasound",
            "sonography",
            "x ray",
            "xray",
            "nuclear medicine",
            "histopathology",
            "microbiology",
            "biochemistry",
        ),
        generic_keywords=frozenset({"lab", "laboratory", "imaging"}),
    ),
    CategoryRule(
        category="blood bank",
        impact_level="critical",
        impact_weight=0.95,
        related_fields=("procedure", "equipment", "capability"),
        patterns=terms(
            "blood bank",
            "blood storage",
            "blood transfusion",
            "transfusion medicine",
            "blood product",
            "blood products",
        ),
    ),
    CategoryRule(
        category="ICU/critical care",
        impact_level="critical",
        impact_weight=1.0,
        related_fields=("specialties", "equipment", "capability"),
        patterns=terms(
            "icu",
            "intensive care",
            "critical care",
            "ccu",
            "nicu",
            "picu",
            "hdu",
            "ventilator",
            "ventilation",
        ),
    ),
]

COMPILED_CATEGORY_RULES = [
    (
        rule,
        tuple((label, re.compile(pattern, flags=re.IGNORECASE)) for label, pattern in rule.patterns),
    )
    for rule in CATEGORY_RULES
]

COMPILED_BROAD_PATTERNS = [
    (label, re.compile(pattern, flags=re.IGNORECASE)) for label, pattern in BROAD_SOURCE_PATTERNS
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--queue-output", type=Path, default=DEFAULT_QUEUE_OUTPUT)
    parser.add_argument("--summary-output", type=Path, default=DEFAULT_SUMMARY_OUTPUT)
    parser.add_argument("--limit", type=int, default=0, help="Optional smoke-test row limit. 0 means all rows.")
    return parser.parse_args()


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "none", "null", "[]"}:
        return ""
    return text


def normalize_for_match(value: Any) -> str:
    text = clean_text(value)
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9/+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def truncate(value: Any, max_len: int = 420) -> str:
    text = re.sub(r"\s+", " ", clean_text(value)).strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def stable_id(*parts: Any) -> str:
    payload = "||".join(clean_text(part).lower() for part in parts)
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]
    return f"claimq_{digest}"


def coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    text = series.astype("string").fillna("").str.lower().str.strip()
    return text.isin({"true", "1", "yes", "y"})


def load_facilities(path: Path, limit: int = 0) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Missing cleaned facility file: {path}")

    header = pd.read_csv(path, nrows=0).columns.tolist()
    usecols = [col for col in INPUT_COLUMNS if col in header]
    kwargs: dict[str, Any] = {"usecols": usecols, "low_memory": False}
    if limit > 0:
        kwargs["nrows"] = limit
    df = pd.read_csv(path, **kwargs)

    for col in INPUT_COLUMNS:
        if col not in df:
            df[col] = np.nan
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in BOOLEAN_COLUMNS:
        df[col] = coerce_bool(df[col])
    return df


def parse_list(value: Any) -> list[str]:
    text = clean_text(value)
    if not text:
        return []
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list):
        return [clean_text(item) for item in parsed if clean_text(item)]
    if text.startswith("[") and text.endswith("]"):
        text = text.strip("[]")
    pieces = re.split(r"\s*,\s*|\s*;\s*", text)
    return [piece.strip("'\" ") for piece in pieces if piece.strip("'\" ")]


def source_urls(value: Any) -> list[str]:
    urls = parse_list(value)
    if urls:
        return urls
    text = clean_text(value)
    if not text:
        return []
    found = re.findall(r"https?://[^\s,\]'\"]+", text)
    return found or [text]


def contact_evidence_types(row: pd.Series) -> list[str]:
    types = []
    if clean_text(row.get("officialPhone")):
        types.append("officialPhone")
    if parse_list(row.get("phone_numbers")):
        types.append("phone_numbers")
    if clean_text(row.get("email")):
        types.append("email")
    return types


def split_claim_sections(claim_text: Any) -> dict[str, str]:
    text = clean_text(claim_text)
    parts = [part.strip() for part in text.split(" | ")]
    if len(parts) > len(CLAIM_SECTIONS):
        parts = parts[: len(CLAIM_SECTIONS) - 1] + [" | ".join(parts[len(CLAIM_SECTIONS) - 1 :])]
    parts.extend([""] * (len(CLAIM_SECTIONS) - len(parts)))
    return dict(zip(CLAIM_SECTIONS, parts))


def field_display(value: Any, max_items: int = 6) -> str:
    items = parse_list(value)
    if items:
        return "; ".join(items[:max_items])
    return clean_text(value)


def matched_field_display(value: Any, matched_keywords: list[str], max_items: int = 8) -> str:
    items = parse_list(value)
    if not items:
        return clean_text(value)

    keyword_patterns = [
        re.compile(rf"\b{re.escape(normalize_for_match(keyword))}\b", flags=re.IGNORECASE)
        for keyword in matched_keywords
        if normalize_for_match(keyword)
    ]
    matched_items = []
    for item in items:
        normalized = normalize_for_match(item)
        if any(pattern.search(normalized) for pattern in keyword_patterns):
            matched_items.append(item)

    return "; ".join((matched_items or items)[:max_items])


def match_category(
    sections: dict[str, str],
    compiled_rule: tuple[CategoryRule, tuple[tuple[str, re.Pattern[str]], ...]],
) -> dict[str, Any]:
    rule, patterns = compiled_rule
    keywords_by_field: dict[str, list[str]] = {}

    for field, section_text in sections.items():
        normalized = normalize_for_match(section_text)
        if not normalized:
            continue
        matches = []
        for label, pattern in patterns:
            if pattern.search(normalized):
                matches.append(label)
        if matches:
            keywords_by_field[field] = sorted(set(matches))

    matched_keywords = sorted({keyword for keywords in keywords_by_field.values() for keyword in keywords})
    matched_fields = [field for field in CLAIM_SECTIONS if field in keywords_by_field]
    return {
        "matched": bool(matched_keywords),
        "matched_keywords": matched_keywords,
        "matched_fields": matched_fields,
        "keywords_by_field": keywords_by_field,
    }


def broad_source_labels(sections: dict[str, str]) -> list[str]:
    normalized = normalize_for_match(" ".join(sections.values()))
    return [label for label, pattern in COMPILED_BROAD_PATTERNS if pattern.search(normalized)]


def is_broad_or_ambiguous(
    rule: CategoryRule,
    match: dict[str, Any],
    broad_labels: list[str],
    row: pd.Series,
) -> bool:
    if not match["matched"]:
        return False

    matched_keywords = set(match["matched_keywords"])
    matched_fields = set(match["matched_fields"])
    only_generic = bool(matched_keywords) and matched_keywords.issubset(rule.generic_keywords)
    indirect_only = bool(broad_labels) and matched_fields.issubset({"description", "capability"})
    capped_claim_list = any(float(row.get(FIELD_COUNT_COLUMNS[field]) or 0) >= 50 for field in rule.related_fields)
    weak_row = bool(row.get("needs_human_review")) or not bool(row.get("trustworthy_supply_signal"))
    return only_generic or indirect_only or (capped_claim_list and weak_row and bool(broad_labels))


def field_missing_reasons(rule: CategoryRule, row: pd.Series) -> list[str]:
    reasons = []
    for field in rule.related_fields:
        status_col = FIELD_STATUS_COLUMNS[field]
        if clean_text(row.get(status_col)) != "observed_claim":
            reasons.append(f"missing_{field}_claim_field")
    return reasons


def evidence_excerpt(rule: CategoryRule, match: dict[str, Any], sections: dict[str, str]) -> str:
    if match["matched_fields"]:
        for field in [*rule.related_fields, "description"]:
            if field in match["matched_fields"]:
                return truncate(matched_field_display(sections[field], match["matched_keywords"]), 500)
    return truncate(field_display(sections.get("description", "")), 280)


def has_high_need_context(row: pd.Series) -> bool:
    desert = safe_float(row.get("medical_desert_priority_score"))
    need = safe_float(row.get("health_need_score"))
    return desert >= 0.50 or need >= 0.60


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(out):
        return default
    return out


def build_review_reasons(
    rule: CategoryRule,
    presence_status: str,
    broad_labels: list[str],
    row: pd.Series,
    matched: bool,
) -> list[str]:
    reasons = []
    if presence_status == "missing":
        reasons.append("category_not_observed_in_local_claim_text")
    if presence_status == "broad_or_ambiguous":
        reasons.append("broad_or_ambiguous_claim_language")
    if broad_labels:
        reasons.extend(f"broad_source:{label}" for label in broad_labels[:3])
    if bool(row.get("needs_human_review")):
        reasons.append("source_row_needs_human_review")
    if not bool(row.get("trustworthy_supply_signal")):
        reasons.append("not_trustworthy_supply_signal")
    if not bool(row.get("has_source_urls")):
        reasons.append("missing_source_url")
    if not clean_text(row.get("officialWebsite")):
        reasons.append("missing_official_website")
    if not bool(row.get("has_contact_evidence")):
        reasons.append("missing_contact_evidence")
    if safe_float(row.get("semantic_data_quality_score"), 1.0) < 0.60:
        reasons.append("low_semantic_quality")

    reasons.extend(field_missing_reasons(rule, row))

    if rule.impact_level in {"critical", "high"} and matched:
        reasons.append("high_impact_observed_claim_requires_verification")
    if rule.impact_level in {"critical", "high"} and presence_status == "missing" and has_high_need_context(row):
        reasons.append("high_impact_missing_in_high_need_context")
    if safe_float(row.get("medical_desert_priority_score")) >= 0.50:
        reasons.append("high_medical_desert_priority")
    if safe_float(row.get("health_need_score")) >= 0.60:
        reasons.append("high_health_need")

    return sorted(dict.fromkeys(reasons))


def needs_verification(rule: CategoryRule, presence_status: str, reasons: list[str]) -> bool:
    reason_set = set(reasons)
    if presence_status == "broad_or_ambiguous":
        return True
    if rule.impact_level in {"critical", "high"} and presence_status != "missing":
        return True
    if "high_impact_missing_in_high_need_context" in reason_set:
        return True
    verification_reasons = {
        "source_row_needs_human_review",
        "not_trustworthy_supply_signal",
        "missing_source_url",
        "missing_official_website",
        "missing_contact_evidence",
        "low_semantic_quality",
    }
    return bool(reason_set & verification_reasons)


def priority_score(
    rule: CategoryRule,
    presence_status: str,
    verification_needed: bool,
    reasons: list[str],
    row: pd.Series,
) -> float:
    score = 8.0
    if presence_status != "missing":
        score += 7.0
    if presence_status == "broad_or_ambiguous":
        score += 10.0
    score += 20.0 * rule.impact_weight
    if verification_needed:
        score += 12.0
    if bool(row.get("needs_human_review")):
        score += 8.0
    if not bool(row.get("trustworthy_supply_signal")):
        score += 7.0
    if "missing_source_url" in reasons:
        score += 6.0
    if "missing_official_website" in reasons:
        score += 4.0
    if "missing_contact_evidence" in reasons:
        score += 4.0
    score += 14.0 * safe_float(row.get("medical_desert_priority_score"))
    score += 12.0 * safe_float(row.get("health_need_score"))
    score += 8.0 * max(0.0, 1.0 - safe_float(row.get("semantic_data_quality_score"), 1.0))
    if "high_impact_missing_in_high_need_context" in reasons:
        score += 12.0
    return round(float(np.clip(score, 0.0, 100.0)), 3)


def validation_action(rule: CategoryRule, presence_status: str, verification_needed: bool, reasons: list[str]) -> str:
    if presence_status == "broad_or_ambiguous":
        return "resolve_broad_or_ambiguous_claim"
    if "high_impact_missing_in_high_need_context" in reasons:
        return "verify_or_fill_missing_high_impact_claim"
    if verification_needed and rule.impact_level in {"critical", "high"} and presence_status != "missing":
        return "verify_observed_high_impact_claim"
    if verification_needed:
        return "verify_source_evidence"
    if presence_status == "missing":
        return "monitor_missing_local_evidence"
    return "accept_observed_proxy"


def build_queue(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []

    for row in df.itertuples(index=False):
        row_s = pd.Series(row._asdict())
        sections = split_claim_sections(row_s.get("claim_text"))
        broad_labels = broad_source_labels(sections)
        urls = source_urls(row_s.get("source_urls"))
        contacts = contact_evidence_types(row_s)

        for compiled_rule in COMPILED_CATEGORY_RULES:
            rule = compiled_rule[0]
            match = match_category(sections, compiled_rule)
            ambiguous = is_broad_or_ambiguous(rule, match, broad_labels, row_s)
            if not match["matched"]:
                presence_status = "missing"
            elif ambiguous:
                presence_status = "broad_or_ambiguous"
            else:
                presence_status = "observed"

            reasons = build_review_reasons(rule, presence_status, broad_labels, row_s, match["matched"])
            verification_needed = needs_verification(rule, presence_status, reasons)
            priority = priority_score(rule, presence_status, verification_needed, reasons, row_s)

            rows.append(
                {
                    "validation_queue_id": stable_id(row_s.get("unique_id"), rule.category, LANE_VERSION),
                    "lane_version": LANE_VERSION,
                    "unique_id": clean_text(row_s.get("unique_id")),
                    "facility_name": clean_text(row_s.get("facility_name")),
                    "facilityTypeId": clean_text(row_s.get("facilityTypeId")),
                    "operatorTypeId": clean_text(row_s.get("operatorTypeId")),
                    **{col: clean_text(row_s.get(col)) for col in ADDRESS_COLUMNS},
                    "claim_category": rule.category,
                    "claim_impact_level": rule.impact_level,
                    "claim_presence_status": presence_status,
                    "observed_claim": presence_status in {"observed", "broad_or_ambiguous"},
                    "missing_local_evidence": presence_status == "missing",
                    "broad_or_ambiguous": ambiguous,
                    "high_impact_claim": rule.impact_level in {"critical", "high"},
                    "needs_verification": verification_needed,
                    "validation_action": validation_action(rule, presence_status, verification_needed, reasons),
                    "priority_score": priority,
                    "review_reasons": "|".join(reasons),
                    "matched_evidence_fields": "|".join(match["matched_fields"]),
                    "matched_keywords": "|".join(match["matched_keywords"]),
                    "broad_source_labels": "|".join(broad_labels),
                    "evidence_excerpt": evidence_excerpt(rule, match, sections),
                    "claim_text_excerpt": truncate(row_s.get("claim_text"), 650),
                    "source_urls": clean_text(row_s.get("source_urls")),
                    "source_url_count": len(urls),
                    "primary_source_url": urls[0] if urls else "",
                    "officialWebsite": clean_text(row_s.get("officialWebsite")),
                    "officialPhone": clean_text(row_s.get("officialPhone")),
                    "phone_numbers": clean_text(row_s.get("phone_numbers")),
                    "email": clean_text(row_s.get("email")),
                    "has_source_urls": bool(row_s.get("has_source_urls")),
                    "has_contact_evidence": bool(row_s.get("has_contact_evidence")),
                    "contact_evidence_types": "|".join(contacts),
                    "description_status": clean_text(row_s.get("description_status")),
                    "specialties_status": clean_text(row_s.get("specialties_status")),
                    "procedure_status": clean_text(row_s.get("procedure_status")),
                    "equipment_status": clean_text(row_s.get("equipment_status")),
                    "equipment_confidence": clean_text(row_s.get("equipment_confidence")),
                    "capability_status": clean_text(row_s.get("capability_status")),
                    "description_item_count": safe_float(row_s.get("description_item_count")),
                    "specialties_item_count": safe_float(row_s.get("specialties_item_count")),
                    "procedure_item_count": safe_float(row_s.get("procedure_item_count")),
                    "equipment_item_count": safe_float(row_s.get("equipment_item_count")),
                    "capability_item_count": safe_float(row_s.get("capability_item_count")),
                    "semantic_data_quality_score": safe_float(row_s.get("semantic_data_quality_score")),
                    "semantic_missing_critical_count": safe_float(row_s.get("semantic_missing_critical_count")),
                    "needs_human_review_source": bool(row_s.get("needs_human_review")),
                    "trustworthy_supply_signal": bool(row_s.get("trustworthy_supply_signal")),
                    "medical_desert_priority_score": safe_float(row_s.get("medical_desert_priority_score")),
                    "health_need_score": safe_float(row_s.get("health_need_score")),
                }
            )

    queue = pd.DataFrame(rows)
    queue = queue.sort_values(
        ["priority_score", "needs_verification", "high_impact_claim", "facility_name", "claim_category"],
        ascending=[False, False, False, True, True],
        kind="mergesort",
    ).reset_index(drop=True)
    queue.insert(0, "queue_rank", np.arange(1, len(queue) + 1))
    return queue


def reason_counts(queue: pd.DataFrame) -> Counter[str]:
    counts: Counter[str] = Counter()
    for raw in queue["review_reasons"].fillna(""):
        for reason in str(raw).split("|"):
            if reason:
                counts[reason] += 1
    return counts


def grouped_counts(df: pd.DataFrame, columns: list[str]) -> list[dict[str, Any]]:
    grouped = df.groupby(columns, dropna=False).size().reset_index(name="rows")
    return grouped.sort_values(["rows", *columns], ascending=[False, *([True] * len(columns))]).to_dict("records")


def json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, (np.bool_,)):
        return bool(value)
    return value


def build_summary(source: pd.DataFrame, queue: pd.DataFrame, input_path: Path, queue_path: Path) -> dict[str, Any]:
    reasons = reason_counts(queue)
    status_counts = {
        col: source[col].fillna("").astype(str).value_counts(dropna=False).to_dict()
        for col in FIELD_STATUS_COLUMNS.values()
        if col in source
    }
    category_presence = grouped_counts(queue, ["claim_category", "claim_presence_status"])
    category_actions = grouped_counts(queue, ["claim_category", "validation_action"])
    priority_quantiles = queue["priority_score"].quantile([0, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0]).round(3)

    summary = {
        "lane_version": LANE_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "input_path": str(input_path.relative_to(ROOT)),
        "queue_output_path": str(queue_path.relative_to(ROOT)),
        "facility_rows": int(len(source)),
        "claim_categories": [rule.category for rule in CATEGORY_RULES],
        "queue_rows": int(len(queue)),
        "presence_status_counts": queue["claim_presence_status"].value_counts(dropna=False).to_dict(),
        "validation_action_counts": queue["validation_action"].value_counts(dropna=False).to_dict(),
        "needs_verification_rows": int(queue["needs_verification"].sum()),
        "high_impact_rows": int(queue["high_impact_claim"].sum()),
        "observed_claim_rows": int(queue["observed_claim"].sum()),
        "missing_local_evidence_rows": int(queue["missing_local_evidence"].sum()),
        "broad_or_ambiguous_rows": int(queue["broad_or_ambiguous"].sum()),
        "top_review_reason_counts": dict(reasons.most_common(25)),
        "category_presence_counts": category_presence,
        "category_action_counts": category_actions,
        "source_evidence_counts": {
            "facilities_with_source_urls": int(source["has_source_urls"].sum()),
            "facilities_with_contact_evidence": int(source["has_contact_evidence"].sum()),
            "facilities_with_official_website": int(source["officialWebsite"].map(clean_text).astype(bool).sum()),
            "queue_rows_with_source_urls": int(queue["has_source_urls"].sum()),
            "queue_rows_with_contact_evidence": int(queue["has_contact_evidence"].sum()),
        },
        "field_status_counts": status_counts,
        "priority_score_quantiles": {str(key): float(value) for key, value in priority_quantiles.items()},
        "top_priority_examples": queue[
            [
                "queue_rank",
                "priority_score",
                "facility_name",
                "claim_category",
                "claim_presence_status",
                "validation_action",
                "review_reasons",
            ]
        ]
        .head(20)
        .to_dict("records"),
        "notes": [
            "No web or API calls are used; source URLs and contact fields are treated as local evidence metadata only.",
            "Observed claims are keyword/regex matches against local claim_text sections, not verified service availability.",
            "Missing means the controlled category was not observed in local claim_text evidence for that facility.",
        ],
    }
    return json_safe(summary)


def main() -> None:
    args = parse_args()
    facilities = load_facilities(args.input, args.limit)
    queue = build_queue(facilities)

    args.queue_output.parent.mkdir(parents=True, exist_ok=True)
    queue.to_csv(args.queue_output, index=False)

    summary = build_summary(facilities, queue, args.input, args.queue_output)
    args.summary_output.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "facility_rows": summary["facility_rows"],
                "queue_rows": summary["queue_rows"],
                "presence_status_counts": summary["presence_status_counts"],
                "validation_action_counts": summary["validation_action_counts"],
                "top_review_reason_counts": dict(list(summary["top_review_reason_counts"].items())[:10]),
                "queue_output_path": str(args.queue_output),
                "summary_output_path": str(args.summary_output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
