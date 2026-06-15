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

    st.markdown('<div class="mdn-panel-h">Why this badge?</div>', unsafe_allow_html=True)
    explain_rows = [
        {
            "Signal": "Readiness / semantic quality",
            "Value": f"{_fmt(f.get('data_readiness_score'))} / {_fmt(f.get('semantic_data_quality_score'))}",
            "Interpretation": "Automated evidence quality from joins, geography, source URLs, contact evidence, and semantic missingness.",
        },
        {
            "Signal": "Join confidence",
            "Value": f"{_fmt(f.get('join_confidence'))} · {f.get('join_strategy', 'unknown')}",
            "Interpretation": f.get("join_uncertainty_reason") or "Facility-to-district context depends on this join.",
        },
        {
            "Signal": "Geo quality",
            "Value": f"{f.get('geo_quality', 'unknown')} · {_fmt(f.get('geo_distance_km_to_pincode_centroid'), 1)} km from PIN centroid",
            "Interpretation": "External geocoding should reduce uncertainty only when it agrees with PIN/district/state.",
        },
        {
            "Signal": "Estimated capacity",
            "Value": f"{_fmt(f.get('capacity_display_value'), 0)} ({_fmt_interval(f.get('capacity_estimate_interval_low'), f.get('capacity_estimate_interval_high'), 0)})",
            "Interpretation": f"{f.get('capacity_confidence', 'unknown')} confidence; estimated={bool(f.get('capacity_is_estimated', False))}.",
        },
        {
            "Signal": "Estimated doctors",
            "Value": f"{_fmt(f.get('doctor_count_display_value'), 0)} ({_fmt_interval(f.get('doctor_count_estimate_interval_low'), f.get('doctor_count_estimate_interval_high'), 0)})",
            "Interpretation": f"{f.get('doctor_count_confidence', 'unknown')} confidence; estimated={bool(f.get('doctor_count_is_estimated', False))}.",
        },
    ]
    st.dataframe(pd.DataFrame(explain_rows), hide_index=True, width="stretch", height=230)
    if status != "Passed checks":
        st.warning("This facility is flagged — verify the claim against the source "
                   "before relying on it.", icon="⚠️")


def _num(v, default=float("nan")):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt(v, digits: int = 2) -> str:
    value = _num(v)
    return "—" if pd.isna(value) else f"{value:.{digits}f}"


def _fmt_interval(low, high, digits: int = 1) -> str:
    lo = _num(low)
    hi = _num(high)
    if pd.isna(lo) or pd.isna(hi):
        return "unknown"
    return f"{lo:.{digits}f} to {hi:.{digits}f}"


def _fmt_int(v) -> str:
    value = _num(v)
    return "—" if pd.isna(value) else f"{int(value):,}"


def reason_chips(labels: list[str]) -> None:
    if not labels:
        st.caption("No reason codes recorded.")
        return
    chips = "".join(
        f"""<span style="display:inline-block;background:#f8fafc;border:1px solid #dbe5ef;
        border-radius:999px;padding:.18rem .55rem;margin:.12rem;font-size:.75rem;
        font-weight:650;color:#334155">{label}</span>"""
        for label in labels
    )
    st.markdown(chips, unsafe_allow_html=True)


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

    st.markdown('<div class="mdn-panel-h">Why this recommendation?</div>',
                unsafe_allow_html=True)
    explanation, reasons = data.district_explanation(row, specialty)
    st.dataframe(explanation, hide_index=True, width="stretch", height=285)
    if not reasons.empty:
        reason_chips(reasons["Reason"].tolist())

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


def active_facility_detail(row: pd.Series) -> None:
    """Explain one row from active_learning_facility_queue.csv."""
    st.markdown('<div class="mdn-panel-h">Why this facility is fragile</div>',
                unsafe_allow_html=True)
    title = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    subtitle = " · ".join(
        item for item in [
            str(row.get("facilityTypeId", "") or "").strip(),
            str(row.get("district_name", "") or "").strip(),
            str(row.get("state_ut", "") or "").strip(),
        ]
        if item
    )
    st.markdown(f"**{title}**")
    if subtitle:
        st.caption(subtitle)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active score", _fmt(row.get("active_uncertainty_score")))
    m2.metric("Proxy trust", _fmt(row.get("proxy_trust_score")))
    m3.metric("Geo uncertainty", _fmt(row.get("external_geo_uncertainty_score")))
    m4.metric("Decision leverage", _fmt(row.get("decision_leverage_score")))

    st.dataframe(data.facility_explanation(row), hide_index=True, width="stretch", height=290)
    reason_chips(data.reason_labels(row.get("active_learning_reasons")))

    source = data._first_url(row.get("source_urls", ""))
    if source:
        st.markdown(f"**Source:** [{source[:90]}]({source})")
    claim = str(row.get("claim_text", "") or "").strip()
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:520]}…")


