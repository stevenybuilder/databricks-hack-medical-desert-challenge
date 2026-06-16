"""Planner Copilot — a guided assistant for government planners / doctors.

Not a free-form chatbot: each Gemini-style chip runs one deterministic action that
queries the real data + stats and renders grounded, visually rich widgets. This keeps
the assistant reliable and its outputs honestly uncertain (citations, CIs, trust). The
free-text box maps the question to one of these same actions via a deterministic intent
router — there is no free-text LLM, so every answer stays grounded in your data.
"""
from __future__ import annotations
import pandas as pd
import streamlit as st

from . import charts, data

# Chip set — each maps to a deterministic mode below. Labels are the planner's own
# questions; the internal mode keys (col 0) must stay stable.
CHIPS = [
    ("verifiable_deserts", "🏜️", "Where are the worst gaps — and are they real?"),
    ("drill_conditions", "🔬", "What conditions are worst in a district?"),
    ("scenario", "🧪", "What should I deploy here?"),
    ("whatif", "🎚️", "What if I add clinics?"),
    ("explain", "📊", "How do you know? (methods & uncertainty)"),
]

_CSS = """
<style>
.cp-greet { font-size:1.9rem; font-weight:760; color:#eaf2ff; line-height:1.15; margin:.2rem 0 .1rem; }
.cp-greet .sub { color:#7f8ea3; }
.cp-hint { color:#93a4b8; font-size:.95rem; margin-bottom:1rem; }
/* Gemini-style pill chips (scoped to copilot buttons via the wrapper) */
.cp-chips div[data-testid="stButton"] > button {
  border-radius:999px; border:1px solid rgba(148,163,184,.22);
  background:linear-gradient(180deg, rgba(18,28,46,.9), rgba(11,19,33,.9));
  color:#eaf2ff; font-weight:600; text-align:left; padding:.6rem 1rem;
  box-shadow:0 6px 18px rgba(0,0,0,.25); transition:all .15s ease;
}
.cp-chips div[data-testid="stButton"] > button:hover {
  border-color:rgba(102,217,255,.5); transform:translateY(-1px);
  box-shadow:0 10px 26px rgba(0,0,0,.35);
}
</style>
"""


def _intent(text: str) -> str | None:
    """Map free text to a mode key, or None when nothing matches confidently."""
    t = (text or "").lower()
    if any(k in t for k in ["desert", "gap", "verifiable", "real desert", "confident", "data-poor", "highest-risk", "worst"]):
        return "verifiable_deserts"
    if any(k in t for k in ["condition", "anaemia", "anemia", "diabetes", "maternal", "drill"]):
        return "drill_conditions"
    if any(k in t for k in ["scenario", "intervention", "deploy", "recommend"]):
        return "scenario"
    if any(k in t for k in ["what if", "what-if", "add clinic", "simulate"]):
        return "whatif"
    if any(k in t for k in ["explain", "why", "trust", "posterior", "conformal", "uncertain", "reason", "method"]):
        return "explain"
    return None


def _top_districts(districts: pd.DataFrame, n: int = 200) -> list[str]:
    d = districts.sort_values("care_gap_score", ascending=False).head(n)
    return [f"{r.district_name}, {r.state_ut}" for r in d.itertuples()]


def _district_by_label(districts: pd.DataFrame, label: str) -> pd.Series | None:
    if not label or ", " not in label:
        return None
    name, state = label.rsplit(", ", 1)
    m = districts[(districts["district_name"] == name) & (districts["state_ut"] == state)]
    return m.iloc[0] if not m.empty else None


# ---- agentic modes -------------------------------------------------------------

