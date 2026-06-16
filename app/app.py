"""CareGap — evidence-checked medical-desert planning across India.

Thin app entry: page config, CSS, data load, the specialty lens, and a 3-tab
nav (Map · Top care gaps · Copilot) dispatching to the per-tab modules. Tab
internals live in ``lib/tab_map.py``, ``lib/tab_gaps.py`` and ``lib/copilot.py``;
shared helpers/constants live in ``lib/tab_common.py``. The design system (tokens
+ reusable components) lives in ``lib/ui.py`` — see docs/DESIGN_SYSTEM.md.

Run locally:
    .venv/bin/streamlit run app/app.py
"""
from __future__ import annotations

import html
import re

import streamlit as st

from lib import config, data, ui, copilot
from lib import tab_map, tab_gaps
# Kept for the next wave: the Copilot will use interventions/simulator and a
# minimal inline Save (decisions). Not routed as standalone views.
from lib import decisions, interventions, simulator  # noqa: F401


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

    # New design-system primitives — patched onto a stale module if missing so
    # the split tab modules never crash mid-session. Canonical defs in lib/ui.py.
    if not hasattr(ui, "panel_header"):
        def panel_header(text: str) -> None:
            st.markdown(
                f'<div class="mdn-panel-h">{html.escape(str(text))}</div>',
                unsafe_allow_html=True,
            )

        ui.panel_header = panel_header

    if not hasattr(ui, "tab_intro"):
        def tab_intro(title: str, subtitle: str = "") -> None:
            sub = f"<span>{html.escape(str(subtitle))}</span>" if subtitle else ""
            st.markdown(
                f"""
                <div class="mdn-earth-strip">
                  <div><strong>{html.escape(str(title))}</strong>{sub}</div>
                  <div class="mdn-status-dot"></div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        ui.tab_intro = tab_intro

    if not hasattr(ui, "detail"):
        def detail(label: str):
            return st.expander(label, expanded=False)

        ui.detail = detail

    if not hasattr(ui, "kpi_row"):
        def kpi_row(items, tone_each=None) -> None:
            items = list(items)[:3]
            if not items:
                return
            tones = list(tone_each or [])
            cols = st.columns(len(items))
            for i, (col, item) in enumerate(zip(cols, items)):
                label, value, caption = (list(item) + ["", "", ""])[:3]
                tone = tones[i] if i < len(tones) else "neutral"
                with col:
                    ui.stat_card(label, value, caption, tone)

        ui.kpi_row = kpi_row


_ensure_ui_helpers()

st.set_page_config(page_title=config.APP_TITLE, layout="wide", page_icon="🩺")
ui.inject_css()


@st.cache_data(show_spinner="Loading facilities…")
def _facilities():
    return data.load_facilities()


@st.cache_data(show_spinner="Loading districts…")
def _districts():
    return data.load_districts()


@st.cache_data(show_spinner="Calibrating provider trust…")
def _districts_with_provider_trust(districts, facilities):
    return data.attach_provider_trust(districts, facilities)


def _route_slug(value: object) -> str:
    text = str(value or "").strip().lower()
    if text == "?":
        return "?"
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _query_value(params: object, key: str) -> str:
    try:
        values = params.get_all(key)
        if values:
            return str(values[-1])
    except (AttributeError, KeyError, TypeError):
        pass

    try:
        value = params.get(key)  # type: ignore[attr-defined]
    except (AttributeError, KeyError, TypeError):
        return ""
    if isinstance(value, (list, tuple)):
        return str(value[-1]) if value else ""
    return str(value or "")


def _view_from_query(value: object) -> str | None:
    return {
        "care gaps": "Top care gaps",
        "copilot": "Copilot",
        "gap": "Top care gaps",
        "gaps": "Top care gaps",
        "map": "Map",
        "maps": "Map",
        "top care gaps": "Top care gaps",
    }.get(_route_slug(value))


def _apply_demo_route_from_query() -> None:
    """One-shot query-param routing for deterministic screenshot demos."""
    params = st.query_params if hasattr(st, "query_params") else st.experimental_get_query_params()
    tab_value = _query_value(params, "tab") or _query_value(params, "view")
    mode_value = _query_value(params, "copilot_mode") or _query_value(params, "mode")
    route_token = f"tab={_route_slug(tab_value)};mode={_route_slug(mode_value)}"
    if route_token == "tab=;mode=":
        st.session_state.pop("_demo_route_token", None)
        return
    if st.session_state.get("_demo_route_token") == route_token:
        return

    routed_view = _view_from_query(tab_value)
    routed_mode = copilot.route_mode_from_query(mode_value)
    if routed_view:
        st.session_state["primary_view"] = routed_view
    if routed_mode:
        st.session_state["cp_mode"] = routed_mode
        st.session_state["primary_view"] = "Copilot"
    st.session_state["_demo_route_token"] = route_token


def main() -> None:
    _apply_demo_route_from_query()
    facilities = _facilities()
    districts = _districts_with_provider_trust(_districts(), facilities)
    ui.header()

    # E4: header collapsed to one line. The redundant orbit-note bubble and the
    # "Plan · Map · …" nav-caption were removed (the segmented control already
    # labels the tabs) so the map / wow-stat sit near the top. Only the
    # specialty lens remains.
    lens_col, _ = st.columns([1.05, 3.2], gap="medium")
    with lens_col:
        specialty = st.selectbox("Filter by service (optional)", list(config.SPECIALTIES.keys()), index=0)

    primary_view = st.segmented_control(
        "Primary view",
        ["Map", "Top care gaps", "Copilot"],
        default=None if "primary_view" in st.session_state else "Map",
        label_visibility="collapsed",
        key="primary_view",
        width="stretch",
    )
    primary_view = primary_view or st.session_state.get("primary_view") or "Map"
    if primary_view == "Map":
        tab_map.render(facilities, districts, specialty)
    elif primary_view == "Top care gaps":
        tab_gaps.render(facilities, districts, specialty)
    else:
        copilot.render_copilot(facilities, districts, specialty)


if __name__ == "__main__":
    main()
