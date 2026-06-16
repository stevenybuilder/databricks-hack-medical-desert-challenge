"""Shared UI helpers: global CSS, header, and small components."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from . import config, data, charts, decisions, photo_enrichment

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

  /* ===== DESIGN SYSTEM TOKENS (single source of truth — see docs/DESIGN_SYSTEM.md) =====
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
.mdn-tip.mdn-trust-tip {
  border-bottom: 0;
  cursor: help;
}
.mdn-tip.mdn-trust-tip::after {
  left: 0;
  bottom: calc(100% + 10px);
  transform: translateY(4px);
  width: min(440px, 78vw);
  max-width: 440px;
  font-size: .78rem;
  line-height: 1.42;
  padding: .75rem .85rem;
  border-radius: 14px;
  background: rgba(8, 15, 26, .96);
  border-color: rgba(102, 217, 255, .26);
}
.mdn-tip.mdn-trust-tip:hover::after,
.mdn-tip.mdn-trust-tip:focus-visible::after {
  transform: translateY(0);
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
.mdn-trust-help {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: .35rem;
  margin-top: .65rem;
  padding: .28rem .58rem;
  border-radius: var(--radius-pill);
  border: 1px solid rgba(102, 217, 255, .32);
  background: rgba(13, 49, 66, .7);
  color: #bdefff;
  font-size: .7rem;
  font-weight: 760;
  letter-spacing: .02em;
  cursor: help;
}
.mdn-trust-help-card {
  position: absolute;
  left: 0;
  top: calc(100% + 8px);
  width: min(340px, 78vw);
  z-index: 70;
  opacity: 0;
  pointer-events: none;
  transform: translateY(-4px);
  transition: opacity .14s ease, transform .14s ease;
  padding: .72rem .82rem;
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  background: rgba(13, 20, 34, .94);
  box-shadow: var(--shadow-float);
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
  color: var(--mdn-text);
  font-size: .76rem;
  font-weight: 520;
  line-height: 1.38;
  letter-spacing: 0;
}
.mdn-trust-help:hover .mdn-trust-help-card,
.mdn-trust-help:focus-visible .mdn-trust-help-card {
  opacity: 1;
  transform: translateY(0);
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
.mdn-guide {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: .6rem;
  margin: .25rem 0 .45rem;
}
.mdn-guide-step {
  background: var(--glass-bg-soft);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: .78rem .85rem;
  min-height: 78px;
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.mdn-guide-step b {
  display: block;
  color: var(--mdn-text);
  font-size: .8rem;
  line-height: 1.15;
}
.mdn-guide-step span {
  display: block;
  color: var(--mdn-muted);
  font-size: .72rem;
  line-height: 1.28;
  margin-top: .25rem;
}
.mdn-provider-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .65rem;
  margin-top: .35rem;
}
.mdn-provider-card {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: .7rem;
  background: var(--glass-bg);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  box-shadow: var(--shadow-card);
  padding: .72rem;
  -webkit-backdrop-filter: var(--glass-blur);
  backdrop-filter: var(--glass-blur);
}
.mdn-provider-art {
  min-height: 92px;
  border-radius: 14px;
  border: 1px solid rgba(102, 217, 255, .24);
  background:
    linear-gradient(135deg, rgba(46, 204, 193, .28), rgba(102, 217, 255, .08)),
    radial-gradient(90px 70px at 28% 22%, rgba(255,255,255,.16), transparent 68%);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: .18rem;
  color: #dffcff;
  font-size: 1.35rem;
  font-weight: 820;
  letter-spacing: -.03em;
  overflow: hidden;
  text-align: center;
}
.mdn-provider-art img {
  width: 100%;
  height: 100%;
  min-height: 92px;
  object-fit: cover;
  display: block;
}
.mdn-provider-art small {
  display: block;
  color: rgba(223, 252, 255, .76);
  font-size: .58rem;
  font-weight: 720;
  letter-spacing: .05em;
  text-transform: uppercase;
}
.mdn-provider-name {
  color: var(--mdn-text);
  font-size: .88rem;
  font-weight: 740;
  line-height: 1.15;
  margin-bottom: .24rem;
}
.mdn-provider-desc {
  color: var(--mdn-muted);
  font-size: .72rem;
  line-height: 1.35;
  margin-top: .35rem;
}
.mdn-provider-claim {
  color: var(--mdn-text);
  font-size: .72rem;
  line-height: 1.35;
  margin-top: .5rem;
  padding-top: .48rem;
  border-top: 1px solid var(--mdn-line);
}
.mdn-region-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: .75rem;
  flex-wrap: wrap;
  margin: .25rem 0 .7rem;
}
.mdn-region-title {
  display: flex;
  align-items: center;
  gap: .55rem;
  flex-wrap: wrap;
}
.mdn-region-name {
  font-size: 1.18rem;
  font-weight: 780;
  color: var(--mdn-text);
  letter-spacing: -.01em;
}
.mdn-region-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .75rem;
  margin: .75rem 0 .85rem;
}
.mdn-region-card {
  background: var(--glass-bg-soft);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: .78rem .88rem;
  min-height: 98px;
  box-shadow: var(--shadow-card);
  -webkit-backdrop-filter: blur(12px) saturate(120%);
  backdrop-filter: blur(12px) saturate(120%);
}
.mdn-region-kicker {
  color: var(--mdn-muted);
  font-size: .72rem;
  font-weight: 760;
  letter-spacing: .04em;
  text-transform: uppercase;
}
.mdn-region-value {
  color: var(--mdn-text);
  font-size: 1.22rem;
  font-weight: 820;
  margin-top: .42rem;
  line-height: 1.08;
}
.mdn-region-caption {
  color: var(--mdn-muted);
  font-size: .76rem;
  line-height: 1.32;
  margin-top: .42rem;
}
.mdn-region-card--good {border-color: rgba(46, 204, 193, .34);}
.mdn-region-card--warn {border-color: rgba(255, 190, 72, .34);}
.mdn-region-card--bad {border-color: rgba(255, 82, 82, .34);}
.mdn-region-card--info {border-color: rgba(102, 217, 255, .28);}
.mdn-condition-summary {
  background: rgba(13, 22, 36, .62);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: .88rem 1rem;
  margin: .35rem 0 .75rem;
}
.mdn-condition-summary b {
  color: var(--mdn-text);
  font-size: .9rem;
}
.mdn-condition-summary span {
  display: block;
  color: var(--mdn-muted);
  font-size: .78rem;
  line-height: 1.36;
  margin-top: .28rem;
}
.mdn-empty-provider {
  grid-template-columns: 80px minmax(0, 1fr);
}
.mdn-condition-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: .65rem;
  margin: .35rem 0 .55rem;
}
.mdn-condition-card {
  background: var(--glass-bg-soft);
  border: 1px solid var(--glass-border);
  border-radius: var(--radius-card);
  padding: .82rem .9rem;
}
.mdn-condition-card b {
  display: block;
  color: var(--mdn-text);
  font-size: .86rem;
  line-height: 1.16;
}
.mdn-condition-card span {
  display: block;
  color: var(--mdn-muted);
  font-size: .73rem;
  line-height: 1.3;
  margin-top: .28rem;
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

@media (max-width: 900px) {
  .mdn-guide, .mdn-condition-grid, .mdn-provider-grid, .mdn-region-grid {
    grid-template-columns: 1fr;
  }
  .mdn-provider-card {
    grid-template-columns: 76px minmax(0, 1fr);
  }
}

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
# See docs/DESIGN_SYSTEM.md. These four enforce the consistency the next-wave tab
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


def _clean_text(value) -> str:
    """Display-safe scalar text: suppress pandas/numpy nan and blank placeholders."""
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    return "" if not text or text.lower() in {"nan", "none", "null", "na", "<na>", "nat"} else text


def _first_clean(*values) -> str:
    for value in values:
        text = _clean_text(value)
        if text:
            return text
    return ""


_SERVICE_SIGNALS = [
    ("Maternity / OB-GYN", "has_maternity_care_signal", "Maternity"),
    ("Emergency / Surgery", "has_emergency_care_signal", "Emergency"),
    ("Diagnostics / Imaging", "has_diagnostic_signal", "Diagnostics"),
    ("Chronic disease (NCD)", "has_ncd_care_signal", "NCD"),
]

_PHOTO_URL_HINTS = (
    "/photo",
    "/photos",
    "view-photo",
    "gallery",
    "/media",
    "/image",
    "/images",
    "album",
)


def _truthy(value) -> bool:
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _region_card(label: str, value: str, caption: str, tone: str = "info",
                 value_html: str | None = None) -> str:
    tone_class = {
        "good": "mdn-region-card--good",
        "warn": "mdn-region-card--warn",
        "bad": "mdn-region-card--bad",
        "info": "mdn-region-card--info",
    }.get(tone, "mdn-region-card--info")
    rendered_value = value_html if value_html is not None else html.escape(str(value))
    return (
        f'<div class="mdn-region-card {tone_class}">'
        f'<div class="mdn-region-kicker">{html.escape(str(label))}</div>'
        f'<div class="mdn-region-value">{rendered_value}</div>'
        f'<div class="mdn-region-caption">{html.escape(str(caption))}</div>'
        '</div>'
    )


def _provider_trust_tier(score: float) -> tuple[str, str, str]:
    if pd.isna(score):
        return "Not scored", "warn", "No mapped provider claims"
    if score >= 0.80:
        return "High trust", "good", "Strong source and claim evidence"
    if score >= 0.55:
        return "Medium trust", "warn", "Some evidence; call to confirm"
    return "Low trust", "bad", "Weak or conflicting evidence"


def _trust_summary(row: pd.Series) -> dict[str, str | float | int]:
    obs = _num(row.get("observed_facility_rows"))
    passed = _num(row.get("trustworthy_supply_rows"))
    rate = _num(row.get("trustworthy_supply_rate"))
    calibrated = _num(row.get("provider_trust_score"))
    posterior_mean = _num(row.get("provider_validity_posterior_mean"))
    smoothed_pass = _num(row.get("provider_pass_rate_smoothed"))
    prior_rate = _num(row.get("provider_trust_prior_rate"))
    prior_strength = _num(row.get("provider_trust_prior_strength"))
    ci_low = _num(row.get("trustworthy_supply_rate_ci_low"))
    ci_high = _num(row.get("trustworthy_supply_rate_ci_high"))
    obs_n = 0 if pd.isna(obs) else int(obs)
    passed_n = 0 if pd.isna(passed) else int(passed)

    if obs_n <= 0:
        label = "Not scored"
        caption = "No mapped provider claims"
        tone = "warn"
        tooltip = (
            "Provider trust score: not scored. This district has zero mapped "
            "provider claims, so there is no local denominator. Use health need, "
            "gap confidence, and calls to likely providers before staffing."
        )
        return {
            "label": label,
            "caption": caption,
            "tone": tone,
            "score": "not_scored",
            "tooltip": tooltip,
            "observed": obs_n,
            "passed": passed_n,
        }
    if pd.isna(rate):
        rate = passed_n / obs_n

    score = max(0.0, min(1.0, float(calibrated if not pd.isna(calibrated) else rate)))
    label = _clean_text(row.get("provider_trust_label"))
    caption = _clean_text(row.get("provider_trust_caption"))
    if label:
        tone = "good" if score >= 0.80 else ("warn" if score >= 0.55 else "bad")
    else:
        label, tone, caption = _provider_trust_tier(score)

    interval = "unknown"
    if not pd.isna(ci_low) and not pd.isna(ci_high):
        interval = f"{ci_low * 100:.0f}% to {ci_high * 100:.0f}%"
    posterior_text = "unknown" if pd.isna(posterior_mean) else f"{posterior_mean * 100:.0f}%"
    smoothed_text = "unknown" if pd.isna(smoothed_pass) else f"{smoothed_pass * 100:.0f}%"
    prior_text = "unknown" if pd.isna(prior_rate) else f"{prior_rate * 100:.0f}%"
    prior_n = "2" if pd.isna(prior_strength) else f"{prior_strength:.0f}"
    tooltip = (
        f"Provider trust score: {score * 100:.0f}% calibrated evidence trust. "
        f"Formula: 75% Bayesian row-validity evidence ({posterior_text}) plus "
        f"25% empirical-Bayes smoothed pass rate ({smoothed_text}; prior {prior_text}, "
        f"prior n={prior_n}). Hard automated checks: {passed_n}/{obs_n}; Wilson interval: "
        f"{interval}. This is evidence-based claim trust, not measured medical truth."
    )
    return {
        "label": label,
        "caption": caption,
        "tone": tone,
        "score": score,
        "tooltip": tooltip,
        "observed": obs_n,
        "passed": passed_n,
    }


def _sample_confidence(households) -> float:
    hh = _num(households)
    if pd.isna(hh):
        return 0.60
    if hh >= 500:
        return 1.00
    if hh >= 250:
        return 0.82
    if hh >= 100:
        return 0.68
    return 0.52


def _gap_confidence_summary(row: pd.Series) -> dict[str, str | float]:
    """Confidence the care gap is real, separate from local provider evidence."""
    need = _num(row.get("health_need_score"))
    need_v = 0.0 if pd.isna(need) else max(0.0, min(1.0, float(need)))
    sample = _sample_confidence(row.get("households_surveyed"))
    category = _clean_text(row.get("planning_category"))
    zero_desert = bool(row.get("zero_facility_desert", False))
    uncertainty = (_clean_text(row.get("district_uncertainty_level")) or "unknown").lower()
    uncertainty_note = f"uncertainty {uncertainty}" if uncertainty != "unknown" else "uncertainty unknown"
    if zero_desert and category == "real_desert_candidate":
        external = 0.78
        external_note = "zero mapped supply plus admin/NFHS evidence"
    else:
        external_raw = _num(row.get("avg_join_confidence"))
        external = 0.60 if pd.isna(external_raw) else max(0.0, min(1.0, float(external_raw)))
        external_note = "provider/admin join confidence"
    score = max(0.0, min(1.0, 0.55 * need_v + 0.30 * sample + 0.15 * external))
    if score >= 0.72:
        label = "High confidence"
        tone = "good"
        caption = f"Strong case; {uncertainty_note}"
    elif score >= 0.55:
        label = "Medium confidence"
        tone = "warn"
        caption = f"Good signal; {uncertainty_note}"
    else:
        label = "Low confidence"
        tone = "bad"
        caption = f"Needs more evidence; {uncertainty_note}"
    tooltip = (
        f"Gap confidence: {score:.2f}. Combines health need ({need_v:.2f}), "
        f"NFHS sample strength ({sample:.2f}), and {external_note} ({external:.2f}). "
        f"District uncertainty tier: {uncertainty.title()}. This is separate from "
        "provider trust."
    )
    return {
        "label": label,
        "caption": caption,
        "tone": tone,
        "score": score,
        "tooltip": tooltip,
    }


def _condition_hint(condition: str) -> str:
    lower = condition.lower()
    if "anaem" in lower:
        return "Prioritize primary care, maternal health, and nutrition-linked outreach."
    if "birth" in lower or "c-section" in lower or "skilled" in lower:
        return "Prioritize OB coverage, referral transport, and safe-delivery access."
    if "blood pressure" in lower or "sugar" in lower or "diabetes" in lower:
        return "Prioritize chronic-disease screening and follow-up capacity."
    if "screen" in lower or "exam" in lower or "cancer" in lower:
        return "Prioritize outreach camps and referral pathways for preventive care."
    if "insurance" in lower:
        return "Pair clinical deployment with enrollment and low-cost referral support."
    return "Use this as the first clinical problem to validate during deployment planning."


def _health_need_summary(row: pd.Series, conds: pd.DataFrame) -> dict[str, str]:
    need = _num(row.get("health_need_score"))
    value = "Unknown" if pd.isna(need) else f"{need:.2f}"
    tone = "bad" if not pd.isna(need) and need >= 0.66 else (
        "warn" if not pd.isna(need) and need >= 0.33 else "info"
    )
    score_text = "Health need score unavailable" if pd.isna(need) else f"Health need score: {need:.2f}"
    households = _num(row.get("households_surveyed"))
    sample = _sample_confidence(row.get("households_surveyed"))
    sample_text = (
        f"NFHS sample: {int(households):,} households; sample strength {sample:.2f}"
        if not pd.isna(households)
        else f"NFHS sample strength: {sample:.2f}"
    )

    driver_text = "Top condition driver unavailable"
    if conds is not None and not conds.empty:
        worst = conds.iloc[0]
        condition = _clean_text(worst.get("Condition")) or "Medical condition"
        district_pct = _num(worst.get("District %"))
        national_pct = _num(worst.get("National %"))
        gap = _num(worst.get("Δ vs national"))
        if not pd.isna(district_pct) and not pd.isna(national_pct):
            driver_text = f"Top driver: {condition} at {district_pct:.1f}% district vs {national_pct:.1f}% national"
            if not pd.isna(gap):
                driver_text += f"; {gap:.1f} point gap"
        elif not pd.isna(district_pct):
            driver_text = f"Top driver: {condition} at {district_pct:.1f}% district"
        else:
            driver_text = f"Top driver: {condition}"
        driver_text += f". {_condition_hint(condition)}"

    tooltip = (
        f"{score_text}. NFHS district indicators summarize patient need. "
        f"{sample_text}. {driver_text}"
    )
    return {
        "value": value,
        "caption": "Higher means more unmet patient need",
        "tone": tone,
        "tooltip": tooltip,
    }


def _condition_summary(conds: pd.DataFrame) -> str:
    if conds is None or conds.empty:
        return ""
    worst = conds.iloc[0]
    condition = _clean_text(worst.get("Condition")) or "Medical condition"
    district_pct = _num(worst.get("District %"))
    national_pct = _num(worst.get("National %"))
    gap = _num(worst.get("Δ vs national"))
    values = ""
    if not pd.isna(district_pct) and not pd.isna(national_pct):
        values = f"{district_pct:.1f}% district vs {national_pct:.1f}% national"
        if not pd.isna(gap):
            values += f" ({gap:.1f} point gap)"
    hint = _condition_hint(condition)
    prefix = f"{values}. " if values else ""
    return (
        '<div class="mdn-condition-summary">'
        f'<b>Top condition driver: {html.escape(condition)}</b>'
        f'<span>{html.escape(prefix + hint)}</span>'
        '</div>'
    )


def _facility_verified(row: pd.Series) -> bool:
    return (
        _truthy(row.get("trustworthy_supply_signal"))
        and not _truthy(row.get("needs_human_review"))
        and not _truthy(row.get("contradicted_or_geo_invalid_signal"))
    )


def _looks_like_photo_page(url: str) -> bool:
    raw = (url or "").lower()
    return any(hint in raw for hint in _PHOTO_URL_HINTS)


def _claim_description(raw) -> str:
    text = _clean_text(raw)
    if not text:
        return ""
    description = " ".join(text.split(" | ", 1)[0].split())
    if len(description) > 150:
        stops = [description.find(stop) for stop in (". ", "; ", " - ") if description.find(stop) >= 60]
        if stops:
            description = description[:min(stops) + 1].rstrip()
    if len(description) > 145:
        description = description[:142].rstrip(" ,;.") + "..."
    return description


def _service_claims(row: pd.Series, specialty: str) -> list[str]:
    relevant = [
        (label, col, short) for label, col, short in _SERVICE_SIGNALS
        if specialty == "All specialties" or specialty == label
    ]
    return [short for _, col, short in relevant if _truthy(row.get(col))]


def _facility_badges(row: pd.Series, specialty: str, verified: bool, source_url: str) -> str:
    chips = [
        '<span class="mdn-pill mdn-pill--deploy">✓ Passed checks</span>'
        if verified else '<span class="mdn-pill mdn-pill--verify">Verify claims</span>'
    ]
    for claim in _service_claims(row, specialty)[:3]:
        chips.append(f'<span class="mdn-pill mdn-pill--info">{html.escape(claim)}</span>')
    if _looks_like_photo_page(source_url):
        chips.append('<span class="mdn-pill mdn-pill--info">Source photos</span>')
    return '<div class="mdn-pill-row">' + "".join(chips) + '</div>'


def _facility_visual_html(row: pd.Series, initials: str) -> tuple[str, str]:
    photo = photo_enrichment.facility_photo(row.to_dict())
    uri = _clean_text(photo.get("photo_uri"))
    if uri:
        attribution = _clean_text(photo.get("attribution")) or "Google Maps"
        visual = (
            '<div class="mdn-provider-art mdn-provider-art--photo">'
            f'<img src="{html.escape(uri, quote=True)}" alt="{html.escape(initials)} facility photo" />'
            '</div>'
        )
        return visual, f"Photo: {html.escape(attribution)}"
    return f'<div class="mdn-provider-art">{html.escape(initials[:2])}</div>', ""


def _local_facilities(facilities: pd.DataFrame | None, row: pd.Series,
                      specialty: str, n: int = 2) -> pd.DataFrame:
    if facilities is None or facilities.empty:
        return pd.DataFrame()
    if "district_name" not in facilities.columns or "state_ut" not in facilities.columns:
        return pd.DataFrame()
    district = _clean_text(row.get("district_name"))
    state = _clean_text(row.get("state_ut"))
    if not district or not state:
        return pd.DataFrame()
    exact = facilities[
        facilities["district_name"].astype(str).str.strip().eq(district)
        & facilities["state_ut"].astype(str).str.strip().eq(state)
    ].copy()
    if exact.empty:
        return exact
    if specialty != "All specialties":
        signal = next((col for label, col, _ in _SERVICE_SIGNALS if label == specialty), None)
        if signal and signal in exact.columns:
            matches = exact[exact[signal].fillna(False).astype(bool)]
            if not matches.empty:
                exact = matches.copy()
    exact["_verified_sort"] = exact.apply(_facility_verified, axis=1).astype(int)
    trust = (
        exact["trust_tier"].astype(str)
        if "trust_tier" in exact.columns
        else pd.Series("", index=exact.index)
    )
    exact["_trust_sort"] = trust.map({"High": 3, "Medium": 2, "Verify": 1}).fillna(0)
    exact["_source_sort"] = (
        exact["has_source_urls"].fillna(False).astype(bool).astype(int)
        if "has_source_urls" in exact.columns
        else 0
    )
    exact["_quality_sort"] = pd.to_numeric(
        exact.get("semantic_data_quality_score", pd.Series(0, index=exact.index)),
        errors="coerce",
    ).fillna(0)
    return exact.sort_values(
        ["_verified_sort", "_trust_sort", "_source_sort", "_quality_sort"],
        ascending=False,
    ).head(n)


def _facility_card_html(row: pd.Series, specialty: str) -> str:
    name = _clean_text(row.get("facility_name")) or "Unnamed facility"
    initials = "".join(part[:1] for part in name.split()[:2]).upper() or "F"
    city = _clean_text(row.get("address_city")) or _clean_text(row.get("district_name"))
    state = _clean_text(row.get("address_stateOrRegion")) or _clean_text(row.get("state_ut"))
    location = ", ".join(part for part in [city, state] if part) or "Location not captured"
    source_url = data._first_url(row.get("source_urls", ""))
    source_domain = _source_domain(source_url) or "source unavailable"
    claim = _claim_description(row.get("claim_text")) or (
        "No extracted service description; call or verify before relying on this provider."
    )
    verified = _facility_verified(row)
    visual_html, photo_caption = _facility_visual_html(row, initials)
    if source_url:
        link_text = "Source photos" if _looks_like_photo_page(source_url) else "View source page"
        source_link = (
            f'<a href="{html.escape(source_url, quote=True)}" target="_blank" rel="noopener">'
            f'{html.escape(link_text)}</a> · {html.escape(source_domain)}'
        )
    else:
        source_link = "No source URL captured"
    if photo_caption:
        source_link += f' · <span translate="no">{photo_caption}</span>'
    return (
        '<div class="mdn-provider-card">'
        f'{visual_html}'
        '<div>'
        f'<div class="mdn-provider-name">{html.escape(name)}</div>'
        f'{_facility_badges(row, specialty, verified, source_url)}'
        f'<div class="mdn-provider-desc">{html.escape(location)}</div>'
        f'<div class="mdn-provider-claim">{html.escape(claim)}</div>'
        f'<div class="mdn-provider-desc">{source_link}</div>'
        '</div>'
        '</div>'
    )


def _facility_evidence_cards(row: pd.Series, facilities: pd.DataFrame | None,
                             specialty: str) -> None:
    panel_header("Facility evidence")
    local = _local_facilities(facilities, row, specialty)
    if local.empty:
        st.markdown(
            '<div class="mdn-provider-grid">'
            '<div class="mdn-provider-card mdn-empty-provider">'
            '<div class="mdn-provider-art">0</div>'
            '<div>'
            '<div class="mdn-provider-name">No mapped provider claims</div>'
            '<div class="mdn-pill-row">'
            '<span class="mdn-pill mdn-pill--verify">Call or verify</span>'
            '</div>'
            '<div class="mdn-provider-claim">'
            'No source-backed provider claim is mapped to this district yet.'
            '</div>'
            '<div class="mdn-provider-desc">Use this as a supply-gap signal; call nearby providers before staffing.</div>'
            '</div>'
            '</div>'
            '</div>',
            unsafe_allow_html=True,
        )
        return

    cards = "".join(_facility_card_html(facility, specialty) for _, facility in local.iterrows())
    st.markdown(f'<div class="mdn-provider-grid">{cards}</div>', unsafe_allow_html=True)


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
    url = _clean_text(f.get("source_url"))
    domain = _source_domain(url)
    evidence = _clean_text(f.get("evidence"))

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


def _fmt_pct(v, digits: int = 0) -> str:
    value = _num(v)
    return "—" if pd.isna(value) else f"{value * 100:.{digits}f}%"


def _district_trust_assessment(row: pd.Series) -> dict[str, str]:
    """Categorical planner trust tier; numeric rate is reserved for hover text."""
    obs = _num(row.get("observed_facility_rows"))
    calibrated = _num(row.get("provider_trust_score"))
    rate = _num(row.get("trustworthy_supply_rate"))
    ci_low = _num(row.get("trustworthy_supply_rate_ci_low"))

    if pd.isna(obs) or obs <= 0:
        label = "Not scored"
        tone = "info"
        caption = "No mapped provider claims."
    elif not pd.isna(calibrated):
        if calibrated >= 0.80:
            label = "High trust"
            tone = "deploy"
            caption = "Strong source and claim evidence."
        elif calibrated >= 0.55:
            label = "Medium trust"
            tone = "verify"
            caption = "Some evidence; call to confirm."
        else:
            label = "Low trust"
            tone = "danger"
            caption = "Weak or conflicting evidence."
    elif pd.isna(rate):
        trusted = _num(row.get("trustworthy_supply_rows"))
        rate = 0.0 if pd.isna(trusted) else trusted / obs
        if rate < 0.34:
            label = "Low trust"
            tone = "danger"
            caption = "Few observed claims pass."
        elif rate >= 0.67 and obs >= 3 and (pd.isna(ci_low) or ci_low >= 0.35):
            label = "High trust"
            tone = "deploy"
            caption = "Most observed claims pass."
        else:
            label = "Medium trust"
            tone = "verify"
            caption = "Some observed claims pass."
    elif rate < 0.34:
        label = "Low trust"
        tone = "danger"
        caption = "Few observed claims pass."
    elif rate >= 0.67 and obs >= 3 and (pd.isna(ci_low) or ci_low >= 0.35):
        label = "High trust"
        tone = "deploy"
        caption = "Most observed claims pass."
    else:
        label = "Medium trust"
        tone = "verify"
        caption = "Some observed claims pass."
    return {"label": label, "tone": tone, "caption": caption}


def _district_trust_tooltip(row: pd.Series) -> str:
    obs_raw = _num(row.get("observed_facility_rows"))
    rate_raw = _num(row.get("trustworthy_supply_rate"))
    calibrated = _num(row.get("provider_trust_score"))
    posterior_mean = _num(row.get("provider_validity_posterior_mean"))
    smoothed_pass = _num(row.get("provider_pass_rate_smoothed"))
    prior_rate = _num(row.get("provider_trust_prior_rate"))
    prior_strength = _num(row.get("provider_trust_prior_strength"))
    if pd.isna(obs_raw) or obs_raw <= 0:
        return (
            "Provider trust score: not scored. This district has zero mapped "
            "provider claims, so there is no local denominator. Use health need, "
            "gap confidence, and calls to likely providers before staffing."
        )
    trusted_raw = _num(row.get("trustworthy_supply_rows"))
    if pd.isna(rate_raw):
        rate_raw = 0.0 if pd.isna(trusted_raw) else trusted_raw / obs_raw
    obs = _fmt_int(obs_raw)
    trusted = _fmt_int(trusted_raw)
    rate = _fmt_pct(rate_raw)
    ci = _fmt_interval(
        row.get("trustworthy_supply_rate_ci_low"),
        row.get("trustworthy_supply_rate_ci_high"),
        2,
    )
    ci_text = "unknown" if ci == "unknown" else f"{ci} Wilson 95% interval"
    uncertainty = _clean_text(row.get("district_uncertainty_level")).title() or "Unknown"
    if not pd.isna(calibrated):
        posterior_text = "unknown" if pd.isna(posterior_mean) else _fmt_pct(posterior_mean)
        smoothed_text = "unknown" if pd.isna(smoothed_pass) else _fmt_pct(smoothed_pass)
        prior_text = "unknown" if pd.isna(prior_rate) else _fmt_pct(prior_rate)
        prior_n = "2" if pd.isna(prior_strength) else f"{prior_strength:.0f}"
        return (
            f"Provider trust score: {_fmt_pct(calibrated)} calibrated evidence trust. "
            f"Formula: 75% Bayesian row-validity evidence ({posterior_text}) plus "
            f"25% empirical-Bayes smoothed pass rate ({smoothed_text}; prior {prior_text}, "
            f"prior n={prior_n}). Hard automated checks: {trusted} of {obs}; Wilson interval: "
            f"{ci_text}. District uncertainty: {uncertainty}. This is evidence-based claim "
            "trust, not measured medical truth."
        )
    return (
        f"Provider trust score: {rate} hard-check pass rate. Mapped provider claims passing "
        f"checks: {trusted} of {obs}. Wilson interval: {ci_text}. District uncertainty: "
        f"{uncertainty}. This is evidence-based claim trust, not measured medical truth."
    )


def _trust_card(row: pd.Series) -> None:
    assessment = _district_trust_assessment(row)
    tone_class = {
        "deploy": "mdn-card--deploy",
        "verify": "mdn-card--verify",
        "danger": "mdn-card--danger",
        "info": "mdn-card--info",
    }.get(assessment["tone"], "")
    tip = html.escape(_district_trust_tooltip(row), quote=True)
    st.markdown(
        f"""
        <div class="mdn-card mdn-trust-card {tone_class}">
          <div class="mdn-card-kicker">Provider trust</div>
          <div class="mdn-card-value mdn-tip" tabindex="0" data-tip="{tip}">
            {html.escape(assessment["label"])}
          </div>
          <div class="mdn-card-caption">{html.escape(assessment["caption"])}</div>
          <div class="mdn-trust-help" tabindex="0">
            How trust is assessed
            <div class="mdn-trust-help-card">
              Accuracy tiers use mapped provider claims that pass source, geography,
              recency, and contradiction checks. Wilson intervals and uncertainty bands
              keep thin samples visibly cautious.
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _split_sample_values(value, limit: int = 3, *, split_semicolon: bool = True) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    if split_semicolon and ";" in text:
        parts = [part.strip() for part in text.split(";")]
    else:
        parts = [text]
    out: list[str] = []
    for part in parts:
        cleaned = _clean_text(part)
        if cleaned and cleaned not in out:
            out.append(cleaned)
        if len(out) >= limit:
            break
    return out


