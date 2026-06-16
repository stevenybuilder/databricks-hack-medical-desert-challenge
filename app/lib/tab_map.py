"""Map tab: medical-desert hexbin + facility coverage map with cited detail.

Entry point: ``render(facilities, districts, specialty) -> None``.

Layout standard (see DESIGN_SYSTEM.md — VFMatch-style split hero): a LEFT frosted
orientation/action card (title + ≤2 KPIs + real pill actions) sits beside the
pydeck map as the CENTERPIECE filling the right column, with a small FLOATING
legend chip (``.mdn-float`` via ``ui.floating_card``) reading as an overlay on the
map. All dense controls (view mode, basemap, H3 resolution, toggles), the coverage
snapshot, the full leaderboard, and the methodology note live behind
``ui.detail(...)`` expanders — depth is opt-in, never forced. First glance =
hero card + map + floating legend + selected-district detail.
"""
from __future__ import annotations

import html

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


def _hero_actions(worst: pd.Series | None) -> None:
    """Real, functional pill actions for the left hero card.

    - "Jump to worst district" selects the #1 care-gap district (drives the detail
      panel below) and re-centers the map on its centroid.
    - "Toggle facility dots" flips the same session-state key the controls toggle
      binds to, so the map updates without opening the controls expander.
    """
    a1, a2 = st.columns(2)
    has_worst = worst is not None
    if a1.button("◎ Jump to worst district", key="hero_jump_worst",
                 type="primary", use_container_width=True, disabled=not has_worst):
        # Selecting = remember the district key (the shape ``_district_row`` expects)
        # so the detail panel resolves to it, and capture its centroid so the map
        # re-centers on the next run.
        st.session_state["map_focus_geo"] = {
            "district_name": worst.get("district_name"),
            "state_ut": worst.get("state_ut"),
        }
        lat = pd.to_numeric(worst.get("district_latitude"), errors="coerce")
        lon = pd.to_numeric(worst.get("district_longitude"), errors="coerce")
        if pd.notna(lat) and pd.notna(lon):
            st.session_state["map_focus_view"] = {
                "latitude": float(lat), "longitude": float(lon), "zoom": 6.4}
        st.rerun()

    dots_on = bool(st.session_state.get("map_dots_on", False))
    if a2.button("● Hide facility dots" if dots_on else "○ Show facility dots",
                 key="hero_toggle_dots", use_container_width=True):
        # Stash the desired state on a plain (non-widget) key; the controls toggle
        # picks it up as its default on the next run, avoiding the "set state for an
        # instantiated widget" exception that binding + writing one key would cause.
        st.session_state["map_dots_pending"] = not dots_on
        st.rerun()


