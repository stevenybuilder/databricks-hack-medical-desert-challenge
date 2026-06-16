"""App configuration: data paths, specialty mapping, and styling constants.

Phase 1 reads the pre-cleaned facility table from the local project output.
A later phase will swap `facility_table_path()` for a Databricks SQL warehouse
read against the Unity Catalog Delta tables (same columns).
"""
from __future__ import annotations

import os
from pathlib import Path

APP_TITLE = "Medical Desert Navigator"
APP_TAGLINE = "Trust-weighted care gaps across India"

# --- Data location -----------------------------------------------------------
# Default to the project's pre-cleaned output; override with DATA_DIR env var.
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "output" / "data"


def data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", str(_DEFAULT_DATA_DIR)))


def facility_table_path() -> Path:
    return data_dir() / "facility_health_cleaned.csv"


def district_table_path() -> Path:
    return data_dir() / "district_health_facility_cleaned.csv"


def golden_facility_seed_report_path() -> Path:
    return data_dir() / "golden_facility_seed_report.json"


def facility_prediction_model_report_path() -> Path:
    return data_dir() / "facility_prediction_model_report.json"


def decision_category_volume_summary_path() -> Path:
    return data_dir() / "decision_category_volume_summary.csv"


def statistical_decision_policy_report_path() -> Path:
    return data_dir() / "statistical_decision_policy_report.json"


def active_facility_queue_path() -> Path:
    return data_dir() / "active_learning_facility_queue.csv"


def active_district_queue_path() -> Path:
    return data_dir() / "active_learning_district_queue.csv"


def geo_validation_candidates_path() -> Path:
    return data_dir() / "geo_validation_candidates.csv"


def geocoder_uncertainty_priors_path() -> Path:
    return data_dir() / "geocoder_uncertainty_priors.csv"


# --- Specialty -> service-signal column (from facility_health_cleaned) --------
# These are the boolean has_*_care_signal columns detected from claim text.
SPECIALTIES: dict[str, str | None] = {
    "All specialties": None,
    "Maternity / OB-GYN": "has_maternity_care_signal",
    "Emergency / Surgery": "has_emergency_care_signal",
    "Diagnostics / Imaging": "has_diagnostic_signal",
    "Chronic disease (NCD)": "has_ncd_care_signal",
}

# --- Map metrics -------------------------------------------------------------
# label -> (facility column, aggregation, higher_is_worse)
# higher_is_worse controls the color ramp direction (worse = red).
METRICS: dict[str, tuple[str, str, bool]] = {
    "Care-gap priority": ("medical_desert_priority_score", "mean", True),
    "Health need (NFHS)": ("health_need_score", "mean", True),
    "Supply passing checks (count)": ("trustworthy_supply_signal", "sum", False),
    "Facility count": ("unique_id", "count", False),
}

DEFAULT_METRIC = "Care-gap priority"
DEFAULT_H3_RESOLUTION = 4  # ~1770 km2 per cell; good for a national India view

# India initial view
INDIA_VIEW = dict(latitude=22.5, longitude=80.0, zoom=3.6)

# Carto basemaps (no token required). Voyager is richer/more polished than the
# flat Positron we started with; Dark Matter for a "command-center" look.
MAP_STYLES = {
    "Voyager": "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json",
    "Light (Positron)": "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
    "Dark Matter": "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
}
DEFAULT_MAP_STYLE = "Dark Matter"
MAP_STYLE = MAP_STYLES[DEFAULT_MAP_STYLE]  # back-compat default

# 3-stop sequential ramp (RGB): good -> mid -> bad. A yellow midpoint avoids the
# muddy brown you get interpolating green->red directly.
COLOR_GOOD = (46, 204, 193)   # luminous teal
COLOR_MID = (255, 190, 72)    # amber
COLOR_BAD = (255, 82, 82)     # red
HEX_ALPHA = 190