def _split_source_url_samples(value, limit: int = 3) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    chunks = [chunk.strip() for chunk in text.split(";") if chunk.strip()] if ";" in text else [text]
    urls: list[str] = []
    for chunk in chunks:
        url = _clean_text(data._first_url(chunk))
        if url and url.lower().startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            return urls
    for raw_url in data._json_list(text):
        url = _clean_text(raw_url)
        if url and url.lower().startswith(("http://", "https://")) and url not in urls:
            urls.append(url)
        if len(urls) >= limit:
            break
    return urls


def _claim_excerpt(value, limit: int = 190) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    parts = [part.strip() for part in text.split("|")]
    natural = next((part for part in parts if part and not part.startswith("[")), text)
    natural = " ".join(natural.split())
    return natural if len(natural) <= limit else natural[: limit - 3].rstrip() + "..."


def _initials(name: str) -> str:
    letters = [
        part[0].upper()
        for part in name.replace("&", " ").replace("-", " ").split()
        if part and part[0].isalnum()
    ]
    return "".join(letters[:2]) or "VF"


def provider_claim_card_html(claim: dict) -> str:
    """Return a compact, source-grounded provider/facility claim card.

    If a sourced image URL is supplied, it is rendered. Otherwise the tile uses
    facility initials so the UI does not imply a missing or broken photo.
    """
    name = _clean_text(claim.get("facility_name") or claim.get("name")) or "Unnamed facility"
    facility_type = _clean_text(claim.get("facility_type") or claim.get("facilityTypeId")) or "Facility claim"
    location = ", ".join(
        item for item in [
            _clean_text(claim.get("city") or claim.get("address_city") or claim.get("district_name")),
            _clean_text(claim.get("state") or claim.get("state_ut") or claim.get("address_stateOrRegion")),
        ]
        if item
    )
    status = _clean_text(claim.get("status")) or "Needs verification"
    status_key = status.lower()
    status_cls = (
        "mdn-pill--deploy" if "pass" in status_key or "high" in status_key
        else "mdn-pill--danger" if "contrad" in status_key or "low" in status_key
        else "mdn-pill--verify"
    )
    source_text = _claim_excerpt(
        claim.get("claim_text") or claim.get("evidence") or claim.get("source_text")
    ) or "No clean source-text excerpt is available for this claim."

    source_url = _clean_text(claim.get("source_url") or claim.get("url"))
    if not source_url:
        source_url = _clean_text(data._first_url(claim.get("source_urls", "")))
    domain = _source_domain(source_url)
    source_html = (
        f'<a href="{html.escape(source_url, quote=True)}" target="_blank">{html.escape(domain)}</a>'
        if source_url and domain else '<span style="color:var(--mdn-muted)">No source URL</span>'
    )

    image_url = _clean_text(claim.get("image_url") or claim.get("photo_url"))
    if image_url and image_url.lower().startswith(("http://", "https://")):
        art = (
            f'<div class="mdn-provider-art"><img src="{html.escape(image_url, quote=True)}" '
            f'alt="{html.escape(name, quote=True)} source image"></div>'
        )
    else:
        art = (
            f'<div class="mdn-provider-art"><span>{html.escape(_initials(name)[:2])}</span>'
            '<small>Source card</small></div>'
        )

    location_html = (
        f'<div class="mdn-provider-desc">{html.escape(location)}</div>'
        if location else ""
    )
    return (
        '<div class="mdn-provider-card">'
        f'{art}'
        '<div>'
        f'<div class="mdn-provider-name">{html.escape(name)}</div>'
        f'<div class="mdn-pill-row"><span class="mdn-pill {status_cls}">{html.escape(status)}</span>'
        f'<span class="mdn-pill mdn-pill--muted">{html.escape(facility_type)}</span></div>'
        f'{location_html}'
        f'<div class="mdn-provider-claim">{html.escape(source_text)}</div>'
        f'<div class="mdn-provider-desc">Source: {source_html}</div>'
        '</div></div>'
    )


