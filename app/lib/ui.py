"""Shared UI helpers: global CSS, header, and small components."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config, data, charts, decisions

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
  --mdn-radius: 16px;        /* alias -> --radius-card (modern rounded surfaces) */
  --mdn-radius-lg: 16px;
  --mdn-font: "Inter", "SF Pro Display", ui-sans-serif, -apple-system,
              BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue",
              system-ui, sans-serif;
  /* tabular numerals -> the precise HUD / command-center readout feel */
  --mdn-tnum: "tnum" 1, "lnum" 1;

  /* ===== DESIGN SYSTEM TOKENS (single source of truth — see DESIGN_SYSTEM.md) =====
     Semantic color tokens. worse = red per the app's higher_is_worse convention.
     These are the canonical names tabs reference; the --mdn-* aliases above are
     kept for back-compat and now point at the same hues. */
  --good: #2eccc1;   /* teal  — deploy / better / passes checks            */
  --mid:  #ffbe48;   /* amber — verify / caution / mid                     */
  --bad:  #ff5252;   /* red   — danger / worse / fails checks (worse=red)  */
  --info: #66d9ff;   /* sky   — neutral evidence / reference accent        */

  /* Surface + text tokens (canonical names; alias the dark theme values). */
  --bg:     var(--mdn-bg);
  --panel:  var(--mdn-panel);
  --text:   var(--mdn-text);
  --muted:  var(--mdn-muted);
  --line:   var(--mdn-line);

  /* ===== MODERN-DARK polish tokens (vfmatch-style: frosted, rounded, airy) =====
     Dark identity retained. Rounding scale, soft shadow, and a reusable
     frosted-glass surface that cards/panels/expanders/legend all share. */
  --radius-card: 16px;   /* cards, panels, expanders, floating cards   */
  --radius-sm:   10px;   /* inputs, inner chips, small controls        */
  --radius-pill: 999px;  /* buttons, segmented control, chips           */

  /* Soft layered depth (calm, not harsh). */
  --shadow-card:  0 8px 30px rgba(0, 0, 0, .35);
  --shadow-float: 0 12px 40px rgba(0, 0, 0, .48);

  /* Frosted-glass surface recipe (translucent panel + blur amount). */
  --glass-bg:      rgba(20, 28, 44, .66);   /* legible translucent panel  */
  --glass-bg-soft: rgba(16, 24, 38, .54);   /* lighter inner surfaces     */
  --glass-blur:    blur(14px) saturate(125%);
  --glass-border:  var(--mdn-glass-border); /* hairline, see token above  */

  /* Airier rhythm: generous default padding + section gaps. */
  --pad-card:  1.2rem;   /* comfortable card / panel padding           */
  --gap-section: 1.1rem; /* vertical breathing room between sections    */

  /* Typographic scale (one ramp the whole app uses). */
  --fs-display: 1.9rem;   /* hero / greeting                        */
  --fs-h1:      1.36rem;  /* KPI value, primary stat                */
  --fs-h2:      1.06rem;  /* tab-intro title, banner title          */
  --fs-body:    .88rem;   /* default body copy                      */
  --fs-caption: .72rem;   /* captions, kickers, panel headers       */

  /* Spacing scale (4px base). */
  --sp-1: .25rem;
  --sp-2: .5rem;
  --sp-3: .75rem;
  --sp-4: 1rem;
  --sp-5: 1.5rem;
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
  padding: 1.1rem 1.4rem 1.6rem 1.4rem;
  max-width: 100%;
}
[data-testid="stVerticalBlock"] {gap: var(--gap-section);}
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
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
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
  padding: .9rem 1rem;
  color: var(--mdn-muted);
  background: var(--glass-bg-soft);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  font-size: .82rem;
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
}
.mdn-earth-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .8rem;
  padding: 1.1rem 1.25rem;
  margin: .3rem 0 .5rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
}
.mdn-earth-strip strong {
  display: block;
  color: var(--mdn-text);
  font-size: 1.46rem;
  font-weight: 780;
  letter-spacing: -.015em;
  line-height: 1.12;
}
.mdn-earth-strip span {
  display: block;
  color: var(--mdn-muted);
  font-size: .86rem;
  margin-top: .28rem;
  line-height: 1.3;
}
.mdn-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: var(--mdn-teal);
  box-shadow: 0 0 14px rgba(46, 204, 193, .7);
  flex: 0 0 auto;
}
/* ===== Reusable frosted-glass surface (the hub recipe) =====
   Any markup can wrap content in .mdn-glass for the standard frosted card.
   .mdn-float is the same surface tuned to FLOAT over the map (heavier shadow,
   slightly more opaque so labels stay legible against bright basemaps). */
.mdn-glass {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: var(--pad-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
  color: var(--mdn-text);
}
.mdn-float {
  background: rgba(13, 20, 34, .82);   /* more opaque -> legible over a map */
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-float);
  padding: .9rem 1rem;
  -webkit-backdrop-filter: blur(16px) saturate(130%);
  backdrop-filter: blur(16px) saturate(130%);
  color: var(--mdn-text);
}
/* ===== .mdn-tip — Tableau-style hover tooltip (E6, pure CSS) =====
   Reusable hover-disclosure for custom markup: put `class="mdn-tip"` on any
   inline element and a `data-tip="…"` attribute with the tooltip text. On
   hover/focus a frosted floating tooltip (--glass tokens + --shadow-float)
   fades in above the element. Keeps wordy captions off the first glance.
   Usage:
     <span class="mdn-tip" data-tip="Estimated from regional medians.">capacity</span>
   The element should be focusable (the cell/row usually is); add tabindex="0"
   on a bare <span> if you want keyboard reveal. Lightweight, no JS. */
.mdn-tip {
  position: relative;
  cursor: help;
  border-bottom: 1px dashed var(--mdn-line-strong);
}
.mdn-tip::after {
  content: attr(data-tip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 8px);
  transform: translateX(-50%) translateY(4px);
  width: max-content;
  max-width: 260px;
  white-space: normal;
  text-align: left;
  font-family: var(--mdn-font);
  font-size: var(--fs-caption);
  font-weight: 500;
  line-height: 1.35;
  color: var(--mdn-text);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-sm);
  box-shadow: var(--shadow-float);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
  padding: .5rem .65rem;
  opacity: 0;
  pointer-events: none;
  z-index: 60;
  transition: opacity .14s ease, transform .14s ease;
}
.mdn-tip:hover::after,
.mdn-tip:focus-visible::after {
  opacity: 1;
  transform: translateX(-50%) translateY(0);
}
/* ===== Facility decision card (E5) — clean labeled key/value detail ===== */
.mdn-fac-head { margin-top: .5rem; padding: .9rem 1rem; }
.mdn-fac-title {
  display: flex;
  align-items: center;
  gap: .55rem;
  flex-wrap: wrap;
}
.mdn-fac-name {
  font-size: var(--fs-h2);
  font-weight: 740;
  letter-spacing: -.01em;
  color: var(--mdn-text);
}
.mdn-fac-badge {
  font-size: var(--fs-caption);
  font-weight: 700;
  padding: .2rem .6rem;
  border-radius: var(--radius-pill);
  white-space: nowrap;
}
.mdn-fac-sub {
  font-size: var(--fs-body);
  color: var(--mdn-muted);
  margin-top: .3rem;
}
.mdn-fact-list {
  margin: .55rem 0 .2rem;
  display: flex;
  flex-direction: column;
  gap: .1rem;
}
.mdn-fact {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  padding: .42rem .15rem;
  border-bottom: 1px solid var(--mdn-line);
}
.mdn-fact:last-child { border-bottom: none; }
.mdn-fact-k {
  font-size: var(--fs-caption);
  text-transform: uppercase;
  letter-spacing: .04em;
  color: var(--mdn-muted);
  flex: 0 0 auto;
}
.mdn-fact-v {
  font-size: var(--fs-body);
  font-weight: 620;
  color: var(--mdn-text);
  text-align: right;
  font-feature-settings: var(--mdn-tnum);
}
/* The cited claim, treated as first-class evidence (quote style). */
.mdn-claim {
  margin: .7rem 0 .35rem;
  padding: .65rem .85rem;
  border-left: 3px solid var(--info);
  border-radius: var(--radius-sm);
  background: var(--glass-bg-soft);
  color: var(--mdn-text);
  font-size: var(--fs-body);
  font-style: italic;
  line-height: 1.4;
}
.mdn-claim-tag {
  display: block;
  margin-top: .4rem;
  font-style: normal;
  font-size: var(--fs-caption);
  font-weight: 650;
  letter-spacing: .03em;
  text-transform: uppercase;
  color: var(--mid);
}

.mdn-card {
  position: relative;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: var(--pad-card);
  min-height: 112px;
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
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
  margin-top: .35rem;
  color: var(--mdn-text);
  font-size: var(--fs-h1);
  font-weight: 820;
  letter-spacing: -.015em;
  line-height: 1.06;
  font-variant-numeric: tabular-nums;
  font-feature-settings: var(--mdn-tnum);
}
.mdn-card-caption {
  margin-top: .4rem;
  color: var(--mdn-muted);
  font-size: .78rem;
  line-height: 1.3;
}
.mdn-decision-banner {
  display: flex;
  align-items: flex-start;
  gap: .8rem;
  padding: var(--pad-card);
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
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
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: .8rem .85rem;
  background: var(--glass-bg-soft);
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
  border-radius: var(--radius-sm);
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
div[data-baseweb="popover"] {background: rgba(8, 16, 28, .98); border-radius: var(--radius-sm);}
[data-testid="stSlider"] [role="slider"] {background: var(--mdn-teal);}
[data-testid="stCheckbox"] label, [data-testid="stToggle"] label,
[data-testid="stSelectbox"] label, [data-testid="stSlider"] label {
  color: #cfdcec !important;
  font-size: .74rem;
  font-weight: 600;
  letter-spacing: .01em;
}
/* ===== Pill buttons (global, modern + usable) =====
   Buttons, form-submit, download, and popover triggers all read as pills:
   rounded-full, translucent/elevated, hairline border, hover lift. Tap
   targets stay >=36px; focus ring handled by the global :focus-visible rule. */
div[data-testid="stButton"] > button,
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stDownloadButton"] > button,
div[data-testid="stPopover"] > button {
  background: var(--glass-bg-soft);
  border: 1px solid var(--mdn-line-strong);
  border-radius: var(--radius-pill);
  color: var(--mdn-text);
  font-weight: 600;
  min-height: 36px;
  padding: .5rem 1.1rem;
  box-shadow: var(--mdn-elev-1);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
div[data-testid="stButton"] > button:hover,
div[data-testid="stFormSubmitButton"] > button:hover,
div[data-testid="stDownloadButton"] > button:hover,
div[data-testid="stPopover"] > button:hover {
  border-color: rgba(46, 204, 193, .6);
  box-shadow: var(--mdn-elev-2);
  transform: translateY(-1px);
  color: #fff;
}
div[data-testid="stButton"] > button:active,
div[data-testid="stFormSubmitButton"] > button:active,
div[data-testid="stDownloadButton"] > button:active {
  transform: translateY(0);
  box-shadow: var(--mdn-elev-1);
}
/* Primary buttons read as a filled teal pill (clear, distinct call-to-action). */
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button[kind="primary"] {
  background: linear-gradient(180deg, rgba(46, 204, 193, .26), rgba(46, 204, 193, .12));
  border-color: rgba(46, 204, 193, .55);
  color: #eafffb;
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
  font-size: .8rem !important;
  padding: .34rem .72rem !important;
  letter-spacing: .005em;
  white-space: nowrap;
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
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: 1rem 1.05rem;
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
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
  font-size: var(--fs-caption);
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
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  color: var(--mdn-text);
  padding: .9rem 1rem;
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
}
[data-testid="stDataFrameResizable"], [data-testid="stDataFrame"] {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  overflow: hidden;
  box-shadow: var(--shadow-card);
}
[data-testid="stSpinner"] {color: var(--mdn-teal);}

/* ---- Expander: a clean rounded "show more" affordance (frosted card) ---- */
[data-testid="stExpander"] {
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  background: var(--glass-bg);
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
  overflow: hidden;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] details > summary {
  border-radius: var(--radius-card);
  padding: .7rem 1.05rem;
  font-weight: 640;
  color: var(--mdn-text);
}
[data-testid="stExpander"] summary:hover {
  background: rgba(102, 217, 255, .06);
  color: #fff;
}
[data-testid="stExpander"] [data-testid="stExpanderDetails"] {
  padding: 0 1.05rem 1rem;
}
[data-testid="stProgress"] > div > div > div {background: var(--mdn-teal);}

.mdn-legend {
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: .85rem 1rem;
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
}
.mdn-legend-bar {
  height: 8px;
  border-radius: var(--radius-pill);
  background: linear-gradient(90deg, var(--good) 0%, var(--mid) 50%, var(--bad) 100%);
  border: 1px solid rgba(255, 255, 255, .12);
  box-shadow: 0 0 16px rgba(46, 204, 193, .18), 0 4px 12px rgba(0, 0, 0, .3);
}
.mdn-legend-row {
  display: flex;
  justify-content: space-between;
  font-size: .72rem;
  color: var(--mdn-muted);
  margin-top: 6px;
}

/* ---- Minimal nav caption (3-tab world) ---- */
.mdn-nav-caption {
  margin: .1rem 0 .15rem;
  font-size: var(--fs-caption);
  letter-spacing: .12em;
  text-transform: uppercase;
  color: var(--mdn-dim);
  font-weight: 700;
}

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
  border: 1px solid var(--glass-border);
  border-left: 3px solid var(--mdn-sky);
  border-radius: var(--radius-card);
  padding: .75rem .95rem;
  margin: .35rem 0;
  background: var(--glass-bg-soft);
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
    # E4: one concise line. The redundant "evidence-weighted / uncertainty
    # visible" chip (restated again in the old orbit-note + nav-caption) was
    # folded away — the single tagline carries the idea once.
    st.markdown(
        f"""
        <div class="mdn-topbar">
          <div class="mdn-logo">C</div>
          <div>
            <div class="mdn-title">{config.APP_TITLE}</div>
            <div class="mdn-sub">{config.APP_TAGLINE}</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---- Standardized tab primitives (every tab consumes these) -----------------
