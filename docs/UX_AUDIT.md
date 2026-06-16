# Medical Desert Navigator — UX Audit & Design Direction

**Author:** Director of UX
**Date:** 2026-06-15
**Scope:** 7 top-level views — Map · Top care gaps · Interventions · Scenario lab · Uncertainty console · Trust & conformal · Decisions & feedback
**Ownership note:** This document is advisory. All code edits are owned by the Frontend Engineer. This file (`docs/UX_AUDIT.md`) is the only artifact I write.

---

## 0. How this audit was grounded

- **Playwright MCP: NOT AVAILABLE.** `ToolSearch("playwright browser screenshot")` returned no matching deferred tools, and no `mcp__playwright*` tools are present. I did **not** launch the app on port 8701, per the "do not block" instruction.
- Grounded instead in: (a) the **7 existing rendered screenshots** in `output/playwright/` (`earth-ui-map-refreshed.png`, `top-care-gaps-final.png`, `top-care-gaps-redesign.png`, `uncertainty-overview-final.png`, `uncertainty-overview-redesign.png`, `uncertainty-triage-redesign.png`, `uncertainty-model-policy-final.png`), and (b) a **structural read** of `app/app.py`, `app/lib/ui.py`, `app/lib/config.py`, `.streamlit/config.toml`, and the 4 new modules `interventions.py`, `simulator.py`, `trust.py`, `decisions.py`.
- **Caveat for QA/FE:** every screenshot in `output/playwright/` shows the **old 3-tab `st.tabs` build** (Map / Top care gaps / Uncertainty console). The live code (`app/app.py:987`) has already moved to a **7-item `st.segmented_control`** with all 4 new views wired in. So the screenshots accurately show the *design system and idiom*, but **not** the current 7-way nav or the 4 new views. A fresh Playwright pass after FE changes is strongly recommended for QA.

**The good news:** the app is already dark, spatial, and substantially Google-Earth-like. The design system in `ui.inject_css` is mature (CSS custom-property tokens, glass panels, tone-coded cards, command-center metric tiles). This is a **refinement and consistency** job, not a rebuild. The biggest real risks are (1) nav scalability at 7 views, (2) one new view (`trust.py`) drifting off the house idiom, and (3) the map not yet reading as the immersive "hero."

---

## 1. Heuristic scorecard (1–5; 5 = excellent)

| # | Dimension | Score | One-line verdict |
|---|-----------|:----:|------------------|
| 1 | Visual hierarchy | **4** | Strong: kicker→value→caption cards, uppercase `mdn-panel-h` rails. Headline metric and "what to do" usually clear. |
| 2 | Navigation / IA | **2** | 7 equal-weight segments in one control is the weakest point. Single-row segmented control will wrap/crowd; no grouping of related views. |
| 3 | Google-Earth immersiveness | **3** | Dark, depth-rich panels are there. But the map is boxed at fixed height with chrome above it; default basemap is **Voyager (light)**, undercutting the dark-space aesthetic. No "space→surface" gradient. |
| 4 | Consistency across 7 views | **3** | Map/Gaps/Interventions/Scenario/Decisions share the idiom well. **`trust.py` is the outlier** (uses `st.subheader`, bare `**bold**` headers, `use_container_width`, no decision_banner/workflow_rail). |
| 5 | Color / semantic discipline | **4** | Clean 4-tone system (deploy=teal, verify=amber, danger=red, info=sky) consistently applied via `stat_card`/`decision_banner` tones. Minor: histograms still hard-code raw hex. |
| 6 | Typography | **3** | Solid weight/size scale, but relies on Streamlit's default "sans serif". No deliberate font stack; numerals not tabular (KPI columns misalign). |
| 7 | Density / whitespace | **3** | Cards and rails breathe well. Uncertainty console is a very long single scroll of stacked dataframes — dense and fatiguing. |
| 8 | States (loading / empty / error) | **4** | Genuinely good: spinners, `st.info` empty states, try/except → `st.error`, session-only persistence caption. `trust.py` empty/error states are present too. |
| 9 | Accessibility / contrast | **3** | Body text `#eaf2ff` on `#05080f` is excellent. Risks: `--mdn-dim #607086` muted text on dark is borderline AA; focus rings not styled; tone is carried by color alone (no icon/text redundancy on cards). |
| 10 | Trust / evidence legibility | **4** | This is the app's soul and it shows: "claimed (unverified)", provisional-conformal warnings, Wilson CIs, "what the app can/cannot say". Could be even more visually distinct (a consistent evidence/citation block treatment). |

