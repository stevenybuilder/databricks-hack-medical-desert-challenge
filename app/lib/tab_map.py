"""Map tab: medical-desert hexbin + facility coverage map with cited detail.

Entry point: ``render(facilities, districts, specialty) -> None``.

Density standard (see DESIGN_SYSTEM.md): the pydeck map is the hero. First glance
shows only a clean ``tab_intro``, a ≤2-card KPI row, the map + a short legend, and
the selected district's detail. All controls (view mode, basemap, H3 resolution,
toggles), the full leaderboard table, the coverage snapshot, and the methodology
note live behind ``ui.detail(...)`` expanders — depth is opt-in, never forced.
"""
from __future__ import annotations

import pandas as pd
import pydeck as pdk
import streamlit as st

from . import config, data, ui, charts
from .tab_common import (
    _picked_facility,
    _picked_district,
    _district_row,
    _action_label,
    _action_tone,
    _fmt_num,
)


# --- local helpers ------------------------------------------------------------

def _worst_district(districts: pd.DataFrame) -> pd.Series | None:
    """The #1 care-gap district — the headline the tab opens on."""
    if districts is None or districts.empty or "care_gap_score" not in districts:
        return None
    ranked = districts.sort_values("care_gap_score", ascending=False)
    return None if ranked.empty else ranked.iloc[0]


def _desert_count(districts: pd.DataFrame) -> int:
    """Districts with NFHS need but zero mapped facilities (the deserts maps miss)."""
    if districts is None or districts.empty:
        return 0
    return int(districts.get("zero_facility_desert", pd.Series(dtype=bool))
               .fillna(False).astype(bool).sum())


def _map_kpis(districts: pd.DataFrame) -> None:
    """≤2 decision-relevant KPIs: the worst care-gap district + zero-facility deserts."""
    worst = _worst_district(districts)
    items: list[tuple[str, str, str]] = []
    tones: list[str] = []
    if worst is not None:
        name = f"{worst.get('district_name', 'unknown')}, {worst.get('state_ut', 'unknown')}"
        items.append((
            "Worst care gap",
            name,
            f"{_action_label(worst.get('planning_category'))} · "
            f"care-gap score {_fmt_num(worst.get('care_gap_score'))}",
        ))
        tones.append(_action_tone(worst.get("planning_category")))
    n_des = _desert_count(districts)
    items.append((
        "Zero-facility deserts",
        f"{n_des:,}",
        "NFHS need, no mapped facility — invisible to facility-count maps",
    ))
    tones.append("danger" if n_des else "neutral")
    if items:
        ui.kpi_row(items, tone_each=tones)


def _build_layers(deserts, cells, points, show_points) -> list:
    layers = []
    if deserts is not None and not deserts.empty:
        layers.append(pdk.Layer(
            "H3HexagonLayer", id="deserts", data=deserts,
            get_hexagon="h3", get_fill_color="fill_color",
            pickable=True, extruded=False, stroked=True, filled=True,
            opacity=0.80, coverage=0.95,
            get_line_color=[255, 255, 255, 45], line_width_min_pixels=0.4))
    if cells is not None and not cells.empty:
        layers.append(pdk.Layer(
            "H3HexagonLayer", id="hexbins", data=cells,
            get_hexagon="h3", get_fill_color="fill_color",
            pickable=True, extruded=False, stroked=True, filled=True,
            opacity=0.55 if show_points else 0.82, coverage=0.92,
            get_line_color=[255, 255, 255, 60], line_width_min_pixels=0.5))
    if points is not None and not points.empty:
        layers.append(pdk.Layer(
            "ScatterplotLayer", id="facilities", data=points,
            get_position="[lon, lat]", get_fill_color="point_color",
            get_radius=600, radius_min_pixels=2.5, radius_max_pixels=9,
            pickable=True, auto_highlight=True, stroked=True,
            get_line_color=[255, 255, 255, 140], line_width_min_pixels=0.4))
    return layers


def _coverage_snapshot(facilities, filtered, districts) -> None:
    """Dense coverage counts + the facility-trust distribution (tucked behind a detail)."""
    total = len(facilities)
    n_des = _desert_count(districts)
    c1, c2 = st.columns(2)
    c1.metric("Facilities mapped", f"{len(filtered):,}",
              help=f"of {total:,} total · {total - len(filtered):,} lack valid coordinates")
    c2.metric("Zero-facility deserts", f"{n_des}",
              help="Districts with NFHS need but no mapped facility.")

    ui.panel_header("Facility data trust")
    tier = (filtered["trust_tier"].value_counts()
            if "trust_tier" in filtered.columns else pd.Series(dtype=int))
    st.altair_chart(
        charts.trust_distribution_bar(int(tier.get("High", 0)), int(tier.get("Medium", 0)),
                                      int(tier.get("Verify", 0))),
        use_container_width=True)
    st.caption("High = passes all checks · Medium = some supply fields estimated (CatBoost) · "
               "Verify = missing supply. Automated checks, not human verification.")


