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

from . import charts, data, interventions, simulator, ui

try:  # persistence is best-effort and never raises to the UI
    from . import decisions
except Exception:  # pragma: no cover - keeps copilot importable headless
    decisions = None  # type: ignore

# Chip set — each maps to a deterministic mode below. Labels are the planner's own
# questions; the internal mode keys (col 0) must stay stable.
CHIPS = [
    ("verifiable_deserts", "1", "Find deployment districts"),
    ("drill_conditions", "2", "Choose doctor specialty"),
    ("scenario", "3", "Build deployment plan"),
    ("whatif", "4", "Test clinic scenario"),
    ("explain", "?", "Explain evidence"),
]

_CONDITION_HELP = {
    "Institutional births": "Low facility delivery suggests gaps in obstetric access, transport, or staffed delivery rooms.",
    "Skilled birth attendance": "Low skilled attendance points to nurse, midwife, or referral gaps.",
    "C-section deliveries": "Low access can signal missing emergency obstetric surgery; extreme high rates need overuse review.",
    "Women 15-49 anaemic": "High anaemia raises maternal and surgical risk; prioritize maternal/primary-care teams.",
    "Women high BP": "High blood pressure burden supports recurring NCD screening and follow-up clinics.",
    "Men high BP": "High blood pressure burden supports recurring NCD screening and follow-up clinics.",
    "Women high blood sugar": "High blood sugar burden points to diabetes diagnostics and continuity of medicines.",
    "Men high blood sugar": "High blood sugar burden points to diabetes diagnostics and continuity of medicines.",
    "Cervical screening": "Low screening suggests women's health outreach and referral pathways.",
    "Breast exam": "Low exam coverage suggests women's health outreach and referral pathways.",
    "Oral cancer exam": "Low exam coverage suggests oral/dental screening outreach.",
    "Health insurance coverage": "Low coverage means referrals may fail unless planners include enrollment support.",
}

# Copilot styling consumes the SHARED design tokens (defined in ui.inject_css's
# :root, injected first in app entry) so the Copilot matches the rest of the app
# — same font, same text/muted/accent colors. See DESIGN_SYSTEM.md.
_CSS = """
<style>
/* Hero greeting: confident display type with calm, airy spacing above the chips. */
.cp-greet { font-family: var(--mdn-font); font-size: var(--fs-display); font-weight:760;
            color: var(--text); line-height:1.15; letter-spacing:-.015em;
            margin:.5rem 0 .25rem; }
.cp-greet .sub { color: var(--muted); }
.cp-hint { color: var(--muted); font-size: var(--fs-body); line-height:1.45;
           margin-bottom:1.1rem; }
/* Gemini-style pill chips — frosted, rounded-full, with a clear hover lift.
   Scoped to copilot chip buttons via the .cp-chips wrapper. */
.cp-chips { margin-bottom:.4rem; }
.cp-chips div[data-testid="stButton"] > button {
  border-radius: var(--radius-pill); border:1px solid var(--glass-border);
  background:linear-gradient(180deg, rgba(20,28,44,.82), rgba(13,20,34,.74));
  color: var(--text); font-family: var(--mdn-font); font-weight:600; text-align:left;
  padding:.7rem 1.15rem; min-height:48px; box-shadow: var(--mdn-elev-1);
  -webkit-backdrop-filter: var(--glass-blur); backdrop-filter: var(--glass-blur);
  transition:all .15s ease;
}
.cp-chips div[data-testid="stButton"] > button:hover {
  border-color: var(--info); transform:translateY(-1px);
  box-shadow: var(--mdn-elev-2); color:#fff;
}
/* Inline Save plan / Shortlist action row — pills already global; keep it tight
   and airy under the grounded answer. */
.cp-actions { margin-top:.35rem; }
/* Methodology method-cards (explain mode): frosted glass instead of the plain
   bordered container, so they read native to the re-skinned Copilot. */
.cp-explain div[data-testid="stVerticalBlockBorderWrapper"]:has(.cp-method-marker) {
  background: var(--glass-bg-soft);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur); backdrop-filter: var(--glass-blur);
}
</style>
"""


def _guide_steps() -> None:
    steps = [
        ("Start", "Pick a guided question."),
        ("Select", "Choose the district or scenario."),
        ("Verify", "Review evidence and uncertainty."),
        ("Save", "Shortlist or save the plan."),
    ]
    body = "".join(
        '<div class="mdn-guide-step">'
        f'<b>{title}</b><span>{text}</span></div>'
        for title, text in steps
    )
    st.markdown(f'<div class="mdn-guide">{body}</div>', unsafe_allow_html=True)


