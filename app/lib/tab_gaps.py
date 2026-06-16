"""Top care gaps tab: a calm first glance (wow stat + top action) with all
depth opt-in behind expanders.

Entry point: ``render(districts, specialty) -> None``.

Layout philosophy (see DESIGN_SYSTEM.md density rule): the default view answers
"where is the worst gap and what do I do" — a calm wow-stat anchor, ≤2 KPIs, a
compact top-6, and the selected-district drill-down. Everything heavier lives
behind ONE ``st.segmented_control`` sub-nav (Ranking · At a glance · Method &
caveats · My Plan) that swaps a single panel in place, so depth is one click,
not three scrolls. The next-wave gaps agent edits this file only; new
chart/helper needs are LOCAL functions here.
"""
from __future__ import annotations

from contextlib import contextmanager

import pandas as pd
import streamlit as st

from . import data, ui, charts, decisions
from .tab_common import (
    ACTION_FILTERS,
    _action_label,
    _action_tone,
    _fmt_num,
    _fmt_pct,
    _ranked_districts,
    _selected_or_first,
)

# How many districts show in the calm default list before "Full ranking".
_SHORTLIST_N = 6


@contextmanager
def _glass_panel():
    """Group loose content into one frosted `.mdn-glass` surface.

    Streamlit can't wrap arbitrary widgets in a raw HTML div, so we scope the
    frosted-card recipe (radius/blur/shadow/padding from the design tokens) onto a
    bordered ``st.container`` and yield it. Keeps the "where to act next" block
    reading as one intentional card rather than loose floating elements."""
    box = st.container(border=True)
    box.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.cg-glass-marker) {
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-card);
          padding: var(--pad-card);
          -webkit-backdrop-filter: var(--glass-blur);
          backdrop-filter: var(--glass-blur);
        }
        </style>
        <div class="cg-glass-marker"></div>
        """,
        unsafe_allow_html=True,
    )
    with box:
        yield box


def _wow_stat(ranked_all: pd.DataFrame) -> tuple[int, int, float]:
    """Honest demo anchor, recomputed live (never hardcoded).

    Among the worst-N care-gap districts, how many have *no* facility passing
    automated trust checks (``trustworthy_supply_rate`` <= 0). Returns
    ``(zero_trust_count, n, pct)``. Gracefully handles a missing column.
    """
    n = min(50, len(ranked_all))
    tsr = pd.to_numeric(
        ranked_all.head(n).get("trustworthy_supply_rate"), errors="coerce"
    ).fillna(0.0)
    zero_trust = int((tsr <= 0).sum())
    pct = (zero_trust / n * 100) if n else 0.0
    return zero_trust, n, pct


def _wow_banner(zero_trust: int, n: int, pct: float) -> None:
    """The single bold anchor of the first glance — a cohesive frosted card with a
    danger accent. Tokenized (radius/shadow/blur from the design system); the
    underlying stat is computed upstream and never touched here."""
    st.markdown(
        '<div class="mdn-glass" style="margin:.1rem 0 .2rem;'
        'border-color:rgba(255,82,82,.32);'
        'background:linear-gradient(100deg,rgba(255,82,82,.13),var(--glass-bg) 62%);'
        'display:flex;align-items:baseline;gap:.9rem;flex-wrap:wrap">'
        '<span style="font-size:2.3rem;font-weight:820;color:#ff8d8d;line-height:1;'
        'letter-spacing:-.02em;font-variant-numeric:tabular-nums">'
        f'{zero_trust}/{n}</span>'
        '<span style="color:var(--text);font-size:1.0rem;line-height:1.4;flex:1 1 16rem">'
        'of the worst care-gap districts have <strong>0% trustworthy supply</strong> — '
        f'{pct:.0f}% of the highest-need places have <em>no</em> facility that '
        'passes automated checks.</span></div>',
        unsafe_allow_html=True,
    )


def _shortlist_table(ranked: pd.DataFrame, gap_label: str) -> pd.DataFrame:
    """Compact, decision-first table: rank, place, action, gap, trust supply."""
    return pd.DataFrame({
        "Rank": ranked["Rank"],
        "District": ranked["district_name"],
        "State": ranked["state_ut"],
        "Action": ranked["Action"],
        gap_label: pd.to_numeric(ranked["gap"], errors="coerce"),
        "Trust supply %": pd.to_numeric(ranked["trustworthy_supply_rate"], errors="coerce") * 100,
    })


def render(districts: pd.DataFrame, specialty: str) -> None:
    ranked_all, gap_label = _ranked_districts(districts, specialty)
    ui.tab_intro(
        "Care-gap leaderboard",
        f"{specialty} · ranked by need, supply, and evidence — with a next action",
    )
    if ranked_all.empty:
        st.info("No district rows are available for this specialty lens.")
        return

    top = ranked_all.iloc[0]
    deploy_count = int(districts["planning_category"].eq("real_desert_candidate").sum())

    # ============================ FIRST GLANCE ===============================
    # 1) The wow stat — single bold anchor (honest, recomputed live).
    zero_trust, wow_n, wow_pct = _wow_stat(ranked_all)
    _wow_banner(zero_trust, wow_n, wow_pct)

    # 2) ≤2 KPI cards: where to act, and how big the deploy queue is.
    ui.kpi_row(
        [
            (
                "Top district",
                f"{top.get('district_name', 'unknown')}, {top.get('state_ut', 'unknown')}",
                f"{_action_label(top.get('planning_category'))} · {gap_label} {_fmt_num(top.get('gap'))}",
            ),
            ("Deploy candidates", f"{deploy_count:,}", "Strong unmet-need signal"),
        ],
        tone_each=[_action_tone(top.get("planning_category")), "deploy"],
    )

    # 3) Short ranked list — the calm "where to act next", grouped into one frosted
    #    panel (full table stays opt-in below).
    shortlist = ranked_all.head(_SHORTLIST_N).copy()
    with _glass_panel():
        ui.panel_header(f"Where to act next · top {_SHORTLIST_N}")
        ev = st.dataframe(
            _shortlist_table(shortlist, gap_label),
            hide_index=True,
            width="stretch",
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                gap_label: st.column_config.NumberColumn(
                    f"{gap_label} ▲ worse", format="%.2f",
                    help="Higher = more unmet need with less trustworthy supply."),
                "Trust supply %": st.column_config.ProgressColumn(
                    "Trust supply ▲ better", format="%d%%", min_value=0, max_value=100,
                    help="Share of observed facilities passing trust checks. Higher is better."),
            },
        )
        st.caption("Select a row to inspect a district. Full ranking and the desert "
                   "fingerprints are in the expanders below.")

    # 4) Selected district → the one rich, but still calm, drill-down panel,
    #    with the inline "add to My Plan" affordances (E8).
    selected = _selected_or_first(ev, shortlist)
    if selected is not None:
        action = _action_label(selected.get("planning_category"))
        ui.decision_banner(
            f"{action}: {selected.get('district_name', 'unknown')}, {selected.get('state_ut', 'unknown')}",
            f"{gap_label} {_fmt_num(selected.get('gap'))} · trust supply "
            f"{_fmt_pct(selected.get('trustworthy_supply_rate'))} · uncertainty "
            f"{str(selected.get('district_uncertainty_level', 'unknown')).title()}",
            _action_tone(selected.get("planning_category")),
        )
        ui.region_detail(selected, specialty, districts)
        _plan_affordances(selected, gap_label)

    # ===================== ONE-CLICK DEPTH (sub-nav) ========================
    # E7: a single segmented control swaps ONE panel in place — no scrolling
    # through stacked expanders. Default to the most useful sub-view (Ranking).
    st.markdown('<div style="margin-top:.6rem"></div>', unsafe_allow_html=True)
    sub = st.segmented_control(
        "Sub-view",
        ["Ranking", "At a glance", "Method & caveats", "My Plan"],
        default="Ranking",
        label_visibility="collapsed",
        key="care_gap_subview",
        width="stretch",
    ) or "Ranking"

    if sub == "Ranking":
        _panel_ranking(ranked_all, gap_label)
    elif sub == "At a glance":
        _panel_at_a_glance(districts)
    elif sub == "Method & caveats":
        _panel_method(districts, wow_n)
    else:
        _panel_my_plan()


# =============================== SUB-VIEW PANELS =============================
# Each panel is the swapped-in content for one segmented choice. They hold the
# depth that used to live in three stacked ``ui.detail`` expanders.


def _plan_affordances(selected: pd.Series, gap_label: str) -> None:
    """Inline 'add to My Plan' row on the drill-down: shortlist pill + quick note.

    Persists via ``decisions.toggle_shortlist`` / ``decisions.save_note`` and
    surfaces the returned ``persistence_status()`` detail as a tiny caption."""
    district = str(selected.get("district_name", "") or "").strip()
    state = str(selected.get("state_ut", "") or "").strip()
    geography_id = f"{district}|{state}"
    label = f"{district}, {state}" if state else district
    key = geography_id.replace(" ", "_")

    try:
        shortlisted = decisions.is_shortlisted(geography_id)
    except Exception:
        shortlisted = False

    with _glass_panel():
        ui.panel_header("Add to My Plan")
        c1, c2 = st.columns([1.1, 1.9])
        with c1:
            verb = "★ Shortlisted" if shortlisted else "☆ Shortlist this district"
            if st.button(verb, key=f"gap_short_{key}", width="stretch"):
                status = decisions.toggle_shortlist(
                    geography_id, label=label,
                    reason=f"Flagged from the care-gap leaderboard · {gap_label} "
                           f"{_fmt_num(selected.get('gap'))}.",
                ) or {}
                st.toast("Shortlist updated.", icon="★")
                st.caption(status.get("detail", ""))
        with c2:
            with st.form(key=f"gap_note_{key}", clear_on_submit=True):
                note = st.text_input(
                    "Quick note", key=f"gap_note_in_{key}",
                    placeholder="e.g. confirm zero-facility status before deploying",
                    label_visibility="collapsed",
                )
                if st.form_submit_button("Save note") and note.strip():
                    status = decisions.save_note(geography_id, note.strip()) or {}
                    st.toast("Note saved.", icon="📝")
                    st.caption(status.get("detail", ""))
        st.caption("Saved actions survive reload — see them in the My Plan sub-view below.")


def _panel_ranking(ranked_all: pd.DataFrame, gap_label: str) -> None:
    """Full leaderboard: action filter + action-mix chart + the 30-row table."""
    filter_choice = st.segmented_control(
        "Action filter",
        list(ACTION_FILTERS.keys()),
        default="All",
        label_visibility="collapsed",
        key="care_gap_action_filter",
        width="stretch",
    )
    filter_choice = filter_choice or "All"
    allowed = ACTION_FILTERS[filter_choice]
    ranked = (ranked_all if allowed is None
              else ranked_all[ranked_all["planning_category"].isin(allowed)])
    ranked = ranked.head(30).copy()

    if ranked.empty:
        st.info("No districts match this action filter.")
        return

    mix = (
        ranked_all["Action"].value_counts()
        .rename_axis("Action")
        .reset_index(name="Districts")
    )
    ui.panel_header("Action mix")
    st.altair_chart(charts.action_mix(mix), use_container_width=True)

    table = pd.DataFrame({
        "Rank": ranked["Rank"],
        "District": ranked["district_name"],
        "State": ranked["state_ut"],
        "Action": ranked["Action"],
        gap_label: pd.to_numeric(ranked["gap"], errors="coerce"),
        "Need": pd.to_numeric(ranked["health_need_score"], errors="coerce"),
        "Trust supply %": pd.to_numeric(ranked["trustworthy_supply_rate"], errors="coerce") * 100,
        "Uncertainty": ranked["district_uncertainty_level"].astype(str).str.title(),
        "Decision logic": ranked["Decision logic"],
    })
    ui.panel_header("Action queue")
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        height=430,
        column_config={
            "Rank": st.column_config.NumberColumn(format="%d"),
            gap_label: st.column_config.NumberColumn(
                f"{gap_label} ▲ worse", format="%.2f",
                help="Higher = more unmet need with less trustworthy supply."),
            "Need": st.column_config.ProgressColumn(
                "Need ▲ worse", format="%.2f", min_value=0, max_value=1,
                help="NFHS health-burden score. Higher is worse."),
            "Trust supply %": st.column_config.ProgressColumn(
                "Trust supply ▲ better", format="%d%%", min_value=0, max_value=100,
                help="Share of observed facilities passing trust checks. Higher is better."),
        },
    )


def _panel_at_a_glance(districts: pd.DataFrame) -> None:
    """Desert fingerprints: small-multiples of the worst districts' condition gaps."""
    st.altair_chart(
        charts.small_multiples_deserts(districts, data.district_top_conditions, n=6),
        use_container_width=True,
    )
    st.caption("Each panel = one of the worst care-gap districts · bars = its top "
               "medical-condition gaps · deeper red = further above the national median.")