def provider_claim_cards(claims, *, empty_message: str = "No provider/facility claim evidence is available.") -> None:
    """Render compact provider/facility claim cards from dict records or a DataFrame."""
    records = claims.to_dict("records") if isinstance(claims, pd.DataFrame) else list(claims or [])
    records = [record for record in records if isinstance(record, dict)]
    if not records:
        st.caption(empty_message)
        return
    st.caption("Provider cards show source text and links. Photos appear only after a matched listing is available.")
    st.markdown(
        '<div class="mdn-provider-grid">' + "".join(provider_claim_card_html(record) for record in records) + '</div>',
        unsafe_allow_html=True,
    )


def _sample_provider_claims(row: pd.Series, limit: int = 3) -> list[dict]:
    names = _split_sample_values(row.get("sample_facility_names"), limit=limit)
    claim_texts = _split_sample_values(row.get("sample_claim_evidence"), limit=1, split_semicolon=False)
    urls = _split_source_url_samples(row.get("sample_source_urls"), limit=limit)
    total = min(limit, max(len(names), len(urls), 1 if claim_texts else 0))
    claims: list[dict] = []
    for i in range(total):
        name = names[i] if i < len(names) else "Sample facility claim"
        url = urls[i] if i < len(urls) else (urls[0] if urls else "")
        text = claim_texts[i] if i < len(claim_texts) else (claim_texts[0] if claim_texts else "")
        if not (name or url or text):
            continue
        claims.append({
            "facility_name": name,
            "facility_type": "Facility claim",
            "status": "Needs verification",
            "claim_text": text,
            "source_url": url,
        })
    return claims


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