def _condition_summary_cards(conds: pd.DataFrame) -> None:
    if conds.empty:
        return
    cards = []
    for _, cond in conds.head(3).iterrows():
        label = str(cond.get("Condition", "Condition"))
        district_pct = pd.to_numeric(cond.get("District %"), errors="coerce")
        national_pct = pd.to_numeric(cond.get("National %"), errors="coerce")
        d_txt = "unknown" if pd.isna(district_pct) else f"{float(district_pct):.0f}%"
        n_txt = "unknown" if pd.isna(national_pct) else f"{float(national_pct):.0f}%"
        help_text = _CONDITION_HELP.get(
            label,
            "Use this as a local health-burden signal when selecting which doctors to deploy.",
        )
        cards.append(
            '<div class="mdn-condition-card">'
            f'<b>{label}</b><span>{d_txt} district vs {n_txt} national.</span>'
            f'<span>{help_text}</span></div>'
        )
    st.markdown('<div class="mdn-condition-grid">' + "".join(cards) + '</div>',
                unsafe_allow_html=True)


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

def _gap_is_real(row) -> str:
    """Honest 'is the care gap genuinely there?' tier — NOT a supply-data score.

    For a real-desert candidate the gap is evidenced by the NEED side (NFHS) plus
    the *absence* of trustworthy supply. A zero-facility desert with a fully
    measured NFHS survey is the strongest case — the absence of facilities IS the
    signal — so it reads High, never 0.00. Derived only from columns that exist:
      • planning_category == real_desert_candidate (need + low supply already met)
      • health_need_score (NFHS burden percentile)
      • NFHS survey coverage (households_surveyed) — is the need well-measured?
    """
    need = pd.to_numeric(row.get("health_need_score"), errors="coerce")
    hh = pd.to_numeric(row.get("households_surveyed"), errors="coerce")
    is_real = str(row.get("planning_category", "")) == "real_desert_candidate"
    well_measured = pd.notna(hh) and hh >= 500  # NFHS district fact-sheet coverage
    need_v = 0.0 if pd.isna(need) else float(need)
    if is_real and need_v >= 0.6 and well_measured:
        return "High"
    if is_real and need_v >= 0.45 and well_measured:
        return "Medium-High"
    if need_v >= 0.5:
        return "Medium"
    return "Low"


def _supply_evidence(row) -> str:
    """Honest 'how much trustworthy facility evidence backs the supply side?'.

    A zero-facility desert has NONE — and that is the point, so we say so plainly
    instead of rendering 0.00. Otherwise we report the trustworthy-supply rate
    over the (small) observed sample as an Observed/Estimated tier.
    Columns: zero_facility_desert, observed_facility_rows, trustworthy_supply_rate.
    """
    if bool(row.get("zero_facility_desert", False)):
        return "None — no facilities on record"
    obs = pd.to_numeric(row.get("observed_facility_rows"), errors="coerce")
    obs_n = 0 if pd.isna(obs) else int(obs)
    if obs_n == 0:
        return "None — no facilities on record"
    tsr = pd.to_numeric(row.get("trustworthy_supply_rate"), errors="coerce")
    tsr_v = 0.0 if pd.isna(tsr) else float(tsr)
    n_word = f"{obs_n} record" + ("s" if obs_n != 1 else "")
    if obs_n < 8:
        return f"Thin — {n_word}, {tsr_v*100:.0f}% trustworthy"
    return f"Observed — {n_word}, {tsr_v*100:.0f}% trustworthy"


