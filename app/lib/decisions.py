"""Decision persistence + source-conflict resolution + human-feedback center.

This module covers the hackathon CORE requirement to *persist user actions*
(notes, overrides, shortlists, scenarios, review decisions) and two ambitious
ideas from the project docs:

  * tricky_fields.md "Ambitious Idea 3 — Conflict Resolution Interface"
    (competing values across sources; planner chooses a planning assumption).
  * Bayesian_stats_product_strategy.md §7 — the self-improving / hillclimbing
    loop, framed the enterprise-safe way: the system *proposes* validated
    improvements from real reviewer feedback, but a human approves before any
    "deployment". Nothing here auto-modifies the model or policy.

Persistence is plain `sqlite3` (standard library, no new dependencies) at
``output/data/planner_decisions.sqlite`` (derived from ``config.data_dir()``).
On a read-only filesystem (some Databricks Apps deployments) we degrade
gracefully to ``st.session_state`` and surface a caption explaining that
persistence is session-only.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

import json

from . import config, data, ui  # ui has stat_card, decision_banner, workflow_rail

# ---------------------------------------------------------------------------
# Persistence layer (sqlite3)
# ---------------------------------------------------------------------------

DB_FILENAME = "planner_decisions.sqlite"
DECISION_TYPES = ["note", "override", "verify", "reject", "follow_up"]

# Set to True the first time a write to the canonical DB fails; from then on the
# whole module falls back to session_state so the UI never crashes on read-only
# filesystems (a known Databricks Apps limitation — see module docstring).
_SESSION_ONLY = False


def db_path() -> Path:
    """Canonical SQLite path under the project's output/data dir."""
    return config.data_dir() / DB_FILENAME


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a connection that is safe for Streamlit reruns.

    ``check_same_thread=False`` because Streamlit may call across threads;
    a short ``timeout`` so concurrent reruns wait briefly rather than erroring.
    """
    target = Path(path) if path is not None else db_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target), check_same_thread=False, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn


_SCHEMA = """
CREATE TABLE IF NOT EXISTS facility_decisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    unique_id     TEXT,
    facility_name TEXT,
    decision_type TEXT,
    field_name    TEXT,
    old_value     TEXT,
    new_value     TEXT,
    note          TEXT,
    reviewer      TEXT,
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS shortlist (
    unique_id     TEXT PRIMARY KEY,
    facility_name TEXT,
    reason        TEXT,
    created_at    TEXT
);
CREATE TABLE IF NOT EXISTS scenario_assumptions (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    district   TEXT,
    key        TEXT,
    value      TEXT,
    created_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_decisions_uid ON facility_decisions(unique_id);
CREATE INDEX IF NOT EXISTS idx_scenario_district ON scenario_assumptions(district);
"""


def init_db(path: Optional[Path] = None) -> None:
    """Create tables if they do not exist. Idempotent / safe on every rerun."""
    conn = _connect(path)
    try:
        conn.executescript(_SCHEMA)
        conn.commit()
    finally:
        conn.close()


# ---- session-state fallback store -----------------------------------------

def _session_store() -> dict:
    if "_decisions_fallback" not in st.session_state:
        st.session_state["_decisions_fallback"] = {
            "facility_decisions": [],
            "shortlist": {},  # unique_id -> row dict
            "scenario_assumptions": [],
        }
    return st.session_state["_decisions_fallback"]


def _mark_session_only() -> None:
    global _SESSION_ONLY
    _SESSION_ONLY = True


def persistence_is_session_only() -> bool:
    return _SESSION_ONLY


# ---- public write/read API -------------------------------------------------

def save_decision(
    unique_id: str,
    facility_name: str = "",
    decision_type: str = "note",
    field_name: str = "",
    old_value: str = "",
    new_value: str = "",
    note: str = "",
    reviewer: str = "",
) -> None:
    """Persist one facility review decision (note|override|verify|reject|follow_up)."""
    row = dict(
        unique_id=str(unique_id),
        facility_name=str(facility_name or ""),
        decision_type=str(decision_type or "note"),
        field_name=str(field_name or ""),
        old_value="" if old_value is None else str(old_value),
        new_value="" if new_value is None else str(new_value),
        note=str(note or ""),
        reviewer=str(reviewer or ""),
        created_at=_now(),
    )
    if _SESSION_ONLY:
        _session_store()["facility_decisions"].append(row)
        return
    try:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO facility_decisions
                   (unique_id, facility_name, decision_type, field_name,
                    old_value, new_value, note, reviewer, created_at)
                   VALUES (:unique_id, :facility_name, :decision_type, :field_name,
                           :old_value, :new_value, :note, :reviewer, :created_at)""",
                row,
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        _mark_session_only()
        _session_store()["facility_decisions"].append(row)


def list_decisions(unique_id: Optional[str] = None) -> pd.DataFrame:
    """Return decision history, newest first; optionally filtered to one facility."""
    cols = ["id", "unique_id", "facility_name", "decision_type", "field_name",
            "old_value", "new_value", "note", "reviewer", "created_at"]
    if _SESSION_ONLY:
        rows = list(_session_store()["facility_decisions"])
        if unique_id is not None:
            rows = [r for r in rows if r.get("unique_id") == str(unique_id)]
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df:
                df[c] = ""
        return df[cols].iloc[::-1].reset_index(drop=True)
    try:
        conn = _connect()
        try:
            if unique_id is not None:
                df = pd.read_sql_query(
                    "SELECT * FROM facility_decisions WHERE unique_id = ? "
                    "ORDER BY id DESC",
                    conn, params=(str(unique_id),),
                )
            else:
                df = pd.read_sql_query(
                    "SELECT * FROM facility_decisions ORDER BY id DESC", conn
                )
        finally:
            conn.close()
        return df if not df.empty else pd.DataFrame(columns=cols)
    except (sqlite3.Error, OSError):
        _mark_session_only()
        return list_decisions(unique_id)


def add_to_shortlist(unique_id: str, facility_name: str = "", reason: str = "") -> None:
    """Add (or replace) a facility on the verification shortlist."""
    row = dict(
        unique_id=str(unique_id),
        facility_name=str(facility_name or ""),
        reason=str(reason or ""),
        created_at=_now(),
    )
    if _SESSION_ONLY:
        _session_store()["shortlist"][row["unique_id"]] = row
        return
    try:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO shortlist (unique_id, facility_name, reason, created_at)
                   VALUES (:unique_id, :facility_name, :reason, :created_at)
                   ON CONFLICT(unique_id) DO UPDATE SET
                       facility_name=excluded.facility_name,
                       reason=excluded.reason,
                       created_at=excluded.created_at""",
                row,
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        _mark_session_only()
        _session_store()["shortlist"][row["unique_id"]] = row


def list_shortlist() -> pd.DataFrame:
    cols = ["unique_id", "facility_name", "reason", "created_at"]
    if _SESSION_ONLY:
        rows = list(_session_store()["shortlist"].values())
        df = pd.DataFrame(rows)
        return df[cols] if not df.empty else pd.DataFrame(columns=cols)
    try:
        conn = _connect()
        try:
            df = pd.read_sql_query(
                "SELECT * FROM shortlist ORDER BY created_at DESC", conn
            )
        finally:
            conn.close()
        return df if not df.empty else pd.DataFrame(columns=cols)
    except (sqlite3.Error, OSError):
        _mark_session_only()
        return list_shortlist()


def remove_from_shortlist(unique_id: str) -> None:
    if _SESSION_ONLY:
        _session_store()["shortlist"].pop(str(unique_id), None)
        return
    try:
        conn = _connect()
        try:
            conn.execute("DELETE FROM shortlist WHERE unique_id = ?", (str(unique_id),))
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        _mark_session_only()
        _session_store()["shortlist"].pop(str(unique_id), None)


def save_scenario_assumption(district: str, key: str, value: str) -> None:
    """Persist a planning assumption tied to a district (or facility scope)."""
    row = dict(
        district=str(district or ""),
        key=str(key or ""),
        value="" if value is None else str(value),
        created_at=_now(),
    )
    if _SESSION_ONLY:
        _session_store()["scenario_assumptions"].append(row)
        return
    try:
        conn = _connect()
        try:
            conn.execute(
                """INSERT INTO scenario_assumptions (district, key, value, created_at)
                   VALUES (:district, :key, :value, :created_at)""",
                row,
            )
            conn.commit()
        finally:
            conn.close()
    except (sqlite3.Error, OSError):
        _mark_session_only()
        _session_store()["scenario_assumptions"].append(row)


def list_scenario_assumptions(district: Optional[str] = None) -> pd.DataFrame:
    cols = ["id", "district", "key", "value", "created_at"]
    if _SESSION_ONLY:
        rows = list(_session_store()["scenario_assumptions"])
        if district is not None:
            rows = [r for r in rows if r.get("district") == str(district)]
        df = pd.DataFrame(rows)
        if df.empty:
            return pd.DataFrame(columns=cols)
        for c in cols:
            if c not in df:
                df[c] = ""
        return df[cols].iloc[::-1].reset_index(drop=True)
    try:
        conn = _connect()
        try:
            if district is not None:
                df = pd.read_sql_query(
                    "SELECT * FROM scenario_assumptions WHERE district = ? "
                    "ORDER BY id DESC",
                    conn, params=(str(district),),
                )
            else:
                df = pd.read_sql_query(
                    "SELECT * FROM scenario_assumptions ORDER BY id DESC", conn
                )
        finally:
            conn.close()
        return df if not df.empty else pd.DataFrame(columns=cols)
    except (sqlite3.Error, OSError):
        _mark_session_only()
        return list_scenario_assumptions(district)


# ===========================================================================
# Unified, UI-callable persistence API
# ===========================================================================
#
# This is the single, documented surface the app.py / ui.py layer should call to
# persist user actions (notes, shortlists, review decisions, scenarios) and read
# them back. It unifies two durable backends so persistence survives restarts on
# the actual deployment target:
#
#   * DATA_BACKEND=warehouse (deployed Databricks App): each write is mirrored to
#     the governed Delta ``caregap_gold`` tables via the write-back functions in
#     ``data.py`` (``append_reviewer_feedback``/``append_recommendation_override``/
#     ``append_scenario_decision``). The local filesystem is ephemeral there, so
#     Delta is the source of truth. We STILL also write to SQLite/session as a
#     best-effort local cache so the current session reads back immediately.
#
#   * local / csv (dev): writes go to SQLite at ``output/data/planner_decisions
#     .sqlite`` (durable on the dev box). No warehouse needed.
#
# Every function here is best-effort and NEVER raises to the UI: a Delta or SQLite
# failure degrades to ``st.session_state`` and is reflected in the status returned
# by ``persistence_status()``. Reads MERGE the persisted store (Delta when in
# warehouse mode, else SQLite) with the in-session store so nothing a user just
# did disappears mid-session.


def _warehouse_mode() -> bool:
    """True when the deployment target is the SQL warehouse / governed Delta."""
    try:
        return data._is_warehouse()
    except Exception:
        return False


# Set True if a governed Delta write-back was attempted and reported failure, so
# the UI can honestly say persistence fell back to the local/session store.
_DELTA_WRITE_FAILED = False


def _mark_delta_failed() -> None:
    global _DELTA_WRITE_FAILED
    _DELTA_WRITE_FAILED = True


def persistence_status() -> dict:
    """Describe where persistence is currently landing (for a UI status caption).

    Returns a dict with:
      backend            : "warehouse" | "sqlite" | "session"
      durable            : bool — survives an app restart on the deployment target
      delta_write_failed : bool — a governed Delta insert was attempted and failed
      detail             : human-readable one-liner
    """
    if _warehouse_mode():
        durable = not _DELTA_WRITE_FAILED
        return {
            "backend": "warehouse",
            "durable": durable,
            "delta_write_failed": _DELTA_WRITE_FAILED,
            "detail": (
                "Decisions persist to governed Delta tables in "
                f"`{data.CAREGAP_CATALOG}.{data.CAREGAP_GOLD_SCHEMA}`."
                if durable else
                "Governed Delta write-back failed (table may not exist); decisions "
                "are session-only until it is created."
            ),
        }
    if _SESSION_ONLY:
        return {
            "backend": "session",
            "durable": False,
            "delta_write_failed": False,
            "detail": (
                "Filesystem is read-only; decisions live in session_state and reset "
                "on restart."
            ),
        }
    return {
        "backend": "sqlite",
        "durable": True,
        "delta_write_failed": False,
        "detail": f"Decisions persist locally to `{db_path()}` (SQLite).",
    }


def _reviewer(user: str = "") -> str:
    return str(user).strip() or _default_reviewer() or "app"


# ---- Notes -----------------------------------------------------------------

def save_note(geography_id: str, text: str, user: str = "", *,
              facility_name: str = "") -> dict:
    """Persist a free-text note for a geography/facility. Never raises.

    Local: stored as a ``note`` decision in SQLite. Warehouse: also mirrored to
    ``caregap_gold.reviewer_feedback`` (feedback_type=``note``). Returns
    ``persistence_status()`` so the caller can surface where it landed.
    """
    reviewer = _reviewer(user)
    # Always record locally (durable on dev; session cache on deployed app).
    save_decision(unique_id=geography_id, facility_name=facility_name,
                  decision_type="note", note=text, reviewer=reviewer)
    if _warehouse_mode():
        try:
            if not data.append_reviewer_feedback(
                geography_id=geography_id, feedback_type="note",
                notes=text, reviewer=reviewer, status="saved",
            ):
                _mark_delta_failed()
        except Exception:
            _mark_delta_failed()
    return persistence_status()


def list_notes(geography_id: Optional[str] = None) -> pd.DataFrame:
    """Return saved notes (newest first), optionally for one geography.

    Columns: geography_id, note, reviewer, created_at. Merges the governed Delta
    store (warehouse mode) with the local SQLite/session store. Never raises.
    """
    cols = ["geography_id", "note", "reviewer", "created_at"]
    frames: List[pd.DataFrame] = []

    local = list_decisions(geography_id)
    if not local.empty and "decision_type" in local:
        notes = local[local["decision_type"].astype(str) == "note"].copy()
        if not notes.empty:
            notes = notes.rename(columns={"unique_id": "geography_id"})
            frames.append(notes.reindex(columns=cols))

    if _warehouse_mode():
        try:
            wh = data.load_reviewer_feedback(geography_id)
            if wh is not None and not wh.empty:
                if "feedback_type" in wh:
                    wh = wh[wh["feedback_type"].astype(str) == "note"]
                if not wh.empty:
                    wh = wh.rename(columns={"notes": "note"})
                    frames.append(wh.reindex(columns=cols))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["geography_id", "note", "created_at"])
    if "created_at" in out:
        out = out.sort_values("created_at", ascending=False)
    return out.reset_index(drop=True)


# ---- Shortlist -------------------------------------------------------------

def is_shortlisted(geography_id: str) -> bool:
    """True if the geography is currently on the shortlist. Never raises."""
    try:
        sl = list_shortlist()
        if sl.empty or "unique_id" not in sl:
            return False
        return str(geography_id) in set(sl["unique_id"].astype(str))
    except Exception:
        return False


def toggle_shortlist(geography_id: str, label: str = "", *,
                     reason: str = "") -> dict:
    """Add the geography to the shortlist if absent, else remove it. Never raises.

    ``label`` is the human-friendly facility/geography name; ``reason`` is an
    optional verify-rationale. Warehouse mode mirrors the add/remove to
    ``caregap_gold.reviewer_feedback`` (feedback_type=``shortlist_add`` /
    ``shortlist_remove``). Returns ``persistence_status()``.
    """
    currently = is_shortlisted(geography_id)
    if currently:
        remove_from_shortlist(geography_id)
        action = "shortlist_remove"
    else:
        add_to_shortlist(unique_id=geography_id, facility_name=label, reason=reason)
        action = "shortlist_add"
    if _warehouse_mode():
        try:
            if not data.append_reviewer_feedback(
                geography_id=geography_id, feedback_type=action,
                notes=reason, payload=str(label), reviewer=_reviewer(),
                status="saved",
            ):
                _mark_delta_failed()
        except Exception:
            _mark_delta_failed()
    return persistence_status()


# ---- Review decisions ------------------------------------------------------

def save_review_decision(geography_id: str, decision: str, user: str = "", *,
                         facility_name: str = "", field_name: str = "",
                         old_value: str = "", new_value: str = "",
                         note: str = "") -> dict:
    """Persist a review decision (verify | reject | follow_up | override | note).

    Local: a row in the SQLite ``facility_decisions`` audit trail. Warehouse: also
    mirrored to ``caregap_gold`` — an override is routed to
    ``recommendation_overrides``; everything else to ``reviewer_feedback``. Never
    raises. Returns ``persistence_status()``.
    """
    decision = str(decision or "note")
    reviewer = _reviewer(user)
    save_decision(unique_id=geography_id, facility_name=facility_name,
                  decision_type=decision, field_name=field_name,
                  old_value=old_value, new_value=new_value, note=note,
                  reviewer=reviewer)
    if _warehouse_mode():
        try:
            if decision == "override":
                ok = data.append_recommendation_override(
                    geography_id=geography_id,
                    original_intervention=str(old_value),
                    chosen_intervention=str(new_value),
                    notes=note or field_name, reviewer=reviewer, status="saved",
                )
            else:
                ok = data.append_reviewer_feedback(
                    geography_id=geography_id, feedback_type=decision,
                    notes=note, payload=field_name, reviewer=reviewer,
                    status="saved",
                )
            if not ok:
                _mark_delta_failed()
        except Exception:
            _mark_delta_failed()
    return persistence_status()


# ---- Scenarios -------------------------------------------------------------

def save_scenario(geography_id: str, assumptions: dict, user: str = "", *,
                  note: str = "") -> dict:
    """Persist a saved what-if scenario (planning assumptions) for a geography.

    ``assumptions`` is a dict of levers / chosen planning values; it is serialized
    to JSON. Local: one row per key in the SQLite ``scenario_assumptions`` table.
    Warehouse: the whole dict is mirrored to ``caregap_gold.scenario_decisions``
    as a JSON payload. Never raises. Returns ``persistence_status()``.
    """
    assumptions = assumptions or {}
    try:
        payload = json.dumps(assumptions, default=str, sort_keys=True)
    except Exception:
        payload = str(assumptions)
    # Local: keep the per-key shape the existing assumptions table expects.
    for key, value in assumptions.items():
        save_scenario_assumption(district=geography_id, key=str(key), value=value)
    if not assumptions:
        save_scenario_assumption(district=geography_id, key="scenario", value=payload)
    if _warehouse_mode():
        try:
            if not data.append_scenario_decision(
                geography_id=geography_id, assumptions=payload,
                notes=note, reviewer=_reviewer(user), status="saved",
            ):
                _mark_delta_failed()
        except Exception:
            _mark_delta_failed()
    return persistence_status()


def list_scenarios(geography_id: Optional[str] = None) -> pd.DataFrame:
    """Return saved scenarios (newest first), optionally for one geography.

    Columns: geography_id, key, value, created_at. Merges the governed Delta store
    (warehouse mode, where each row's ``assumptions`` JSON is exploded back into
    key/value pairs) with the local SQLite/session store. Never raises.
    """
    cols = ["geography_id", "key", "value", "created_at"]
    frames: List[pd.DataFrame] = []

    local = list_scenario_assumptions(geography_id)
    if not local.empty:
        local = local.rename(columns={"district": "geography_id"})
        frames.append(local.reindex(columns=cols))

    if _warehouse_mode():
        try:
            wh = data.load_scenario_decisions(geography_id)
            if wh is not None and not wh.empty:
                exploded = []
                for _, r in wh.iterrows():
                    gid = r.get("geography_id", "")
                    created = r.get("created_at", "")
                    raw = r.get("assumptions", "")
                    parsed = None
                    try:
                        parsed = json.loads(raw) if isinstance(raw, str) else raw
                    except Exception:
                        parsed = None
                    if isinstance(parsed, dict) and parsed:
                        for k, v in parsed.items():
                            exploded.append({"geography_id": gid, "key": str(k),
                                             "value": v, "created_at": created})
                    else:
                        exploded.append({"geography_id": gid, "key": "scenario",
                                         "value": raw, "created_at": created})
                if exploded:
                    frames.append(pd.DataFrame(exploded).reindex(columns=cols))
        except Exception:
            pass

    if not frames:
        return pd.DataFrame(columns=cols)
    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset=["geography_id", "key", "value", "created_at"])
    if "created_at" in out:
        out = out.sort_values("created_at", ascending=False)
    return out.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Streamlit view
# ---------------------------------------------------------------------------

def _safe_init() -> None:
    """Initialise the DB once per session; flip to session-only on failure."""
    if _SESSION_ONLY:
        return
    try:
        init_db()
    except (sqlite3.Error, OSError):
        _mark_session_only()


def _fmt(value, digits: int = 0) -> str:
    try:
        num = float(value)
        if pd.isna(num):
            return "unknown"
        return f"{num:,.{digits}f}"
    except (TypeError, ValueError):
        text = str(value or "").strip()
        return text or "unknown"


def _facility_label(row: pd.Series) -> str:
    name = str(row.get("facility_name", "") or "Unnamed").strip() or "Unnamed"
    loc = " · ".join(
        x for x in [str(row.get("district_name", "") or "").strip(),
                    str(row.get("state_ut", "") or "").strip()] if x
    )
    return f"{name} — {loc}" if loc else name


def render_decisions(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    """Self-contained decision-persistence + conflict-resolution + feedback view."""
    _safe_init()

    ui.decision_banner(
        "Decision desk",
        "Persist reviewer notes, overrides, shortlists, and planning assumptions. "
        "Resolve source conflicts. Review system-proposed policy updates before approval.",
        tone="info",
    )
    ui.workflow_rail([
        ("1 · Review", "Open a facility, see its values"),
        ("2 · Resolve", "Pick a planning value across competing sources"),
        ("3 · Shortlist", "Queue facilities to verify"),
        ("4 · Persist", "Decisions saved to SQLite"),
        ("5 · Improve", "Approve proposed policy updates"),
    ])

    if _SESSION_ONLY:
        st.caption(
            "Persistence is session-only: the filesystem is read-only "
            "(common on Databricks Apps), so decisions live in session_state and "
            "reset when the app restarts. Locally they persist to "
            f"`{db_path()}`."
        )
    else:
        st.caption(f"Decisions persist to `{db_path()}` (SQLite).")

    if facilities is None or facilities.empty:
        st.info("No facilities loaded — nothing to review yet.")
        return

    try:
        section = st.segmented_control(
            "Section",
            ["Facility review & override", "Conflict resolution",
             "Shortlist", "Feedback / improvement center"],
            default="Facility review & override",
            label_visibility="collapsed",
        )
    except Exception:
        # Older Streamlit without segmented_control: fall back to radio.
        section = st.radio(
            "Section",
            ["Facility review & override", "Conflict resolution",
             "Shortlist", "Feedback / improvement center"],
            horizontal=True, label_visibility="collapsed",
        )
    if not section:
        section = "Facility review & override"

    if section == "Facility review & override":
        _render_review(facilities)
    elif section == "Conflict resolution":
        _render_conflict(facilities)
    elif section == "Shortlist":
        _render_shortlist(facilities)
    else:
        _render_feedback(facilities)


def _pick_facility(facilities: pd.DataFrame, key: str) -> Optional[pd.Series]:
    """Selectbox over (a capped sample of) facilities; returns the chosen row."""
    df = facilities.copy()
    if "unique_id" not in df:
        st.error("Facility table is missing `unique_id`; cannot persist decisions.")
        return None
    # Cap options for a responsive selectbox; keep flagged rows first.
    if "needs_human_review" in df:
        df = df.sort_values("needs_human_review", ascending=False)
    df = df.head(750).reset_index(drop=True)
    labels = {int(i): _facility_label(r) for i, r in df.iterrows()}
    idx = st.selectbox(
        "Facility",
        options=list(labels.keys()),
        format_func=lambda i: labels[i],
        key=key,
    )
    if idx is None:
        return None
    return df.iloc[int(idx)]


def _current_fields(row: pd.Series) -> pd.DataFrame:
    fields = [
        ("facility_name", "Facility name"),
        ("facilityTypeId", "Facility type"),
        ("capacity_display_value", "Capacity (display)"),
        ("capacity_status", "Capacity status"),
        ("doctor_count_display_value", "Doctor count (display)"),
        ("doctor_count_status", "Doctor count status"),
        ("geo_quality", "Geo quality"),
        ("officialPhone", "Phone"),
        ("officialWebsite", "Website"),
        ("trustworthy_supply_signal", "Passes supply checks"),
        ("needs_human_review", "Needs human review"),
    ]
    return pd.DataFrame(
        [{"Field": label, "Current value": str(row.get(col, "")) if row.get(col, "") != "" else "unknown"}
         for col, label in fields if col in row.index]
    )


def _render_review(facilities: pd.DataFrame) -> None:
    st.markdown('<div class="mdn-panel-h">Facility review &amp; override</div>',
                unsafe_allow_html=True)
    row = _pick_facility(facilities, key="review_pick")
    if row is None:
        return
    uid = str(row.get("unique_id"))
    name = str(row.get("facility_name", "") or "")

    left, right = st.columns([1.1, 1])
    with left:
        st.caption("Current field values (claims, not verified truth)")
        st.dataframe(_current_fields(row), hide_index=True, width="stretch", height=300)

    with right:
        with st.form(key=f"review_form_{uid}", clear_on_submit=True):
            st.caption("Record a decision")
            dtype = st.selectbox("Decision type", DECISION_TYPES, key=f"dt_{uid}")
            field_name = st.text_input("Field (optional, for override)", key=f"fn_{uid}")
            old_value = st.text_input("Old value (optional)", key=f"ov_{uid}")
            new_value = st.text_input("New value (optional)", key=f"nv_{uid}")
            note = st.text_area("Note / rationale", key=f"nt_{uid}", height=80)
            reviewer = st.text_input("Reviewer", value=_default_reviewer(),
                                     key=f"rv_{uid}")
            submitted = st.form_submit_button("Save decision")
        if submitted:
            if dtype == "override" and not field_name.strip():
                st.warning("An override should name the field being overridden.")
            else:
                save_decision(
                    unique_id=uid, facility_name=name, decision_type=dtype,
                    field_name=field_name, old_value=old_value, new_value=new_value,
                    note=note, reviewer=reviewer,
                )
                st.success(f"Saved {dtype} for {name or uid}.")

    st.markdown('<div class="mdn-panel-h">Decision history for this facility</div>',
                unsafe_allow_html=True)
    hist = list_decisions(uid)
    if hist.empty:
        st.caption("No decisions recorded yet for this facility.")
    else:
        show = hist.drop(columns=["id", "unique_id"], errors="ignore")
        st.dataframe(show, hide_index=True, width="stretch", height=240)


def _default_reviewer() -> str:
    # Pre-fill from the signed-in user when the host injects it; harmless locally.
    return os.environ.get("DATABRICKS_USER_EMAIL", "") or ""


def _competing_values(row: pd.Series) -> pd.DataFrame:
    """Frame capacity claim + model estimate interval as competing sources.

    The dataset is single-source per row, so we honestly label the interval as
    the *model's value range*, matching tricky_fields.md Ambitious Idea 3.
    """
    disp = pd.to_numeric(pd.Series([row.get("capacity_display_value")]), errors="coerce").iloc[0]
    low = pd.to_numeric(pd.Series([row.get("capacity_estimate_interval_low")]), errors="coerce").iloc[0]
    high = pd.to_numeric(pd.Series([row.get("capacity_estimate_interval_high")]), errors="coerce").iloc[0]
    rows = []
    if not pd.isna(disp):
        rows.append({"Source / basis": "Extracted claim (display value)",
                     "Capacity value": _fmt(disp),
                     "Confidence": str(row.get("capacity_confidence", "unknown") or "unknown")})
    if not pd.isna(low):
        rows.append({"Source / basis": "Model estimate — low (p10)",
                     "Capacity value": _fmt(low), "Confidence": "lower bound"})
    if not pd.isna(low) and not pd.isna(high):
        rows.append({"Source / basis": "Model estimate — median",
                     "Capacity value": _fmt((low + high) / 2.0), "Confidence": "central"})
    if not pd.isna(high):
        rows.append({"Source / basis": "Model estimate — high (p90)",
                     "Capacity value": _fmt(high), "Confidence": "upper bound"})
    return pd.DataFrame(rows), disp, low, high


def _render_conflict(facilities: pd.DataFrame) -> None:
    st.markdown('<div class="mdn-panel-h">Conflict resolution — choose a planning assumption</div>',
                unsafe_allow_html=True)
    st.caption(
        "When competing values exist, the app does not silently pick one. "
        "These are the capacity claim and the model's value range; choose the "
        "value you will plan with, or mark for verification."
    )
    row = _pick_facility(facilities, key="conflict_pick")
    if row is None:
        return
    uid = str(row.get("unique_id"))
    name = str(row.get("facility_name", "") or "")
    district = str(row.get("district_name", "") or "")

    table, disp, low, high = _competing_values(row)
    if table.empty:
        st.info("No capacity claim or estimate interval on this facility — "
                "nothing to resolve. Use the review tab to flag missing capacity.")
        return

    st.dataframe(table, hide_index=True, width="stretch")

    options = []
    if not pd.isna(disp):
        options.append(("Extracted claim", float(disp)))
    if not pd.isna(low):
        options.append(("Low (p10)", float(low)))
    if not pd.isna(low) and not pd.isna(high):
        options.append(("Median", float((low + high) / 2.0)))
    if not pd.isna(high):
        options.append(("High (p90)", float(high)))
    option_labels = [f"{lbl} = {_fmt(val)}" for lbl, val in options] + ["Custom value"]

    with st.form(key=f"conflict_form_{uid}", clear_on_submit=False):
        choice = st.radio("Planning assumption", option_labels, key=f"ch_{uid}")
        custom = st.number_input("Custom capacity value", min_value=0.0,
                                 value=0.0, step=1.0, key=f"cu_{uid}")
        status = st.selectbox("Mark as", ["verified", "needs_follow_up"], key=f"st_{uid}")
        note = st.text_area("Note (why this value?)", key=f"cn_{uid}", height=70)
        reviewer = st.text_input("Reviewer", value=_default_reviewer(), key=f"cr_{uid}")
        submitted = st.form_submit_button("Save planning assumption")

    if submitted:
        if choice == "Custom value":
            chosen_label, chosen_value = "custom", custom
        else:
            i = option_labels.index(choice)
            chosen_label, chosen_value = options[i][0], options[i][1]
        dtype = "verify" if status == "verified" else "follow_up"
        # One decision row (audit trail) + one scenario assumption (planning input).
        save_decision(
            unique_id=uid, facility_name=name, decision_type=dtype,
            field_name="capacity", old_value=_fmt(disp) if not pd.isna(disp) else "",
            new_value=f"{chosen_label}={_fmt(chosen_value)}", note=note, reviewer=reviewer,
        )
        save_scenario_assumption(
            district=district or name,
            key=f"capacity_assumption::{uid}",
            value=f"{chosen_label}={_fmt(chosen_value)} ({status})",
        )
        st.success(
            f"Saved planning assumption: capacity = {_fmt(chosen_value)} "
            f"({chosen_label}, {status})."
        )

    st.markdown('<div class="mdn-panel-h">Saved assumptions for this district</div>',
                unsafe_allow_html=True)
    asn = list_scenario_assumptions(district or name)
    if asn.empty:
        st.caption("No saved planning assumptions yet.")
    else:
        st.dataframe(asn.drop(columns=["id"], errors="ignore"),
                     hide_index=True, width="stretch", height=200)


def _render_shortlist(facilities: pd.DataFrame) -> None:
    st.markdown('<div class="mdn-panel-h">Verification shortlist</div>',
                unsafe_allow_html=True)
    row = _pick_facility(facilities, key="shortlist_pick")
    if row is not None:
        uid = str(row.get("unique_id"))
        name = str(row.get("facility_name", "") or "")
        c1, c2 = st.columns([2, 1])
        with c1:
            reason = st.text_input("Reason to verify", key=f"sl_reason_{uid}",
                                   placeholder="e.g. capacity claim looks implausible")
        with c2:
            st.caption("")
            if st.button("Add to shortlist", key=f"sl_add_{uid}"):
                add_to_shortlist(unique_id=uid, facility_name=name, reason=reason)
                st.success(f"Added {name or uid} to shortlist.")

    sl = list_shortlist()
    if sl.empty:
        st.caption("Shortlist is empty. Add facilities above.")
        return

    st.dataframe(sl, hide_index=True, width="stretch", height=240)
    try:
        csv = sl.to_csv(index=False).encode("utf-8")
        st.download_button("Download shortlist CSV", data=csv,
                           file_name="verification_shortlist.csv", mime="text/csv")
    except Exception:
        st.caption("CSV export unavailable.")

    remove_label = {f"{r.unique_id} · {r.facility_name}": r.unique_id
                    for r in sl.itertuples(index=False)}
    to_remove = st.selectbox("Remove from shortlist", ["—"] + list(remove_label.keys()),
                             key="sl_remove_pick")
    if to_remove != "—" and st.button("Remove", key="sl_remove_btn"):
        remove_from_shortlist(remove_label[to_remove])
        st.success("Removed. Re-run to refresh the table.")


# ---------------------------------------------------------------------------
# Feedback / improvement center (human-in-the-loop)
# ---------------------------------------------------------------------------

def _derive_proposals(decisions: pd.DataFrame) -> List[dict]:
    """Turn persisted reviewer decisions into PROPOSED policy updates.

    Mirrors Bayesian_stats_product_strategy.md §7: detect a repeated pattern in
    real feedback, propose a small validated change, await human approval. These
    are proposals only — nothing is auto-deployed.
    """
    proposals: List[dict] = []
    if decisions.empty:
        return proposals

    dt = decisions["decision_type"].astype(str)
    notes = decisions["note"].astype(str).str.lower()
    fields = decisions["field_name"].astype(str).str.lower()

    rejects = int((dt == "reject").sum())
    overrides = int((dt == "override").sum())
    follow_ups = int((dt == "follow_up").sum())

    geo_signals = int((notes.str.contains("geo|coordinate|location|outside india")
                       | fields.str.contains("geo")).sum())
    capacity_signals = int((fields.str.contains("capacity")
                            | notes.str.contains("capacity|bed")).sum())
    weak_evidence_signals = int(notes.str.contains(
        "telehealth|weak|no source|unverified|stale|no evidence").sum())

    if geo_signals >= 2:
        proposals.append({
            "policy": "Geo gate v1.1",
            "title": f"Tighten geo validity gate ({geo_signals} geo-flagged decisions)",
            "observed": f"Reviewers flagged geography in {geo_signals} decisions.",
            "proposed": "Lower the auto-pass threshold for coordinates far from the "
                        "PIN centroid and route more rows to external geocoding.",
            "validation": "Re-score the labeled review set; deploy only if reviewer "
                          "agreement does not regress.",
        })
    if capacity_signals >= 2:
        proposals.append({
            "policy": "Capacity trust v1.2",
            "title": f"Add capacity-claim penalty ({capacity_signals} capacity decisions)",
            "observed": f"{capacity_signals} decisions overrode or queried capacity.",
            "proposed": "Down-weight extracted capacity when it sits outside the model "
                        "p10–p90 interval and require a chosen planning assumption.",
            "validation": "Check that flagged-capacity rows now route to conflict "
                          "resolution before entering planning aggregates.",
        })
    if weak_evidence_signals >= 2:
        proposals.append({
            "policy": "Evidence weighting v1.3",
            "title": f"Penalize weak-evidence claims ({weak_evidence_signals} cases)",
            "observed": f"Reviewers cited weak/telehealth/unverified evidence in "
                        f"{weak_evidence_signals} notes.",
            "proposed": "Reduce trust contribution from claims lacking a source URL or "
                        "recent update; raise their needs-review priority.",
            "validation": "Confirm improved agreement with reviewer reject/follow-up "
                          "decisions on a holdout slice.",
        })
    if rejects >= 3:
        proposals.append({
            "policy": "Reject-rate watch v1.0",
            "title": f"Investigate elevated reject rate ({rejects} rejects)",
            "observed": f"{rejects} facilities were rejected by reviewers.",
            "proposed": "Cluster rejected facilities by source domain / facility type "
                        "to find a systematic extraction failure to fix upstream.",
            "validation": "Manual review of the cluster before any pipeline change.",
        })
    if overrides >= 3 and not any(p["policy"].startswith("Capacity") for p in proposals):
        proposals.append({
            "policy": "Override-pattern review v1.0",
            "title": f"Review frequent field overrides ({overrides} overrides)",
            "observed": f"{overrides} field overrides recorded across facilities.",
            "proposed": "Audit which fields are most overridden and propose a targeted "
                        "extraction or normalization fix for the top field.",
            "validation": "Compare pre/post override rate on the affected field.",
        })
    if follow_ups >= 3:
        proposals.append({
            "policy": "Follow-up queue v1.0",
            "title": f"Prioritize follow-up backlog ({follow_ups} follow-ups)",
            "observed": f"{follow_ups} decisions await follow-up.",
            "proposed": "Promote these facilities to the top of the verification queue.",
            "validation": "Track follow-up resolution rate over the next session.",
        })
    return proposals


def _render_feedback(facilities: pd.DataFrame) -> None:
    st.markdown('<div class="mdn-panel-h">Feedback &amp; improvement center (human-in-the-loop)</div>',
                unsafe_allow_html=True)
    st.caption(
        "The system reads back persisted reviewer decisions and proposes validated "
        "policy updates. Nothing here is auto-deployed — each proposal awaits human "
        "approval, matching the enterprise-safe self-improving loop."
    )

    decisions = list_decisions(None)
    n_dec = len(decisions)
    n_short = len(list_shortlist())
    n_asn = len(list_scenario_assumptions(None))

    c1, c2, c3 = st.columns(3)
    with c1:
        ui.stat_card("Persisted decisions", str(n_dec),
                     "notes / overrides / verify / reject / follow-up", tone="info")
    with c2:
        ui.stat_card("Shortlisted", str(n_short), "facilities queued to verify",
                     tone="verify")
    with c3:
        ui.stat_card("Planning assumptions", str(n_asn),
                     "chosen capacity / scenario values", tone="deploy")

    if decisions.empty:
        st.info(
            "No reviewer feedback yet. Record decisions in the other tabs; once a "
            "pattern repeats, the system will surface a proposed policy update here "
            "for your approval."
        )
        return

    proposals = _derive_proposals(decisions)
    if not proposals:
        st.info(
            "Feedback recorded, but no repeated pattern has crossed the proposal "
            "threshold yet. Proposals appear once a signal (e.g. geo, capacity, "
            "weak evidence, rejects) recurs."
        )
    else:
        st.markdown('<div class="mdn-panel-h">Proposed policy updates — awaiting approval</div>',
                    unsafe_allow_html=True)
        for i, p in enumerate(proposals):
            with st.container(border=True):
                st.markdown(f"**{p['title']}**  \n"
                            f"_{p['policy']} · awaiting approval_")
                st.markdown(f"- Observed: {p['observed']}")
                st.markdown(f"- Proposed: {p['proposed']}")
                st.markdown(f"- Validation: {p['validation']}")
                b1, b2, _ = st.columns([1, 1, 3])
                with b1:
                    if st.button("Approve", key=f"appr_{i}"):
                        save_decision(
                            unique_id=f"POLICY::{p['policy']}",
                            facility_name=p["policy"], decision_type="verify",
                            field_name="policy_proposal",
                            old_value="awaiting_approval", new_value="approved",
                            note=p["title"], reviewer=_default_reviewer(),
                        )
                        st.success(f"Approved {p['policy']} (logged; not auto-deployed).")
                with b2:
                    if st.button("Dismiss", key=f"dism_{i}"):
                        save_decision(
                            unique_id=f"POLICY::{p['policy']}",
                            facility_name=p["policy"], decision_type="reject",
                            field_name="policy_proposal",
                            old_value="awaiting_approval", new_value="dismissed",
                            note=p["title"], reviewer=_default_reviewer(),
                        )
                        st.info(f"Dismissed {p['policy']}.")

    st.markdown('<div class="mdn-panel-h">Decision log</div>', unsafe_allow_html=True)
    st.dataframe(decisions.drop(columns=["id"], errors="ignore"),
                 hide_index=True, width="stretch", height=260)
