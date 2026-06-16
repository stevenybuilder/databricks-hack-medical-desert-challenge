"""Medical Desert Navigator.

Phase 1: VF-Match-style hexbin + facility map (zoom, click-to-fly, cited detail).
Phase 2: Top Care Gaps leaderboard + region detail (conditions + cited evidence).

Run locally:
    .venv/bin/streamlit run app/app.py
"""
from __future__ import annotations

import html

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from lib import config, data, ui
from lib import decisions, interventions, simulator, trust


def _ensure_ui_helpers() -> None:
    """Patch missing UI helpers in long-running Streamlit sessions.

    Streamlit can keep an imported submodule alive across reruns. If `app.py`
    reloads before `lib.ui`, the app can see a stale module without newer helper
    functions. These fallbacks keep the running demo from crashing; the canonical
    implementations still live in `app/lib/ui.py`.
    """

    if not hasattr(ui, "stat_card"):
        def stat_card(label: str, value: str, caption: str = "", tone: str = "neutral") -> None:
            tone_class = {
                "deploy": "mdn-card--deploy",
                "verify": "mdn-card--verify",
                "danger": "mdn-card--danger",
                "info": "mdn-card--info",
            }.get(tone, "")
            st.markdown(
                f"""
                <div class="mdn-card {tone_class}">
                  <div class="mdn-card-kicker">{html.escape(str(label))}</div>
                  <div class="mdn-card-value">{html.escape(str(value))}</div>
                  <div class="mdn-card-caption">{html.escape(str(caption))}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        ui.stat_card = stat_card

    if not hasattr(ui, "decision_banner"):
        def decision_banner(title: str, subtitle: str, tone: str = "info") -> None:
            pill_class = {
                "deploy": "mdn-pill--deploy",
                "verify": "mdn-pill--verify",
                "danger": "mdn-pill--danger",
                "info": "mdn-pill--info",
            }.get(tone, "mdn-pill--muted")
            label = {
                "deploy": "Deploy",
                "verify": "Verify",
                "danger": "Caution",
                "info": "Evidence",
            }.get(tone, "Context")
            st.markdown(
                f"""
                <div class="mdn-decision-banner">
                  <span class="mdn-pill {pill_class}">{html.escape(label)}</span>
                  <div>
                    <strong>{html.escape(str(title))}</strong>
                    <span>{html.escape(str(subtitle))}</span>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        ui.decision_banner = decision_banner

    if not hasattr(ui, "workflow_rail"):
        def workflow_rail(steps: list[tuple[str, str]]) -> None:
            body = "".join(
                f"""<div class="mdn-rail-step"><b>{html.escape(title)}</b>
                <span>{html.escape(text)}</span></div>"""
                for title, text in steps
            )
            st.markdown(f'<div class="mdn-rail">{body}</div>', unsafe_allow_html=True)

        ui.workflow_rail = workflow_rail


_ensure_ui_helpers()

st.set_page_config(page_title=config.APP_TITLE, layout="wide", page_icon="🩺")
ui.inject_css()


@st.cache_data(show_spinner="Loading facilities…")
def _facilities():
    return data.load_facilities()


@st.cache_data(show_spinner="Loading districts…")
def _districts():
    return data.load_districts()


def _picked_facility(state):
    """Pull the single clicked facility object out of a pydeck selection state."""
    try:
        objs = state["selection"]["objects"]
        fac = objs.get("facilities")
        return fac[0] if fac else None
    except (TypeError, KeyError, AttributeError):
        return None


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


def map_tab(facilities: pd.DataFrame, specialty: str) -> None:
    st.markdown(
        f"""
        <div class="mdn-earth-strip">
          <div>
            <strong>India care-gap atlas</strong>
            <span>{specialty} lens · trust-weighted demand, supply, and uncertainty</span>
          </div>
          <div class="mdn-status-dot"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4, c5 = st.columns([1.5, 1.2, 0.9, 0.9, 1.1])
    with c1:
        metric_label = st.selectbox("Layer", list(config.METRICS.keys()),
                                    index=list(config.METRICS).index(config.DEFAULT_METRIC))
    with c2:
        basemap = st.selectbox("Style", list(config.MAP_STYLES.keys()),
                               index=list(config.MAP_STYLES).index(config.DEFAULT_MAP_STYLE))
    with c3:
        resolution = st.slider("Cell size", 3, 6, config.DEFAULT_H3_RESOLUTION)
    with c4:
        include_geo_flagged = st.toggle("Flagged geo", value=False,
                                        help="Include impossible / out-of-India coordinates")
    with c5:
        show_points = st.checkbox("Facility dots", value=True,
                                  help="Individual facility dots with detail and source evidence")

    filtered = data.filter_facilities(facilities, specialty, include_geo_flagged)
    cells = data.hexbin(filtered, metric_label, resolution)
    points = data.facility_points(filtered) if show_points else None
    higher_is_worse = config.METRICS[metric_label][2]

    map_col, panel_col = st.columns([4.25, 1.08], gap="medium")

    with map_col:
        if cells.empty:
            st.info("No mappable facilities for this selection.")
            return

        # recenter on the previously-clicked facility (click-to-fly)
        prior = _picked_facility(st.session_state.get("map"))
        if prior:
            view = pdk.ViewState(latitude=float(prior["lat"]), longitude=float(prior["lon"]),
                                 zoom=10, pitch=0)
        else:
            view = pdk.ViewState(**config.INDIA_VIEW)

        layers = [pdk.Layer(
            "H3HexagonLayer", id="hexbins", data=cells,
            get_hexagon="h3", get_fill_color="fill_color",
            pickable=True, extruded=False, stroked=True, filled=True,
            opacity=0.55 if show_points else 0.82, coverage=0.92,
            get_line_color=[255, 255, 255, 60], line_width_min_pixels=0.5,
        )]
        if points is not None and not points.empty:
            layers.append(pdk.Layer(
                "ScatterplotLayer", id="facilities", data=points,
                get_position="[lon, lat]", get_fill_color="point_color",
                get_radius=600, radius_min_pixels=2.5, radius_max_pixels=9,
                pickable=True, auto_highlight=True, stroked=True,
                get_line_color=[255, 255, 255, 140], line_width_min_pixels=0.4,
            ))

        tooltip = {"html": "{tip}",
                   "style": {"backgroundColor": "#07111f", "color": "#eaf2ff",
                             "fontSize": "12px", "borderRadius": "8px",
                             "border": "1px solid rgba(148,163,184,.34)",
                             "padding": "8px"}}
        deck = pdk.Deck(layers=layers, initial_view_state=view,
                        map_style=config.MAP_STYLES[basemap], tooltip=tooltip)
        event = st.pydeck_chart(deck, width="stretch", height=680, key="map",
                                on_select="rerun", selection_mode="single-object")
        ui.legend("Lower", "Higher", higher_is_worse)

        lc, rc = st.columns([3, 1])
        lc.caption(f"{len(cells):,} regions · {len(filtered):,} facilities · "
                   "scroll to zoom · select a facility for source evidence.")
        if rc.button("Reset view", width="stretch"):
            st.session_state.pop("map", None)
            st.rerun()

        picked = _picked_facility(event) or prior
        if picked:
            ui.facility_card(picked)

    with panel_col:
        st.markdown('<div class="mdn-panel-h">Scene inspector</div>', unsafe_allow_html=True)
        st.metric("Facilities shown", f"{len(filtered):,}")
        st.metric("Passed readiness checks", f"{int(filtered['trustworthy_supply_signal'].sum()):,}",
                  help="Automated checks only, not human verification.")
        review = int(filtered["needs_human_review"].sum())
        st.metric("Need review", f"{review:,}",
                  delta=f"{(review/max(len(filtered),1))*100:.0f}% of shown", delta_color="inverse")
        st.metric("Contradicted / geo-invalid",
                  f"{int(filtered['contradicted_or_geo_invalid_signal'].sum()):,}")
        readiness = pd.to_numeric(filtered.get("data_readiness_score", pd.Series(dtype=float)),
                                  errors="coerce")
        semantic = pd.to_numeric(filtered.get("semantic_data_quality_score", pd.Series(dtype=float)),
                                 errors="coerce")
        posture = pd.DataFrame([
            {
                "Signal": "Mean readiness",
                "Value": "unknown" if pd.isna(readiness.mean()) else f"{readiness.mean():.2f}",
            },
            {
                "Signal": "Mean semantic quality",
                "Value": "unknown" if pd.isna(semantic.mean()) else f"{semantic.mean():.2f}",
            },
            {
                "Signal": "Review load",
                "Value": f"{(review / max(len(filtered), 1)):.0%}",
            },
        ])
        st.dataframe(posture, hide_index=True, width="stretch", height=145)
        if not cells.empty:
            st.markdown('<div class="mdn-panel-h">Distribution across regions</div>',
                        unsafe_allow_html=True)
            counts, edges = np.histogram(cells["value"].dropna(), bins=18)
            hist = pd.DataFrame({"bin": np.round((edges[:-1] + edges[1:]) / 2, 2),
                                 "regions": counts}).set_index("bin")
            st.bar_chart(hist, height=170, color="#66d9ff")


def gaps_tab(districts: pd.DataFrame, specialty: str) -> None:
    ranked_all, gap_label = _ranked_districts(districts, specialty)
    st.markdown(
        f"""
        <div class="mdn-earth-strip">
          <div>
            <strong>Mission planner</strong>
            <span>{specialty} lens · need, supply, evidence quality, and next action</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if ranked_all.empty:
        st.info("No district rows are available for this specialty lens.")
        return

    deploy_count = int(districts["planning_category"].eq("real_desert_candidate").sum())
    verify_count = int(districts["planning_category"].eq("phantom_desert_or_verification_gap").sum())
    fragile_count = int(districts["planning_category"].isin([
        "phantom_desert_or_verification_gap",
        "supply_record_quality_problem",
    ]).sum())
    higher_uncertainty = int(districts["district_uncertainty_level"].astype(str).str.lower().eq("higher").sum())
    top = ranked_all.iloc[0]

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.stat_card(
            "Top district",
            f"{top.get('district_name', 'unknown')}, {top.get('state_ut', 'unknown')}",
            f"{_action_label(top.get('planning_category'))} · {gap_label} {_fmt_num(top.get('gap'))}",
            _action_tone(top.get("planning_category")),
        )
    with c2:
        ui.stat_card("Deploy candidates", f"{deploy_count:,}", "Strong unmet-need signal", "deploy")
    with c3:
        ui.stat_card("Verify-first districts", f"{verify_count:,}", "Fragile evidence can reverse the call", "verify")
    with c4:
        ui.stat_card("Higher uncertainty", f"{higher_uncertainty:,}", f"{fragile_count:,} fragile action districts", "danger")

    ui.workflow_rail([
        ("Need", "NFHS patient-condition burden"),
        ("Supply", "Trustworthy specialty signals"),
        ("Evidence", "Source text, joins, geo quality"),
        ("Interval", "Wilson and proxy uncertainty"),
        ("Action", "Deploy, verify, fix, refer, or monitor"),
    ])

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
    ranked = ranked_all if allowed is None else ranked_all[ranked_all["planning_category"].isin(allowed)]
    ranked = ranked.head(30).copy()

    if ranked.empty:
        st.info("No districts match this action filter.")
        return

    mix = (
        ranked_all["Action"].value_counts()
        .rename_axis("Action")
        .reset_index(name="Districts")
        .set_index("Action")
    )
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

    queue_col, detail_col = st.columns([1.18, 1], gap="medium")
    with queue_col:
        st.markdown('<div class="mdn-panel-h">Action queue</div>', unsafe_allow_html=True)
        st.bar_chart(mix, height=170, color="#66d9ff")
        ev = st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            height=430,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Rank": st.column_config.NumberColumn(format="%d"),
                gap_label: st.column_config.NumberColumn(format="%.2f"),
                "Need": st.column_config.ProgressColumn("Need", format="%.2f", min_value=0, max_value=1),
                "Trust supply %": st.column_config.ProgressColumn(
                    "Trust supply", format="%d%%", min_value=0, max_value=100
                ),
            },
        )

    selected = _selected_or_first(ev, ranked)
    with detail_col:
        if selected is None:
            st.info("No district selected.")
            return
        action = _action_label(selected.get("planning_category"))
        ui.decision_banner(
            f"{action}: {selected.get('district_name', 'unknown')}, {selected.get('state_ut', 'unknown')}",
            f"{gap_label} {_fmt_num(selected.get('gap'))} · trust supply {_fmt_pct(selected.get('trustworthy_supply_rate'))} · uncertainty {str(selected.get('district_uncertainty_level', 'unknown')).title()}",
            _action_tone(selected.get("planning_category")),
        )
        ui.region_detail(selected, specialty)


