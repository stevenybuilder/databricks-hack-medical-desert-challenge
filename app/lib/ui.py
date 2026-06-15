"""Shared UI helpers: global CSS, header, and small components."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import config, data

_CSS = """
<style>
/* tighten the page + hide default chrome */
#MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden;}
.block-container {padding: 0.6rem 1.4rem 1rem 1.4rem; max-width: 100%;}

/* branded top bar */
.mdn-topbar {display:flex; align-items:center; gap:.7rem; padding:.5rem .2rem .2rem;}
.mdn-logo {width:30px;height:30px;border-radius:8px;background:#FF3621;color:#fff;
  display:flex;align-items:center;justify-content:center;font-size:16px;font-weight:700;}
.mdn-title {font-size:1.35rem;font-weight:750;color:#0f172a;line-height:1;}
.mdn-sub {font-size:.82rem;color:#64748b;margin-top:2px;}
.mdn-chip {margin-left:auto;font-size:.72rem;font-weight:600;color:#475569;
  background:#eef2f7;border:1px solid #e2e8f0;border-radius:999px;padding:.28rem .7rem;}

/* metric cards */
[data-testid="stMetric"] {background:#fff;border:1px solid #e8edf3;border-radius:12px;
  padding:.7rem .9rem;box-shadow:0 1px 2px rgba(15,23,42,.04);}
[data-testid="stMetricLabel"] p {font-size:.78rem;color:#64748b;font-weight:600;}
[data-testid="stMetricValue"] {font-size:1.5rem;font-weight:750;}

/* panel section headers */
.mdn-panel-h {font-size:.8rem;font-weight:700;letter-spacing:.04em;
  text-transform:uppercase;color:#94a3b8;margin:.4rem 0 .3rem;}

/* legend */
.mdn-legend-bar {height:10px;border-radius:6px;
  background:linear-gradient(90deg,#26a69a 0%,#ffca3a 50%,#e53935 100%);}
.mdn-legend-row {display:flex;justify-content:space-between;font-size:.72rem;color:#64748b;margin-top:3px;}

/* compact selectboxes */
div[data-baseweb="select"] > div {border-radius:10px;}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def header() -> None:
    st.markdown(
        f"""
        <div class="mdn-topbar">
          <div class="mdn-logo">◆</div>
          <div>
            <div class="mdn-title">{config.APP_TITLE}</div>
            <div class="mdn-sub">{config.APP_TAGLINE}</div>
          </div>
          <div class="mdn-chip">Databricks Apps &amp; Agents for Good · Medical Desert Planner</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


_BADGE = {
    "Passed checks": ("#0f766e", "#ccfbf1"),
    "Needs review": ("#92400e", "#fef3c7"),
    "Contradicted / geo-invalid": ("#991b1b", "#fee2e2"),
    "Unknown": ("#475569", "#e2e8f0"),
}


def facility_card(f: dict) -> None:
    """Render a clicked facility's detail with status badge and cited source."""
    status = f.get("status", "Unknown")
    fg, bg = _BADGE.get(status, _BADGE["Unknown"])
    name = f.get("facility_name", "Unnamed facility")
    loc = " · ".join(x for x in [f.get("city"), f.get("district"), f.get("state")]
                     if x and x != "—")
    url = (f.get("source_url") or "").strip()
    evidence = (f.get("evidence") or "").strip()

    st.markdown(
        f"""
        <div style="border:1px solid #e8edf3;border-radius:12px;padding:.9rem 1rem;
             margin-top:.6rem;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.06)">
          <div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">
            <span style="font-size:1.05rem;font-weight:700;color:#0f172a">{name}</span>
            <span style="background:{bg};color:{fg};font-size:.72rem;font-weight:700;
                  padding:.2rem .6rem;border-radius:999px">{status}</span>
          </div>
          <div style="font-size:.83rem;color:#64748b;margin-top:.25rem">
            {f.get('facility_type','—')} · {loc or '—'} · geo: {f.get('geo_quality','—')}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if evidence:
        st.markdown(f"**Claimed (unverified):** {evidence}…")
    if url:
        st.markdown(f"**Source:** [{url[:80]}]({url})")
    else:
        st.caption("No source URL on record for this facility.")
    if status != "Passed checks":
        st.warning("This facility is flagged — verify the claim against the source "
                   "before relying on it.", icon="⚠️")


def _num(v, default=float("nan")):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def region_detail(row: pd.Series, specialty: str) -> None:
    """Full district detail: recommendation, patient conditions, supply, evidence."""
    cat = str(row.get("planning_category", "mixed_or_monitor"))
    chip, rec = data.PLANNING.get(cat, data.PLANNING["mixed_or_monitor"])
    name = f"{row.get('district_name','—')}, {row.get('state_ut','—')}"

    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-top:.3rem">
        <span style="font-size:1.15rem;font-weight:750;color:#0f172a">{name}</span>
        <span style="background:#eef2f7;border:1px solid #e2e8f0;border-radius:999px;
        padding:.22rem .7rem;font-size:.78rem;font-weight:700;color:#334155">{chip}</span>
        </div>""", unsafe_allow_html=True)
    st.info(rec, icon="🧭")

    obs = _num(row.get("observed_facility_rows"))
    trust = _num(row.get("trustworthy_supply_rows"))
    rate = _num(row.get("trustworthy_supply_rate"))
    c1, c2, c3 = st.columns(3)
    c1.metric("Health need", f"{_num(row.get('health_need_score')):.2f}")
    c2.metric("Trustworthy supply",
              "—" if pd.isna(rate) else f"{rate*100:.0f}%",
              help=f"{0 if pd.isna(trust) else int(trust)} of "
                   f"{0 if pd.isna(obs) else int(obs)} observed facilities passed checks")
    c3.metric("Data uncertainty", str(row.get("district_uncertainty_level", "—")).title())

    # ---- patient-condition profile (what you'll treat) ----
    _, cond_cols = data.SPECIALTY_DISTRICT.get(specialty, (None, []))
    rows = [{"Condition": data.COND_LABELS.get(c, c), "Percent": _num(row.get(c))}
            for c in cond_cols if not pd.isna(_num(row.get(c)))]
    if rows:
        st.markdown('<div class="mdn-panel-h">Patient conditions here (NFHS district context)</div>',
                    unsafe_allow_html=True)
        prof = pd.DataFrame(rows)
        st.dataframe(
            prof, hide_index=True, width="stretch",
            column_config={"Percent": st.column_config.ProgressColumn(
                "Percent", format="%.1f%%", min_value=0, max_value=100)})
        st.caption("Context, not a facility fact. For access measures (births, screening) "
                   "low = worse; for burden (anaemia, BP, sugar) high = worse.")

    # ---- evidence / citations ----
    st.markdown('<div class="mdn-panel-h">Evidence (sample facilities & sources)</div>',
                unsafe_allow_html=True)
    names = str(row.get("sample_facility_names", "") or "").strip()
    claim = str(row.get("sample_claim_evidence", "") or "").strip()
    url = data._first_url(row.get("sample_source_urls", ""))
    if names:
        st.markdown(f"**Facilities:** {names[:300]}")
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:300]}…")
    if url:
        st.markdown(f"**Source:** [{url[:80]}]({url})")
    if not (names or claim or url):
        st.caption("No sample evidence recorded for this district.")


def verification_detail(row: pd.Series) -> None:
    """Inspect one facility candidate from the external validation queue."""
    name = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    concern = str(row.get("primary_concern", "—") or "—")
    seed = str(row.get("label_seed", "—") or "—")
    channel = str(row.get("verification_channel", "—") or "—")
    loc = " · ".join(
        x for x in [
            row.get("address_city"),
            row.get("district_name"),
            row.get("state_ut"),
        ]
        if isinstance(x, str) and x.strip()
    )

    st.markdown('<div class="mdn-panel-h">Selected verification candidate</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="border:1px solid #e8edf3;border-radius:12px;padding:.9rem 1rem;
             margin-top:.2rem;background:#fff;box-shadow:0 1px 3px rgba(15,23,42,.06)">
          <div style="font-size:1rem;font-weight:750;color:#0f172a">{name}</div>
          <div style="font-size:.83rem;color:#64748b;margin-top:.2rem">{loc or '—'}</div>
          <div style="display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.55rem">
            <span style="background:#eef2f7;border:1px solid #e2e8f0;border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#334155">{seed}</span>
            <span style="background:#fff7ed;border:1px solid #fed7aa;border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#9a3412">{concern}</span>
            <span style="background:#ecfdf5;border:1px solid #bbf7d0;border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#166534">{channel}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Readiness", f"{_num(row.get('data_readiness_score')):.2f}")
    c2.metric("Join confidence", f"{_num(row.get('join_confidence')):.2f}")
    c3.metric("Review priority", f"{_num(row.get('review_priority')):.1f}")

    contacts = []
    for label, value in [
        ("Phone", row.get("officialPhone")),
        ("Email", row.get("email")),
        ("Website", row.get("officialWebsite")),
        ("Source", row.get("first_source_url")),
    ]:
        value = str(value or "").strip()
        if value:
            contacts.append({"Field": label, "Value": value})
    if contacts:
        st.dataframe(pd.DataFrame(contacts), hide_index=True, width="stretch")
    else:
        st.caption("No direct contact or source field on this candidate.")

    claim = str(row.get("claim_text", "") or "").strip()
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:420]}…")

    st.caption("Seed labels are bootstrapping labels for a golden set. A Tier A match or "
               "manual call/email outcome should replace the seed before model calibration.")


def legend(low_label: str, high_label: str, higher_is_worse: bool) -> None:
    left, right = (low_label, high_label)
    st.markdown('<div class="mdn-legend-bar"></div>', unsafe_allow_html=True)
    # ramp is green(low)->red(high) when higher_is_worse; flip labels otherwise
    a, b = (left, right) if higher_is_worse else (right, left)
    st.markdown(
        f'<div class="mdn-legend-row"><span>{a}</span><span>{b}</span></div>',
        unsafe_allow_html=True,
    )