def _panel_method(districts: pd.DataFrame, wow_n: int) -> None:
    """Methodology / honesty note: how the ranking is built and what it is not."""
    _desert = districts.get("zero_facility_desert")
    if _desert is not None:
        n_desert = int(_desert.fillna(False).astype(bool).sum())
        top50 = districts.nlargest(50, "care_gap_score")
        n_top = int(top50.get("zero_facility_desert", pd.Series(False, index=top50.index))
                    .fillna(False).astype(bool).sum())
        st.markdown(
            f"**{n_desert} districts have zero mapped facilities** — and they hold "
            f"**{n_top} of the top 50** care gaps. Facility-count maps miss them; "
            "this ranking surfaces them by leading with NFHS health need and the "
            "absence of trustworthy supply."
        )
    st.markdown(
        "Care-gap score = **0.55 need · 0.25 supply scarcity · 0.20 low trust**. "
        f"The wow stat above recomputes live across the worst {wow_n} districts."
    )
    st.caption(
        "Source: NFHS-5 district health indicators (2019–21) + web-derived FDR facility "
        "snapshot · 706 districts · observed FDR rows are claims, not a verified facility "
        "census · scores are proxy decision-support, not gold-validated."
    )


def _panel_my_plan() -> None:
    """E8: the visible persistence surface — shortlisted districts, saved notes,
    and a 'Persisted to <backend> ✓' badge. Delegates to the reusable helper in
    ``decisions`` so the logic stays tidy and shared."""
    decisions.render_my_plan()