def region_detail(row: pd.Series, specialty: str, districts: pd.DataFrame | None = None,
                  facilities: pd.DataFrame | None = None) -> None:
    """District drill-down for planners: decision first, statistics on demand."""
    cat = str(row.get("planning_category", "mixed_or_monitor"))
    chip, rec = data.PLANNING.get(cat, data.PLANNING["mixed_or_monitor"])
    district = _clean_text(row.get("district_name")) or "Unknown district"
    state = _clean_text(row.get("state_ut")) or "Unknown state"
    name = f"{district}, {state}"
    chip_lower = chip.lower()
    banner_tone = "deploy" if "deploy" in chip_lower or "build" in chip_lower else (
        "verify" if "verify" in chip_lower else "info"
    )

    st.markdown(
        '<div class="mdn-region-head">'
        '<div class="mdn-region-title">'
        f'<span class="mdn-region-name">{html.escape(name)}</span>'
        f'<span class="mdn-pill mdn-pill--info">{html.escape(chip)}</span>'
        '</div>'
        '<span class="mdn-muted">Click map or rail row to change district</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    decision_banner(chip, rec, banner_tone)

    conds = data.district_top_conditions(row, districts) if districts is not None else pd.DataFrame()
    need = _health_need_summary(row, conds)
    need_tip = html.escape(str(need["tooltip"]), quote=True)
    need_value = (
        f'<span tabindex="0" class="mdn-tip mdn-trust-tip" data-tip="{need_tip}">'
        f'{html.escape(str(need["value"]))} <span aria-hidden="true">ⓘ</span></span>'
    )
    gap_conf = _gap_confidence_summary(row)
    gap_tip = html.escape(str(gap_conf["tooltip"]), quote=True)
    gap_value = (
        f'<span tabindex="0" class="mdn-tip mdn-trust-tip" data-tip="{gap_tip}">'
        f'{html.escape(str(gap_conf["label"]))} <span aria-hidden="true">ⓘ</span></span>'
    )
    supply = _trust_summary(row)
    supply_tip = html.escape(str(supply["tooltip"]), quote=True)
    supply_value = (
        f'<span tabindex="0" class="mdn-tip mdn-trust-tip" data-tip="{supply_tip}">'
        f'{html.escape(str(supply["label"]))} <span aria-hidden="true">ⓘ</span></span>'
    )
    uncertainty = (_clean_text(row.get("district_uncertainty_level")) or "unknown").title()
    uncertainty_tone = "warn" if uncertainty.lower() in {"higher", "high"} else "info"
    cards = [
        _region_card("Health need", str(need["value"]), str(need["caption"]),
                     str(need["tone"]), value_html=need_value),
        _region_card("Gap confidence", str(gap_conf["label"]), str(gap_conf["caption"]),
                     str(gap_conf["tone"]), value_html=gap_value),
        _region_card("Provider trust", str(supply["label"]), str(supply["caption"]),
                     str(supply["tone"]), value_html=supply_value),
    ]
    st.markdown('<div class="mdn-region-grid">' + "".join(cards) + '</div>',
                unsafe_allow_html=True)

    summary = _condition_summary(conds)
    if summary:
        st.markdown(summary, unsafe_allow_html=True)
    else:
        st.caption("No NFHS condition indicators available for this district.")

    _facility_evidence_cards(row, facilities, specialty)

    geo_id = f"{state}|{district}"
    shortlisted = decisions.is_shortlisted(geo_id)
    st.caption("Next step: add this district to the plan or leave a call note.")
    sc1, sc2 = st.columns([1, 1])
    if sc1.button("In plan" if shortlisted else "Add to plan",
                  key=f"sl_{geo_id}", use_container_width=True):
        decisions.toggle_shortlist(geo_id, label=name)
        st.rerun()
    with sc2.popover("Add note", use_container_width=True):
        txt = st.text_area("Planner note", key=f"nt_{geo_id}",
                           label_visibility="collapsed",
                           placeholder="Example: send mobile OB team; verify local PHC supply first.")
        if st.button("Save note", key=f"sn_{geo_id}") and txt.strip():
            decisions.save_note(geo_id, txt.strip())
            st.toast("Note saved")

    with detail("More detail: medical-condition gaps"):
        if not conds.empty:
            st.altair_chart(charts.condition_gaps(conds), use_container_width=True,
                            key="region_condition_gaps_chart")
            worst = conds.iloc[0]
            st.caption(
                f"Worst gap: {worst['Condition']} "
                f"({worst['District %']}% district vs {worst['National %']}% national). "
                "Bar = district; gray tick = national median."
            )
        else:
            st.caption("No NFHS condition indicators available for this district.")

    with detail("More detail: score formula"):
        breakdown, total, _ = data.care_gap_breakdown(row)
        st.altair_chart(charts.care_gap_contributions(breakdown), use_container_width=True,
                        key="region_care_gap_contributions_chart")
        st.caption(f"Care-gap score = {total:.2f}: 0.55 need + 0.25 supply scarcity + 0.20 low trust.")

    with detail("Why this recommendation"):
        explanation, reasons = data.district_explanation(row, specialty)
        st.dataframe(explanation, hide_index=True, width="stretch", height=285)
        if not reasons.empty:
            reason_chips(reasons["Reason"].tolist())

    with detail("Raw evidence & sources"):
        names = _clean_text(row.get("sample_facility_names"))
        claim = _clean_text(row.get("sample_claim_evidence"))
        url = data._first_url(row.get("sample_source_urls", ""))
        if names:
            st.markdown(f"**Facilities:** {names[:300]}")
        if claim:
            st.markdown(f"**Claim text:** {claim[:300]}...")
        if url:
            st.markdown(f"**Source:** [{url[:80]}]({url})")
        if not (names or claim or url):
            st.caption("No raw facility source evidence recorded for this district.")


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
                "Signal": "Provider hard-check pass rate",
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
    documented in docs/DESIGN_SYSTEM.md. ``inner_html`` is trusted markup (the caller
    is responsible for escaping any user/data text it interpolates).
    """
    st.markdown(f'<div class="mdn-float">{inner_html}</div>', unsafe_allow_html=True)
