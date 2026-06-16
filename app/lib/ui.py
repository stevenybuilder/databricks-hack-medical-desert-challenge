"""Shared UI helpers: global CSS, header, and small components."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config, data

_CSS = """
<style>
:root {
  --mdn-bg: #04070d;
  --mdn-panel: rgba(11, 19, 33, .68);
  --mdn-panel-soft: rgba(13, 23, 39, .55);
  --mdn-glass-border: rgba(148, 174, 214, .14);
  --mdn-line: rgba(148, 174, 214, .15);
  --mdn-line-strong: rgba(148, 174, 214, .28);
  --mdn-text: #eef4ff;
  --mdn-muted: #97a8c2;
  --mdn-dim: #8295ad;
  --mdn-teal: #2eccc1;
  --mdn-sky: #66d9ff;
  --mdn-amber: #ffbe48;
  --mdn-red: #ff5252;
  --mdn-elev: 0 18px 48px rgba(0, 0, 0, .42);
  --mdn-elev-soft: 0 10px 30px rgba(0, 0, 0, .28);
  /* two-tier elevation scale: depth is intentional, not ad-hoc */
  --mdn-elev-1: 0 6px 18px rgba(0, 0, 0, .28);
  --mdn-elev-2: 0 14px 34px rgba(0, 0, 0, .42);
  --mdn-radius: 12px;
  --mdn-radius-lg: 14px;
  --mdn-font: "Inter", "SF Pro Display", ui-sans-serif, -apple-system,
              BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
              system-ui, sans-serif;
  /* tabular numerals -> the precise HUD / command-center readout feel */
  --mdn-tnum: "tnum" 1, "lnum" 1;
}

#MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden;}
html, body, .stApp, [data-testid="stAppViewContainer"] {
  /* deep space -> surface: radial glow over a vertical descent gradient */
  background:
    radial-gradient(1200px 620px at 18% -8%, rgba(46, 204, 193, .10), transparent 60%),
    radial-gradient(1100px 720px at 88% 0%, rgba(102, 217, 255, .08), transparent 58%),
    radial-gradient(1400px 900px at 50% 120%, rgba(8, 22, 44, .9), transparent 70%),
    linear-gradient(178deg, #05090f 0%, #04070d 42%, #03060b 100%);
  background-attachment: fixed;
  color: var(--mdn-text);
  font-family: var(--mdn-font);
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
  letter-spacing: .005em;
}
html, body, .stApp, [data-testid="stAppViewContainer"],
[data-testid="stMarkdownContainer"], button, input, select, textarea {
  font-family: var(--mdn-font);
}
[data-testid="stSidebar"] {background: rgba(7, 13, 24, .9);}
.block-container {
  padding: .7rem 1.15rem 1.2rem 1.15rem;
  max-width: 100%;
}
[data-testid="stVerticalBlock"] {gap: .74rem;}
[data-testid="stMarkdownContainer"], [data-testid="stCaptionContainer"],
[data-testid="stText"], label, p, span {color: inherit;}
[data-testid="stCaptionContainer"] {color: var(--mdn-muted);}
a {color: var(--mdn-sky); text-decoration: none;}
a:hover {text-decoration: underline;}
hr {border-color: var(--mdn-line);}
* {transition: border-color .18s ease, box-shadow .18s ease,
   background-color .18s ease, color .18s ease, transform .18s ease;}

.mdn-topbar {
  position: sticky;
  top: .4rem;
  z-index: 50;
  display: flex;
  align-items: center;
  gap: .7rem;
  padding: .6rem .85rem;
  margin-bottom: .2rem;
  background: linear-gradient(180deg, rgba(11, 21, 38, .8), rgba(6, 12, 22, .72));
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius-lg);
  box-shadow: var(--mdn-elev);
  -webkit-backdrop-filter: blur(20px) saturate(140%);
  backdrop-filter: blur(20px) saturate(140%);
}
.mdn-logo {
  width: 32px;
  height: 32px;
  border-radius: 10px;
  background: radial-gradient(120% 120% at 30% 20%, rgba(46, 204, 193, .35), rgba(7, 17, 31, .9));
  border: 1px solid rgba(102, 217, 255, .42);
  color: #d4faff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 800;
  box-shadow: 0 0 18px rgba(46, 204, 193, .35);
}
.mdn-title {font-size: 1.1rem; font-weight: 720; color: var(--mdn-text); line-height: 1; letter-spacing: -.01em;}
.mdn-sub {font-size: .76rem; color: var(--mdn-muted); margin-top: 3px;}
.mdn-chip {
  margin-left: auto;
  font-size: .7rem;
  font-weight: 600;
  color: #cfe0f3;
  background: rgba(14, 26, 44, .7);
  border: 1px solid var(--mdn-glass-border);
  border-radius: 999px;
  padding: .28rem .68rem;
  white-space: nowrap;
  -webkit-backdrop-filter: blur(8px);
  backdrop-filter: blur(8px);
}
.mdn-orbit-note {
  min-height: 56px;
  display: flex;
  align-items: center;
  padding: .72rem .9rem;
  color: var(--mdn-muted);
  background: var(--mdn-panel-soft);
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  font-size: .82rem;
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
}
.mdn-earth-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .8rem;
  padding: .68rem .85rem;
  background: linear-gradient(180deg, rgba(13, 24, 42, .62), rgba(8, 15, 26, .5));
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  box-shadow: var(--mdn-elev-soft);
  -webkit-backdrop-filter: blur(16px) saturate(130%);
  backdrop-filter: blur(16px) saturate(130%);
}
.mdn-earth-strip strong {
  display: block;
  color: var(--mdn-text);
  font-size: 1rem;
  line-height: 1.1;
}
.mdn-earth-strip span {color: var(--mdn-muted); font-size: .78rem;}
.mdn-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--mdn-teal);
  box-shadow: 0 0 14px rgba(46, 204, 193, .7);
  flex: 0 0 auto;
}
.mdn-card {
  position: relative;
  background: linear-gradient(180deg, rgba(13, 24, 42, .6), rgba(8, 15, 26, .48));
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  padding: .9rem .95rem;
  min-height: 104px;
  box-shadow: var(--mdn-elev-soft);
  -webkit-backdrop-filter: blur(14px) saturate(125%);
  backdrop-filter: blur(14px) saturate(125%);
  overflow: hidden;
}
.mdn-card::before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--mdn-line-strong);
  opacity: .7;
}
.mdn-card:hover {
  transform: translateY(-1px);
  box-shadow: var(--mdn-elev-2);
  border-color: var(--mdn-line-strong);
}
.mdn-card--deploy {border-color: rgba(46, 204, 193, .38);}
.mdn-card--deploy::before {background: var(--mdn-teal); box-shadow: 0 0 16px rgba(46, 204, 193, .6);}
.mdn-card--verify {border-color: rgba(255, 190, 72, .38);}
.mdn-card--verify::before {background: var(--mdn-amber); box-shadow: 0 0 16px rgba(255, 190, 72, .55);}
.mdn-card--danger {border-color: rgba(255, 82, 82, .38);}
.mdn-card--danger::before {background: var(--mdn-red); box-shadow: 0 0 16px rgba(255, 82, 82, .55);}
.mdn-card--info {border-color: rgba(102, 217, 255, .38);}
.mdn-card--info::before {background: var(--mdn-sky); box-shadow: 0 0 16px rgba(102, 217, 255, .55);}
.mdn-card-kicker {
  color: var(--mdn-muted);
  font-size: .68rem;
  font-weight: 760;
  letter-spacing: .08em;
  text-transform: uppercase;
}
.mdn-card-value {
  margin-top: .28rem;
  color: var(--mdn-text);
  font-size: 1.36rem;
  font-weight: 800;
  line-height: 1.08;
  font-variant-numeric: tabular-nums;
  font-feature-settings: var(--mdn-tnum);
}
.mdn-card-caption {
  margin-top: .32rem;
  color: var(--mdn-muted);
  font-size: .78rem;
  line-height: 1.28;
}
.mdn-decision-banner {
  display: flex;
  align-items: flex-start;
  gap: .72rem;
  padding: .9rem .95rem;
  background: linear-gradient(180deg, rgba(13, 24, 42, .66), rgba(8, 15, 26, .52));
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  box-shadow: var(--mdn-elev-soft);
  -webkit-backdrop-filter: blur(14px);
  backdrop-filter: blur(14px);
}
.mdn-decision-banner strong {
  display: block;
  color: var(--mdn-text);
  font-size: 1.06rem;
  line-height: 1.15;
}
.mdn-decision-banner span {
  display: block;
  color: var(--mdn-muted);
  font-size: .8rem;
  line-height: 1.35;
  margin-top: .22rem;
}
.mdn-rail {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: .5rem;
}
.mdn-rail-step {
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  padding: .64rem .7rem;
  background: var(--mdn-panel-soft);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.mdn-rail-step:hover {border-color: var(--mdn-line-strong); transform: translateY(-1px);}
.mdn-rail-step b {
  display: block;
  color: var(--mdn-text);
  font-size: .78rem;
}
.mdn-rail-step span {
  display: block;
  color: var(--mdn-muted);
  font-size: .72rem;
  line-height: 1.25;
  margin-top: .18rem;
}
.mdn-pill-row {display: flex; flex-wrap: wrap; gap: .35rem; margin: .25rem 0 .15rem;}
.mdn-pill {
  display: inline-flex;
  align-items: center;
  border-radius: 999px;
  border: 1px solid var(--mdn-line);
  background: rgba(12, 22, 38, .94);
  color: #c9d8ea;
  padding: .18rem .5rem;
  font-size: .7rem;
  font-weight: 700;
}
.mdn-pill--deploy {color:#a7fff3; background:#0d3c3a; border-color:rgba(46,204,193,.35);}
.mdn-pill--verify {color:#ffe2a4; background:#49310f; border-color:rgba(255,190,72,.35);}
.mdn-pill--danger {color:#ffc2c2; background:#4a171b; border-color:rgba(255,82,82,.35);}
.mdn-pill--info {color:#bdefff; background:#0d3142; border-color:rgba(102,217,255,.35);}
.mdn-pill--muted {color:#d0d8e6; background:#1b2738; border-color:rgba(148,163,184,.28);}

[data-testid="stSelectbox"], [data-testid="stSlider"], [data-testid="stCheckbox"],
[data-testid="stToggle"], [data-testid="stButton"] {color: var(--mdn-text);}
div[data-baseweb="select"] > div {
  background: rgba(9, 17, 30, .8);
  border-color: var(--mdn-line-strong);
  border-radius: 10px;
  min-height: 40px;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
div[data-baseweb="select"] > div:hover {border-color: rgba(102, 217, 255, .5);}
div[data-baseweb="select"]:focus-within > div {
  border-color: var(--mdn-teal);
  box-shadow: 0 0 0 2px rgba(46, 204, 193, .22);
}
div[data-baseweb="select"] div,
div[data-baseweb="select"] span,
div[data-baseweb="select"] input {
  color: var(--mdn-text) !important;
}
div[data-baseweb="select"] svg {fill: var(--mdn-muted) !important;}
div[data-baseweb="popover"] {background: rgba(8, 16, 28, .98); border-radius: 10px;}
[data-testid="stSlider"] [role="slider"] {background: var(--mdn-teal);}
[data-testid="stCheckbox"] label, [data-testid="stToggle"] label,
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label {
  color: #cfdcec !important;
  font-size: .74rem;
  font-weight: 600;
  letter-spacing: .01em;
}
[data-testid="stButton"] button {
  background: rgba(13, 24, 42, .7);
  border: 1px solid var(--mdn-line-strong);
  border-radius: 10px;
  color: var(--mdn-text);
  font-weight: 600;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
[data-testid="stButton"] button:hover {
  border-color: rgba(46, 204, 193, .6);
  box-shadow: 0 0 0 2px rgba(46, 204, 193, .16);
  color: #fff;
}

button[data-baseweb="tab"] {
  color: var(--mdn-muted);
  background: transparent;
  border-radius: 0;
  padding: .55rem .75rem;
}
button[data-baseweb="tab"][aria-selected="true"] {color: #fff;}
div[data-baseweb="tab-highlight"] {background: var(--mdn-teal);}
div[data-baseweb="tab-border"] {background: var(--mdn-line);}

/* ---- Segmented control: primary navigation + in-view sub-nav ---- */
div[data-testid="stSegmentedControl"] {margin: .15rem 0 .35rem;}
div[data-testid="stSegmentedControl"] > div {
  background: linear-gradient(180deg, rgba(11, 21, 38, .66), rgba(7, 13, 24, .58));
  border: 1px solid var(--mdn-glass-border);
  border-radius: 999px;
  padding: .22rem;
  gap: .12rem;
  box-shadow: var(--mdn-elev-soft);
  -webkit-backdrop-filter: blur(16px) saturate(130%);
  backdrop-filter: blur(16px) saturate(130%);
}
div[data-testid="stSegmentedControl"] button {
  background: transparent !important;
  border: 1px solid transparent !important;
  border-radius: 999px !important;
  color: var(--mdn-muted) !important;
  font-weight: 600 !important;
  font-size: .82rem !important;
  padding: .34rem .8rem !important;
  letter-spacing: .005em;
}
div[data-testid="stSegmentedControl"] button:hover {
  color: var(--mdn-text) !important;
  background: rgba(102, 217, 255, .08) !important;
}
div[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[data-testid="stSegmentedControl"] button[aria-selected="true"],
div[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"] {
  background: linear-gradient(180deg, rgba(46, 204, 193, .24), rgba(46, 204, 193, .1)) !important;
  border-color: rgba(46, 204, 193, .55) !important;
  color: #eafffb !important;
  box-shadow: 0 0 14px rgba(46, 204, 193, .28), inset 0 1px 0 rgba(255, 255, 255, .06);
}

/* radio (segmented-control fallback in some views) */
div[role="radiogroup"] label:hover {color: var(--mdn-text);}

[data-testid="stMetric"] {
  background: linear-gradient(180deg, rgba(13, 24, 42, .58), rgba(8, 15, 26, .46));
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  padding: .72rem .8rem;
  box-shadow: var(--mdn-elev-soft);
  -webkit-backdrop-filter: blur(12px) saturate(120%);
  backdrop-filter: blur(12px) saturate(120%);
}
[data-testid="stMetric"]:hover {border-color: var(--mdn-line-strong); transform: translateY(-1px);}
[data-testid="stMetricLabel"] p {font-size: .72rem; color: var(--mdn-muted); font-weight: 600; letter-spacing: .02em;}
[data-testid="stMetricValue"] {
  font-size: 1.34rem; font-weight: 760; color: var(--mdn-text); letter-spacing: -.01em;
  font-variant-numeric: tabular-nums;
  font-feature-settings: var(--mdn-tnum);
}
/* precise, non-jittering numbers in dense leaderboards & queues */
[data-testid="stDataFrame"], [data-testid="stTable"],
[data-testid="stMetricDelta"], .stDataFrame [role="gridcell"] {
  font-variant-numeric: tabular-nums;
  font-feature-settings: var(--mdn-tnum);
}
[data-testid="stMetricDelta"] svg {display: none;}
.mdn-panel-h {
  font-size: .72rem;
  font-weight: 700;
  letter-spacing: .1em;
  text-transform: uppercase;
  color: #93a8c4;
  margin: .45rem 0 .3rem;
  display: flex;
  align-items: center;
  gap: .5rem;
}
.mdn-panel-h::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: var(--mdn-teal);
  box-shadow: 0 0 10px rgba(46, 204, 193, .7);
  flex: 0 0 auto;
}
.mdn-muted {color: var(--mdn-muted); font-size: .8rem;}
[data-testid="stAlert"] {
  background: rgba(11, 21, 38, .62);
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  color: var(--mdn-text);
  -webkit-backdrop-filter: blur(12px);
  backdrop-filter: blur(12px);
}
[data-testid="stDataFrameResizable"], [data-testid="stDataFrame"] {
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  overflow: hidden;
  box-shadow: var(--mdn-elev-soft);
}
[data-testid="stSpinner"] {color: var(--mdn-teal);}
[data-testid="stExpander"] {
  border: 1px solid var(--mdn-glass-border);
  border-radius: var(--mdn-radius);
  background: var(--mdn-panel-soft);
  overflow: hidden;
}
[data-testid="stProgress"] > div > div > div {background: var(--mdn-teal);}

.mdn-legend-bar {
  height: 8px;
  border-radius: 999px;
  background: linear-gradient(90deg,#2eccc1 0%,#ffbe48 50%,#ff5252 100%);
  border: 1px solid rgba(255, 255, 255, .12);
  box-shadow: 0 0 16px rgba(46, 204, 193, .18), 0 4px 12px rgba(0, 0, 0, .3);
}
.mdn-legend-row {
  display: flex;
  justify-content: space-between;
  font-size: .7rem;
  color: var(--mdn-muted);
  margin-top: 4px;
}

/* ---- Two-tier navigation grouping (purely visual; labels drive dispatch) ---- */
.mdn-nav-groups {
  display: flex;
  align-items: center;
  gap: .55rem;
  flex-wrap: wrap;
  margin: .1rem 0 .15rem;
  font-size: .68rem;
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--mdn-dim);
  font-weight: 700;
}
.mdn-nav-groups .mdn-nav-grp {
  display: inline-flex;
  align-items: center;
  gap: .42rem;
  padding: .12rem .1rem;
}
.mdn-nav-groups .mdn-nav-grp::before {
  content: "";
  width: 6px;
  height: 6px;
  border-radius: 999px;
}
.mdn-nav-groups .mdn-nav-explore::before {background: var(--mdn-sky); box-shadow: 0 0 9px rgba(102,217,255,.6);}
.mdn-nav-groups .mdn-nav-act::before {background: var(--mdn-teal); box-shadow: 0 0 9px rgba(46,204,193,.6);}
.mdn-nav-groups .mdn-nav-verify::before {background: var(--mdn-amber); box-shadow: 0 0 9px rgba(255,190,72,.6);}
.mdn-nav-groups .mdn-nav-sep {color: rgba(148,174,214,.3); font-weight: 400;}

/* ---- Heading idiom: keep st.subheader / st.header on the house look ---- */
[data-testid="stHeading"] h1, [data-testid="stHeading"] h2,
[data-testid="stHeading"] h3, .stApp h1, .stApp h2, .stApp h3 {
  color: var(--mdn-text);
  font-family: var(--mdn-font);
  font-weight: 740;
  letter-spacing: -.01em;
}
[data-testid="stHeading"] h3, .stApp h3 {
  font-size: 1.04rem;
  line-height: 1.18;
}

/* ---- Accessibility: visible keyboard focus ring (was missing) ---- */
:where(button, [role="tab"], a, input, select, textarea,
       [data-baseweb="select"] > div, [role="checkbox"], [role="switch"],
       [role="slider"]):focus-visible {
  outline: 2px solid var(--mdn-sky);
  outline-offset: 2px;
  border-radius: 8px;
}

/* ---- "Live telemetry" pulse on the active primary-nav segment ---- */
@keyframes mdn-nav-pulse {
  0%, 100% { box-shadow: 0 0 12px rgba(46, 204, 193, .26), inset 0 1px 0 rgba(255,255,255,.06); }
  50%      { box-shadow: 0 0 20px rgba(46, 204, 193, .42), inset 0 1px 0 rgba(255,255,255,.08); }
}
div[data-testid="stSegmentedControl"] button[aria-checked="true"],
div[data-testid="stSegmentedControl"] button[aria-selected="true"],
div[data-testid="stSegmentedControl"] button[kind="segmented_controlActive"] {
  animation: mdn-nav-pulse 3.6s ease-in-out infinite;
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; }
}

/* ---- Consistent evidence / citation block (source links read as a HUD) ---- */
.mdn-evidence {
  border: 1px solid var(--mdn-glass-border);
  border-left: 3px solid var(--mdn-sky);
  border-radius: var(--mdn-radius);
  padding: .6rem .8rem;
  margin: .35rem 0;
  background: var(--mdn-panel-soft);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
  font-size: .82rem;
  color: var(--mdn-muted);
}

/* ---- Bar charts: align rendered svg corners with our radius ---- */
[data-testid="stVegaLiteChart"], [data-testid="stArrowVegaLiteChart"] {
  border-radius: var(--mdn-radius);
  overflow: hidden;
}
</style>
"""


def inject_css() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def header() -> None:
    st.markdown(
        f"""
        <div class="mdn-topbar">
          <div class="mdn-logo">M</div>
          <div>
            <div class="mdn-title">{config.APP_TITLE}</div>
            <div class="mdn-sub">{config.APP_TAGLINE}</div>
          </div>
          <div class="mdn-chip">India · evidence-weighted planning · uncertainty visible</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def workflow_rail(steps: list[tuple[str, str]]) -> None:
    body = "".join(
        f"""<div class="mdn-rail-step"><b>{html.escape(title)}</b>
        <span>{html.escape(text)}</span></div>"""
        for title, text in steps
    )
    st.markdown(f'<div class="mdn-rail">{body}</div>', unsafe_allow_html=True)


_BADGE = {
    "Passed checks": ("#a7fff3", "#0d3c3a"),
    "Needs review": ("#ffe2a4", "#49310f"),
    "Contradicted / geo-invalid": ("#ffc2c2", "#4a171b"),
    "Unknown": ("#d0d8e6", "#1b2738"),
}


def facility_card(f: dict) -> None:
    """Render a clicked facility's detail with status badge and cited source."""
    status = f.get("status", "Unknown")
    fg, bg = _BADGE.get(status, _BADGE["Unknown"])
    name = f.get("facility_name", "Unnamed facility")
    loc = " · ".join(x for x in [f.get("city"), f.get("district"), f.get("state")]
                     if x and x != "—")
    url = (f.get("source_url") or "").strip()
    evidence = (f.get("evidence") or "").strip()

    st.markdown(
        f"""
        <div style="border:1px solid rgba(148,174,214,.16);border-radius:12px;padding:.9rem 1rem;
             margin-top:.6rem;background:linear-gradient(180deg,rgba(13,24,42,.6),rgba(8,15,26,.48));
             box-shadow:0 10px 30px rgba(0,0,0,.28);backdrop-filter:blur(14px)">
          <div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap">
            <span style="font-size:1.05rem;font-weight:700;color:#eaf2ff">{name}</span>
            <span style="background:{bg};color:{fg};font-size:.72rem;font-weight:700;
                  padding:.2rem .6rem;border-radius:999px">{status}</span>
          </div>
          <div style="font-size:.83rem;color:#93a4b8;margin-top:.25rem">
            {f.get('facility_type','—')} · {loc or '—'} · geo: {f.get('geo_quality','—')}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if evidence:
        st.markdown(f"**Claimed (unverified):** {evidence}…")
    if url:
        st.markdown(f"**Source:** [{url[:80]}]({url})")
    else:
        st.caption("No source URL on record for this facility.")

    st.markdown('<div class="mdn-panel-h">Why this badge?</div>', unsafe_allow_html=True)
    explain_rows = [
        {
            "Signal": "Readiness / semantic quality",
            "Value": f"{_fmt(f.get('data_readiness_score'))} / {_fmt(f.get('semantic_data_quality_score'))}",
            "Interpretation": "Automated evidence quality from joins, geography, source URLs, contact evidence, and semantic missingness.",
        },
        {
            "Signal": "Join confidence",
            "Value": f"{_fmt(f.get('join_confidence'))} · {f.get('join_strategy', 'unknown')}",
            "Interpretation": f.get("join_uncertainty_reason") or "Facility-to-district context depends on this join.",
        },
        {
            "Signal": "Geo quality",
            "Value": f"{f.get('geo_quality', 'unknown')} · {_fmt(f.get('geo_distance_km_to_pincode_centroid'), 1)} km from PIN centroid",
            "Interpretation": "External geocoding should reduce uncertainty only when it agrees with PIN/district/state.",
        },
        {
            "Signal": "Estimated capacity",
            "Value": f"{_fmt(f.get('capacity_display_value'), 0)} ({_fmt_interval(f.get('capacity_estimate_interval_low'), f.get('capacity_estimate_interval_high'), 0)})",
            "Interpretation": f"{f.get('capacity_confidence', 'unknown')} confidence; estimated={bool(f.get('capacity_is_estimated', False))}.",
        },
        {
            "Signal": "Estimated doctors",
            "Value": f"{_fmt(f.get('doctor_count_display_value'), 0)} ({_fmt_interval(f.get('doctor_count_estimate_interval_low'), f.get('doctor_count_estimate_interval_high'), 0)})",
            "Interpretation": f"{f.get('doctor_count_confidence', 'unknown')} confidence; estimated={bool(f.get('doctor_count_is_estimated', False))}.",
        },
    ]
    st.dataframe(pd.DataFrame(explain_rows), hide_index=True, width="stretch", height=230)
    if status != "Passed checks":
        st.warning("This facility is flagged — verify the claim against the source "
                   "before relying on it.")


def _num(v, default=float("nan")):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt(v, digits: int = 2) -> str:
    value = _num(v)
    return "—" if pd.isna(value) else f"{value:.{digits}f}"


def _fmt_interval(low, high, digits: int = 1) -> str:
    lo = _num(low)
    hi = _num(high)
    if pd.isna(lo) or pd.isna(hi):
        return "unknown"
    return f"{lo:.{digits}f} to {hi:.{digits}f}"


def _fmt_int(v) -> str:
    value = _num(v)
    return "—" if pd.isna(value) else f"{int(value):,}"


def reason_chips(labels: list[str]) -> None:
    if not labels:
        st.caption("No reason codes recorded.")
        return
    chips = "".join(
        f"""<span style="display:inline-block;background:rgba(12,22,38,.95);
        border:1px solid rgba(148,163,184,.26);border-radius:999px;padding:.18rem .55rem;
        margin:.12rem;font-size:.75rem;font-weight:650;color:#c9d8ea">{label}</span>"""
        for label in labels
    )
    st.markdown(chips, unsafe_allow_html=True)


def region_detail(row: pd.Series, specialty: str) -> None:
    """Full district detail: recommendation, patient conditions, supply, evidence."""
    cat = str(row.get("planning_category", "mixed_or_monitor"))
    chip, rec = data.PLANNING.get(cat, data.PLANNING["mixed_or_monitor"])
    district = str(row.get("district_name", "—") or "—").strip()
    state = str(row.get("state_ut", "—") or "—").strip()
    name = f"{district}, {state}"

    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:.6rem;flex-wrap:wrap;margin-top:.3rem">
        <span style="font-size:1.15rem;font-weight:750;color:#eaf2ff">{name}</span>
        <span style="background:rgba(12,22,38,.95);border:1px solid rgba(148,163,184,.26);border-radius:999px;
        padding:.22rem .7rem;font-size:.78rem;font-weight:700;color:#c9d8ea">{chip}</span>
        </div>""", unsafe_allow_html=True)
    st.info(rec)

    obs = _num(row.get("observed_facility_rows"))
    trust = _num(row.get("trustworthy_supply_rows"))
    rate = _num(row.get("trustworthy_supply_rate"))
    c1, c2, c3 = st.columns(3)
    c1.metric("Health need", f"{_num(row.get('health_need_score')):.2f}")
    c2.metric("Trustworthy supply",
              "—" if pd.isna(rate) else f"{rate*100:.0f}%",
              help=f"{0 if pd.isna(trust) else int(trust)} of "
                   f"{0 if pd.isna(obs) else int(obs)} observed facilities passed checks")
    c3.metric("Data uncertainty", str(row.get("district_uncertainty_level", "—")).title())

    st.markdown('<div class="mdn-panel-h">Why this recommendation?</div>',
                unsafe_allow_html=True)
    explanation, reasons = data.district_explanation(row, specialty)
    st.dataframe(explanation, hide_index=True, width="stretch", height=285)
    if not reasons.empty:
        reason_chips(reasons["Reason"].tolist())

    # ---- patient-condition profile (what you'll treat) ----
    _, cond_cols = data.SPECIALTY_DISTRICT.get(specialty, (None, []))
    rows = [{"Condition": data.COND_LABELS.get(c, c), "Percent": _num(row.get(c))}
            for c in cond_cols if not pd.isna(_num(row.get(c)))]
    if rows:
        st.markdown('<div class="mdn-panel-h">Patient conditions here (NFHS district context)</div>',
                    unsafe_allow_html=True)
        prof = pd.DataFrame(rows)
        st.dataframe(
            prof, hide_index=True, width="stretch",
            column_config={"Percent": st.column_config.ProgressColumn(
                "Percent", format="%.1f%%", min_value=0, max_value=100)})
        st.caption("Context, not a facility fact. For access measures (births, screening) "
                   "low = worse; for burden (anaemia, BP, sugar) high = worse.")

    # ---- evidence / citations ----
    st.markdown('<div class="mdn-panel-h">Evidence (sample facilities & sources)</div>',
                unsafe_allow_html=True)
    names = str(row.get("sample_facility_names", "") or "").strip()
    claim = str(row.get("sample_claim_evidence", "") or "").strip()
    url = data._first_url(row.get("sample_source_urls", ""))
    if names:
        st.markdown(f"**Facilities:** {names[:300]}")
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:300]}…")
    if url:
        st.markdown(f"**Source:** [{url[:80]}]({url})")
    if not (names or claim or url):
        st.caption("No sample evidence recorded for this district.")


def verification_detail(row: pd.Series) -> None:
    """Inspect one facility candidate from the external validation queue."""
    name = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    concern = str(row.get("primary_concern", "—") or "—")
    seed = str(row.get("label_seed", "—") or "—")
    channel = str(row.get("verification_channel", "—") or "—")
    loc = " · ".join(
        x for x in [
            row.get("address_city"),
            row.get("district_name"),
            row.get("state_ut"),
        ]
        if isinstance(x, str) and x.strip()
    )

    st.markdown('<div class="mdn-panel-h">Selected verification candidate</div>',
                unsafe_allow_html=True)
    st.markdown(
        f"""
        <div style="border:1px solid rgba(148,174,214,.16);border-radius:12px;padding:.9rem 1rem;
             margin-top:.2rem;background:linear-gradient(180deg,rgba(13,24,42,.6),rgba(8,15,26,.48));
             box-shadow:0 10px 30px rgba(0,0,0,.28);backdrop-filter:blur(14px)">
          <div style="font-size:1rem;font-weight:750;color:#eaf2ff">{name}</div>
          <div style="font-size:.83rem;color:#93a4b8;margin-top:.2rem">{loc or '—'}</div>
          <div style="display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.55rem">
            <span style="background:#1b2738;border:1px solid rgba(148,163,184,.28);border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#d0d8e6">{seed}</span>
            <span style="background:#49310f;border:1px solid rgba(255,190,72,.35);border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#ffe2a4">{concern}</span>
            <span style="background:#0d3c3a;border:1px solid rgba(46,204,193,.35);border-radius:999px;
                  padding:.18rem .55rem;font-size:.76rem;font-weight:700;color:#a7fff3">{channel}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3 = st.columns(3)
    c1.metric("Readiness", f"{_num(row.get('data_readiness_score')):.2f}")
    c2.metric("Join confidence", f"{_num(row.get('join_confidence')):.2f}")
    c3.metric("Review priority", f"{_num(row.get('review_priority')):.1f}")

    contacts = []
    for label, value in [
        ("Phone", row.get("officialPhone")),
        ("Email", row.get("email")),
        ("Website", row.get("officialWebsite")),
        ("Source", row.get("first_source_url")),
    ]:
        value = str(value or "").strip()
        if value:
            contacts.append({"Field": label, "Value": value})
    if contacts:
        st.dataframe(pd.DataFrame(contacts), hide_index=True, width="stretch")
    else:
        st.caption("No direct contact or source field on this candidate.")

    claim = str(row.get("claim_text", "") or "").strip()
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:420]}…")

    st.caption("Seed labels are bootstrapping labels for a golden set. A Tier A match or "
               "manual call/email outcome should replace the seed before model calibration.")


def active_facility_detail(row: pd.Series) -> None:
    """Explain one row from active_learning_facility_queue.csv."""
    st.markdown('<div class="mdn-panel-h">Why this facility is fragile</div>',
                unsafe_allow_html=True)
    title = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    subtitle = " · ".join(
        item for item in [
            str(row.get("facilityTypeId", "") or "").strip(),
            str(row.get("district_name", "") or "").strip(),
            str(row.get("state_ut", "") or "").strip(),
        ]
        if item
    )
    st.markdown(f"**{title}**")
    if subtitle:
        st.caption(subtitle)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active score", _fmt(row.get("active_uncertainty_score")))
    m2.metric("Proxy trust", _fmt(row.get("proxy_trust_score")))
    m3.metric("Geo uncertainty", _fmt(row.get("external_geo_uncertainty_score")))
    m4.metric("Decision leverage", _fmt(row.get("decision_leverage_score")))

    st.dataframe(data.facility_explanation(row), hide_index=True, width="stretch", height=290)
    reason_chips(data.reason_labels(row.get("active_learning_reasons")))

    source = data._first_url(row.get("source_urls", ""))
    if source:
        st.markdown(f"**Source:** [{source[:90]}]({source})")
    claim = str(row.get("claim_text", "") or "").strip()
    if claim:
        st.markdown(f"**Claimed (unverified):** {claim[:520]}…")


def active_district_detail(row: pd.Series, specialty: str) -> None:
    """Explain one row from active_learning_district_queue.csv."""
    st.markdown('<div class="mdn-panel-h">Why this district is fragile</div>',
                unsafe_allow_html=True)
    district = str(row.get("district_name", "—") or "—").strip()
    state = str(row.get("state_ut", "—") or "—").strip()
    title = f"{district}, {state}"
    st.markdown(f"**{title}**")
    chip, rec = data.PLANNING.get(str(row.get("planning_category", "")), data.PLANNING["mixed_or_monitor"])
    st.info(f"{chip}: {rec}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Active score", _fmt(row.get("active_uncertainty_score")))
    m2.metric("Aggregate CI width", _fmt(row.get("aggregate_ci_width")))
    m3.metric("Observed rows", _fmt_int(row.get("observed_facility_rows")))
    m4.metric("Sample uncertainty", _fmt(row.get("sample_size_uncertainty_score")))

    display = pd.DataFrame(
        [
            {
                "Signal": "Need/recommendation",
                "Value": f"need {_fmt(row.get('health_need_score'))}; care gap {_fmt(row.get('care_gap_score'))}; trust gap {_fmt(row.get('trust_gap_score'))}",
                "Interpretation": "High values mean the district need is strong and supply evidence is weak.",
            },
            {
                "Signal": "Needs-review rate",
                "Value": f"{_fmt_interval(row.get('needs_human_review_rate_ci_low'), row.get('needs_human_review_rate_ci_high'))}",
                "Interpretation": "Wilson interval for rows needing uncertainty review.",
            },
            {
                "Signal": "Critical supply-gap rate",
                "Value": f"{_fmt_interval(row.get('critical_supply_gap_rate_ci_low'), row.get('critical_supply_gap_rate_ci_high'))}",
                "Interpretation": "Wilson interval for missing/estimated critical operational evidence.",
            },
            {
                "Signal": "Trustworthy supply rate",
                "Value": f"{_fmt_interval(row.get('trustworthy_supply_rate_ci_low'), row.get('trustworthy_supply_rate_ci_high'))}",
                "Interpretation": "Wilson interval for observed rows that passed automated checks.",
            },
        ]
    )
    st.dataframe(display, hide_index=True, width="stretch", height=235)
    reason_chips(data.reason_labels(row.get("active_learning_reasons")))

    claim = str(row.get("sample_claim_evidence", "") or "").strip()
    source = data._first_url(row.get("sample_source_urls", ""))
    if claim:
        st.markdown(f"**Sample evidence:** {claim[:460]}…")
    if source:
        st.markdown(f"**Source:** [{source[:90]}]({source})")


def geo_candidate_detail(row: pd.Series) -> None:
    """Explain one generated geocoding candidate."""
    st.markdown('<div class="mdn-panel-h">Geo source-agreement explanation</div>',
                unsafe_allow_html=True)
    title = str(row.get("facility_name", "Unnamed facility") or "Unnamed facility")
    st.markdown(f"**{title}**")
    st.caption(str(row.get("raw_india_address", "") or row.get("geocoder_query", "")))

    m1, m2, m3 = st.columns(3)
    m1.metric("External priority", _fmt(row.get("external_validation_priority_score")))
    m2.metric("Geo review score", _fmt(row.get("geo_review_score"), 1))
    m3.metric("PIN distance km", _fmt(row.get("geo_distance_km_to_pincode_centroid"), 1))

    checks, reasons = data.geo_candidate_explanation(row)
    st.dataframe(checks, hide_index=True, width="stretch", height=255)
    if not reasons.empty:
        reason_chips(reasons["Reason code"].tolist())

    sources = data._json_list(row.get("external_evidence_sources_to_check"))
    if sources:
        st.markdown("**External evidence to check:** " + " · ".join(sources))
    query = str(row.get("geocoder_query", "") or "").strip()
    if query:
        st.code(query, language="text")


def legend(low_label: str, high_label: str, higher_is_worse: bool) -> None:
    left, right = (low_label, high_label)
    st.markdown('<div class="mdn-legend-bar"></div>', unsafe_allow_html=True)
    # ramp is green(low)->red(high) when higher_is_worse; flip labels otherwise
    a, b = (left, right) if higher_is_worse else (right, left)
    st.markdown(
        f'<div class="mdn-legend-row"><span>{a}</span><span>{b}</span></div>',
        unsafe_allow_html=True,
    )
