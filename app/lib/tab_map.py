"""Map tab: medical-desert hexbin + facility coverage map with cited detail.

Entry point: ``render(facilities, districts, specialty) -> None``.

Layout standard (see docs/DESIGN_SYSTEM.md — VFMatch-style composition): a LEFT frosted
DISTRICT RAIL (search + 2 compact KPIs + a scrollable, ranked care-gap list with
tone-coded action pills) sits beside the pydeck map as the CENTERPIECE filling the
right column, with a small FLOATING legend chip (``.mdn-float`` via
``ui.floating_card``) reading as an overlay on the map. Selecting a rail row drives
the SAME selection state as a map click — it recenters the map AND updates the
detail panel below. All dense controls (view mode, basemap, H3 resolution, toggles),
the coverage snapshot, and the methodology note live behind ``ui.detail(...)``
expanders — depth is opt-in, never forced. First glance = district rail + map +
floating legend + selected-district detail.
"""
from __future__ import annotations

import html

import pandas as pd
import pydeck as pdk
import streamlit as st

from . import config, data, ui, charts
from .tab_common import (
    _district_scope_control,
    _district_scope_filter,
    _district_scope_value,
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


# --- E2: robust centroid resolution (NaN-safe) -------------------------------

# A sensible nationwide fallback so a jump ALWAYS lands somewhere usable.
_INDIA_FALLBACK = (float(config.INDIA_VIEW["latitude"]),
                   float(config.INDIA_VIEW["longitude"]))


def _district_centroid(row, districts: pd.DataFrame, facilities: pd.DataFrame,
                       resolution: int = 4) -> tuple[float, float]:
    """Resolve a usable (lat, lon) for a district even when its centroid is NaN.

    73/706 districts (incl. the #1 care-gap district, Uttar Dinajpur WB) have NaN
    ``district_latitude/longitude``. This walks a fallback chain so ``map_focus_view``
    is ALWAYS set and the map visibly recenters:

      1. the district's own centroid (when present);
      2. the mean lat/lon of that district's hex cells (``data.district_hexes``);
      3. the mean of that district's mapped facility coordinates;
      4. the mean centroid of its STATE's districts (state-level fallback);
      5. the nationwide India centroid (last resort).
    """
    if row is None:
        return _INDIA_FALLBACK
    name = row.get("district_name")
    state = row.get("state_ut")

    # 1) the district's own centroid.
    lat = pd.to_numeric(row.get("district_latitude"), errors="coerce")
    lon = pd.to_numeric(row.get("district_longitude"), errors="coerce")
    if pd.notna(lat) and pd.notna(lon):
        return float(lat), float(lon)

    # 2) mean of this district's hex cells (carry lat/lon for the matching rows).
    try:
        hexes = data.district_hexes(districts, resolution)
        if hexes is not None and not hexes.empty and {"lat", "lon"} <= set(hexes.columns):
            sub = hexes[(hexes.get("district_name") == name)
                        & (hexes.get("state_ut") == state)]
            la = pd.to_numeric(sub.get("lat"), errors="coerce").dropna()
            lo = pd.to_numeric(sub.get("lon"), errors="coerce").dropna()
            if not la.empty and not lo.empty:
                return float(la.mean()), float(lo.mean())
    except Exception:
        pass

    # 3) mean of this district's mapped facility coordinates.
    try:
        if facilities is not None and not facilities.empty:
            fsub = facilities[(facilities.get("district_name") == name)
                              & (facilities.get("state_ut") == state)]
            fla = pd.to_numeric(fsub.get("facility_latitude"), errors="coerce").dropna()
            flo = pd.to_numeric(fsub.get("facility_longitude"), errors="coerce").dropna()
            if not fla.empty and not flo.empty:
                return float(fla.mean()), float(flo.mean())
    except Exception:
        pass

    # 4) state-level fallback: mean centroid of the state's districts.
    try:
        if districts is not None and not districts.empty and state is not None:
            ssub = districts[districts.get("state_ut") == state]
            sla = pd.to_numeric(ssub.get("district_latitude"), errors="coerce").dropna()
            slo = pd.to_numeric(ssub.get("district_longitude"), errors="coerce").dropna()
            if not sla.empty and not slo.empty:
                return float(sla.mean()), float(slo.mean())
    except Exception:
        pass

    # 5) nationwide last resort — never leaves the focus view unset.
    return _INDIA_FALLBACK


def _focus_on(row, districts: pd.DataFrame, facilities: pd.DataFrame,
              zoom: float = 6.2) -> None:
    """Set the persistent focus-geo + one-shot focus-view for a chosen district.

    ``map_focus_geo`` is PERSISTENT (drives the detail panel + the "Now viewing"
    confirmation until another selection replaces it). ``map_focus_view`` is the
    one-shot recenter, consumed only when actually applied to the ViewState — so a
    stray map ``on_select`` rerun cannot swallow a pending jump.
    """
    if row is None:
        return
    st.session_state.pop("map_focus_facility", None)
    st.session_state["map_focus_geo"] = {
        "district_name": row.get("district_name"),
        "state_ut": row.get("state_ut"),
    }
    lat, lon = _district_centroid(row, districts, facilities)
    st.session_state["map_focus_view"] = {
        "latitude": float(lat), "longitude": float(lon), "zoom": float(zoom)}


def _focus_on_facility(row: pd.Series, zoom: float = 8.2) -> None:
    """Focus a verification candidate and open its evidence detail."""
    if row is None:
        return
    payload = row.to_dict()
    st.session_state["map_focus_facility"] = payload
    st.session_state.pop("map_focus_geo", None)
    lat = pd.to_numeric(row.get("facility_latitude"), errors="coerce")
    lon = pd.to_numeric(row.get("facility_longitude"), errors="coerce")
    if pd.notna(lat) and pd.notna(lon):
        st.session_state["map_focus_view"] = {
            "latitude": float(lat), "longitude": float(lon), "zoom": float(zoom)
        }


def _now_viewing_chip(districts: pd.DataFrame) -> None:
    """Small visible confirmation that a jump/selection is active in the hero."""
    facility = st.session_state.get("map_focus_facility")
    if facility:
        name = html.escape(str(facility.get("facility_name") or "verification candidate"))
        st.markdown(
            '<div style="display:inline-flex;align-items:center;gap:.4rem;'
            'margin:.1rem 0 .55rem;padding:.22rem .6rem;border-radius:var(--radius-pill);'
            'background:rgba(255,190,72,.13);border:1px solid rgba(255,190,72,.34);'
            'font-size:.72rem;font-weight:640;color:var(--text)">'
            '<span style="color:var(--mid)">◎</span>'
            '<span style="color:var(--mdn-muted);font-weight:600">Now checking</span>'
            f'<span>{name}</span></div>',
            unsafe_allow_html=True,
        )
        return
    geo = st.session_state.get("map_focus_geo")
    if not geo:
        return
    name = geo.get("district_name") or "unknown"
    state = geo.get("state_ut") or ""
    label = f"{html.escape(str(name))}, {html.escape(str(state))}" if state else html.escape(str(name))
    st.markdown(
        '<div style="display:inline-flex;align-items:center;gap:.4rem;'
        'margin:.1rem 0 .55rem;padding:.22rem .6rem;border-radius:var(--radius-pill);'
        'background:rgba(46,204,193,.14);border:1px solid rgba(46,204,193,.34);'
        'font-size:.72rem;font-weight:640;color:var(--text)">'
        '<span style="color:var(--good)">◎</span>'
        f'<span style="color:var(--mdn-muted);font-weight:600">Now viewing</span>'
        f'<span>{label}</span></div>',
        unsafe_allow_html=True,
    )


# --- E3: left district rail ---------------------------------------------------

def _rail_kpis(districts: pd.DataFrame) -> None:
    """≤2 decision-relevant KPIs kept compact above the list."""
    worst = _worst_district(districts)
    items: list[tuple[str, str, str]] = []
    tones: list[str] = []
    if worst is not None:
        name = f"{worst.get('district_name', 'unknown')}, {worst.get('state_ut', 'unknown')}"
        items.append((
            "Worst care gap",
            name,
            f"{_action_label(worst.get('planning_category'))} · "
            f"score {_fmt_num(worst.get('care_gap_score'))}",
        ))
        tones.append(_action_tone(worst.get("planning_category")))
    n_des = _desert_count(districts)
    items.append((
        "Zero-facility deserts",
        f"{n_des:,}",
        "NFHS need, no mapped facility",
    ))
    tones.append("danger" if n_des else "neutral")
    if items:
        ui.kpi_row(items, tone_each=tones)


# Tone -> the design-system color token (for custom rail markup only).
_TONE_VAR = {
    "deploy": "var(--good)", "verify": "var(--mid)", "danger": "var(--bad)",
    "info": "var(--info)", "neutral": "var(--mdn-muted)",
}


def _rail_row(row: pd.Series, districts: pd.DataFrame, facilities: pd.DataFrame,
              idx: int) -> None:
    """One selectable rail row: name+state, action pill, care-gap mini-bar, desert chip.

    The row is a thin (non-widget) button styled as a pill-row; clicking it focuses
    that district (recenter + detail) via ``_focus_on``.
    """
    name = str(row.get("district_name", "—"))
    state = str(row.get("state_ut", "—"))
    cat = row.get("planning_category")
    action = _action_label(cat)
    tone = _action_tone(cat)
    score = pd.to_numeric(row.get("care_gap_score"), errors="coerce")
    is_desert = bool(row.get("zero_facility_desert", False))

    selected = False
    geo = st.session_state.get("map_focus_geo")
    if geo and geo.get("district_name") == row.get("district_name") \
            and geo.get("state_ut") == row.get("state_ut"):
        selected = True

    # Mini care-gap bar (0..1 → width %). NaN -> no bar.
    pct = 0.0 if pd.isna(score) else max(0.0, min(1.0, float(score)))
    score_txt = "—" if pd.isna(score) else f"{float(score):.2f}"
    desert_chip = (
        '<span style="font-size:.6rem;font-weight:700;letter-spacing:.04em;'
        'padding:.06rem .34rem;border-radius:var(--radius-pill);'
        'background:rgba(255,82,82,.16);border:1px solid rgba(255,82,82,.4);'
        'color:var(--bad);white-space:nowrap">0 facilities</span>'
        if is_desert else ""
    )
    tone_color = _TONE_VAR.get(tone, "var(--mdn-muted)")
    sel_ring = ("box-shadow:0 0 0 1px var(--good) inset;background:rgba(46,204,193,.08);"
                if selected else "")

    st.markdown(
        f'<div class="rail-row" style="{sel_ring}">'
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:.5rem">'
        f'<div style="min-width:0"><div style="font-weight:640;font-size:.8rem;color:var(--text);'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{html.escape(name)}</div>'
        f'<div style="font-size:.68rem;color:var(--mdn-muted)">{html.escape(state)}</div></div>'
        '<div style="display:flex;align-items:center;gap:.35rem;flex-shrink:0">'
        f'{desert_chip}'
        f'<span style="font-size:.62rem;font-weight:740;letter-spacing:.03em;'
        f'padding:.1rem .46rem;border-radius:var(--radius-pill);color:{tone_color};'
        f'background:color-mix(in srgb,{tone_color} 15%,transparent);'
        f'border:1px solid color-mix(in srgb,{tone_color} 40%,transparent);'
        f'white-space:nowrap">{html.escape(action)}</span></div></div>'
        '<div style="display:flex;align-items:center;gap:.45rem;margin-top:.32rem">'
        '<span style="flex:1;height:5px;border-radius:999px;background:rgba(148,174,214,.16);'
        'overflow:hidden;display:block">'
        f'<span style="display:block;height:100%;width:{pct * 100:.0f}%;'
        f'background:{tone_color};border-radius:999px"></span></span>'
        f'<span style="font-size:.66rem;font-weight:680;color:var(--mdn-muted);'
        f'font-variant-numeric:tabular-nums">{score_txt}</span></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Select", key=f"rail_pick_{idx}",
                 use_container_width=True):
        _focus_on(row, districts, facilities)
        st.rerun()


def _verification_row(row: pd.Series, idx: int) -> None:
    """One compact facility row from the verification-priority queue."""
    def _clean(value) -> str:
        text = "" if value is None else str(value).strip()
        return "" if text.lower() in {"", "nan", "none", "null", "<na>"} else text

    name = _clean(row.get("facility_name")) or "Unnamed facility"
    district = _clean(row.get("district_name"))
    state = _clean(row.get("state_ut"))
    concern = str(row.get("primary_concern", "verify") or "verify").replace("_", " ")
    channel = str(row.get("verification_channel", "Check source") or "Check source")
    priority = pd.to_numeric(row.get("review_priority"), errors="coerce")
    priority_txt = "—" if pd.isna(priority) else f"{float(priority):.1f}"
    selected = False
    focused = st.session_state.get("map_focus_facility") or {}
    uid = str(row.get("unique_id", "") or "")
    if uid and str(focused.get("unique_id", "") or "") == uid:
        selected = True
    elif not uid and str(focused.get("facility_name", "") or "") == name:
        selected = True
    sel_ring = ("box-shadow:0 0 0 1px var(--mid) inset;background:rgba(255,190,72,.08);"
                if selected else "")
    loc = ", ".join(part for part in [district, state] if part) or "Location needs review"
    st.markdown(
        f'<div class="rail-row" style="{sel_ring}">'
        '<div style="display:flex;align-items:center;justify-content:space-between;gap:.55rem">'
        f'<div style="min-width:0"><div style="font-weight:650;font-size:.8rem;color:var(--text);'
        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">{html.escape(name)}</div>'
        f'<div style="font-size:.68rem;color:var(--mdn-muted);overflow:hidden;text-overflow:ellipsis;'
        f'white-space:nowrap">{html.escape(loc)}</div></div>'
        f'<span style="font-size:.66rem;font-weight:760;color:var(--mid);'
        f'font-variant-numeric:tabular-nums">{priority_txt}</span></div>'
        '<div style="display:flex;align-items:center;gap:.35rem;margin-top:.34rem;flex-wrap:wrap">'
        f'<span style="font-size:.62rem;font-weight:720;padding:.08rem .42rem;'
        f'border-radius:var(--radius-pill);background:rgba(255,190,72,.13);'
        f'border:1px solid rgba(255,190,72,.34);color:var(--mid)">{html.escape(channel)}</span>'
        f'<span style="font-size:.62rem;color:var(--mdn-muted);overflow:hidden;'
        f'text-overflow:ellipsis;white-space:nowrap">{html.escape(concern)}</span></div></div>',
        unsafe_allow_html=True,
    )
    if st.button("Open", key=f"verify_pick_{idx}", use_container_width=True):
        _focus_on_facility(row)
        st.rerun()


def _verification_rail(facilities: pd.DataFrame, specialty: str) -> None:
    """Compact queue of facilities with the highest verification priority."""
    queue = data.verification_queue(facilities, specialty, "All", top_n=75)
    if queue.empty:
        st.caption("No verification candidates match this service filter.")
        return
    st.caption(f"{len(queue):,} facilities · highest verification priority · click **Open**")
    with st.container(height=360):
        for i, (_, row) in enumerate(queue.iterrows()):
            _verification_row(row, i)


def _left_rail(
    districts: pd.DataFrame,
    facilities: pd.DataFrame,
    specialty: str,
    all_districts: pd.DataFrame | None = None,
) -> None:
    """The frosted LEFT district rail: 2 KPIs + search + scrollable ranked list.

    Reuses the care-gap ranking (worst first). The list lives in a height-bounded,
    scrollable container so the page does NOT grow tall (the "too much scrolling"
    fix). Selecting a row drives map recenter + detail via ``_focus_on``.
    """
    box = st.container(border=True)
    box.markdown(
        """
        <style>
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.map-rail-marker) {
          background: var(--glass-bg);
          border: 1px solid var(--glass-border);
          border-radius: var(--radius-card);
          box-shadow: var(--shadow-card);
          padding: var(--pad-card);
          -webkit-backdrop-filter: var(--glass-blur);
          backdrop-filter: var(--glass-blur);
        }
        /* Compact, pill-row look for each rail entry's hidden Select button. */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.map-rail-marker)
          .rail-row { padding:.5rem .55rem;border-radius:var(--radius-sm);
          border:1px solid var(--glass-border);background:var(--glass-bg-soft);
          margin-bottom:.05rem; }
        </style>
        <div class="map-rail-marker"></div>
        """,
        unsafe_allow_html=True,
    )
    with box:
        mode = st.segmented_control(
            "Rail mode",
            ["Districts", "Needs verification"],
            default="Districts",
            key="map_rail_mode",
            label_visibility="collapsed",
            width="stretch",
        ) or "Districts"
        header = "District rail" if mode == "Districts" else "Verification rail"
        st.markdown(f'<div class="mdn-panel-h">{header}</div>', unsafe_allow_html=True)
        _now_viewing_chip(districts)
        if mode == "Needs verification":
            _verification_rail(facilities, specialty)
            return
        scope_source = all_districts if all_districts is not None else districts
        _district_scope_control(
            scope_source,
            "map_district_scope_filter",
            clear_on_change=("map_focus_geo", "map_focus_facility"),
        )
        _rail_kpis(districts)
        st.markdown('<div style="height:.4rem"></div>', unsafe_allow_html=True)

        query = st.text_input(
            "Search districts", key="rail_search", placeholder="Filter by district name…",
            label_visibility="collapsed")

        ranked = pd.DataFrame()
        if districts is not None and not districts.empty and "care_gap_score" in districts:
            ranked = districts.sort_values("care_gap_score", ascending=False).copy()
            if query:
                q = query.strip().lower()
                mask = (ranked.get("district_name").astype(str).str.lower().str.contains(q, na=False)
                        | ranked.get("state_ut").astype(str).str.lower().str.contains(q, na=False))
                ranked = ranked[mask]

        if ranked.empty:
            st.caption("No districts match your search.")
            return

        st.caption(f"{len(ranked):,} districts · worst care gap first · click **Select** to focus")
        # Height-bounded, scrollable list keeps the page from growing tall.
        list_box = st.container(height=360)
        with list_box:
            for i, (_, row) in enumerate(ranked.head(60).iterrows()):
                _rail_row(row, districts, facilities, i)
        if len(ranked) > 60:
            st.caption(f"Showing the worst 60 of {len(ranked):,}. Refine the search to narrow.")


def _floating_legend(view_mode: str, n_plotted: int, filtered_n: int,
                     total_n: int) -> None:
    """The color-ramp legend rendered as a floating chip (``.mdn-float``) over the map.

    Streamlit's flow makes true absolute-over-canvas positioning brittle, so per
    docs/DESIGN_SYSTEM.md this acceptable compromise sits directly above the map within
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


def _map_tooltip() -> dict:
    """E6: a richer hover — a small nested dark card instead of a flat ``{tip}`` line.

    Both layer payloads carry a pre-rendered ``tip`` HTML string (district / facility);
    pydeck templates can't do conditional logic, so we keep ``{tip}`` as the body but
    upgrade its CARD styling (rounded, dark, legible, accent rule) and let
    ``data.district_hexes`` / ``data.facility_points`` decide which fields each tip
    carries — missing fields are simply absent from the rendered string (no fabrication).

    The district ``tip`` already includes care gap + need + facility count; we enrich it
    below at build time when the extra columns (action, trust-supply %, uncertainty) are
    present on the layer data.
    """
    return {
        "html": (
            '<div style="font-family:Inter,system-ui,sans-serif;min-width:170px;'
            'max-width:260px">{tip}</div>'
        ),
        "style": {
            "backgroundColor": "rgba(7,17,31,.96)",
            "color": "#eaf2ff",
            "fontSize": "12px",
            "lineHeight": "1.42",
            "borderRadius": "12px",
            "border": "1px solid rgba(148,163,184,.34)",
            "boxShadow": "0 12px 40px rgba(0,0,0,.48)",
            "padding": "10px 12px",
            "backdropFilter": "blur(8px)",
        },
    }


def _enrich_desert_tips(deserts: pd.DataFrame) -> pd.DataFrame:
    """Augment the per-district hover ``tip`` with action, provider trust, uncertainty.

    Renders a small nested card. Each extra row is added ONLY when the source field is
    present/usable on the layer data — absent fields are omitted, never fabricated.
    """
    if deserts is None or deserts.empty or "tip" not in deserts.columns:
        return deserts
    d = deserts.copy()

    cat = d.get("planning_category")
    tone_token = {
        "real_desert_candidate": "#2eccc1",
        "phantom_desert_or_verification_gap": "#ffbe48",
        "supply_record_quality_problem": "#ff5252",
        "referral_or_capacity_candidate": "#66d9ff",
        "mixed_or_monitor": "#97a8c2",
    }

    def _row(r):
        parts = [str(r.get("tip", ""))]
        # Recommended action (tone-coded chip), when planning_category is present.
        if cat is not None:
            c = r.get("planning_category")
            if pd.notna(c):
                lbl = _action_label(c)
                col = tone_token.get(str(c), "#97a8c2")
                parts.append(
                    f'<div style="margin-top:6px;font-size:11px"><span style="color:#97a8c2">'
                    f'Action</span> <b style="color:{col}">{html.escape(lbl)}</b></div>'
                )
        # Provider-trust %, when present and non-NaN.
        tsr = pd.to_numeric(
            r.get("provider_trust_score", r.get("trustworthy_supply_rate")),
            errors="coerce",
        )
        if pd.notna(tsr):
            parts.append(
                f'<div style="font-size:11px;color:#97a8c2">Provider trust '
                f'<b style="color:#eaf2ff">{tsr * 100:.0f}%</b></div>'
            )
        # Uncertainty tier, when present.
        unc = r.get("district_uncertainty_level")
        if unc is not None and pd.notna(unc) and str(unc).strip():
            parts.append(
                f'<div style="font-size:11px;color:#97a8c2">Uncertainty '
                f'<b style="color:#eaf2ff">{html.escape(str(unc).title())}</b></div>'
            )
        return "".join(parts)

    d["tip"] = d.apply(_row, axis=1)
    return d


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
        use_container_width=True,
        key="map_trust_distribution_chart")
    st.caption("High = passes all checks · Medium = some supply fields estimated (CatBoost) · "
               "Verify = missing supply. Automated checks, not human verification.")


def _region_detail(row: pd.Series, specialty: str, districts: pd.DataFrame,
                   facilities: pd.DataFrame) -> None:
    """Render district detail with facility cards when the shared UI supports it."""
    try:
        ui.region_detail(row, specialty, districts, facilities=facilities)
    except TypeError as exc:
        if "unexpected keyword argument 'facilities'" not in str(exc):
            raise
        ui.region_detail(row, specialty, districts)


def render(facilities: pd.DataFrame, districts: pd.DataFrame, specialty: str) -> None:
    active_scope = _district_scope_value()
    scoped_districts = _district_scope_filter(districts, active_scope)
    scoped_facilities_all = data.filter_facilities_to_districts(facilities, scoped_districts)

    ui.tab_intro(
        "India care-gap atlas",
        f"{specialty} lens · trust-weighted demand, supply, and uncertainty",
    )

    # --- Header orientation: one calm line, with explanation only on hover/focus. ---
    st.markdown(
        '<div class="mdn-muted" style="margin:-.2rem 0 .25rem;line-height:1.4">'
        'Every district is scored by care gap — search the rail or click the map to '
        'pick one.'
        '<span class="mdn-inline-help" tabindex="0">why this matters'
        '<span class="mdn-inline-help-card">Districts with high NFHS need still count '
        'when mapped provider evidence is sparse. That keeps likely medical deserts '
        'visible instead of hiding them as missing data.</span></span></div>',
        unsafe_allow_html=True,
    )

    # ---- All controls behind one detail expander (kept off the first glance).
    # Expander bodies still execute every run, so the widget values below are always
    # resolved — collapsing only hides them, it does not skip them. ----
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

    st.session_state["map_dots_on"] = bool(show_points)
    filtered = data.filter_facilities(scoped_facilities_all, specialty, include_geo_flagged)
    deserts = data.district_hexes(scoped_districts, resolution) if view_mode == "Medical deserts" else None
    cells = data.hexbin(filtered, config.DEFAULT_METRIC, resolution) if view_mode == "Facility coverage" else None
    points = data.facility_points(filtered) if show_points else None

    # E6: enrich the per-district hover tip with action / trust-supply / uncertainty
    # by joining the extra columns from the source districts table onto the layer.
    if deserts is not None and not deserts.empty:
        extra_cols = [c for c in ("planning_category", "district_uncertainty_level", "provider_trust_score")
                      if c in scoped_districts.columns]
        if extra_cols:
            merge_cols = ["district_name", "state_ut", *extra_cols]
            deserts = deserts.merge(
                scoped_districts[merge_cols].drop_duplicates(["district_name", "state_ut"]),
                on=["district_name", "state_ut"], how="left")
        deserts = _enrich_desert_tips(deserts)

    layers = _build_layers(deserts, cells, points, show_points)
    if not layers:
        # Still show the rail so the tab never collapses to a bare info box.
        hcol, mcol = st.columns([1, 2.3])
        with hcol:
            _left_rail(scoped_districts, facilities, specialty, districts)
        with mcol:
            st.info("No mappable data for this selection.")
        return

    # ---- Re-center the map when a jump/selection was made; else the calm national
    # overview. Consume the one-shot focus view ONLY when applying it (so a stray
    # on_select rerun cannot swallow a pending jump — map_focus_geo stays persistent). ----
    focus_view = st.session_state.pop("map_focus_view", None)
    view = pdk.ViewState(**(focus_view if focus_view else config.INDIA_VIEW))

    deck = pdk.Deck(layers=layers, initial_view_state=view,
                    map_style=config.MAP_STYLES[basemap], tooltip=_map_tooltip())

    # ===== COMPOSITION: left district rail · right map (centerpiece) =====
    rail_col, map_col = st.columns([1, 2.3])
    with rail_col:
        _left_rail(scoped_districts, facilities, specialty, districts)
    with map_col:
        # Floating legend chip reads as an overlay sitting just above the map canvas.
        n_plotted = 0 if deserts is None else len(deserts)
        _floating_legend(view_mode, n_plotted, len(filtered), len(scoped_facilities_all))
        event = st.pydeck_chart(deck, height=620, key="map",
                                on_select="rerun", selection_mode="single-object")

    # ---- Selected detail: facility card or district drill-down (opens on an answer).
    # A fresh click on the map wins; otherwise the persistent focus (rail/jump); else
    # the worst district. A map district click also refreshes the persistent focus so
    # the "Now viewing" chip + rail highlight stay in sync. ----
    picked_f = _picked_facility(event)
    picked_d = _picked_district(event)
    if picked_f:
        st.session_state.pop("map_focus_geo", None)
        st.session_state.pop("map_focus_facility", None)
        ui.facility_card(picked_f)
    else:
        row = _district_row(scoped_districts, picked_d) if picked_d else None
        if row is not None:
            # A map hex click becomes the persistent selection (rail highlight + chip).
            st.session_state.pop("map_focus_facility", None)
            st.session_state["map_focus_geo"] = {
                "district_name": row.get("district_name"),
                "state_ut": row.get("state_ut"),
            }
        if row is None and st.session_state.get("map_focus_facility"):
            ui.verification_detail(pd.Series(st.session_state["map_focus_facility"]))
        else:
            focus_geo = st.session_state.get("map_focus_geo")
            if focus_geo:
                row = _district_row(scoped_districts, focus_geo)
            if row is None:
                row = _worst_district(scoped_districts)
                if row is not None:
                    st.caption("Showing the highest care-gap district. Select a hex or rail row to change it.")
            if row is not None:
                _region_detail(row, specialty, scoped_districts, facilities)

    # ---- Depth on demand: coverage snapshot, methodology ----
    with ui.detail("Coverage snapshot & data trust"):
        _coverage_snapshot(scoped_facilities_all, filtered, scoped_districts)

    with ui.detail("How to read this map"):
        st.markdown(
            "- **Medical deserts** colors every district by its care-gap score "
            "(green = better coverage, red = wider gap), so zero-facility deserts that "
            "facility-count maps miss still appear.\n"
            "- **Facility coverage** hexbins the mapped facilities by the "
            f"*{config.DEFAULT_METRIC}* metric.\n"
            "- **Facility dots** overlay individual facilities; click one for its cited "
            "evidence and trust badge.\n"
            "- The **district rail** (left) lists every district worst-gap-first; search "
            "or click **Select** to recenter the map and open its breakdown.\n"
            "- Scores are proxy decision-support from NFHS-5 district indicators (2019–21) "
            "and a web-derived facility snapshot — claims, not a verified census."
        )