# See DESIGN_SYSTEM.md. These four enforce the consistency the next-wave tab
# agents must inherit: one title treatment, a capped KPI row, one expander
# affordance, and one section-header style.

def tab_intro(title: str, subtitle: str = "") -> None:
    """Standard tab header. Every tab MUST start with this.

    One consistent title treatment + an optional one-line subtitle.
    """
    sub = f"<span>{html.escape(str(subtitle))}</span>" if subtitle else ""
    st.markdown(
        f"""
        <div class="mdn-earth-strip">
          <div>
            <strong>{html.escape(str(title))}</strong>
            {sub}
          </div>
          <div class="mdn-status-dot"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: list[tuple[str, str, str]], tone_each: list[str] | None = None) -> None:
    """Minimal KPI row reusing ``stat_card`` (capped at 3 — minimalist first glance).

    ``items`` is a list of (label, value, caption). ``tone_each`` optionally
    supplies a tone per card ("deploy"/"verify"/"danger"/"info"/"neutral").
    """
    items = list(items)[:3]
    if not items:
        return
    tones = list(tone_each or [])
    cols = st.columns(len(items))
    for i, (col, item) in enumerate(zip(cols, items)):
        label, value, caption = (list(item) + ["", "", ""])[:3]
        tone = tones[i] if i < len(tones) else "neutral"
        with col:
            stat_card(label, value, caption, tone)


def detail(label: str):
    """The ONE progressive-disclosure affordance every tab uses for "more detail".

    Thin wrapper around a collapsed ``st.expander``; returns the expander context
    so callers can ``with ui.detail("..."):``. Keeps depth uniform across tabs.
    """
    return st.expander(label, expanded=False)


def panel_header(text: str) -> None:
    """Consistent in-tab section header (the ``mdn-panel-h`` treatment)."""
    st.markdown(
        f'<div class="mdn-panel-h">{html.escape(str(text))}</div>',
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


def _source_domain(url: str) -> str:
    """Parse a clean, human-readable domain from a source URL.

    Never returns a raw 80-char URL — strips scheme, ``www.``, path/query, and
    falls back to the trimmed host. Returns "" if no usable host is present.
    """
    raw = (url or "").strip()
    if not raw:
        return ""
    host = raw.split("://", 1)[-1]          # drop scheme
    host = host.split("/", 1)[0]            # drop path
    host = host.split("?", 1)[0].split("#", 1)[0]
    host = host.split("@", 1)[-1]           # drop credentials
    host = host.split(":", 1)[0]            # drop port
    if host.lower().startswith("www."):
        host = host[4:]
    return host.strip().lower()


def _stat_line(label: str, value: str, tip: str = "") -> str:
    """One labeled key-value line (one fact per line) for the facility card."""
    tip_attr = (
        f' data-tip="{html.escape(tip, quote=True)}"' if tip else ""
    )
    tip_cls = " mdn-tip" if tip else ""
    return (
        '<div class="mdn-fact">'
        f'<span class="mdn-fact-k{tip_cls}"{tip_attr}>{html.escape(label)}</span>'
        f'<span class="mdn-fact-v">{html.escape(value)}</span>'
        '</div>'
    )


def facility_card(f: dict) -> None:
    """Clean, labeled decision card for a clicked facility (E5).

    Status badge + one-fact-per-line key/value rows + a first-class cited claim
    (quote style) with a clean ``Source: <domain>`` link. The raw signal table
    is demoted behind a "Why this badge?" expander.
    """
    status = f.get("status", "Unknown") or "Unknown"
    fg, bg = _BADGE.get(status, _BADGE["Unknown"])
    name = str(f.get("facility_name") or "Unnamed facility")
    loc = " · ".join(
        x for x in [f.get("city"), f.get("district"), f.get("state")]
        if x and str(x) != "—"
    )
    ftype = str(f.get("facility_type") or "—")
    url = (f.get("source_url") or "").strip()
    domain = _source_domain(url)
    evidence = (f.get("evidence") or "").strip()

    # ---- Header: name + status badge + a quiet type/location line ----
    sub = " · ".join(x for x in [ftype, loc] if x and x != "—") or "—"
    st.markdown(
        f"""
        <div class="mdn-glass mdn-fac-head">
          <div class="mdn-fac-title">
            <span class="mdn-fac-name">{html.escape(name)}</span>
            <span class="mdn-fac-badge" style="background:{bg};color:{fg}">{html.escape(str(status))}</span>
          </div>
          <div class="mdn-fac-sub">{html.escape(sub)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ---- Clean, labeled facts: ONE human-readable fact per line ----
    cap_v = _fmt(f.get("capacity_display_value"), 0)
    cap_iv = _fmt_interval(f.get("capacity_estimate_interval_low"),
                           f.get("capacity_estimate_interval_high"), 0)
    cap_conf = str(f.get("capacity_confidence") or "unknown")
    doc_v = _fmt(f.get("doctor_count_display_value"), 0)
    doc_iv = _fmt_interval(f.get("doctor_count_estimate_interval_low"),
                           f.get("doctor_count_estimate_interval_high"), 0)
    doc_conf = str(f.get("doctor_count_confidence") or "unknown")
    geo_q = str(f.get("geo_quality") or "unknown")
    geo_km = _fmt(f.get("geo_distance_km_to_pincode_centroid"), 1)
    trust = ("Passes supply checks" if status == "Passed checks"
             else "Flagged — verify before relying")

    facts: list[str] = []
    if cap_v != "—":
        iv = f" ({cap_iv})" if cap_iv != "unknown" else ""
        facts.append(_stat_line(
            "Estimated capacity", f"{cap_v} beds{iv}, {cap_conf} confidence",
            tip="Estimated when the source omits a bed count; the interval is the "
                "plausible range, not a precise figure.",
        ))
    if doc_v != "—":
        iv = f" ({doc_iv})" if doc_iv != "unknown" else ""
        facts.append(_stat_line(
            "Doctors", f"{doc_v}{iv}, {doc_conf} confidence",
            tip="Estimated doctor count with its plausible range.",
        ))
    facts.append(_stat_line(
        "Trust", trust,
        tip="Whether the facility passes the automated supply/evidence checks.",
    ))
    geo_v = geo_q if geo_km == "—" else f"{geo_q} ({geo_km} km from PIN centroid)"
    facts.append(_stat_line(
        "Geo quality", geo_v,
        tip="How well external geocoding agrees with the PIN / district / state.",
    ))
    st.markdown(
        '<div class="mdn-fact-list">' + "".join(facts) + '</div>',
        unsafe_allow_html=True,
    )

    # ---- Cited claim (first-class, quote style) + clean source link ----
    if evidence:
        st.markdown(
            f'<blockquote class="mdn-claim">{html.escape(evidence)}'
            '<span class="mdn-claim-tag">claimed · unverified</span></blockquote>',
            unsafe_allow_html=True,
        )
    if domain:
        st.markdown(f"Source: [{domain}]({url})")
    else:
        st.caption("No source URL on record for this facility.")

    if status != "Passed checks":
        st.warning("This facility is flagged — verify the claim against the source "
                   "before relying on it.")

    # ---- Raw signals demoted behind an expander (off the first glance) ----
    with detail("Why this badge?"):
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
                "Value": f"{geo_q} · {geo_km} km from PIN centroid",
                "Interpretation": "External geocoding should reduce uncertainty only when it agrees with PIN/district/state.",
            },
            {
                "Signal": "Estimated capacity",
                "Value": f"{cap_v} ({cap_iv})",
                "Interpretation": f"{cap_conf} confidence; estimated={bool(f.get('capacity_is_estimated', False))}.",
            },
            {
                "Signal": "Estimated doctors",
                "Value": f"{doc_v} ({doc_iv})",
                "Interpretation": f"{doc_conf} confidence; estimated={bool(f.get('doctor_count_is_estimated', False))}.",
            },
        ]
        st.dataframe(pd.DataFrame(explain_rows), hide_index=True, width="stretch", height=230)


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


