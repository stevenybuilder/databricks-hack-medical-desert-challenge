"""Next Best Health Access Intervention — recommender engine + Streamlit view.

Feature 2 of the product strategy. For each district we rank a small, fixed
catalog of plausible interventions with a transparent expected-value-style score:

    EV = P(addresses_need) * benefit - P(wrong) * harm - operating_cost

Every component is a transparent heuristic built only from columns that actually
exist in the cleaned district table (see tricky_fields.md / Bayesian_stats doc).
The strategy doc references signals this dataset does NOT have — there is no
broadband column and no elderly-share column (only population_below_age_15_years_pct).
We do not fabricate them: telehealth is treated as a LOW-confidence default and we
explicitly note "broadband not in dataset"; where the doc names a missing signal we
substitute the nearest real proxy and LABEL it as a proxy in the rationale.

Public API:
    recommend_interventions(districts, facilities, specialty) -> pd.DataFrame
    render_interventions(facilities, districts, specialty) -> None

`recommend_interventions` prefers the precomputed CSV artifact
(scripts/build_intervention_recommendations.py) and falls back to computing the
same engine in-process, so the app works even if the artifact is absent.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

POLICY_VERSION = "intervention-policy-v1"

# --- Intervention catalog ----------------------------------------------------
# Each intervention carries a cost prior (operating-cost component on the same
# 0..1 scale as benefit/harm) and a display cost tier. The `trigger` callable
# returns (fired: bool, p_addresses_need: float in 0..1, need_gap: float 0..1,
# signals: list[str]) given a district row + helpers. Telehealth is special-cased
# as a low-confidence default with a not-recommended flag in weak-evidence areas.

# Cost priors (operating-cost component, 0..1) and human-readable tiers.
_COST = {
    "Mobile primary care clinic":            (0.55, "High"),
    "OB referral network + prenatal telehealth & transport": (0.42, "Medium-High"),
    "Pharmacy-based chronic care screening": (0.22, "Low-Medium"),
    "Community health worker outreach":      (0.30, "Medium"),
    "PM-JAY / insurance enrollment support": (0.18, "Low"),
    "Verify-first data / records campaign":  (0.12, "Low"),
    "Telehealth-first program":              (0.20, "Low"),
}

# Harm prior (cost of a wrong recommendation, 0..1). Higher for capital-heavy /
# hard-to-reverse actions; lower for cheap, reversible data/outreach actions.
_HARM = {
    "Mobile primary care clinic":            0.60,
    "OB referral network + prenatal telehealth & transport": 0.45,
    "Pharmacy-based chronic care screening": 0.30,
    "Community health worker outreach":      0.25,
    "PM-JAY / insurance enrollment support": 0.25,
    "Verify-first data / records campaign":  0.10,
    "Telehealth-first program":              0.40,
}

CONF_ORDER = {"Low": 0, "Medium": 1, "High": 2}


def _num(value, default: float = np.nan) -> float:
    try:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _pct01(value, default: float = np.nan) -> float:
    """NFHS *_pct columns are 0..100; return 0..1 (clamped)."""
    v = _num(value, default)
    if np.isnan(v):
        return default
    return float(np.clip(v / 100.0, 0.0, 1.0))


def _rate01(value, default: float = 0.0) -> float:
    v = _num(value, default)
    if np.isnan(v):
        return default
    return float(np.clip(v, 0.0, 1.0))


def _uncertainty_p_wrong(row: pd.Series) -> tuple[float, list[str]]:
    """Probability the recommendation is wrong, from fragile-evidence signals.

    Scales with the district uncertainty level and the width/weakness of the
    underlying evidence (small samples, high needs-review, high critical-gap).
    Returns (p_wrong in ~0.05..0.85, fragility note list).
    """
    notes: list[str] = []
    level = str(row.get("district_uncertainty_level", "")).strip().lower()
    base = {"lower": 0.12, "medium": 0.25, "higher": 0.42}.get(level, 0.30)
    if level:
        notes.append(f"district uncertainty: {level}")

    obs = _num(row.get("observed_facility_rows"), 0.0)
    if not np.isnan(obs) and obs < 8:
        base += 0.15
        notes.append(f"small observed sample ({int(obs)} rows)")

    review = _rate01(row.get("needs_human_review_rate"))
    if review >= 0.85:
        base += 0.12
        notes.append(f"high needs-review rate ({review*100:.0f}%)")

    crit = _rate01(row.get("critical_supply_gap_rate"))
    if crit >= 0.75:
        base += 0.08
        notes.append(f"high critical-supply-gap rate ({crit*100:.0f}%)")

    # Wide trustworthy-supply CI -> fragile supply evidence.
    lo = _num(row.get("trustworthy_supply_rate_ci_low"))
    hi = _num(row.get("trustworthy_supply_rate_ci_high"))
    if not (np.isnan(lo) or np.isnan(hi)) and (hi - lo) >= 0.5:
        base += 0.06
        notes.append(f"wide supply CI ({lo*100:.0f}-{hi*100:.0f}%)")

    return float(np.clip(base, 0.05, 0.85)), notes


def _confidence_label(p_wrong: float, p_addresses: float) -> str:
    """Map evidence strength to Low/Medium/High. Tied to uncertainty + fit."""
    if p_wrong <= 0.22 and p_addresses >= 0.55:
        return "High"
    if p_wrong >= 0.5 or p_addresses < 0.35:
        return "Low"
    return "Medium"


# --- Per-intervention candidate builders -------------------------------------
# Each returns dict(intervention, p_addresses_need, need_gap, trigger_signals,
# rationale, not_recommended_flag, not_recommended_reason) or None if it does not
# even weakly apply to this district.

def _cand_mobile_clinic(row, need):
    cat = str(row.get("planning_category", ""))
    trust = _rate01(row.get("trustworthy_supply_rate"))
    cap_obs = _rate01(row.get("capacity_observed_rate"))
    cap_med = _num(row.get("observed_capacity_median"))
    gap = float(np.clip((1.0 - trust) * 0.6 + (1.0 - cap_obs) * 0.4, 0, 1))
    p = 0.35 + 0.4 * gap
    sig = [
        f"planning_category={cat}",
        f"trustworthy_supply_rate={trust*100:.0f}%",
        f"capacity_observed_rate={cap_obs*100:.0f}%",
    ]
    if cat == "real_desert_candidate":
        p += 0.2
    rationale = (
        "Genuine unmet need with little trustworthy, observed supply — physical "
        "capacity, not just data, appears to be missing."
    )
    if not np.isnan(cap_med):
        sig.append(f"observed_capacity_median={cap_med:.0f}")
    return dict(intervention="Mobile primary care clinic",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_maternal(row, need):
    births = _pct01(row.get("institutional_birth_5y_pct"))
    anaemia = _pct01(row.get("all_w15_49_who_are_anaemic_pct"))
    mat_signal = _rate01(row.get("maternity_signal_rate"))
    # Low institutional births + high anaemia + weak maternity supply signal.
    birth_gap = 0.0 if np.isnan(births) else (1.0 - births)
    anaemia_burden = 0.0 if np.isnan(anaemia) else anaemia
    supply_gap = 1.0 - mat_signal
    gap = float(np.clip(birth_gap * 0.5 + anaemia_burden * 0.3 + supply_gap * 0.2, 0, 1))
    p = 0.3 + 0.5 * gap
    sig = [
        f"institutional_birth_5y_pct={'unknown' if np.isnan(births) else f'{births*100:.0f}%'}",
        f"anaemia_w15_49_pct={'unknown' if np.isnan(anaemia) else f'{anaemia*100:.0f}%'}",
        f"maternity_signal_rate={mat_signal*100:.0f}%",
    ]
    rationale = (
        "Maternal-care gap: institutional births are low and anaemia burden high, "
        "while observed maternity supply signal is thin. The telehealth leg is a "
        "PROXY for prenatal monitoring (broadband not in dataset) — pair with transport."
    )
    return dict(intervention="OB referral network + prenatal telehealth & transport",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_ncd(row, need):
    w_bp = _pct01(row.get("w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"))
    m_bp = _pct01(row.get("m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"))
    w_sug = _pct01(row.get("w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct"))
    m_sug = _pct01(row.get("m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct"))
    bp = np.nanmean([w_bp, m_bp])
    sug = np.nanmean([w_sug, m_sug])
    ncd_signal = _rate01(row.get("ncd_signal_rate"))
    diag_signal = _rate01(row.get("diagnostic_signal_rate"))
    bp_b = 0.0 if np.isnan(bp) else bp
    sug_b = 0.0 if np.isnan(sug) else sug
    supply_gap = 1.0 - max(ncd_signal, diag_signal)
    gap = float(np.clip(bp_b * 0.4 + sug_b * 0.4 + supply_gap * 0.2, 0, 1))
    p = 0.3 + 0.5 * gap
    sig = [
        f"high_bp_pct={'unknown' if np.isnan(bp) else f'{bp*100:.0f}%'}",
        f"high_blood_sugar_pct={'unknown' if np.isnan(sug) else f'{sug*100:.0f}%'}",
        f"ncd_signal_rate={ncd_signal*100:.0f}%",
        f"diagnostic_signal_rate={diag_signal*100:.0f}%",
    ]
    rationale = (
        "Chronic-disease burden (BP / blood sugar) is elevated and the NCD/diagnostic "
        "service signal is weak — pharmacy-based screening can find undiagnosed cases "
        "close to home."
    )
    return dict(intervention="Pharmacy-based chronic care screening",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_insurance(row, need):
    ins = _pct01(row.get("hh_member_covered_health_insurance_pct"))
    cat = str(row.get("planning_category", ""))
    ins_gap = 0.0 if np.isnan(ins) else (1.0 - ins)
    gap = float(np.clip(ins_gap, 0, 1))
    p = 0.25 + 0.55 * gap
    if cat == "referral_or_capacity_candidate":
        p += 0.15  # capacity exists; affordability is the live barrier
    sig = [
        f"hh_health_insurance_pct={'unknown' if np.isnan(ins) else f'{ins*100:.0f}%'}",
        f"planning_category={cat}",
    ]
    rationale = (
        "Affordability gap: household insurance coverage is low. Where trustworthy "
        "capacity already exists, PM-JAY enrollment unlocks care without building new "
        "supply."
    )
    return dict(intervention="PM-JAY / insurance enrollment support",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_chw(row, need):
    # Records weak / supply uncertain -> human outreach. source_url_rate is ~1.0
    # across this web-derived dataset, so we lean on contact evidence + review burden.
    contact = _rate01(row.get("contact_evidence_rate"), 1.0)
    review = _rate01(row.get("needs_human_review_rate"))
    src = _rate01(row.get("source_url_rate"), 1.0)
    contact_gap = 1.0 - contact
    gap = float(np.clip(review * 0.5 + contact_gap * 0.4 + (1.0 - src) * 0.1, 0, 1))
    p = 0.3 + 0.45 * gap
    sig = [
        f"needs_human_review_rate={review*100:.0f}%",
        f"contact_evidence_rate={contact*100:.0f}%",
        f"source_url_rate={src*100:.0f}%",
    ]
    rationale = (
        "Records are weak and supply is uncertain (high review burden / thin contact "
        "evidence). Community health workers can both deliver outreach and ground-truth "
        "what actually exists."
    )
    return dict(intervention="Community health worker outreach",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_verify(row, need):
    cat = str(row.get("planning_category", ""))
    review = _rate01(row.get("needs_human_review_rate"))
    crit = _rate01(row.get("critical_supply_gap_rate"))
    fits = cat in {"phantom_desert_or_verification_gap", "supply_record_quality_problem"}
    # Verify-first is a gating prerequisite, not a substitute for care. It should
    # only lead when the data problem is the *primary* blocker: the right planning
    # category, or an extreme review burden. Otherwise it stays a low-impact option
    # so a well-matched care intervention can outrank it.
    primary_blocker = fits or review >= 0.9
    gap = float(np.clip(review * 0.5 + crit * 0.5, 0, 1))
    if not primary_blocker:
        gap *= 0.45  # damp so it cannot crowd out substantive care actions
    p = 0.35 + 0.45 * gap + (0.15 if fits else 0.0)
    sig = [
        f"planning_category={cat}",
        f"needs_human_review_rate={review*100:.0f}%",
        f"critical_supply_gap_rate={crit*100:.0f}%",
    ]
    rationale = (
        "Apparent gap may be a data artifact: facilities likely exist but records are "
        "broken or unverified. Run a verify-first campaign before committing capital."
    )
    return dict(intervention="Verify-first data / records campaign",
                p_addresses_need=float(np.clip(p, 0, 0.95)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=False, not_recommended_reason="")


def _cand_telehealth(row, need):
    # Low-confidence default. We have NO broadband and NO elderly-share columns, so
    # we cannot confidently recommend telehealth-first. Flag it as not recommended
    # in weak-evidence districts and always note the missing signal.
    trust = _rate01(row.get("trustworthy_supply_rate"))
    gap = float(np.clip(1.0 - trust, 0, 1))
    p = 0.18 + 0.25 * gap  # deliberately modest
    review = _rate01(row.get("needs_human_review_rate"))
    weak_evidence = review >= 0.7 or str(row.get("district_uncertainty_level", "")).lower() == "higher"
    sig = [
        f"trustworthy_supply_rate={trust*100:.0f}%",
        "broadband_coverage=NOT IN DATASET (cannot confirm telehealth viability)",
        "elderly_share=NOT IN DATASET (only population_below_age_15_years_pct exists)",
    ]
    rationale = (
        "Telehealth-first is a LOW-confidence default: the dataset has no broadband or "
        "elderly-share columns, so the doc's penalty for low-broadband/elderly areas "
        "cannot be evaluated. Prefer mobile care or CHW outreach unless connectivity is "
        "separately confirmed."
    )
    not_rec = bool(weak_evidence)
    reason = ""
    if not_rec:
        reason = (
            "Not recommended: viability signals (broadband, elderly share) are absent "
            "from the dataset and local evidence is weak — do not lead with telehealth."
        )
    return dict(intervention="Telehealth-first program",
                p_addresses_need=float(np.clip(p, 0, 0.7)), need_gap=gap,
                trigger_signals=sig, rationale=rationale,
                not_recommended_flag=not_rec, not_recommended_reason=reason)


_BUILDERS = [
    _cand_mobile_clinic, _cand_maternal, _cand_ncd, _cand_insurance,
    _cand_chw, _cand_verify, _cand_telehealth,
]


def _score_district(row: pd.Series) -> pd.DataFrame:
    """Build the full ranked candidate table for one district row."""
    need = _rate01(row.get("health_need_score"), 0.5)
    p_wrong, fragility = _uncertainty_p_wrong(row)
    state = str(row.get("state_ut", "")).strip()
    district = str(row.get("district_name", "")).strip()

    records = []
    for build in _BUILDERS:
        cand = build(row, need)
        if cand is None:
            continue
        p_add = cand["p_addresses_need"]
        gap = cand["need_gap"]
        # Benefit scales with district health need and the relevant need gap.
        # It is the leading term: a well-matched action in a high-need district
        # should beat a cheap-but-low-impact default. Scaled to a 0..1.6 range so
        # P(addresses)*benefit can outweigh the harm/cost penalties for a good fit.
        benefit = 1.6 * float(np.clip(0.35 + 0.65 * need, 0, 1)) * float(np.clip(0.3 + 0.7 * gap, 0, 1))
        cost, cost_tier = _COST[cand["intervention"]]
        harm = _HARM[cand["intervention"]]
        # Telehealth flagged not-recommended takes an extra EV penalty.
        eff_p_wrong = min(0.95, p_wrong + 0.15) if cand["not_recommended_flag"] else p_wrong
        # Harm and cost are discounted so EV differentiates by which need is most
        # acute, not merely by which action is cheapest. A confident, high-impact
        # match can still justify a capital-heavy intervention.
        ev = p_add * benefit - eff_p_wrong * harm * 0.6 - cost * 0.6
        # Expected access gain: people-reachable-style 0..100 index (benefit*fit).
        access_gain = round(float(np.clip(
            62.5 * p_add * benefit * (1.0 - 0.5 * eff_p_wrong), 0, 100)), 1)
        confidence = "Low" if cand["not_recommended_flag"] else _confidence_label(eff_p_wrong, p_add)
        signals = list(cand["trigger_signals"]) + (
            [f"fragility: {', '.join(fragility)}"] if fragility else []
        )
        records.append({
            "state_ut": state,
            "district_name": district,
            "intervention": cand["intervention"],
            "ev_score": round(float(ev), 4),
            "expected_access_gain": access_gain,
            "est_cost_tier": cost_tier,
            "confidence": confidence,
            "p_addresses_need": round(p_add, 3),
            "p_wrong": round(eff_p_wrong, 3),
            "benefit": round(benefit, 3),
            "trigger_signals": " | ".join(signals),
            "rationale": cand["rationale"],
            "not_recommended_flag": cand["not_recommended_flag"],
            "not_recommended_reason": cand["not_recommended_reason"],
        })

    out = pd.DataFrame(records)
    if out.empty:
        return out
    # Telehealth-first is never the headline recommendation (doc posture: it cannot
    # be confidently recommended without broadband/elderly signals, which the dataset
    # lacks). It is demoted alongside any flagged not-recommended option so it can
    # never rank #1, while still appearing in the transparent table.
    out["_demote"] = (
        out["not_recommended_flag"]
        | out["intervention"].eq("Telehealth-first program")
    )
    out = out.sort_values(
        ["_demote", "ev_score"], ascending=[True, False]
    ).reset_index(drop=True)
    out = out.drop(columns=["_demote"])
    out["rank"] = np.arange(1, len(out) + 1)
    return out


def compute_recommendations(districts: pd.DataFrame) -> pd.DataFrame:
    """Run the engine over every district. One row per district x intervention."""
    if districts is None or districts.empty:
        return pd.DataFrame()
    frames = [
        _score_district(row)
        for _, row in districts.iterrows()
    ]
    frames = [f for f in frames if not f.empty]
    if not frames:
        return pd.DataFrame()
    cols = [
        "state_ut", "district_name", "intervention", "rank", "ev_score",
        "expected_access_gain", "est_cost_tier", "confidence",
        "p_addresses_need", "p_wrong", "benefit",
        "trigger_signals", "rationale",
        "not_recommended_flag", "not_recommended_reason",
    ]
    result = pd.concat(frames, ignore_index=True)
    return result[cols]


def _load_precomputed():
    try:
        from . import config
        path = config.data_dir() / "intervention_recommendations.csv"
    except Exception:
        return None
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return None
    return df if not df.empty else None


def recommend_interventions(
    districts: pd.DataFrame, facilities: pd.DataFrame, specialty: str
) -> pd.DataFrame:
    """Return ranked intervention recommendations for districts.

    `facilities` is accepted for signature compatibility / future facility-level
    evidence; the current engine is district-driven. Prefers the precomputed CSV
    artifact and falls back to computing the same engine in-process.

    When `specialty` is a specific specialty (not "All specialties"), candidates
    are re-ranked to surface the matching intervention without dropping the
    transparent EV table.
    """
    df = _load_precomputed()
    if df is None:
        df = compute_recommendations(districts)
    if df is None or df.empty:
        return pd.DataFrame()

    # Specialty-aware re-rank: nudge the matching intervention up so the view
    # reflects the user's selected lens, while keeping EV transparent.
    pref = _SPECIALTY_INTERVENTION.get(specialty)
    if pref:
        df = df.copy()
        df["specialty_match"] = df["intervention"].eq(pref)
        df = df.sort_values(
            ["state_ut", "district_name", "specialty_match", "ev_score"],
            ascending=[True, True, False, False],
        )
        df["rank"] = df.groupby(["state_ut", "district_name"]).cumcount() + 1
        df = df.drop(columns=["specialty_match"]).reset_index(drop=True)
    return df


_SPECIALTY_INTERVENTION = {
    "Maternity / OB-GYN": "OB referral network + prenatal telehealth & transport",
    "Chronic disease (NCD)": "Pharmacy-based chronic care screening",
    "Diagnostics / Imaging": "Pharmacy-based chronic care screening",
    "Emergency / Surgery": "Mobile primary care clinic",
}


# --- Streamlit view ----------------------------------------------------------

def _tone_for(intervention: str, not_recommended: bool) -> str:
    if not_recommended:
        return "danger"
    return {
        "Mobile primary care clinic": "deploy",
        "OB referral network + prenatal telehealth & transport": "deploy",
        "Pharmacy-based chronic care screening": "info",
        "Community health worker outreach": "verify",
        "PM-JAY / insurance enrollment support": "info",
        "Verify-first data / records campaign": "verify",
        "Telehealth-first program": "danger",
    }.get(intervention, "info")


def _glass_panel(st):
    """Group loose content into one frosted `.mdn-glass` surface (design-system
    recipe scoped onto a bordered ``st.container``). Local helper — styling only."""
    from contextlib import contextmanager

    @contextmanager
    def _cm():
        box = st.container(border=True)
        box.markdown(
            """
            <style>
            div[data-testid="stVerticalBlockBorderWrapper"]:has(.iv-glass-marker) {
              background: var(--glass-bg);
              border: 1px solid var(--glass-border);
              border-radius: var(--radius-card);
              box-shadow: var(--shadow-card);
              padding: var(--pad-card);
              -webkit-backdrop-filter: var(--glass-blur);
              backdrop-filter: var(--glass-blur);
            }
            </style>
            <div class="iv-glass-marker"></div>
            """,
            unsafe_allow_html=True,
        )
        with box:
            yield box

    return _cm()


def render_interventions(
    facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str,
    *, embedded: bool = False,
) -> None:
    """Self-contained Streamlit view for the Intervention Recommender.

    When ``embedded`` is True (hosted inside the Planner Copilot conversation),
    the redundant top-level title is dropped and the methodology (banner + rail)
    is tucked behind a ``ui.detail`` expander so the copilot's conversational
    lead-in stays the headline. Styling uses the shared design tokens either way.
    """
    import streamlit as st
    from . import ui

    if not embedded:
        st.markdown(
            '<div class="mdn-panel-h">Next Best Health Access Intervention</div>',
            unsafe_allow_html=True,
        )
        ui.decision_banner(
            "What should be deployed first, and how sure are we?",
            "Each district is scored with a transparent expected-value rule: "
            "EV = P(addresses need) x benefit − P(wrong) x harm − operating cost. "
            "Confidence reflects data uncertainty, never measured accuracy.",
            tone="info",
        )
        ui.workflow_rail([
            ("1. Rank deserts", "Highest care-gap districts first"),
            ("2. Match action", "Need signals pick the intervention"),
            ("3. Score EV", "Benefit vs harm vs cost"),
            ("4. Show confidence", "Uncertainty stays visible"),
            ("5. Cite evidence", "Sample facilities & sources"),
        ])
    else:
        with ui.detail("How this is scored (EV rule & workflow)"):
            st.markdown(
                "Each district is scored with a transparent expected-value rule: "
                "**EV = P(addresses need) × benefit − P(wrong) × harm − operating cost.** "
                "Confidence reflects data uncertainty, never measured accuracy."
            )
            ui.workflow_rail([
                ("1. Rank deserts", "Highest care-gap districts first"),
                ("2. Match action", "Need signals pick the intervention"),
                ("3. Score EV", "Benefit vs harm vs cost"),
                ("4. Show confidence", "Uncertainty stays visible"),
                ("5. Cite evidence", "Sample facilities & sources"),
            ])

    # --- load (with states) ---
    try:
        with st.spinner("Scoring interventions…"):
            recs = recommend_interventions(districts, facilities, specialty)
    except Exception as exc:  # pragma: no cover - defensive UI guard
        st.error(f"Could not compute intervention recommendations: {exc}")
        return

    if recs is None or recs.empty:
        st.info("No intervention recommendations available for the current data.")
        return

    # Top-N districts by their #1 recommendation's expected access gain.
    top1 = recs[recs["rank"] == 1].copy()
    if top1.empty:
        st.info("No ranked recommendations to display.")
        return
    top1 = top1.sort_values("expected_access_gain", ascending=False)

    st.markdown(
        '<div class="mdn-panel-h">Top districts · #1 recommended intervention</div>',
        unsafe_allow_html=True,
    )
    show = top1.head(6)
    cols = st.columns(3)
    for i, (_, r) in enumerate(show.iterrows()):
        with cols[i % 3]:
            ui.stat_card(
                f"{r['district_name']}, {r['state_ut']}",
                r["intervention"],
                f"Access gain {r['expected_access_gain']:.0f} · "
                f"EV {r['ev_score']:.2f} · {r['confidence']} confidence · "
                f"cost {r['est_cost_tier']}",
                tone=_tone_for(r["intervention"], bool(r["not_recommended_flag"])),
            )

    # --- district detail picker ---
    st.markdown(
        '<div class="mdn-panel-h">Inspect a district</div>', unsafe_allow_html=True
    )
    top1 = top1.reset_index(drop=True)
    labels = (top1["district_name"] + ", " + top1["state_ut"]).tolist()
    if not labels:
        return
    choice = st.selectbox("District", labels, index=0, key="interv_district")
    sel_idx = labels.index(choice)
    sel = top1.iloc[sel_idx]
    state = sel["state_ut"]
    district = sel["district_name"]

    detail = recs[
        (recs["state_ut"] == state) & (recs["district_name"] == district)
    ].sort_values("rank")

    best = detail[detail["rank"] == 1].iloc[0]
    ui.decision_banner(
        f"Recommended intervention: {best['intervention']}",
        f"{best['confidence']} confidence · expected access gain "
        f"{best['expected_access_gain']:.0f} · cost {best['est_cost_tier']}",
        tone=_tone_for(best["intervention"], bool(best["not_recommended_flag"])),
    )

    # Reason bullets (doc "Output example" idiom) from the firing signals, grouped
    # with the headline probabilities into one frosted answer card.
    with _glass_panel(st):
        st.markdown("**Reason:**")
        st.markdown(best["rationale"])
        chips = [s.strip() for s in str(best["trigger_signals"]).split("|") if s.strip()]
        ui.reason_chips(chips)

        m1, m2, m3 = st.columns(3)
        m1.metric("P(addresses need)", f"{_num(best.get('p_addresses_need')):.2f}")
        m2.metric("P(wrong)", f"{_num(best.get('p_wrong')):.2f}")
        m3.metric("Expected access gain", f"{_num(best.get('expected_access_gain')):.0f}")

    # Not-recommended callout (kept visible — it is a safety signal).
    flagged = detail[detail["not_recommended_flag"] == True]  # noqa: E712
    for _, fr in flagged.iterrows():
        if str(fr["not_recommended_reason"]).strip():
            st.warning(f"{fr['intervention']} — {fr['not_recommended_reason']}")

    # Dense backing detail (ranked table, trigger signals, cited evidence). Behind
    # a single progressive-disclosure expander when embedded in the copilot so the
    # first glance stays the recommendation; shown inline standalone.
    import contextlib

    def _depth_ctx():
        if embedded:
            return ui.detail("Full ranking, trigger signals & cited evidence")
        return contextlib.nullcontext()

    with _depth_ctx():
        # Full ranked table.
        st.markdown(
            '<div class="mdn-panel-h">All candidate interventions (ranked by EV)</div>',
            unsafe_allow_html=True,
        )
        table = detail[[
            "rank", "intervention", "ev_score", "expected_access_gain",
            "est_cost_tier", "confidence", "p_addresses_need", "p_wrong",
        ]].rename(columns={
            "rank": "Rank", "intervention": "Intervention", "ev_score": "EV",
            "expected_access_gain": "Access gain", "est_cost_tier": "Cost tier",
            "confidence": "Confidence", "p_addresses_need": "P(addresses need)",
            "p_wrong": "P(wrong)",
        })
        st.dataframe(table, hide_index=True, width="stretch")

        # Firing signals per candidate.
        st.markdown(
            '<div class="mdn-panel-h">Trigger signals that fired</div>',
            unsafe_allow_html=True,
        )
        sig_table = detail[["intervention", "trigger_signals"]].rename(
            columns={"intervention": "Intervention", "trigger_signals": "Signals (real values)"}
        )
        st.dataframe(sig_table, hide_index=True, width="stretch")

        # Evidence: cited sample facilities / sources from the district row.
        st.markdown(
            '<div class="mdn-panel-h">Evidence (sample facilities & sources)</div>',
            unsafe_allow_html=True,
        )
        drow = districts[
            (districts["state_ut"].astype(str).str.strip() == str(state).strip())
            & (districts["district_name"].astype(str).str.strip() == str(district).strip())
        ]
        if drow.empty:
            st.caption("No matching district row for evidence.")
        else:
            from . import data as _data
            drow0 = drow.iloc[0]
            names = str(drow0.get("sample_facility_names", "") or "").strip()
            claim = str(drow0.get("sample_claim_evidence", "") or "").strip()
            url = _data._first_url(drow0.get("sample_source_urls", ""))
            warn = str(drow0.get("facility_supply_warning", "") or "").strip()
            if names:
                st.markdown(f"**Facilities:** {names[:300]}")
            if claim:
                st.markdown(f"**Claimed (unverified):** {claim[:300]}…")
            if url:
                st.markdown(f"**Source:** [{url[:80]}]({url})")
            if warn:
                st.caption(warn)
            if not (names or claim or url):
                st.caption("No sample evidence recorded for this district.")

        st.caption(
            "Estimates are heuristic, not measured accuracy. Telehealth is a low-confidence "
            "default because broadband and elderly-share signals are not in this dataset."
        )