def _left_hero(districts: pd.DataFrame) -> None:
    """The frosted LEFT orientation/action card: context line, 2 KPIs, pill actions.

    Streamlit can't wrap live widgets (KPI cards, buttons) in a raw HTML div, so
    the frosted-card recipe is scoped onto a bordered ``st.container`` via a marker
    + ``:has()`` selector (the same idiom the sibling tabs use), keeping the left
    column reading as ONE intentional orientation card rather than loose elements.
    """
    worst = _worst_district(districts)
    box = st.container(border=True)
    box.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.map-hero-marker) {
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-card);
          padding: var(--pad-card);
          -webkit-backdrop-filter: var(--glass-blur);
          backdrop-filter: var(--glass-blur);
        }
        </style>
        <div class="map-hero-marker"></div>
        """,
        unsafe_allow_html=True,
    )
    with box:
        st.markdown(
            '<div class="mdn-panel-h">Orientation</div>'
            '<div class="mdn-muted" style="margin:-.15rem 0 .55rem;line-height:1.35">'
            'Every district scored by care gap — even zero-facility deserts that '
            'facility-count maps miss. Pick a district on the map, or jump to the '
            'worst one to start.</div>',
            unsafe_allow_html=True,
        )
        _map_kpis(districts)
        st.markdown('<div style="height:.35rem"></div>', unsafe_allow_html=True)
        _hero_actions(worst)
        st.caption("Need a recommended plan or the AI walkthrough? Open the "
                   "**Care gaps** and **Copilot** tabs above.")


def _floating_legend(view_mode: str, n_plotted: int, filtered_n: int,
                     total_n: int) -> None:
    """The color-ramp legend rendered as a floating chip (``.mdn-float``) over the map.

    Streamlit's flow makes true absolute-over-canvas positioning brittle, so per
    DESIGN_SYSTEM.md this acceptable compromise sits directly above the map within
    the right column — styled as a compact floating chip, not a full-width bar.
    """
    if view_mode == "Medical deserts":
        a, b = "Medical desert", "Better coverage"  # ramp red(worse)->green
        sub = f"{n_plotted:,} districts mapped · click a hex for its breakdown"
    else:
        lo_worse = config.METRICS[config.DEFAULT_METRIC][2]
        a, b = ("Higher", "Lower") if lo_worse else ("Lower", "Higher")
        excluded = total_n - filtered_n
        sub = (f"{filtered_n:,} of {total_n:,} facilities mapped "
               f"({excluded:,} excluded) · click a hex or dot")
    inner = (
        '<div style="display:flex;align-items:center;gap:.65rem">'
        '<span style="font-size:.66rem;font-weight:760;letter-spacing:.08em;'
        'text-transform:uppercase;color:var(--mdn-muted);white-space:nowrap">Legend</span>'
        '<span style="flex:1;height:8px;border-radius:999px;'
        'background:linear-gradient(90deg,var(--bad) 0%,var(--mid) 50%,var(--good) 100%);'
        'border:1px solid rgba(255,255,255,.12);min-width:90px"></span>'
        '</div>'
        '<div style="display:flex;justify-content:space-between;font-size:.7rem;'
        f'color:var(--mdn-muted);margin-top:5px"><span>{html.escape(a)}</span>'
        f'<span>{html.escape(b)}</span></div>'
        '<div style="font-size:.7rem;color:var(--mdn-dim);margin-top:.45rem;'
        f'line-height:1.3">{html.escape(sub)}</div>'
    )
    ui.floating_card(inner)


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

    # ---- All controls behind one detail expander (kept off the first glance).
    # Expander bodies still execute every run, so the widget values below are always
    # resolved — collapsing only hides them, it does not skip them. The hero
    # "facility dots" pill drives the toggle via the ``map_dots_*`` keys below. ----
    # The hero "facility dots" pill stashes its intent on a plain key; consume it
    # here (before the widget instantiates) so the toggle's default reflects it.
    if "map_dots_pending" in st.session_state:
        st.session_state["map_dots_on"] = st.session_state.pop("map_dots_pending")
    dots_default = bool(st.session_state.get("map_dots_on", False))

    with ui.detail("Map controls"):
        cc1, cc2 = st.columns([1.4, 1.0])
        with cc1:
            view_mode = st.segmented_control(
                "Map shows", ["Medical deserts", "Facility coverage"],
                default="Medical deserts", key="map_view_mode",
                width="stretch") or "Medical deserts"
        with cc2:
            show_points = st.toggle("Facility dots", value=dots_default)
        oc1, oc2, oc3 = st.columns(3)
        basemap = oc1.selectbox("Basemap style", list(config.MAP_STYLES.keys()),
                                index=list(config.MAP_STYLES).index(config.DEFAULT_MAP_STYLE))
        resolution = oc2.slider("Desert cell size", 3, 6, 4,
                                help="Lower = bigger hexes (national view); higher = finer detail.")
        include_geo_flagged = oc3.toggle("Include flagged-geo facilities", value=False,
                                         help="Impossible / out-of-India coordinates")

    # Keep the plain key in sync with the live toggle so the hero pill label is
    # accurate even when the user flips the toggle directly in the expander.
    st.session_state["map_dots_on"] = bool(show_points)
    filtered = data.filter_facilities(facilities, specialty, include_geo_flagged)
    deserts = data.district_hexes(districts, resolution) if view_mode == "Medical deserts" else None
    cells = data.hexbin(filtered, config.DEFAULT_METRIC, resolution) if view_mode == "Facility coverage" else None
    points = data.facility_points(filtered) if show_points else None

    layers = _build_layers(deserts, cells, points, show_points)
    if not layers:
        # Still show the orientation card so the tab never collapses to a bare info box.
        hcol, mcol = st.columns([1, 2.4])
        with hcol:
            _left_hero(districts)
        with mcol:
            st.info("No mappable data for this selection.")
        return

    # ---- Re-center the map when the hero "jump to worst district" was used; else
    # the calm national overview. Consume the one-shot focus view after applying it. ----
    focus_view = st.session_state.pop("map_focus_view", None)
    view = pdk.ViewState(**(focus_view if focus_view else config.INDIA_VIEW))

    tooltip = {"html": "{tip}",
               "style": {"backgroundColor": "#07111f", "color": "#eaf2ff",
                         "fontSize": "12px", "borderRadius": "8px",
                         "border": "1px solid rgba(148,163,184,.34)",
                         "padding": "8px"}}
    deck = pdk.Deck(layers=layers, initial_view_state=view,
                    map_style=config.MAP_STYLES[basemap], tooltip=tooltip)

    # ===== SPLIT HERO: left orientation/action card · right map (centerpiece) =====
    hero_left, hero_right = st.columns([1, 2.4])
    with hero_left:
        _left_hero(districts)
    with hero_right:
        # Floating legend chip reads as an overlay sitting just above the map canvas.
        n_plotted = 0 if deserts is None else len(deserts)
        _floating_legend(view_mode, n_plotted, len(filtered), len(facilities))
        event = st.pydeck_chart(deck, height=620, key="map",
                                on_select="rerun", selection_mode="single-object")

    # ---- Selected detail: facility card or district drill-down (opens on an answer).
    # A click on the map wins; otherwise the hero "jump" focus; otherwise the worst. ----
    picked_f = _picked_facility(event)
    picked_d = _picked_district(event)
    if picked_f:
        st.session_state.pop("map_focus_geo", None)
        ui.facility_card(picked_f)
    else:
        row = _district_row(districts, picked_d) if picked_d else None
        if row is None:
            focus_geo = st.session_state.get("map_focus_geo")
            if focus_geo:
                row = _district_row(districts, focus_geo)
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