**Headline:** **Overall ≈ 3.3 / 5.** Mature, honest, already-dark command center. The two scores dragging it down are **Navigation/IA (2)** and the cluster at **3** (immersiveness, consistency, typography, density, a11y). Fixing nav grouping, pulling `trust.py` onto the idiom, switching the default basemap to dark, and adding a font stack + tabular numerals would move the whole app to ~4.2.

---

## 2. Prioritized, concrete design spec (for the Frontend Engineer)

Ordered by impact-to-effort. Each item names the exact file/function.

### P0 — Navigation grouping for 7 views (biggest UX win)
**Problem:** `app/app.py:987` renders all 7 views in one `st.segmented_control(..., width="stretch")`. Seven equal segments on one row crowd badly and flatten the IA — a planner can't tell that "Map / Top care gaps / Interventions / Scenario lab" are the *planning* flow while "Uncertainty console / Trust & conformal / Decisions & feedback" are the *evidence & governance* flow.

**Recommendation — two-level nav (preferred):** Replace the single 7-way control with a **2-group primary control + contextual secondary control**, mirroring the pattern the app *already* uses successfully inside the Uncertainty console (`st.tabs`) and Decisions (`st.segmented_control`).

```
Primary (segmented_control, 2 options):   [ Plan ]   [ Evidence & Trust ]
  Plan         → secondary segmented_control: Map · Top care gaps · Interventions · Scenario lab
  Evidence & Trust → secondary segmented_control: Uncertainty console · Trust & conformal · Decisions & feedback
```

- Keep `key="primary_view"`; add `key="plan_view"` / `key="evidence_view"` for the secondary controls so deep-link/session state survives reruns.
- This caps any single row at **4 segments max**, which `segmented_control` renders cleanly at `width="stretch"`.
- **Lower-effort fallback** if two-level is too much churn before the deadline: keep one control but **insert a visual group divider** — render the control label not collapsed but as two captioned clusters, or prepend group kickers using the existing `.mdn-panel-h` class ("PLAN" / "EVIDENCE & TRUST") above two separate `segmented_control`s on the same row via `st.columns([4,3])`. Either way, **stop showing 7 flat equal segments.**

### P0 — Pull `trust.py` onto the house idiom (consistency)
`app/lib/trust.py::render_trust` is the one new view that breaks the established pattern. Concrete fixes:
- **Header:** replace `st.subheader("Record-validity confidence")` (`trust.py:582`) with a `ui.decision_banner(...)` + `ui.workflow_rail([...])` opener, matching `interventions.render_interventions` (`interventions.py:517-530`) and `decisions.render_decisions` (`decisions.py:378-390`). Suggested rail: `Claim → Score posterior → Calibrate (conformal) → Decompose trust → Cite sources`.
- **Section headers:** replace the three bare `st.markdown("**…**")` calls (`trust.py:627, 641, 703`) with `st.markdown('<div class="mdn-panel-h">…</div>', unsafe_allow_html=True)` so they match every other view's uppercase section kicker.
- **Deprecated width arg:** change `use_container_width=True` (`trust.py:697`) to `width="stretch"` — the rest of the app standardized on `width="stretch"`; mixing the two is a latent deprecation warning and a subtle styling inconsistency.
- The stat-card row and the provisional-conformal `st.warning` are already on-idiom — keep them.

