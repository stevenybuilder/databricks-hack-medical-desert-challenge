"""CareGap — evidence-checked medical-desert planning across India.

Thin app entry: page config, CSS, data load, the specialty lens, and a 3-tab
nav (Map · Top care gaps · Copilot) dispatching to the per-tab modules. Tab
internals live in ``lib/tab_map.py``, ``lib/tab_gaps.py`` and ``lib/copilot.py``;
shared helpers/constants live in ``lib/tab_common.py``. The design system (tokens
+ reusable components) lives in ``lib/ui.py`` — see DESIGN_SYSTEM.md.

Run locally:
    .venv/bin/streamlit run app/app.py
"""
from __future__ import annotations

import html

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


def main() -> None:
    facilities = _facilities()
    districts = _districts()
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
        default="Map",
        label_visibility="collapsed",
        key="primary_view",
        width="stretch",
    )
    primary_view = primary_view or "Map"
    if primary_view == "Map":
        tab_map.render(facilities, districts, specialty)
    elif primary_view == "Top care gaps":
        tab_gaps.render(districts, specialty)
    else:
        copilot.render_copilot(facilities, districts, specialty)


if __name__ == "__main__":
    main()
