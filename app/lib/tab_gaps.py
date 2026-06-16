"""Top care gaps tab: a calm first glance (wow stat + top action) with all
depth opt-in behind expanders.

Entry point: ``render(districts, specialty) -> None``.

Layout philosophy (see DESIGN_SYSTEM.md density rule): the default view answers
"where is the worst gap and what do I do." Everything heavier — the full
leaderboard, the desert small-multiples, the condition/methodology explainers —
lives behind ``ui.detail(...)`` expanders. The next-wave gaps agent edits this
file only; new chart/helper needs are LOCAL functions here.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from . import data, ui, charts
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
    """The single bold anchor of the first glance (danger tone, tokenized)."""
    st.markdown(
        '<div style="margin:.2rem 0 .55rem;padding:.85rem 1.1rem;border-radius:12px;'
        'border:1px solid rgba(255,82,82,.34);background:linear-gradient(90deg,'
        'rgba(255,82,82,.12),rgba(255,82,82,.02));display:flex;align-items:baseline;'
        'gap:.7rem;flex-wrap:wrap">'
        '<span style="font-size:2.1rem;font-weight:800;color:#ff8d8d;line-height:1;'
        'font-variant-numeric:tabular-nums">'
        f'{zero_trust}/{n}</span>'
        '<span style="color:#eaf2ff;font-size:1.0rem;line-height:1.35">of the worst '
        'care-gap districts have <strong>0% trustworthy supply</strong> — '
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

    # 3) Short ranked list — the calm "where to act next" (full table is opt-in).
    ui.panel_header(f"Where to act next · top {_SHORTLIST_N}")
    shortlist = ranked_all.head(_SHORTLIST_N).copy()
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

    # 4) Selected district → the one rich, but still calm, drill-down panel.
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

    # =========================== OPT-IN DEPTH ================================
    # Full leaderboard: action filter + action-mix chart + the 30-row table.
    with ui.detail("Full district ranking"):
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
        else:
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

    # Desert fingerprints: small-multiples (heavy, so opt-in).
    with ui.detail("Top deserts at a glance"):
        st.altair_chart(
            charts.small_multiples_deserts(districts, data.district_top_conditions, n=6),
            use_container_width=True,
        )
        st.caption("Each panel = one of the worst care-gap districts · bars = its top "
                   "medical-condition gaps · deeper red = further above the national median.")

    # Methodology / honesty note: how the ranking is built and what it is not.
    with ui.detail("How this ranking is built & data caveats"):
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