### P1 — Map as hero (immersiveness)
In `app/app.py::map_tab` and `config.py`:
- **Default to a dark basemap.** `config.DEFAULT_MAP_STYLE` is currently `"Voyager"` (light), which fights the `#05080f` shell. Set `DEFAULT_MAP_STYLE = "Dark Matter"` so first paint reads as the dark command center the rest of the chrome promises. (Note: the task brief's claim that the default is already "Dark Matter" does **not** match the code — flag for the team.)
- **Give the map more vertical presence.** It's currently `pdk.Deck(..., height=580)` inside a `[3.1, 1]` column split with a full row of controls stacked above. Consider raising height to ~640–680 and moving the 5 map controls (`map_tab` `c1..c5`) into a compact `st.popover("Layers")` or a single collapsed control strip so the map is the first thing the eye lands on, not the fourth.
- **Luminous data over restrained chrome (Google-Earth cue).** Keep hexbins translucent (`opacity` already 0.55/0.82) but raise facility-dot glow: the scatter layer can use a brighter `get_line_color` and a subtle radius pulse on highlight. The legend (`ui.legend`) is good; keep it directly under the map.

### P1 — Typography: deliberate font stack + tabular numerals
In `ui.inject_css` (the `_CSS` string):
- Add a modern system/geometric stack to `html, body, .stApp` and especially to numeric displays:
  `font-family: "Inter", "SF Pro Display", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;`
- Add `font-variant-numeric: tabular-nums; font-feature-settings:"tnum" 1;` to `.mdn-card-value`, `[data-testid="stMetricValue"]`, and dataframe cells so KPI columns and the leaderboard numbers stop jittering between digits. This single change makes the "command center" feel far more precise.
- `.streamlit/config.toml` `font = "sans serif"` can stay; the CSS stack above overrides where it matters.

### P1 — Glassmorphism / elevation polish (depth-rich, Google-Earth depth)
In `ui.inject_css`:
- The `.mdn-card`, `.mdn-decision-banner`, `.mdn-rail-step` panels already use translucent fills + shadows. Add `backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);` to `.mdn-card`, `.mdn-decision-banner`, and `.mdn-earth-strip` (the topbar already has `blur(16px)`) so panels read as frosted glass floating over the dark map — the core Google-Earth "panels over the world" feel.
- **Elevation scale:** introduce two shadow tokens in `:root` — `--mdn-elev-1: 0 6px 18px rgba(0,0,0,.28)` and `--mdn-elev-2: 0 14px 34px rgba(0,0,0,.40)` — and apply elev-1 to cards, elev-2 to the sticky topbar and any selected/active card, so depth is consistent and intentional rather than ad-hoc per-rule shadows.
- **Hover lift:** add a subtle `transition: transform .15s ease, border-color .15s ease;` + `:hover { transform: translateY(-1px); }` to `.mdn-card` and `.mdn-rail-step` for the "alive, responsive surface" Earth quality. Keep it to 1px — restrained chrome.

### P2 — Focus states & a11y (accessibility/contrast)
In `ui.inject_css`:
- Add a visible focus ring for keyboard users:
  `:where(button, [role="tab"], a, [data-baseweb="select"] > div):focus-visible { outline: 2px solid var(--mdn-sky); outline-offset: 2px; }`
- **Redundant encoding for tone:** stat cards currently signal deploy/verify/danger/info via **border color only** (`mdn-card--deploy` etc.). Add a small leading dot or a single-word kicker tone (the `decision_banner` already does this with its pill — replicate a tiny tone pill or colored left-border bar in `stat_card`) so color-blind users get the semantic without relying on hue.
- Bump `--mdn-dim` from `#607086` → ~`#7d8fa6` for any text that uses it, to clear WCAG AA on the `#05080f` background.

### P2 — Uncertainty console density (whitespace)
`app/app.py::uncertainty_tab` is a long vertical stack of dataframes (model card, seed report, supervised report, active queues, validation sources, missingness, verification protocol, geo pipeline, candidates, review queue). The screenshots show it's already using an internal `st.tabs`/sub-segment idiom (Overview / Triage queues / Geo source agreement / Missingness / Model policy) — **good**. Make sure *every* heavy section lives under that secondary nav rather than below it as an endless scroll, and cap default dataframe `height` to ~280 so no single table dominates the viewport. This is the model for how the other dense views should chunk content.

### P3 — Color token unification for charts
`st.bar_chart` calls hard-code hex (`map_tab` uses `color="#FF3621"` Databricks red — *off-palette*; `trust.py`/`simulator.py` charts use defaults). Route all chart colors through the established tokens (`--mdn-sky #66d9ff` for neutral distributions, `--mdn-teal/amber/red` for semantic). The `#FF3621` in `map_tab`'s histogram is a leftover from the old light theme and clashes with the cyan/teal system — replace with `#66d9ff`.

---

## 3. Google Earth reference cues → Streamlit/CSS translation

No WebGL globe needed. Emulate the *feel*, not the literal globe:

| Google Earth cue | Translate to (Streamlit/CSS) |
|------------------|------------------------------|
| Deep space-to-surface dark gradient | Replace the flat `--mdn-bg: #05080f` on `[data-testid="stAppViewContainer"]` with a subtle radial: `radial-gradient(120% 120% at 50% -10%, #0a1422 0%, #05080f 55%, #03060c 100%)`. Top-of-page reads like the upper atmosphere; content sits "on the surface." |
| Luminous data over dark terrain | Keep map dark (Dark Matter default), make facility dots/hexbins the brightest thing on screen. Use the teal/amber/red ramp at high opacity; let chrome stay muted (`--mdn-muted`). Data glows, UI recedes. |
| Subtle depth / floating panels | Frosted glass (`backdrop-filter: blur`) + the two-tier elevation shadow tokens (P1). Panels feel like they hover above the map. |
| Restrained chrome | Controls in popovers/collapsed strips (P1 map item); muted borders (`--mdn-line` at .22 alpha — already good); never compete with the data for brightness. |
| Smooth, calm transitions | Add `transition` on cards/tabs/buttons (150–200ms ease). The app already does "click-to-fly" recentre in `map_tab` (`_picked_facility` → new `ViewState`) — that *is* the Earth fly-to gesture; keep and lean into it. |
| Crisp, precise readouts (the HUD feel) | Tabular numerals (P1 typography), uppercase kickers (already via `.mdn-panel-h`), the teal status-dot with glow (`.mdn-status-dot` already has `box-shadow: 0 0 14px` — extend this "live telemetry" motif to the active nav item). |

---

## 4. "DO NOT BREAK" — public `ui` surface the new modules depend on

The 4 new modules import and call these `ui` helpers. **Their names and signatures must be preserved** through any CSS/refactor work:

| Helper | Signature | Used by |
|--------|-----------|---------|
| `ui.inject_css()` | `() -> None` | `app.py` (must stay the single CSS entry point) |
| `ui.header()` | `() -> None` | `app.py` |
| `ui.stat_card(label, value, caption="", tone="neutral")` | tones: `deploy/verify/danger/info/neutral` | interventions, simulator, trust, decisions |
| `ui.decision_banner(title, subtitle, tone="info")` | tones: `deploy/verify/danger/info` | interventions, simulator, decisions (and **should** be added to trust) |
| `ui.workflow_rail(steps)` | `steps: list[tuple[str,str]]` | interventions, decisions (and **should** be added to trust) |
| `ui.reason_chips(labels)` | `labels: list[str]` | interventions, plus map/uncertainty detail panels |
| `ui.facility_card(f)` | `f: dict` | `map_tab` |
| `ui.region_detail(row, specialty)` | | `gaps_tab` |
| `ui.legend(low_label, high_label, higher_is_worse)` | | `map_tab` |
| `ui.active_district_detail`, `ui.active_facility_detail`, `ui.geo_candidate_detail`, `ui.verification_detail` | `(row[, specialty])` | `uncertainty_tab` |

**CSS class contract — keep these selectors (renaming breaks inline-styled components):**
`.mdn-card` (+ `--deploy/--verify/--danger/--info`), `.mdn-card-kicker/-value/-caption`, `.mdn-decision-banner`, `.mdn-rail` / `.mdn-rail-step`, `.mdn-pill` (+ tone modifiers), `.mdn-panel-h`, `.mdn-topbar/-logo/-title/-sub/-chip`, `.mdn-orbit-note`, `.mdn-earth-strip`, `.mdn-status-dot`, `.mdn-legend-bar/-row`. The `:root` CSS custom properties (`--mdn-bg/-panel/-line/-text/-muted/-teal/-sky/-amber/-red`) are referenced throughout — **extend them, don't remove them.**

**Semantic tone → token mapping must stay stable:** `deploy=teal`, `verify=amber`, `danger=red`, `info=sky`. Multiple modules hard-map planning categories and conformal decisions to these tones (e.g. `simulator._INTERVENTIONS`, `trust.render_trust` action tones, `interventions._tone_for`). Repainting these colors silently changes the meaning of the whole app's status language — change the hex *values* of the tokens if needed, but never the tone→role mapping.

---

## 5. Quick wins checklist (if time is short)
1. **Group the nav** into 2 primary groups (P0) — single biggest perceived-quality jump.
2. **Default basemap → Dark Matter** (`config.py`, one line) — instant immersiveness.
3. **`trust.py`**: swap `st.subheader`/`**bold**` → `decision_banner` + `mdn-panel-h`, `use_container_width` → `width="stretch"` (P0 consistency).
4. **Font stack + tabular numerals** in `ui.inject_css` (P1) — makes everything feel precise.
5. **Replace `#FF3621` histogram color** in `map_tab` with `#66d9ff` (P3) — kills the last light-theme artifact.