def active_district_detail(row: pd.Series, specialty: str) -> None:
    """Explain one row from active_learning_district_queue.csv."""
    st.markdown('<div class="mdn-panel-h">Why this district is fragile</div>',
                unsafe_allow_html=True)
    title = f"{row.get('district_name', '—')}, {row.get('state_ut', '—')}"
    st.markdown(f"**{title}**")
    chip, rec = data.PLANNING.get(str(row.get("planning_category", "")), data.PLANNING["mixed_or_monitor"])
    st.info(f"{chip}: {rec}", icon="🧭")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active score", _fmt(row.get("active_uncertainty_score")))
    m2.metric("Aggregate CI width", _fmt(row.get("aggregate_ci_width")))
    m3.metric("Observed rows", _fmt_int(row.get("observed_facility_rows")))
    m4.metric("Sample uncertainty", _fmt(row.get("sample_size_uncertainty_score")))

    display = pd.DataFrame(
        [
            {
                "Signal": "Need/recommendation",
                "Value": f"need {_fmt(row.get('health_need_score'))}; care gap {_fmt(row.get('care_gap_score'))}; trust gap {_fmt(row.get('trust_gap_score'))}",
                "Interpretation": "High values mean the district need is strong and supply evidence is weak.",
            },
            {
                "Signal": "Needs-review rate",
                "Value": f"{_fmt_interval(row.get('needs_human_review_rate_ci_low'), row.get('needs_human_review_rate_ci_high'))}",
                "Interpretation": "Wilson interval for rows needing uncertainty review.",
            },
            {
                "Signal": "Critical supply-gap rate",
                "Value": f"{_fmt_interval(row.get('critical_supply_gap_rate_ci_low'), row.get('critical_supply_gap_rate_ci_high'))}",
                "Interpretation": "Wilson interval for missing/estimated critical operational evidence.",
            },
            {
                "Signal": "Trustworthy supply rate",
                "Value": f"{_fmt_interval(row.get('trustworthy_supply_rate_ci_low'), row.get('trustworthy_supply_rate_ci_high'))}",
                "Interpretation": "Wilson interval for observed rows that passed automated checks.",
            },
        ]
    )
    st.dataframe(display, hide_index=True, width="stretch", height=235)
    reason_chips(data.reason_labels(row.get("active_learning_reasons")))

    claim = str(row.get("sample_claim_evidence", "") or "").strip()
    source = data._first_url(row.get("sample_source_urls", ""))
    if claim:
        st.markdown(f"**Sample evidence:** {claim[:460]}…")
    if source:
        st.markdown(f"**Source:** [{source[:90]}]({source})")


def geo_candidate_detail(row: pd.Series) -> None:
    """Explain one generated geocoding candidate."""
    st.markdown('<div class="mdn-panel-h">Geo source-agreement explanation</div>',
                unsafe_allow_html=True)
    title = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    st.markdown(f"**{title}**")
    st.caption(str(row.get("raw_india_address", "") or row.get("geocoder_query", "")))

    m1, m2, m3 = st.columns(3)
    m1.metric("External priority", _fmt(row.get("external_validation_priority_score")))
    m2.metric("Geo review score", _fmt(row.get("geo_review_score"), 1))
    m3.metric("PIN distance km", _fmt(row.get("geo_distance_km_to_pincode_centroid"), 1))

    checks, reasons = data.geo_candidate_explanation(row)
    st.dataframe(checks, hide_index=True, width="stretch", height=255)
    if not reasons.empty:
        reason_chips(reasons["Reason code"].tolist())

    sources = data._json_list(row.get("external_evidence_sources_to_check"))
    if sources:
        st.markdown("**External evidence to check:** " + " · ".join(sources))
    query = str(row.get("geocoder_query", "") or "").strip()
    if query:
        st.code(query, language="text")


def legend(low_label: str, high_label: str, higher_is_worse: bool) -> None:
    left, right = (low_label, high_label)
    st.markdown('<div class="mdn-legend-bar"></div>', unsafe_allow_html=True)
    # ramp is green(low)->red(high) when higher_is_worse; flip labels otherwise
    a, b = (left, right) if higher_is_worse else (right, left)
    st.markdown(
        f'<div class="mdn-legend-row"><span>{a}</span><span>{b}</span></div>',
        unsafe_allow_html=True,
    )