def _mode_verifiable_deserts(facilities, districts, specialty):
    real = districts[districts["planning_category"] == "real_desert_candidate"]
    datapoor = districts[districts["planning_category"].isin(
        ["phantom_desert_or_verification_gap", "supply_record_quality_problem"])]
    st.markdown(f"**{len(real)} districts are deployment candidates.** "
                f"**{len(datapoor)} more need claim/data verification first.**")

    top = real.sort_values("care_gap_score", ascending=False).head(5)
    # Two HONEST signals instead of one misleading 0.00 "Confidence":
    #   • "Gap is real" — confidence the care gap genuinely exists (need-evidenced).
    #     For zero-facility deserts this is High: the absence of facilities IS the
    #     signal, and the NFHS need is fully measured.
    #   • "Supply evidence" — how much trustworthy facility evidence exists. For a
    #     zero-facility desert: an honest "None — no facilities" chip, never a number.
    show = pd.DataFrame({
        "District": (top["district_name"] + ", " + top["state_ut"]).values,
        "Care gap": pd.to_numeric(top["care_gap_score"], errors="coerce").round(2).values,
        "Gap is real": [_gap_is_real(r) for _, r in top.iterrows()],
        "Supply evidence": [_supply_evidence(r) for _, r in top.iterrows()],
        "Next step": ["Call or verify" if bool(r.get("zero_facility_desert", False))
                      else "Confirm records" for _, r in top.iterrows()],
    })
    st.markdown("**Start here:**")
    st.dataframe(
        show, hide_index=True, width="stretch",
        column_config={
            "Care gap": st.column_config.NumberColumn(
                "Care gap", format="%.2f",
                help="0–1 composite: NFHS need + supply scarcity + low trustworthy supply."),
            "Gap is real": st.column_config.TextColumn(
                "Gap is real",
                help="Confidence the care gap genuinely exists — evidenced by NFHS "
                     "need and the absence of trustworthy supply. For a zero-facility "
                     "desert this is High: the absence of facilities IS the signal."),
            "Supply evidence": st.column_config.TextColumn(
                "Supply evidence", width="medium",
                help="How much trustworthy facility evidence backs the supply side. "
                     "Zero-facility deserts have none on record — that is the gap, "
                     "not a low-confidence score."),
        },
    )
    st.caption("Two checks: **Gap is real** uses NFHS need; **Supply evidence** shows "
               "trusted facility records. For zero-facility deserts, absence is the "
               "signal; call or verify before acting.")
    with ui.detail("Open chart and full evidence view"):
        st.altair_chart(charts.desert_quadrant(districts), use_container_width=True)
        st.caption("Top-right = high gap and well-evidenced (act now). "
                   "Top-left = high gap but low confidence (verify first). "
                   "Dashed lines: gap 0.6 / confidence 0.5.")


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
    _condition_summary_cards(conds)
    worst = conds.iloc[0]
    st.caption(f"Biggest gap: **{worst['Condition']}** ({worst['District %']}% vs "
               f"{worst['National %']}% national). Use this to choose which clinical team to deploy.")
    with ui.detail("Open condition chart"):
        st.altair_chart(charts.condition_gaps(conds), use_container_width=True)
        st.caption("Bar = district · gray tick = national median.")


def _save_affordance(geography_id: str, label: str, *, assumptions: dict | None = None,
                     note: str = "", key: str = "") -> None:
    """Standardized inline 'Save plan' / 'Shortlist district' row.

    Replaces the removed standalone Decisions desk so the persistence we built
    stays reachable from the copilot's grounded answers. Best-effort: every
    ``decisions.*`` call already swallows errors and returns a status dict, so
    this row never raises. A tiny caption reports where the write landed.
    """
    if decisions is None or not geography_id:
        return
    st.markdown('<div class="cp-actions"></div>', unsafe_allow_html=True)
    c1, c2, _ = st.columns([1.1, 1.1, 2.2])
    with c1:
        if st.button("💾 Save plan", key=f"cp_save_{key}", use_container_width=True):
            status = decisions.save_scenario(
                geography_id=geography_id, assumptions=assumptions or {}, note=note,
            ) or {}
            st.toast("Plan saved.", icon="💾")
            st.caption(status.get("detail", ""))
    with c2:
        shortlisted = False
        try:
            shortlisted = decisions.is_shortlisted(geography_id)
        except Exception:
            shortlisted = False
        verb = "★ Shortlisted" if shortlisted else "☆ Shortlist district"
        if st.button(verb, key=f"cp_short_{key}", use_container_width=True):
            status = decisions.toggle_shortlist(
                geography_id, label=label,
                reason="Flagged from Planner Copilot for verification.",
            ) or {}
            st.toast("Shortlist updated.", icon="★")
            st.caption(status.get("detail", ""))