def region_detail(row: pd.Series, specialty: str, districts: pd.DataFrame | None = None) -> None:
    """District drill-down for planners/doctors: clean headline + the top medical-condition
    gaps, with the causal score breakdown and the heavy evidence tucked into expanders."""
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

    # ---- act → save (persisted): shortlist + planner note ----
    geo_id = f"{state}|{district}"
    shortlisted = decisions.is_shortlisted(geo_id)
    sc1, sc2 = st.columns([1, 1])
    if sc1.button("★ In plan" if shortlisted else "☆ Add to plan",
                  key=f"sl_{geo_id}", use_container_width=True):
        decisions.toggle_shortlist(geo_id, label=name)
        st.rerun()
    with sc2.popover("📝 Add note", use_container_width=True):
        txt = st.text_area("Planner note", key=f"nt_{geo_id}",
                           label_visibility="collapsed", placeholder="Add a note for this district…")
        if st.button("Save note", key=f"sn_{geo_id}") and txt.strip():
            decisions.save_note(geo_id, txt.strip())
            st.toast("Note saved")
    _ps = decisions.persistence_status()
    st.caption(f"Saved actions persist to **{_ps.get('backend', 'session')}**"
               + ("" if _ps.get("durable") else " · session-only until gold tables are provisioned"))

    if bool(row.get("zero_facility_desert", False)):
        st.warning(
            "⚠ **Zero mapped facilities.** Invisible to facility-count views — score is driven by NFHS "
            "health need and the absence of trustworthy supply. Next step: **deploy new access** "
            "(mobile clinic / CHW outreach), not optimize existing supply."
        )

    # ---- HERO: top medical-condition gaps vs national (the planner's "why here") ----
    st.markdown('<div class="mdn-panel-h">Top medical-condition gaps vs national</div>',
                unsafe_allow_html=True)
    conds = data.district_top_conditions(row, districts) if districts is not None else pd.DataFrame()
    if not conds.empty:
        st.altair_chart(charts.condition_gaps(conds), use_container_width=True)
        worst = conds.iloc[0]
        st.caption(f"Worst gap: **{worst['Condition']}** "
                   f"({worst['District %']}% vs {worst['National %']}% national). "
                   "Bar = district · gray tick = national median · deeper red = worse. "
                   "Burden (anaemia/BP/sugar) + access (births/screening) gaps, ranked by severity.")
    else:
        st.caption("No NFHS condition indicators available for this district.")

    # ---- causal: how the care-gap score is built ----
    breakdown, total, _ = data.care_gap_breakdown(row)
    st.markdown('<div class="mdn-panel-h">How this care-gap score is built</div>',
                unsafe_allow_html=True)
    st.altair_chart(charts.care_gap_contributions(breakdown), use_container_width=True)
    st.caption(f"Care-gap score = Σ contributions = **{total:.2f}** · 0.55 need · 0.25 supply "
               "scarcity · 0.20 low trust.")

    # ---- cite the underlying facility text behind the score (core requirement #4) ----
    _fac = str(row.get("sample_facility_names", "") or "").strip()
    _claim = str(row.get("sample_claim_evidence", "") or "").strip()
    _url = data._first_url(row.get("sample_source_urls", ""))
    if _fac or _claim:
        cite = "**Grounded in facility text:** "
        if _fac:
            cite += f"_{_fac.split(';')[0][:55]}_"
        if _claim:
            cite += f" — “{_claim[:130]}…”"
        if _url:
            cite += f" · [source]({_url})"
        st.caption(cite)
    elif bool(row.get("zero_facility_desert", False)):
        st.caption("**Grounded in:** NFHS-5 district health indicators (no facility records "
                   "mapped here — that absence *is* the signal).")

    # ---- progressive disclosure: heavy detail only on expand ----
    with st.expander("Why this recommendation — full signal breakdown"):
        explanation, reasons = data.district_explanation(row, specialty)
        st.dataframe(explanation, hide_index=True, width="stretch", height=285)
        if not reasons.empty:
            reason_chips(reasons["Reason"].tolist())

    with st.expander("Evidence & sources"):
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
    # ramp is green(low)->red(high) when higher_is_worse; flip labels otherwise
    a, b = (left, right) if higher_is_worse else (right, left)
    st.markdown(
        f"""
        <div class="mdn-legend">
          <div class="mdn-legend-bar"></div>
          <div class="mdn-legend-row"><span>{html.escape(str(a))}</span><span>{html.escape(str(b))}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def floating_card(inner_html: str) -> None:
    """Render a frosted card tuned to FLOAT over the map (legend / stat overlay).

    Wraps caller-supplied ``inner_html`` in the ``.mdn-float`` surface (more
    opaque than ``.mdn-glass`` so text stays legible against a bright basemap).
    The map agent may also apply the ``.mdn-float`` CSS class directly to its
    own positioned container instead of calling this — both are supported and
    documented in DESIGN_SYSTEM.md. ``inner_html`` is trusted markup (the caller
    is responsible for escaping any user/data text it interpolates).
    """
    st.markdown(f'<div class="mdn-float">{inner_html}</div>', unsafe_allow_html=True)