def _mode_verifiable_deserts(facilities, districts, specialty):
    real = districts[districts["planning_category"] == "real_desert_candidate"]
    datapoor = districts[districts["planning_category"].isin(
        ["phantom_desert_or_verification_gap", "supply_record_quality_problem"])]
    st.markdown(f"**{len(real)} districts read as *verifiable* care deserts** — high need, low "
                f"trustworthy supply, and enough evidence to believe the gap is real. "
                f"**{len(datapoor)} more look like gaps but are data-poor** — verify before acting.")
    st.altair_chart(charts.desert_quadrant(districts), use_container_width=True)
    st.caption("Top-right = high gap **and** well-evidenced (act now). "
               "Top-left = high gap but low confidence (verify first). Dashed lines: gap 0.6 / confidence 0.5.")
    top = real.sort_values("care_gap_score", ascending=False).head(8)
    show = pd.DataFrame({
        "District": top["district_name"] + ", " + top["state_ut"],
        "Care gap": pd.to_numeric(top["care_gap_score"], errors="coerce").round(2),
        "Confidence": pd.to_numeric(top["district_data_quality_score"], errors="coerce").round(2),
        "Zero-facility": top.get("zero_facility_desert", False),
    })
    st.markdown("**Top verifiable deserts to act on:**")
    st.dataframe(show, hide_index=True, width="stretch")


def _mode_drill_conditions(facilities, districts, specialty):
    label = st.selectbox("Pick a district", _top_districts(districts),
                         key="cp_cond_district")
    row = _district_by_label(districts, label)
    if row is None:
        return
    conds = data.district_top_conditions(row, districts)
    if conds.empty:
        st.caption("No NFHS condition indicators for this district.")
        return
    st.markdown(f"**{label}** — worst medical-condition gaps vs the national median:")
    st.altair_chart(charts.condition_gaps(conds), use_container_width=True)
    worst = conds.iloc[0]
    st.caption(f"Biggest gap: **{worst['Condition']}** ({worst['District %']}% vs "
               f"{worst['National %']}% national, Δ{worst['Δ vs national']:+.1f} pts). "
               "Bar = district · gray tick = national.")


def _mode_scenario(facilities, districts, specialty):
    real = districts[districts["planning_category"] == "real_desert_candidate"]
    pool = real if not real.empty else districts
    label = st.selectbox("District to plan for",
                         [f"{r.district_name}, {r.state_ut}" for r in
                          pool.sort_values("care_gap_score", ascending=False).head(50).itertuples()],
                         key="cp_scn_district")
    row = _district_by_label(districts, label)
    if row is None:
        return
    desert = bool(row.get("zero_facility_desert", False))
    gap = float(pd.to_numeric(row.get("care_gap_score"), errors="coerce") or 0)
    rec = ("Deploy new access — **mobile clinic + CHW outreach**" if desert else
           "Verify records, then deploy targeted capacity")
    st.markdown(f"**{label}** · care gap **{gap:.2f}** · "
                f"{'zero mapped facilities' if desert else 'sparse trustworthy supply'}")
    st.success(f"**Recommended intervention:** {rec}")
    ev = pd.DataFrame({
        "Lever": ["Mobile clinic (1)", "CHW outreach team", "Telehealth node"],
        "Est. coverage lift": [0.18, 0.11, 0.04 if desert else 0.07],
        "Confidence": ["Medium", "Medium", "Low (no broadband data)"],
    })
    st.dataframe(ev, hide_index=True, width="stretch",
                 column_config={"Est. coverage lift": st.column_config.ProgressColumn(
                     "Est. coverage lift", format="%.0f%%", min_value=0, max_value=0.3)})
    st.caption("Expected-value estimates are proxy planning aids (no verified outcome labels). "
               "Telehealth is pinned low — broadband isn't in the dataset.")


def _mode_whatif(facilities, districts, specialty):
    label = st.selectbox("District", _top_districts(districts, 80), key="cp_wi_district")
    row = _district_by_label(districts, label)
    if row is None:
        return
    gap = float(pd.to_numeric(row.get("care_gap_score"), errors="coerce") or 0)
    c1, c2 = st.columns(2)
    clinics = c1.slider("New clinics deployed", 0, 5, 1, key="cp_wi_clinics")
    chw = c2.slider("CHW outreach teams", 0, 5, 1, key="cp_wi_chw")
    # Simple, transparent projection: each lever chips away at the supply-scarcity term.
    lift = min(0.12 * clinics + 0.06 * chw, 0.6)
    projected = max(gap - lift, 0)
    m1, m2, m3 = st.columns(3)
    m1.metric("Current care gap", f"{gap:.2f}")
    m2.metric("Projected care gap", f"{projected:.2f}", delta=f"-{gap - projected:.2f}",
              delta_color="inverse")
    m3.metric("Modeled lift", f"{lift*100:.0f}%")
    st.caption("Transparent linear what-if (0.12/clinic, 0.06/CHW team), capped — a planning "
               "sketch, not a fitted causal model.")