def _mode_scenario(facilities, districts, specialty):
    # The Copilot's grounded answer to "What should I deploy here?" is the full
    # Interventions recommender, hosted natively inside the conversation.
    st.markdown(
        "Rank districts by expected value, then inspect the recommended action and evidence."
    )
    interventions.render_interventions(facilities, districts, specialty, embedded=True)

    # Inline persistence on the district the recommender is currently inspecting.
    sel = st.session_state.get("interv_district")
    row = _district_by_label(districts, sel) if sel else None
    if row is not None:
        gap = float(pd.to_numeric(row.get("care_gap_score"), errors="coerce") or 0)
        _save_affordance(
            geography_id=f"{row['district_name']}|{row['state_ut']}",
            label=sel,
            assumptions={
                "source": "copilot_interventions",
                "district": str(row["district_name"]),
                "state_ut": str(row["state_ut"]),
                "specialty": str(specialty),
                "care_gap_score": gap,
            },
            note=f"Intervention plan saved from Copilot for {sel}.",
            key="scn",
        )


def _mode_whatif(facilities, districts, specialty):
    # The Copilot's grounded answer to "What if I add clinics?" is the full
    # Scenario lab (what-if simulator + supply bands), hosted in the conversation.
    st.markdown(
        "Pick a district and move the levers. Supply bands and intervention ranks update "
        "with uncertainty."
    )
    simulator.render_simulator(facilities, districts, specialty, embedded=True)

    # Inline persistence on the scenario context the simulator just published.
    ctx = st.session_state.get("cp_scenario_ctx") or {}
    if ctx.get("geography_id"):
        _save_affordance(
            geography_id=ctx["geography_id"],
            label=ctx.get("label", ""),
            assumptions=ctx.get("assumptions") or {},
            note=f"What-if scenario saved from Copilot for {ctx.get('label', '')}.",
            key="wi",
        )


def _mode_explain(facilities, districts, specialty):
    st.markdown("**CareGap methods** — trust and uncertainty behind each score:")
    tiers = (facilities["trust_tier"].value_counts() if "trust_tier" in facilities.columns
             else pd.Series(dtype=int))
    a, b, c = st.columns(3)
    a.metric("High-trust facilities", f"{int(tiers.get('High', 0)):,}")
    b.metric("Medium", f"{int(tiers.get('Medium', 0)):,}")
    c.metric("Verify-first", f"{int(tiers.get('Verify', 0)):,}")
    items = [
        ("🧮 Bayesian validity posterior", "P(record valid | evidence) from geo, source, recency, "
         "and contradiction signals. Drives accept / review / quarantine."),
        ("📏 Wilson confidence intervals", "Trust, review, and supply rates carry intervals; wide "
         "bands flag small-sample fragility."),
        ("🎯 Split-conformal coverage", "Calibrated to ~91.8% proxy-label coverage (α=0.1), so "
         "uncertainty is shown beside each score."),
        ("🌲 CatBoost supply imputation", "Missing capacity/doctor counts use CatBoost with p10–p90 "
         "intervals; estimates stay labeled."),
        ("🗺️ Real vs data-poor", "planning_category separates deploy-ready gaps from weak-evidence "
         "gaps, so missing supply is not shown as good coverage."),
    ]
    st.markdown('<div class="cp-explain">', unsafe_allow_html=True)
    for title, body in items:
        with st.container(border=True):
            st.markdown('<div class="cp-method-marker"></div>', unsafe_allow_html=True)
            st.markdown(f"**{title}**")
            st.caption(body)
    st.markdown('</div>', unsafe_allow_html=True)


_MODES = {
    "verifiable_deserts": _mode_verifiable_deserts,
    "drill_conditions": _mode_drill_conditions,
    "scenario": _mode_scenario,
    "whatif": _mode_whatif,
    "explain": _mode_explain,
}


def render_copilot(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    # Standard tab header (design-system contract); the conversational greeting
    # below remains the hero when no mode is active.
    ui.tab_intro("Planner Copilot",
                 "Guided actions for deciding where to deploy doctors.")
    _guide_steps()
    mode = st.session_state.get("cp_mode")

    if not mode:
        st.markdown('<div class="cp-greet">Choose the next planning move</div>',
                    unsafe_allow_html=True)
        st.markdown('<div class="cp-hint">Start with deployment districts, choose clinical '
                    'focus, then save a plan.</div>',
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

    with ui.detail("Optional: type a planner question"):
        prompt = st.text_input(
            "Planner question",
            placeholder="e.g. What conditions are worst in Uttar Dinajpur?",
            label_visibility="collapsed",
            key="cp_free_text",
        )
        if st.button("Route question", key="cp_route_question") and prompt:
            st.session_state["cp_mode"] = _intent(prompt) or "_fallback"
            st.rerun()