def uncertainty_tab(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    snapshot = data.quality_snapshot(facilities, districts)
    total = max(snapshot["facility_rows"], 1)
    district_queue = data.active_district_queue()
    facility_queue = data.active_facility_queue()
    geo_candidates = data.geo_validation_candidates(facilities, top_n=50)
    decision_volume, decision_concepts, decision_rules, decision_policy = data.statistical_decision_report()

    st.markdown(
        """
        <div class="mdn-earth-strip">
          <div>
            <strong>Evidence console</strong>
            <span>Semantic missingness, confidence intervals, source agreement, and active uncertainty queues</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    s1, s2, s3, s4 = st.columns(4)
    with s1:
        ui.stat_card(
            "Review load",
            _fmt_pct(snapshot["needs_human_review"] / total),
            f"{snapshot['needs_human_review']:,} of {total:,} facility rows",
            "verify",
        )
    with s2:
        ui.stat_card(
            "Trusted supply",
            _fmt_pct(snapshot["trustworthy_supply"] / total),
            f"{snapshot['trustworthy_supply']:,} rows passed automated checks",
            "deploy",
        )
    with s3:
        ui.stat_card(
            "Geo / contradiction risk",
            f"{snapshot['contradicted_or_geo_invalid']:,}",
            "Rows that can move supply to the wrong place",
            "danger",
        )
    with s4:
        ui.stat_card(
            "Active queue",
            f"{len(district_queue):,} / {len(facility_queue):,}",
            "District and facility rows ranked by value of information",
            "info",
        )

    ui.workflow_rail([
        ("Claim", "Crawl and extracted facility text"),
        ("Clean", "Semantic nulls, joins, and geo checks"),
        ("Estimate", "Capacity/doctor intervals where sparse"),
        ("Corroborate", "HFR, PM-JAY, India Post, OSM, geocoders"),
        ("Decide", "Recommend, verify, enrich, or abstain"),
    ])

    view = st.segmented_control(
        "Evidence view",
        ["Overview", "Triage queues", "Geo source agreement", "Missingness", "Model policy"],
        default="Overview",
        label_visibility="collapsed",
        key="uncertainty_console_view",
        width="stretch",
    )
    view = view or "Overview"

    if view == "Overview":
        o1, o2 = st.columns([1, 1], gap="medium")
        with o1:
            st.markdown('<div class="mdn-panel-h">What can break the recommendation</div>',
                        unsafe_allow_html=True)
            st.dataframe(
                data.messiness_breakdown(facilities, districts),
                hide_index=True,
                width="stretch",
                height=285,
            )
        with o2:
            st.markdown('<div class="mdn-panel-h">What the app is allowed to claim</div>',
                        unsafe_allow_html=True)
            st.dataframe(
                data.explainability_model_card(),
                hide_index=True,
                width="stretch",
                height=285,
            )
        if not decision_volume.empty:
            st.markdown('<div class="mdn-panel-h">Decision volume proof</div>',
                        unsafe_allow_html=True)
            focus_groups = ["Facility quality flags", "District planning category"]
            proof = decision_volume[decision_volume["category_group"].isin(focus_groups)].copy()
            chart = proof[proof["category_group"].eq("Facility quality flags")].copy()
            if not chart.empty:
                chart = chart.sort_values("rows", ascending=False).head(8)
                st.bar_chart(chart.set_index("category")["rows"], height=220, color="#66d9ff")
            proof = proof.rename(columns={
                "category_group": "Group",
                "grain": "Grain",
                "category": "Category",
                "rows": "Rows",
                "denominator": "Denominator",
            })
            st.dataframe(
                proof[["Group", "Grain", "Category", "Rows", "Denominator", "Pct", "Wilson 95%", "Bayes 95%"]],
                hide_index=True,
                width="stretch",
                height=260,
                column_config={
                    "Rows": st.column_config.NumberColumn(format="%d"),
                    "Denominator": st.column_config.NumberColumn(format="%d"),
                },
            )

    elif view == "Triage queues":
        focus = st.segmented_control(
            "Queue type",
            ["Districts", "Facilities"],
            default="Districts",
            label_visibility="collapsed",
            key="active_queue_type",
            width="stretch",
        )
        focus = focus or "Districts"
        if focus == "Districts":
            if district_queue.empty:
                st.info("No active district queue artifact found.")
            else:
                dq_source = district_queue.head(40).copy()
                top_action = str(dq_source.get("active_learning_action", pd.Series(["unknown"])).mode().iloc[0])
                q1, q2, q3 = st.columns(3)
                with q1:
                    ui.stat_card("Rows ranked", f"{len(district_queue):,}", "Districts with decision-fragile evidence", "info")
                with q2:
                    ui.stat_card("Top action", top_action.replace("_", " "), "Dominant value-of-information route", "verify")
                with q3:
                    ui.stat_card("Median CI width", _fmt_num(dq_source.get("aggregate_ci_width", pd.Series(dtype=float)).median()), "Aggregate uncertainty span", "danger")
                dq = dq_source.rename(columns={
                    "active_uncertainty_rank": "Rank",
                    "active_uncertainty_score": "Score",
                    "active_learning_action": "Action",
                    "state_ut": "State",
                    "district_name": "District",
                    "planning_category": "Planning category",
                    "observed_facility_rows": "Observed rows",
                    "care_gap_score": "Care gap",
                    "trust_gap_score": "Trust gap",
                    "aggregate_ci_width": "CI width",
                    "sample_size_uncertainty_score": "Sample uncertainty",
                })
                left, right = st.columns([1.2, 1], gap="medium")
                with left:
                    ev = st.dataframe(
                        dq[[
                            "Rank", "Score", "Action", "State", "District",
                            "Planning category", "Observed rows", "Care gap",
                            "Trust gap", "CI width", "Sample uncertainty",
                        ]],
                        hide_index=True,
                        width="stretch",
                        height=430,
                        on_select="rerun",
                        selection_mode="single-row",
                        column_config={
                            "Score": st.column_config.NumberColumn(format="%.3f"),
                            "Care gap": st.column_config.NumberColumn(format="%.3f"),
                            "Trust gap": st.column_config.NumberColumn(format="%.3f"),
                            "CI width": st.column_config.NumberColumn(format="%.3f"),
                            "Sample uncertainty": st.column_config.NumberColumn(format="%.3f"),
                        },
                    )
                row = _selected_or_first(ev, dq_source)
                with right:
                    if row is not None:
                        ui.active_district_detail(row, specialty)
        else:
            if facility_queue.empty:
                st.info("No active facility queue artifact found.")
            else:
                fq_source = facility_queue.head(40).copy()
                f1, f2, f3 = st.columns(3)
                with f1:
                    ui.stat_card("Rows ranked", f"{len(facility_queue):,}", "Facility claims most likely to change decisions", "info")
                with f2:
                    ui.stat_card("Median trust band", _fmt_num((fq_source["proxy_trust_interval_high"] - fq_source["proxy_trust_interval_low"]).median()), "Proxy interval width", "verify")
                with f3:
                    ui.stat_card("Median geo band", _fmt_km(fq_source.get('pre_geocode_uncertainty_band_high_km', pd.Series(dtype=float)).median()), "Before external source agreement", "danger")
                fq = fq_source.rename(columns={
                    "active_uncertainty_rank": "Rank",
                    "active_uncertainty_score": "Score",
                    "active_learning_action": "Action",
                    "external_validation_action": "External action",
                    "facility_name": "Facility",
                    "facilityTypeId": "Type",
                    "state_ut": "State",
                    "district_name": "District",
                    "proxy_trust_interval_low": "Trust low",
                    "proxy_trust_interval_high": "Trust high",
                    "pre_geocode_uncertainty_band_high_km": "Geo band high km",
                    "first_source_url": "Source",
                })
                show = [
                    "Rank", "Score", "Action", "External action", "Facility",
                    "Type", "State", "District", "Trust low", "Trust high",
                    "Geo band high km", "Source",
                ]
                left, right = st.columns([1.2, 1], gap="medium")
                with left:
                    ev = st.dataframe(
                        fq[[c for c in show if c in fq]],
                        hide_index=True,
                        width="stretch",
                        height=430,
                        on_select="rerun",
                        selection_mode="single-row",
                        column_config={
                            "Score": st.column_config.NumberColumn(format="%.3f"),
                            "Trust low": st.column_config.NumberColumn(format="%.3f"),
                            "Trust high": st.column_config.NumberColumn(format="%.3f"),
                            "Geo band high km": st.column_config.NumberColumn(format="%.1f"),
                            "Source": st.column_config.LinkColumn("Source"),
                        },
                    )
                row = _selected_or_first(ev, fq_source)
                with right:
                    if row is not None:
                        ui.active_facility_detail(row)

    elif view == "Geo source agreement":
        if geo_candidates.empty:
            st.info("No geo-validation candidates artifact found.")
        else:
            g1, g2, g3 = st.columns(3)
            with g1:
                ui.stat_card("Candidates", f"{len(geo_candidates):,}", "Highest-priority rows for geocoder/source checks", "info")
            with g2:
                ui.stat_card("Median planning band", _fmt_km(geo_candidates["pre_geocode_uncertainty_band_high_km"].median()), "Pre-geocode high band", "verify")
            with g3:
                ui.stat_card("Max priority", _fmt_num(geo_candidates["external_validation_priority_score"].max(), 2), "Clinical impact plus geo fragility", "danger")
        p1, p2 = st.columns([1.05, 1], gap="medium")
        with p1:
            st.markdown('<div class="mdn-panel-h">Validation pipeline</div>', unsafe_allow_html=True)
            st.dataframe(data.geo_validation_steps(), hide_index=True, width="stretch", height=245)
        with p2:
            st.markdown('<div class="mdn-panel-h">Acceptance rules</div>', unsafe_allow_html=True)
            st.dataframe(data.geo_quality_rules(), hide_index=True, width="stretch", height=245)

        priors = data.geocoder_uncertainty_priors()
        if not priors.empty:
            st.markdown('<div class="mdn-panel-h">Geocoder uncertainty priors</div>',
                        unsafe_allow_html=True)
            st.dataframe(
                priors,
                hide_index=True,
                width="stretch",
                height=220,
                column_config={
                    "proxy_confidence_low": st.column_config.NumberColumn(format="%.2f"),
                    "proxy_confidence_high": st.column_config.NumberColumn(format="%.2f"),
                    "planning_uncertainty_radius_km": st.column_config.NumberColumn(format="%.1f"),
                },
            )

        if not geo_candidates.empty:
            st.markdown('<div class="mdn-panel-h">Geo-validation candidates</div>',
                        unsafe_allow_html=True)
            geo_source = geo_candidates.head(35).copy()
            geo_display = geo_source.rename(columns={
                "facility_name": "Facility",
                "facilityTypeId": "Type",
                "geo_review_reason": "Reason",
                "geo_review_score": "Priority",
                "geo_quality": "Current geo quality",
                "geo_distance_km_to_pincode_centroid": "PIN distance km",
                "current_coordinates": "Current coordinates",
                "address_city": "City",
                "address_stateOrRegion": "State",
                "address_zipOrPostcode": "PIN",
                "geocoder_query": "Geocoder query",
                "external_validation_action": "External action",
                "external_validation_priority_score": "External priority",
                "pre_geocode_uncertainty_band_high_km": "Geo band high km",
                "fuzzy_precheck_status": "Fuzzy precheck",
            })
            geo_cols = [
                "Facility", "Type", "Reason", "External action", "External priority",
                "Priority", "Current geo quality", "PIN distance km", "Geo band high km",
                "Fuzzy precheck", "City", "State", "PIN", "Geocoder query",
            ]
            left, right = st.columns([1.25, 1], gap="medium")
            with left:
                geo_event = st.dataframe(
                    geo_display[[c for c in geo_cols if c in geo_display]],
                    hide_index=True,
                    width="stretch",
                    height=390,
                    on_select="rerun",
                    selection_mode="single-row",
                    column_config={
                        "Priority": st.column_config.NumberColumn(format="%.1f"),
                        "External priority": st.column_config.NumberColumn(format="%.3f"),
                        "PIN distance km": st.column_config.NumberColumn(format="%.1f"),
                        "Geo band high km": st.column_config.NumberColumn(format="%.1f"),
                    },
                )
            row = _selected_or_first(geo_event, geo_source)
            with right:
                if row is not None:
                    ui.geo_candidate_detail(row)

        st.markdown('<div class="mdn-panel-h">External validation sources</div>',
                    unsafe_allow_html=True)
        st.dataframe(
            data.validation_sources(),
            hide_index=True,
            width="stretch",
            height=260,
            column_config={"URL": st.column_config.LinkColumn("URL")},
        )

    elif view == "Missingness":
        missing = data.missingness_summary(facilities)
        card_cols = st.columns(3)
        for col, (_, row) in zip(card_cols, missing.head(3).iterrows()):
            with col:
                ui.stat_card(
                    str(row["Incomplete area"]),
                    str(row["Pct of records"]),
                    f"{int(row['Rows']):,} rows need estimation, enrichment, or review",
                    "verify",
                )

        left, right = st.columns([1, 1], gap="medium")
        with left:
            st.markdown('<div class="mdn-panel-h">Incomplete fields and handling</div>',
                        unsafe_allow_html=True)
            st.dataframe(
                missing,
                hide_index=True,
                width="stretch",
                height=320,
                column_config={"Rows": st.column_config.NumberColumn(format="%d")},
            )
        with right:
            st.markdown('<div class="mdn-panel-h">Allowed treatments</div>',
                        unsafe_allow_html=True)
            st.dataframe(data.missing_data_methods(), hide_index=True, width="stretch", height=320)

        st.markdown('<div class="mdn-panel-h">Evidence review seed queue</div>',
                    unsafe_allow_html=True)
        qc1, qc2 = st.columns([1.2, 1])
        with qc1:
            focus = st.selectbox(
                "Queue focus",
                ["Highest-risk first", "Uncertainty review queue", "Contradictions and geo failures",
                 "Positive controls"],
            )
        with qc2:
            top_n = st.slider("Rows", 25, 150, 75, step=25)

        queue = data.verification_queue(facilities, specialty, focus, top_n=top_n)
        if queue.empty:
            st.info("No facilities match this queue focus for the selected specialty.")
        else:
            display = queue.rename(columns={
                "facility_name": "Facility",
                "facilityTypeId": "Type",
                "address_city": "City",
                "district_name": "District",
                "state_ut": "State",
                "service_signal": "Service signal",
                "primary_concern": "Primary concern",
                "verification_channel": "First action",
                "label_seed": "Seed label",
                "review_priority": "Priority",
                "data_readiness_score": "Readiness",
                "join_confidence": "Join confidence",
                "geo_quality": "Geo quality",
                "first_source_url": "Source",
            })
            show_cols = ["Facility", "Type", "City", "District", "State", "Service signal",
                         "Primary concern", "First action", "Seed label", "Priority",
                         "Readiness", "Join confidence", "Geo quality", "Source"]
            left, right = st.columns([1.25, 1], gap="medium")
            with left:
                ev = st.dataframe(
                    display[[c for c in show_cols if c in display]],
                    hide_index=True,
                    width="stretch",
                    height=390,
                    on_select="rerun",
                    selection_mode="single-row",
                    column_config={
                        "Priority": st.column_config.NumberColumn(format="%.1f"),
                        "Readiness": st.column_config.NumberColumn(format="%.2f"),
                        "Join confidence": st.column_config.NumberColumn(format="%.2f"),
                        "Source": st.column_config.LinkColumn("Source"),
                    },
                )
            row = _selected_or_first(ev, queue)
            with right:
                if row is not None:
                    ui.verification_detail(row)

        st.markdown('<div class="mdn-panel-h">Verification protocol</div>',
                    unsafe_allow_html=True)
        st.dataframe(
            data.verification_checks(),
            hide_index=True,
            width="stretch",
            height=215,
            column_config={"Priority": st.column_config.NumberColumn(format="%d")},
        )

    else:
        seed_summary, seed_breakdown, seed_report = data.golden_seed_report()
        model_summary, model_tasks, model_report = data.supervised_model_report()

        if not decision_volume.empty:
            st.markdown('<div class="mdn-panel-h">Decision category volumes and statistical policy</div>',
                        unsafe_allow_html=True)
            groups = sorted(decision_volume["category_group"].dropna().unique().tolist())
            preferred_group = "Facility quality flags"
            selected_group = st.selectbox(
                "Decision volume lens",
                groups,
                index=groups.index(preferred_group) if preferred_group in groups else 0,
            )
            shown = decision_volume[decision_volume["category_group"].eq(selected_group)].copy()
            shown = shown.rename(columns={
                "category_group": "Group",
                "grain": "Grain",
                "category": "Category",
                "rows": "Rows",
                "denominator": "Denominator",
                "exclusive": "Exclusive",
                "method_note": "Method note",
            })
            st.dataframe(
                shown[[
                    "Group", "Grain", "Category", "Rows", "Denominator",
                    "Pct", "Wilson 95%", "Bayes 95%", "Exclusive", "Method note",
                ]],
                hide_index=True,
                width="stretch",
                height=360,
                column_config={
                    "Rows": st.column_config.NumberColumn(format="%d"),
                    "Denominator": st.column_config.NumberColumn(format="%d"),
                },
            )

        p1, p2 = st.columns([1, 1], gap="medium")
        with p1:
            if not decision_concepts.empty:
                st.markdown('<div class="mdn-panel-h">Statistical concepts in use</div>',
                            unsafe_allow_html=True)
                st.dataframe(
                    decision_concepts[["Concept", "Use now", "Where applied", "Why relevant"]],
                    hide_index=True,
                    width="stretch",
                    height=300,
                )
        with p2:
            if not decision_rules.empty:
                st.markdown('<div class="mdn-panel-h">Decision rules</div>',
                            unsafe_allow_html=True)
                st.dataframe(
                    decision_rules[["Decision", "Rule", "Statistical role"]],
                    hide_index=True,
                    width="stretch",
                    height=300,
                )
        ev_policy = decision_policy.get("expected_value_policy", {})
        if ev_policy:
            ui.decision_banner(
                "Expected value, not blind confidence",
                "EV(action) = P(correct) * benefit - P(wrong) * harm - operating_cost. "
                f"Current probability source: {ev_policy.get('probability_source_now', 'proxy evidence score')}.",
                "info",
            )

        if not seed_summary.empty:
            st.markdown('<div class="mdn-panel-h">Golden prediction seed report</div>',
                        unsafe_allow_html=True)
            r1, r2 = st.columns([1, 1], gap="medium")
            with r1:
                st.dataframe(
                    seed_summary,
                    hide_index=True,
                    width="stretch",
                    height=240,
                    column_config={"Value": st.column_config.NumberColumn(format="%d")},
                )
            with r2:
                st.dataframe(
                    seed_breakdown,
                    hide_index=True,
                    width="stretch",
                    height=240,
                    column_config={"Rows": st.column_config.NumberColumn(format="%d")},
                )
            guardrails = seed_report.get("guardrails", [])
            if guardrails:
                st.caption("Guardrails: " + " · ".join(guardrails))

        if not model_summary.empty:
            st.markdown('<div class="mdn-panel-h">Supervised model trainer report</div>',
                        unsafe_allow_html=True)
            policy = model_report.get("model_policy", {})
            ui.decision_banner(
                "No gold labels, no accuracy claim",
                policy.get("why", "Rows become trainable only after source corroboration."),
                "verify",
            )
            m1, m2 = st.columns([1, 1], gap="medium")
            with m1:
                st.dataframe(model_summary, hide_index=True, width="stretch", height=230)
            with m2:
                st.dataframe(model_tasks, hide_index=True, width="stretch", height=230)
            st.caption("Upgrade path: " + policy.get("upgrade_path", ""))


def main() -> None:
    facilities = _facilities()
    districts = _districts()
    ui.header()

    lens_col, note_col = st.columns([1.05, 3.2], gap="medium")
    with lens_col:
        specialty = st.selectbox("Specialty lens", list(config.SPECIALTIES.keys()), index=0)
    with note_col:
        st.markdown(
            '<div class="mdn-orbit-note">NFHS health need, facility supply, source evidence, '
            'geocoding quality, and uncertainty intervals are surfaced together for planning.</div>',
            unsafe_allow_html=True,
        )

    primary_view = st.segmented_control(
        "Primary view",
        ["Map", "Top care gaps", "Interventions", "Scenario lab",
         "Uncertainty console", "Trust & conformal", "Decisions & feedback"],
        default="Map",
        label_visibility="collapsed",
        key="primary_view",
        width="stretch",
    )
    primary_view = primary_view or "Map"
    if primary_view == "Map":
        map_tab(facilities, specialty)
    elif primary_view == "Top care gaps":
        gaps_tab(districts, specialty)
    elif primary_view == "Interventions":
        interventions.render_interventions(facilities, districts, specialty)
    elif primary_view == "Scenario lab":
        simulator.render_simulator(facilities, districts, specialty)
    elif primary_view == "Uncertainty console":
        uncertainty_tab(facilities, districts, specialty)
    elif primary_view == "Trust & conformal":
        trust.render_trust(facilities, districts, specialty)
    else:
        decisions.render_decisions(facilities, districts, specialty)


if __name__ == "__main__":
    main()
