"""Shared helpers and constants for the CareGap tabs.

This is the single source the per-tab modules (`tab_map`, `tab_gaps`) and the
app entry import from. It holds the numeric formatters, the planning-category
action vocabulary (label/tone/reason), the leaderboard ranker, and the small
pydeck/dataframe selection helpers. Keep these pure and view-agnostic so any tab
can reuse them without re-importing the app entry module.
"""
from __future__ import annotations

import pandas as pd

from . import data


# --- pydeck selection helpers ------------------------------------------------

def _picked_facility(state):
    """Pull the single clicked facility object out of a pydeck selection state."""
    try:
        objs = state["selection"]["objects"]
        fac = objs.get("facilities")
        return fac[0] if fac else None
    except (TypeError, KeyError, AttributeError):
        return None


def _picked_district(state):
    """Pull the single clicked district-desert hex out of a pydeck selection state."""
    try:
        objs = state["selection"]["objects"]
        d = objs.get("deserts")
        return d[0] if d else None
    except (TypeError, KeyError, AttributeError):
        return None


def _district_row(districts: pd.DataFrame, picked) -> pd.Series | None:
    """Match a clicked desert hex back to its full district row for the causal card."""
    if picked is None:
        return None
    name, state = picked.get("district_name"), picked.get("state_ut")
    m = districts[(districts["district_name"] == name) & (districts["state_ut"] == state)]
    return m.iloc[0] if not m.empty else None


# --- Planning-category action vocabulary -------------------------------------

ACTION_LABELS = {
    "real_desert_candidate": "Deploy",
    "phantom_desert_or_verification_gap": "Verify first",
    "supply_record_quality_problem": "Fix records",
    "referral_or_capacity_candidate": "Refer",
    "mixed_or_monitor": "Monitor",
}

ACTION_FILTERS = {
    "All": None,
    "Deploy": {"real_desert_candidate"},
    "Verify first": {"phantom_desert_or_verification_gap"},
    "Fix records": {"supply_record_quality_problem"},
    "Refer": {"referral_or_capacity_candidate"},
    "Monitor": {"mixed_or_monitor"},
}

ACTION_TONES = {
    "real_desert_candidate": "deploy",
    "phantom_desert_or_verification_gap": "verify",
    "supply_record_quality_problem": "danger",
    "referral_or_capacity_candidate": "info",
    "mixed_or_monitor": "neutral",
}

ACTION_REASON = {
    "real_desert_candidate": "High need and low trustworthy supply",
    "phantom_desert_or_verification_gap": "Decision depends on fragile evidence",
    "supply_record_quality_problem": "Supply likely exists, but records are weak",
    "referral_or_capacity_candidate": "Trustworthy capacity is already visible",
    "mixed_or_monitor": "Mixed signal; track but do not overcommit",
}


# --- Numeric formatters ------------------------------------------------------

def _num(value, default=float("nan")) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_num(value, digits: int = 2) -> str:
    value = _num(value)
    return "unknown" if pd.isna(value) else f"{value:.{digits}f}"


def _fmt_pct(value, digits: int = 0) -> str:
    value = _num(value)
    return "unknown" if pd.isna(value) else f"{value * 100:.{digits}f}%"


def _fmt_int(value) -> str:
    value = _num(value)
    return "unknown" if pd.isna(value) else f"{int(value):,}"


def _fmt_km(value, digits: int = 0) -> str:
    value = _num(value)
    return "unknown" if pd.isna(value) else f"{value:,.{digits}f} km"


def _action_label(category) -> str:
    return ACTION_LABELS.get(str(category), "Monitor")


def _action_tone(category) -> str:
    return ACTION_TONES.get(str(category), "neutral")


def _ranked_districts(districts: pd.DataFrame, specialty: str) -> tuple[pd.DataFrame, str]:
    ranked, gap_label = data.leaderboard(districts, specialty, top_n=len(districts))
    ranked = ranked.copy()
    ranked.insert(0, "Rank", range(1, len(ranked) + 1))
    ranked["Action"] = ranked["planning_category"].map(_action_label).fillna("Monitor")
    ranked["Decision logic"] = ranked["planning_category"].map(ACTION_REASON).fillna(ACTION_REASON["mixed_or_monitor"])
    return ranked, gap_label


def _selected_or_first(event, frame: pd.DataFrame) -> pd.Series | None:
    if frame.empty:
        return None
    selection = event.selection.rows if event and event.selection else []
    return frame.iloc[selection[0]] if selection else frame.iloc[0]
