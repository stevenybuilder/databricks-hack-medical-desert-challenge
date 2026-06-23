# CareGap — Enhancements Round 2 (UX + Product gap analysis → execution)

**Date:** 2026-06-16 · **Track:** Medical Desert Planner · **Reference bar:** vfmatch.org/explore
**Process:** Director of UX Design + Director of Product each ran an independent gap
analysis (live Playwright walkthrough of our app + VFMatch, code root-causing, against
the judging criteria + the user's reported issues), then their findings were debated and
reconciled into the prioritized plan below.

## Judging criteria (devpost)
1. **Product judgment** — Is the user clear? Are workflow & tradeoffs thoughtful?
2. **Evidence & Uncertainty** — Outputs grounded in citations? Uncertainty handled honestly?
3. **Technical Execution** — Works reliably in a live demo? Databricks used well?
4. **Ambition** — Beyond the minimum workflow, meaningfully?
Hard requirements: cite facility text; communicate uncertainty transparently; **persist user actions**.

---

## Director debate — where they agreed, and the one disagreement

**Agreed (both directors, independently):**
- The **0-confidence Copilot table** is the single worst-looking element and attacks the
  criterion we should *win* (Evidence & Uncertainty). Highest-priority fix.
- A **browsable district list / left rail** (VFMatch's spine) is the highest *structural*
  gap — we have list+detail+map ingredients but never compose them; the ranking is buried
  in a collapsed expander.
- The **header is over-dense** (the same "evidence-weighted, uncertainty-visible" idea is
  restated ~3×), pushing the payload below the fold.
- **Facility detail** reads like a debug dataframe, not a clean card.
- Need **hover / nested disclosure** (Tableau-style) instead of flat captions + raw tooltips.

**Disagreement — "Jump to worst district":** Product director observed it *working* in a
Playwright run (map appeared to recenter); UX director **root-caused it broken** in code.
**Resolution (verified in data):** the #1 district *Uttar Dinajpur, West Bengal* has
`district_latitude/longitude = NaN`, and **73/706 districts have null centroids**. The
recenter guard fails → `map_focus_view` never sets → the map does not move. The
after-click screenshot is pixel-identical. **UX is correct; it is broken for any
NaN-centroid district.** Fix = centroid fallback, not a no-op.

**Added by Product (narrative, not just UX):** persistence is durable (SQLite locally /
Delta in warehouse) but **invisible** to judges — surface a "My Plan" view + badge; and
stage one explicit 3-minute spine (worst desert → decide → persist → reload-to-prove).

---

## Confirmed root causes (empirical)
- **0-confidence:** `copilot.py::_mode_verifiable_deserts` maps `Confidence =
  district_data_quality_score`; all top `real_desert_candidate` districts have score `0.0`
  because `zero_facility_desert=True` (no facilities → no supply evidence). The text above
  says "enough evidence to believe the gap is real" → self-contradiction.
- **Jump button:** worst district centroid is NaN (73/706 null) → `map_focus_view` unset.
- **Facility detail:** `ui.facility_card` body is a 5-row `st.dataframe` of mashed
  `signal / value / interpretation` tuples + truncated `source_url`.

---

## Complaint → fix → criterion

| # | User complaint | Fix | Criterion |
|---|----------------|-----|-----------|
| 1 | "Jump to worst district" broken | NaN-centroid fallback (hex-centroid mean) + visible recenter + "Now viewing" confirm; resolve focus after map on_select | Technical Execution |
| 2 | Too much header text | Collapse header to one line; drop redundant tagline/chip/orbit-note restatements; shorten map orientation | Product clarity |
| 3 | Want hover → nested detail | Rich map tooltip (nested card) + hover tooltips on KPIs/rows; wordy captions behind hover/expander | Product polish |
| 4 | Missing browsable place list | Left **district rail**: search + ranked list driving map + detail | Product judgment |
| 5 | Messy-JSON facility detail | Rebuild `facility_card` as clean labeled key-value card; cited source; raw signals behind "Why this badge?" | Evidence presentation |
| 6 | Copilot "0 confidence" | Reframe to two honest signals: **"Gap is real"** confidence (high for zero-facility) vs **supply evidence** tier; never show bare 0.00 — zero-facility rows show an honest "No facilities — verify on ground" chip | Evidence & Uncertainty |
| 7 | Ugly elements | #6 + #3 (remove the worst offenders) | Cross-cutting |
| 8 | Too much scrolling | #4 rail composition + segmented sub-views instead of stacked expanders → one viewport | Product clarity |
| 9 | Visual cleanup / minimalism | All of the above + stronger hierarchy (action pills, badges) | Product judgment |

---

## Prioritized enhancement plan (for parallel execution)

**P0 — fix the "looks broken" moments (first 30 seconds of the demo)**
- **E1. Reframe the 0-confidence table** → two-signal honest uncertainty. *(Evidence & Uncertainty — highest leverage; both directors' #1.)* — `copilot.py`
- **E2. Fix Jump-to-worst** → NaN-centroid fallback + visible recenter + "Now viewing" confirmation + resolve focus after on_select. *(Technical Execution.)* — `tab_map.py`

**P1 — structural UX (the VFMatch composition)**
- **E3. Left district rail** → searchable, ranked list driving the same selection state as map clicks (promotes the buried ranking). *(Product judgment; fixes complaints 4 & 8.)* — `tab_map.py`
- **E4. Collapse the header** to one line; drop the redundant restatements; shorten the map orientation paragraph. *(Clarity; 2, 7, 8.)* — `ui.py` (`header`) + `app.py` (nav/orbit captions)
- **E5. Clean facility detail card** → labeled key-value rows, prominent cited claim + clean source link, raw signals behind an expander. *(Evidence presentation; 5.)* — `ui.py` (`facility_card`)

**P2 — depth & polish**
- **E6. Hover / nested disclosure** → rich map tooltip card; hover tooltips on KPI cards & leaderboard rows; wordy quadrant-explainer caption behind hover/expander. *(Polish; 3, 7.)* — `tab_map.py` (tooltip), `copilot.py` (caption), `ui.py` (tooltip CSS utility)
- **E7. Reduce scroll via segmented sub-views** → Coverage / Full ranking / How-to-read as a segmented sub-nav rather than three stacked expanders. *(Clarity; 8.)* — `tab_gaps.py`, `tab_map.py`
- **E8. Visible "My Plan" persistence surface** → shortlist + notes + "Persisted ✓" badge, reload-to-prove. *(Hard requirement + Product judgment.)* — `tab_gaps.py` + `decisions.py`

**Single highest-leverage change (both directors):** E1 (kill the 0.00 contradiction →
flagship honest-uncertainty story) + E3 (the district rail that makes the app *read* like
VFMatch). E2 removes the on-stage failure the user already hit.

---

## Execution assignment (conflict-free, disjoint files)
- **Agent A — Map experience** (`tab_map.py`): E2, E3, E6 (tooltip), header-orientation trim.
- **Agent B — Evidence / Copilot** (`copilot.py`, `interventions.py`, `simulator.py`): E1, E6 (caption).
- **Agent C — Chrome + facility card** (`ui.py`, `app.py`): E4, E5, E6 (hover CSS utility).
- **Agent D — Gaps + My Plan** (`tab_gaps.py`, `decisions.py`): E7, E8.

---

## Results (executed 2026-06-16, 4 parallel agents on disjoint files)

All four execution agents completed; the app was restarted (the local watcher is
unreliable — Watchdog not installed) and verified: full import OK, HTTP 200, no startup
errors, and Playwright screenshots confirm each change.

### Agent A — Map experience (`app/lib/tab_map.py`)
- **E2 — Jump/Select fixed (verified).** New `_district_centroid` fallback chain: own
  centroid → mean of the district's hex centroids (`data.district_hexes`) → mean of its
  facilities → **state-level** centroid → India centroid. Uttar Dinajpur (NaN centroid,
  zero facilities) now resolves to the West Bengal centroid and the map **visibly
  recenters** (zoom 6.2) — confirmed in `v2_jump_worst.png`. `map_focus_view` is consumed
  only when applied to the ViewState, so a stray map `on_select` rerun can no longer
  swallow a pending jump. A "◎ Now viewing <district>, <state>" chip confirms the state.
- **E3 — Left district rail.** Replaced the orientation card with a frosted rail: 2 compact
  KPIs + search box + height-bounded (`container(height=360)`, top-60) ranked list. Each
  row: district+state, tone-coded action pill, care-gap mini-bar + score, "0 facilities"
  chip. Selecting a row drives both map recenter and detail (same state as a map click).
  `st.columns([1, 2.3])` keeps the map dominant. Fixes complaints 4 & 8.
- **E6 (tooltip)** — pydeck tooltip upgraded to a rounded nested card with action /
  trust-supply % / uncertainty tier (only when present, never fabricated).
- Orientation paragraph trimmed to one line; the rest behind a hover tooltip.

### Agent B — Evidence / Copilot (`app/lib/copilot.py`)
- **E1 — Two-signal honest reframe (verified, highest leverage).** Replaced the
  self-contradictory `Confidence = district_data_quality_score` (always 0.00 for deserts)
  with **"Gap is real"** (tier from `planning_category` + `health_need_score` +
  `households_surveyed` → High for well-surveyed zero-facility deserts) and **"Supply
  evidence"** (zero-facility rows → honest "None — no facilities on record" chip; few-facility
  → "Thin — N records, X% trustworthy"), plus a "Next step" column. Never renders a bare
  0.00. Confirmed true to data. `v2_copilot_deserts.png` shows the fix.
- **E6 (caption)** — quadrant methodology caption moved behind `ui.detail("How to read this
  quadrant")`.
- Scanned `interventions.py`/`simulator.py`: their Confidence columns are already honest
  tiers (no raw 0.00) — left unchanged.

### Agent C — Chrome + facility card (`app/lib/ui.py`, `app/app.py`)
- **E5 — `facility_card` rebuilt** as a clean decision card: labeled one-fact-per-line stats
  (capacity/doctors with intervals + confidence, trust, geo quality), the cited claim in a
  quote block, a clean "Source: <domain>" link (`_source_domain` parses host, never dumps a
  raw URL), and the raw signal table demoted behind "Why this badge?". Fixes complaint 5.
- **E4 — Header collapsed.** Dropped the redundant chip in `ui.header`, and removed the
  orbit-note bubble + nav-caption in `app.py` (the segmented control already labels tabs).
  Reclaims the fold. Fixes complaints 2, 7, 8. Confirmed in `v2_map.png`.
- **E6 — `.mdn-tip` hover utility** added (pure-CSS frosted tooltip via `data-tip="..."`),
  for Tableau-style hover depth.

### Agent D — Gaps + persistence visibility (`app/lib/tab_gaps.py`, `app/lib/decisions.py`)
- **E7 — Segmented sub-nav** replaces three stacked expanders: Ranking (default) · At a
  glance · Method & caveats · My Plan — one click, not three scrolls. Calm first glance
  (wow-stat + 2 KPIs + top-6 + drill-down) preserved above it.
- **E8 — Visible "My Plan"** (`decisions.render_my_plan()`): shortlisted districts + saved
  notes + a tone-coded **"✓ Persisted to Delta/SQLite"** badge from `persistence_status()`,
  with a "saved actions survive reload" hint. An "Add to My Plan" affordance on the
  drill-down (Shortlist pill + Save note) makes the hard-requirement persistence visible and
  demoable. Wow-stat computation unchanged.

### Verification artifacts
`output/screenshots/`: `v2_map.png` (rail + collapsed header), `v2_jump_worst.png` (map
recenters — E2 fixed), `v2_copilot_deserts.png` (two-signal table — E1 fixed),
`v2_gaps.png` / `v2_gaps_myplan.png` (sub-nav + My Plan). Full import OK; HTTP 200; no
startup errors.

### Status vs. complaints
1 ✅ jump fixed · 2 ✅ header collapsed · 3 ✅ hover tooltip + nested disclosure · 4 ✅
district rail · 5 ✅ clean facility card · 6 ✅ two-signal (no 0.00) · 7 ✅ ugly elements
removed · 8 ✅ rail + sub-nav reduce scroll · 9 ✅ overall minimalism + hierarchy.

### Deferred (recommended, not yet executed)
- Backfill district `lat/lon` in the data pipeline (73/706 null) as the *durable* jump fix
  (app-side fallback handles it now).
- Stage one explicit scripted 3-minute demo spine end-to-end (worst desert → deploy → save
  → reload-to-prove) as a guided mode.
