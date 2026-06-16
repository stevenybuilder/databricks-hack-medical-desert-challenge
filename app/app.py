"""Medical Desert Navigator.

Phase 1: VF-Match-style hexbin + facility map (zoom, click-to-fly, cited detail).
Phase 2: Top Care Gaps leaderboard + region detail (conditions + cited evidence).

Run locally:
    .venv/bin/streamlit run app/app.py
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pydeck as pdk
import streamlit as st

from lib import config, data, ui

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


def map_tab(facilities: pd.DataFrame, specialty: str) -> None:
    c1, c2, c3, c4, c5 = st.columns([1.5, 1.2, 0.9, 0.9, 1.1])
    with c1:
        metric_label = st.selectbox("Map layer", list(config.METRICS.keys()),
                                    index=list(config.METRICS).index(config.DEFAULT_METRIC))
    with c2:
        basemap = st.selectbox("Basemap", list(config.MAP_STYLES.keys()),
                               index=list(config.MAP_STYLES).index(config.DEFAULT_MAP_STYLE))
    with c3:
        resolution = st.slider("Hex size", 3, 6, config.DEFAULT_H3_RESOLUTION)
    with c4:
        include_geo_flagged = st.toggle("Geo-flagged", value=False,
                                        help="Include impossible / out-of-India coordinates")
    with c5:
        show_points = st.checkbox("Show facilities", value=True,
                                  help="Individual facility dots — click one for detail + source")

    filtered = data.filter_facilities(facilities, specialty, include_geo_flagged)
    cells = data.hexbin(filtered, metric_label, resolution)
    points = data.facility_points(filtered) if show_points else None
    higher_is_worse = config.METRICS[metric_label][2]

    map_col, panel_col = st.columns([3.1, 1], gap="medium")

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
                   "style": {"backgroundColor": "#0f172a", "color": "white",
                             "fontSize": "12px", "borderRadius": "8px", "padding": "8px"}}
        deck = pdk.Deck(layers=layers, initial_view_state=view,
                        map_style=config.MAP_STYLES[basemap], tooltip=tooltip)
        event = st.pydeck_chart(deck, use_container_width=True, height=580, key="map",
                                on_select="rerun", selection_mode="single-object")
        ui.legend("Lower", "Higher", higher_is_worse)

        lc, rc = st.columns([3, 1])
        lc.caption(f"{len(cells):,} regions · {len(filtered):,} facilities · "
                   "scroll to zoom · click a dot to fly in & see its source.")
        if rc.button("↺ Reset view", width="stretch"):
            st.session_state.pop("map", None)
            st.rerun()

        picked = _picked_facility(event) or prior
        if picked:
            ui.facility_card(picked)

    with panel_col:
        st.markdown('<div class="mdn-panel-h">Coverage snapshot</div>', unsafe_allow_html=True)
        st.metric("Facilities shown", f"{len(filtered):,}")
        st.metric("Passed readiness checks", f"{int(filtered['trustworthy_supply_signal'].sum()):,}",
                  help="Automated checks only — NOT human verification.")
        review = int(filtered["needs_human_review"].sum())
        st.metric("Need human review", f"{review:,}",
                  delta=f"{(review/max(len(filtered),1))*100:.0f}% of shown", delta_color="inverse")
        st.metric("Contradicted / geo-invalid",
                  f"{int(filtered['contradicted_or_geo_invalid_signal'].sum()):,}")
        if not cells.empty:
            st.markdown('<div class="mdn-panel-h">Distribution across regions</div>',
                        unsafe_allow_html=True)
            counts, edges = np.histogram(cells["value"].dropna(), bins=18)
            hist = pd.DataFrame({"bin": np.round((edges[:-1] + edges[1:]) / 2, 2),
                                 "regions": counts}).set_index("bin")
            st.bar_chart(hist, height=160, color="#FF3621")


def gaps_tab(districts: pd.DataFrame, specialty: str) -> None:
    lb, gap_label = data.leaderboard(districts, specialty, top_n=15)
    st.markdown(f'<div class="mdn-panel-h">Top care gaps · {specialty}</div>',
                unsafe_allow_html=True)
    st.caption("Ranked by health need vs trustworthy, service-specific supply. "
               "The recommendation says whether to **deploy, verify, fix, or refer** — "
               "we don't tell you to build where the data is just unverified.")

    chips = {k: v[0] for k, v in data.PLANNING.items()}
    disp = pd.DataFrame({
        "District": lb["district_name"], "State": lb["state_ut"],
        "Recommendation": lb["planning_category"].map(chips).fillna("👁 Monitor"),
        gap_label: pd.to_numeric(lb["gap"], errors="coerce").round(2),
        "Need": pd.to_numeric(lb["health_need_score"], errors="coerce").round(2),
        "Trust supply %": (pd.to_numeric(lb["trustworthy_supply_rate"], errors="coerce") * 100).round(0),
        "Uncertainty": lb["district_uncertainty_level"].astype(str).str.title(),
    })

    left, right = st.columns([1.35, 1], gap="medium")
    with left:
        ev = st.dataframe(disp, hide_index=True, width="stretch", height=540,
                          on_select="rerun", selection_mode="single-row",
                          column_config={"Trust supply %": st.column_config.NumberColumn(format="%d%%")})
    with right:
        sel = ev.selection.rows if ev and ev.selection else []
        if sel:
            ui.region_detail(lb.iloc[sel[0]], specialty)
        else:
            st.info("Select a district on the left to see its recommendation, patient "
                    "conditions, and cited evidence.", icon="👈")


def uncertainty_tab(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    snapshot = data.quality_snapshot(facilities, districts)
    total = max(snapshot["facility_rows"], 1)

    st.markdown('<div class="mdn-panel-h">Data-quality reality</div>', unsafe_allow_html=True)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Need review", f"{snapshot['needs_human_review']:,}",
              delta=f"{snapshot['needs_human_review'] / total:.0%}", delta_color="inverse")
    c2.metric("Passed checks", f"{snapshot['trustworthy_supply']:,}",
              delta=f"{snapshot['trustworthy_supply'] / total:.0%}")
    c3.metric("Bad geo / contradictions", f"{snapshot['contradicted_or_geo_invalid']:,}")
    c4.metric("Contact evidence", f"{snapshot['contact_evidence_rows']:,}",
              help="Phone/email/site present. This does not mean the facility is reachable.")
    c5.metric("Avg readiness", f"{snapshot['avg_data_readiness']:.2f}")

    st.dataframe(
        data.messiness_breakdown(facilities, districts),
        hide_index=True,
        width="stretch",
        height=250,
    )
    st.markdown('<div class="mdn-panel-h">How the app explains uncertainty</div>',
                unsafe_allow_html=True)
    st.dataframe(
        data.explainability_model_card(),
        hide_index=True,
        width="stretch",
        height=245,
    )

    seed_summary, seed_breakdown, seed_report = data.golden_seed_report()
    if not seed_summary.empty:
        st.markdown('<div class="mdn-panel-h">Golden prediction seed report</div>',
                    unsafe_allow_html=True)
        st.caption(
            "These are seed artifacts for the supervised phase, not trainable ground truth. "
            "Rows become trainable only after Tier A/B source corroboration."
        )
        r1, r2 = st.columns([1, 1], gap="medium")
        with r1:
            st.dataframe(
                seed_summary,
                hide_index=True,
                width="stretch",
                height=280,
                column_config={"Value": st.column_config.NumberColumn(format="%d")},
            )
        with r2:
            st.dataframe(
                seed_breakdown,
                hide_index=True,
                width="stretch",
                height=280,
                column_config={"Rows": st.column_config.NumberColumn(format="%d")},
            )
        guardrails = seed_report.get("guardrails", [])
        if guardrails:
            st.caption("Guardrails: " + " · ".join(guardrails))

    model_summary, model_tasks, model_report = data.supervised_model_report()
    if not model_summary.empty:
        st.markdown('<div class="mdn-panel-h">Supervised model trainer report</div>',
                    unsafe_allow_html=True)
        policy = model_report.get("model_policy", {})
        st.caption(policy.get("why", ""))
        m1, m2 = st.columns([1, 1], gap="medium")
        with m1:
            st.dataframe(
                model_summary,
                hide_index=True,
                width="stretch",
                height=250,
            )
        with m2:
            st.dataframe(
                model_tasks,
                hide_index=True,
                width="stretch",
                height=250,
            )
        st.caption("Upgrade path: " + policy.get("upgrade_path", ""))

    district_queue = data.active_district_queue()
    facility_queue = data.active_facility_queue()
    if not district_queue.empty or not facility_queue.empty:
        st.markdown('<div class="mdn-panel-h">Active uncertainty explanations</div>',
                    unsafe_allow_html=True)
        st.caption(
            "These queues are active-learning inspired without human-oracle labels. "
            "They rank where source enrichment or cautious UI treatment would most reduce decision risk."
        )
        q_tabs = st.tabs(["District drivers", "Facility drivers"])
        with q_tabs[0]:
            if district_queue.empty:
                st.info("No active district queue artifact found.")
            else:
                dq = district_queue.rename(columns={
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
                ev = st.dataframe(
                    dq[[
                        "Rank", "Score", "Action", "State", "District",
                        "Planning category", "Observed rows", "Care gap",
                        "Trust gap", "CI width", "Sample uncertainty",
                    ]],
                    hide_index=True,
                    width="stretch",
                    height=360,
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
                sel = ev.selection.rows if ev and ev.selection else []
                if sel:
                    ui.active_district_detail(district_queue.iloc[sel[0]], specialty)
                else:
                    st.caption("Select a district row to see the scoring drivers and confidence intervals.")
        with q_tabs[1]:
            if facility_queue.empty:
                st.info("No active facility queue artifact found.")
            else:
                fq = facility_queue.rename(columns={
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
                ev = st.dataframe(
                    fq[[c for c in show if c in fq]],
                    hide_index=True,
                    width="stretch",
                    height=360,
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
                sel = ev.selection.rows if ev and ev.selection else []
                if sel:
                    ui.active_facility_detail(facility_queue.iloc[sel[0]])
                else:
                    st.caption("Select a facility row to see proxy trust bands, estimates, and source checks.")

    st.markdown('<div class="mdn-panel-h">External validation sources</div>',
                unsafe_allow_html=True)
    st.dataframe(
        data.validation_sources(),
        hide_index=True,
        width="stretch",
        height=300,
        column_config={"URL": st.column_config.LinkColumn("URL")},
    )

    st.markdown('<div class="mdn-panel-h">Missing and incomplete data handling</div>',
                unsafe_allow_html=True)
    st.dataframe(
        data.missingness_summary(facilities),
        hide_index=True,
        width="stretch",
        height=285,
        column_config={"Rows": st.column_config.NumberColumn(format="%d")},
    )
    st.dataframe(
        data.missing_data_methods(),
        hide_index=True,
        width="stretch",
        height=285,
    )

    st.markdown('<div class="mdn-panel-h">Verification protocol</div>',
                unsafe_allow_html=True)
    st.dataframe(
        data.verification_checks(),
        hide_index=True,
        width="stretch",
        height=215,
        column_config={"Priority": st.column_config.NumberColumn(format="%d")},
    )

    st.markdown('<div class="mdn-panel-h">Geo fix pipeline: LLM parser + map validator</div>',
                unsafe_allow_html=True)
    st.caption("LLMs clean Indian address text; Google Maps/Mappls validate physical location. "
               "No training labels are required; ambiguous API outcomes stay visible as uncertainty.")
    g1, g2 = st.columns([1.05, 1], gap="medium")
    with g1:
        st.dataframe(
            data.geo_validation_steps(),
            hide_index=True,
            width="stretch",
            height=260,
        )
    with g2:
        st.dataframe(
            data.geo_quality_rules(),
            hide_index=True,
            width="stretch",
            height=260,
        )
    priors = data.geocoder_uncertainty_priors()
    if not priors.empty:
        st.markdown('<div class="mdn-panel-h">Geocoder uncertainty priors</div>',
                    unsafe_allow_html=True)
        st.dataframe(
            priors,
            hide_index=True,
            width="stretch",
            height=245,
            column_config={
                "proxy_confidence_low": st.column_config.NumberColumn(format="%.2f"),
                "proxy_confidence_high": st.column_config.NumberColumn(format="%.2f"),
                "planning_uncertainty_radius_km": st.column_config.NumberColumn(format="%.1f"),
            },
        )

    geo_candidates = data.geo_validation_candidates(facilities, top_n=25)
    if not geo_candidates.empty:
        st.markdown('<div class="mdn-panel-h">Geo-validation candidates</div>',
                    unsafe_allow_html=True)
        geo_display = geo_candidates.rename(columns={
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
        geo_event = st.dataframe(
            geo_display[[c for c in geo_cols if c in geo_display]],
            hide_index=True,
            width="stretch",
            height=300,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Priority": st.column_config.NumberColumn(format="%.1f"),
                "External priority": st.column_config.NumberColumn(format="%.3f"),
                "PIN distance km": st.column_config.NumberColumn(format="%.1f"),
                "Geo band high km": st.column_config.NumberColumn(format="%.1f"),
            },
        )
        geo_sel = geo_event.selection.rows if geo_event and geo_event.selection else []
        if geo_sel:
            ui.geo_candidate_detail(geo_candidates.iloc[geo_sel[0]])
        else:
            st.caption("Select a geo candidate to see source-agreement rules and reason codes.")

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
        return

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
    ev = st.dataframe(
        display[[c for c in show_cols if c in display]],
        hide_index=True,
        width="stretch",
        height=420,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Priority": st.column_config.NumberColumn(format="%.1f"),
            "Readiness": st.column_config.NumberColumn(format="%.2f"),
            "Join confidence": st.column_config.NumberColumn(format="%.2f"),
            "Source": st.column_config.LinkColumn("Source"),
        },
    )

    sel = ev.selection.rows if ev and ev.selection else []
    if sel:
        ui.verification_detail(queue.iloc[sel[0]])
    else:
        st.caption("Select a queue row to inspect contact fields, source evidence, and the seed label.")


def main() -> None:
    facilities = _facilities()
    districts = _districts()
    ui.header()

    specialty = st.selectbox("Specialty (applies to both views)",
                             list(config.SPECIALTIES.keys()), index=0)

    tab_map, tab_gaps, tab_uncertainty = st.tabs(["🗺️  Map", "📊  Top care gaps", "Uncertainty"])
    with tab_map:
        map_tab(facilities, specialty)
    with tab_gaps:
        gaps_tab(districts, specialty)
    with tab_uncertainty:
        uncertainty_tab(facilities, districts, specialty)


if __name__ == "__main__":
    main()