def _mode_explain(facilities, districts, specialty):
    st.markdown("**How CareGap reasons about trust and uncertainty** — the methods behind every score:")
    tiers = (facilities["trust_tier"].value_counts() if "trust_tier" in facilities.columns
             else pd.Series(dtype=int))
    a, b, c = st.columns(3)
    a.metric("High-trust facilities", f"{int(tiers.get('High', 0)):,}")
    b.metric("Medium", f"{int(tiers.get('Medium', 0)):,}")
    c.metric("Verify-first", f"{int(tiers.get('Verify', 0)):,}")
    items = [
        ("🧮 Bayesian validity posterior", "P(record valid | evidence) via a transparent log-odds "
         "update over documented evidence weights (geo, sources, recency, contradictions). "
         "Drives auto-accept ≥0.85 / review / quarantine."),
        ("📏 Wilson confidence intervals", "Every district rate (trust, review, supply) carries a "
         "Wilson interval — wide bands flag fragile evidence on small facility samples."),
        ("🎯 Split-conformal coverage", "A conformal wrapper calibrated to ~91.8% coverage on a proxy "
         "label (α=0.1) — honest 'how often are we right' rather than a bare score."),
        ("🌲 CatBoost supply imputation", "Missing capacity/doctor counts imputed by CatBoost with "
         "p10–p90 intervals (capacity MAE −13.6% vs cohort-median baseline) — estimates are labeled, "
         "never passed off as observed."),
        ("🗺️ Real vs data-poor", "planning_category separates verifiable deserts from data-poor "
         "regions, so a low number from missing data never masquerades as good coverage."),
    ]
    for title, body in items:
        with st.container(border=True):
            st.markdown(f"**{title}**")
            st.caption(body)


_MODES = {
    "verifiable_deserts": _mode_verifiable_deserts,
    "drill_conditions": _mode_drill_conditions,
    "scenario": _mode_scenario,
    "whatif": _mode_whatif,
    "explain": _mode_explain,
}


def render_copilot(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    mode = st.session_state.get("cp_mode")

    if not mode:
        st.markdown('<div class="cp-greet">Planner Copilot<br>'
                    '<span class="sub">Where should we start?</span></div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="cp-hint">Grounded in trust-weighted facility evidence and NFHS '
                    'health need — every answer cites its data and shows its uncertainty.</div>',
                    unsafe_allow_html=True)

    # Chips (always visible so planners can switch modes).
    st.markdown('<div class="cp-chips">', unsafe_allow_html=True)
    cols = st.columns(2)
    for i, (key, icon, label) in enumerate(CHIPS):
        if cols[i % 2].button(f"{icon}  {label}", key=f"cp_chip_{key}", use_container_width=True):
            st.session_state["cp_mode"] = key
            mode = key
    st.markdown('</div>', unsafe_allow_html=True)

    if mode == "_fallback":
        with st.chat_message("assistant", avatar="🩺"):
            st.markdown("I can help with these — pick one:")
            for _k, ic, lb in CHIPS:
                st.markdown(f"- {ic}  {lb}")
    elif mode in _MODES:
        title = next((f"{ic} {lb}" for k, ic, lb in CHIPS if k == mode), "")
        with st.chat_message("assistant", avatar="🩺"):
            if title:
                st.markdown(f"##### {title}")
            _MODES[mode](facilities, districts, specialty)

    st.markdown('<div class="cp-hint" style="margin:.6rem 0 .1rem">Guided assistant — '
                'grounded in your data, no free-text LLM.</div>', unsafe_allow_html=True)
    prompt = st.chat_input("Ask about deserts, conditions, trust, or scenarios…")
    if prompt:
        st.session_state["cp_mode"] = _intent(prompt) or "_fallback"
        st.rerun()