def _leaderboard(districts: pd.DataFrame) -> None:
    """The full care-gap district ranking — behind a detail so the map stays the hero."""
    if districts is None or districts.empty or "care_gap_score" not in districts:
        st.caption("No district rows available to rank.")
        return
    ranked = districts.sort_values("care_gap_score", ascending=False).head(30).copy()
    table = pd.DataFrame({
        "District": ranked.get("district_name"),
        "State": ranked.get("state_ut"),
        "Action": ranked.get("planning_category").map(_action_label).fillna("Monitor"),
        "Care-gap": pd.to_numeric(ranked.get("care_gap_score"), errors="coerce"),
        "Need": pd.to_numeric(ranked.get("health_need_score"), errors="coerce"),
        "Trust supply %": pd.to_numeric(ranked.get("trustworthy_supply_rate"), errors="coerce") * 100,
    })
    st.dataframe(
        table, hide_index=True, width="stretch", height=360,
        column_config={
            "Care-gap": st.column_config.NumberColumn(
                "Care-gap ▲ worse", format="%.2f",
                help="Higher = more unmet need with less trustworthy supply."),
            "Need": st.column_config.ProgressColumn(
                "Need ▲ worse", format="%.2f", min_value=0, max_value=1),
            "Trust supply %": st.column_config.ProgressColumn(
                "Trust supply ▲ better", format="%d%%", min_value=0, max_value=100),
        },
    )
    st.caption("Top 30 by care-gap score. Open the **Care gaps** tab for the full ranked queue "
               "with per-district actions.")


def render(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    ui.tab_intro(
        "India care-gap atlas",
        f"{specialty} lens · trust-weighted demand, supply, and uncertainty",
    )

    # ---- First glance: ≤2 decision-relevant KPIs ----
    _map_kpis(districts)

    # ---- All controls behind one detail expander (kept off the first glance).
    # Expander bodies still execute every run, so the widget values below are always
    # resolved — collapsing only hides them, it does not skip them. ----
    with ui.detail("Map controls"):
        cc1, cc2 = st.columns([1.4, 1.0])
        with cc1:
            view_mode = st.segmented_control(
                "Map shows", ["Medical deserts", "Facility coverage"],
                default="Medical deserts", key="map_view_mode",
                width="stretch") or "Medical deserts"
        with cc2:
            show_points = st.toggle("Facility dots", value=(view_mode == "Facility coverage"))
        oc1, oc2, oc3 = st.columns(3)
        basemap = oc1.selectbox("Basemap style", list(config.MAP_STYLES.keys()),
                                index=list(config.MAP_STYLES).index(config.DEFAULT_MAP_STYLE))
        resolution = oc2.slider("Desert cell size", 3, 6, 4,
                                help="Lower = bigger hexes (national view); higher = finer detail.")
        include_geo_flagged = oc3.toggle("Include flagged-geo facilities", value=False,
                                         help="Impossible / out-of-India coordinates")

    filtered = data.filter_facilities(facilities, specialty, include_geo_flagged)
    deserts = data.district_hexes(districts, resolution) if view_mode == "Medical deserts" else None
    cells = data.hexbin(filtered, config.DEFAULT_METRIC, resolution) if view_mode == "Facility coverage" else None
    points = data.facility_points(filtered) if show_points else None

    # ---- The hero: the map, full-width, with a short legend underneath ----
    view = pdk.ViewState(**config.INDIA_VIEW)
    layers = _build_layers(deserts, cells, points, show_points)

    if not layers:
        st.info("No mappable data for this selection.")
        return

    tooltip = {"html": "{tip}",
               "style": {"backgroundColor": "#07111f", "color": "#eaf2ff",
                         "fontSize": "12px", "borderRadius": "8px",
                         "border": "1px solid rgba(148,163,184,.34)",
                         "padding": "8px"}}
    deck = pdk.Deck(layers=layers, initial_view_state=view,
                    map_style=config.MAP_STYLES[basemap], tooltip=tooltip)
    event = st.pydeck_chart(deck, height=600, key="map",
                            on_select="rerun", selection_mode="single-object")

    # ---- Short legend + one-line orientation (the only inline explainer) ----
    if view_mode == "Medical deserts":
        ui.legend("Better coverage", "Medical desert", higher_is_worse=True)
        n_plotted = 0 if deserts is None else len(deserts)
        st.caption(f"{n_plotted:,} districts · green = better coverage, red = wider care gap · "
                   "click a **hex** for the district breakdown, a **dot** for facility evidence.")
    else:
        ui.legend("Lower", "Higher", config.METRICS[config.DEFAULT_METRIC][2])
        total = len(facilities)
        st.caption(f"{len(filtered):,} of {total:,} facilities mapped "
                   f"({total - len(filtered):,} excluded) · click a **hex** for the district "
                   "breakdown, a **dot** for facility evidence.")

    # ---- Selected detail: facility card or district drill-down (opens on an answer) ----
    picked_f = _picked_facility(event)
    picked_d = _picked_district(event)
    if picked_f:
        ui.facility_card(picked_f)
    else:
        row = _district_row(districts, picked_d) if picked_d else None
        if row is None:
            row = _worst_district(districts)
            if row is not None:
                st.caption("Showing the highest care-gap district — click any hex to inspect another.")
        if row is not None:
            ui.region_detail(row, specialty, districts)

    # ---- Depth on demand: coverage snapshot, full leaderboard, methodology ----
    with ui.detail("Coverage snapshot & data trust"):
        _coverage_snapshot(facilities, filtered, districts)

    with ui.detail("Full care-gap district ranking"):
        _leaderboard(districts)

    with ui.detail("How to read this map"):
        st.markdown(
            "- **Medical deserts** colors every district by its care-gap score "
            "(green = better coverage, red = wider gap), so zero-facility deserts that "
            "facility-count maps miss still appear.\n"
            "- **Facility coverage** hexbins the mapped facilities by the "
            f"*{config.DEFAULT_METRIC}* metric.\n"
            "- **Facility dots** overlay individual facilities; click one for its cited "
            "evidence and trust badge.\n"
            "- Scores are proxy decision-support from NFHS-5 district indicators (2019–21) "
            "and a web-derived facility snapshot — claims, not a verified census."
        )
