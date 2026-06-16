# UX QA Report — Medical Desert Navigator

**QA Engineer** · Date: 2026-06-15 · App: `app/app.py` (7 top-level views)
Streamlit 1.50.0 · Python 3.9 · headless `streamlit.testing.v1.AppTest`

> Scope: read-only QA. No code edited. Defects are filed below for the Frontend Engineer.
> Note: a Frontend Engineer was editing code in parallel during this run. The one
> failure below was **re-run 3x (incl. after a pause) and reproduced every time** — it
> is a real, stable defect, not a transient mid-edit artifact.

---

## 1. Functional regression — per-view AppTest results

Harness: `AppTest.from_file(app/app.py)`, set `session_state['primary_view']=view`,
`at.run(timeout=90)`, inspect `at.exception` / `at.error`. (App dir must be on
`sys.path` so `from lib import ...` resolves — this is how Streamlit runs it normally.)

| # | View | Status | dataframe | metric | markdown | Notes |
|---|------|--------|-----------|--------|----------|-------|
| 1 | Map | **FAIL** | 0 | 0 | 5 | Blocker — exception in `st.pydeck_chart` (see DEFECT-1). Header/markdown render, but the map element raises before content. |
| 2 | Top care gaps | **PASS** | 3 | 3 | 20 | Renders tables + metrics + region detail. |
| 3 | Interventions | **PASS** | 2 | 3 | 25 | New module renders content (dataframes + metrics). |
| 4 | Scenario lab | **PASS** | 2 | 0 | 11 | New module renders content (scenario band dataframes). No `st.metric` used (bands shown as tables) — acceptable. |
| 5 | Uncertainty console | **PASS** | 3 | 0 | 13 | Renders content. |
| 6 | Trust & conformal | **PASS** | 1 | 0 | 20 | New module renders content (validity table + markdown). |
| 7 | Decisions & feedback | **PASS** | 1 | 0 | 8 | New module renders content. |

**6 / 7 views PASS. 1 blocker (Map).**

### Interactive widget exercise
- The **specialty selectbox** (`label="Specialty lens"`, 5 options) is exercised
  directly via the library render functions across all 5 specialties in the
  data-integrity pass (Section 3) — no exceptions for any specialty.
- The **primary-view `st.segmented_control`** cannot be driven through AppTest 1.50
  (`AppTest` exposes no `segmented_control` accessor, and re-running after a separate
  widget interaction with `primary_view` preset via `session_state` makes the
  segmented_control proto raise `content "<X>" is not in list`). **This is a known
  AppTest tooling limitation, NOT an app defect** — single-run navigation to every
  view via `session_state['primary_view']` works (table above). Flagged so the
  orchestrator's final gate does not misread it as a regression.

---

## 2. New-module sanity (do the 4 new views render real content?)

All four new modules render non-empty content (confirmed via element counts above):

| New view | Evidence rendered |
|----------|-------------------|
| Interventions | 2 dataframes, 3 metrics, 25 markdown blocks |
| Scenario lab | 2 dataframes (best/most-likely/worst bands), 11 markdown blocks |
| Trust & conformal | 1 dataframe (validity posteriors), 20 markdown blocks |
| Decisions & feedback | 1 dataframe (decision/shortlist history), 8 markdown blocks |

**PASS** — no empty/blank new modules.

---

## 3. Data-integrity spot-checks (UX-trust relevant)

Run against the live data loaders (10,077 facilities, 494 districts).

| Check | Result | Detail |
|-------|--------|--------|
| Posteriors in [0,1] (`trust.facility_validity_posterior`) | **PASS** | min 0.054, max 0.992, **0 NaN**, all within [0,1]. |
| Intervention EV no NaN for valid districts | **PASS** | `interventions.compute_recommendations` → 3,458 rows, **0 NaN** in `ev_score`. |
| Scenario bands ordered best ≥ most-likely ≥ worst | **PASS** | `simulator.scenario_bands` checked on 30 districts → **0 ordering violations** (Est. capacity monotone). |
| Decisions persist + read back | **PASS** | `save_decision` → `list_decisions` round-trip OK; sqlite at `output/data/planner_decisions.sqlite` (not session-only). Shortlist add/remove also OK. QA test rows cleaned up afterward. |

All trust-relevant data integrity checks pass.

---

## 4. Accessibility / polish heuristics (static scan of `ui.py` inject_css)

| Heuristic | Finding |
|-----------|---------|
| Text contrast on dark bg | **PASS.** WCAG AA contrast vs panel `#0b1321`: text `#eef4ff` 16.8:1, muted `#97a8c2` 7.7:1, dim `#8295ad` 6.1:1, sky 11.5:1, teal 9.3:1, amber 11.3:1. All exceed AA (4.5:1); muted/dim comfortably exceed it. |
| Focus states | **PASS.** Explicit `:focus-visible` with `outline: 2px solid var(--mdn-sky); outline-offset: 2px` on interactive roles (slider etc.), plus `:focus-within` on selects. |
| Low-opacity text | **None.** The only `opacity: .7` is on a 3px decorative accent bar (`.mdn-card::before`), not text. |
| Fixed pixel heights (clip risk) | **Low risk.** Heights are `min-height` (56/104/40px) which grow with content; the one hard `height: 32px` is the header logo badge. No content-bearing container uses a hard max-height/overflow:hidden combo. |
| Small fonts | **Minor.** Smallest is `0.68rem` (~11px) on uppercase eyebrow/label text (`.mdn-pill`-class labels). Borderline-small but used only for labels, not body copy. |

No accessibility blockers. One minor polish note (11px label text).

---

## 5. Playwright / screenshots

- **Playwright MCP: NOT available.** `ToolSearch` for "playwright browser screenshot
  navigate" and "browser navigate screenshot snapshot playwright chrome" returned no
  matching tools. The app was therefore **not** launched on port 8702 for live capture.
- Relying on AppTest (above) + existing screenshots in `output/playwright/`:
  `earth-ui-map-refreshed.png`, `top-care-gaps-final.png`, `top-care-gaps-redesign.png`,
  `uncertainty-model-policy-final.png`, `uncertainty-overview-final.png`,
  `uncertainty-overview-redesign.png`, `uncertainty-triage-redesign.png`.
  (These predate the 4 new views; no captures exist for Interventions / Scenario lab /
  Trust & conformal / Decisions & feedback.)
- **Recommendation:** once DEFECT-1 is fixed, capture live screenshots of all 7 views
  (especially the 4 new ones) for the UX record.

---

## 6. Defects

### DEFECT-1 — Map view crashes: `st.pydeck_chart(width="stretch")` invalid in Streamlit 1.50
- **Severity: BLOCKER** (the primary/default landing view is unusable).
- **File / line:** `app/app.py:276`
- **Exception:** `TypeError: 'str' object cannot be interpreted as an integer`
  raised at `streamlit/elements/deck_gl_json_chart.py:473` (`pydeck_proto.width = width`).
- **Root cause:** Streamlit 1.50.0 `st.pydeck_chart` signature is
  `pydeck_chart(pydeck_obj, *, use_container_width=True, width: int|None=None, height: int|None=None, ...)`.
  `width` must be an **int** (or `None`); the code passes the string `"stretch"`.
  (`"stretch"` is valid for layout primitives like `st.columns`/`st.dataframe`, but
  NOT for `pydeck_chart` in this version.)
- **Current call:**
  ```python
  event = st.pydeck_chart(deck, width="stretch", height=680, key="map",
                          on_select="rerun", selection_mode="single-object")
  ```
- **Suggested fix:** drop `width="stretch"` and rely on the default
  `use_container_width=True` (which already stretches to the container):
  ```python
  event = st.pydeck_chart(deck, height=680, key="map",
                          on_select="rerun", selection_mode="single-object")
  ```
- **Repro:** `AppTest.from_file('app/app.py')`; `at.session_state['primary_view']='Map'`;
  `at.run()` → `at.exception` is non-empty. Reproduced on 3 consecutive runs (stable).

### Minor polish notes (non-blocking)
- 11px (`0.68rem`) uppercase label text in pill-style components — verify legibility
  at the intended display size.
- No live screenshots exist for the 4 new views (tooling gap, see Section 5).

---

## Summary

- **6 / 7 views PASS** functional regression; **Map is a BLOCKER** (`pydeck_chart`
  `width="stretch"` invalid in Streamlit 1.50 — one-line fix at `app/app.py:276`).
- **All 4 new modules render real content.**
- **All data-integrity checks PASS** (posteriors in [0,1] & 0 NaN; EV 0 NaN over 3,458 rows;
  scenario bands correctly ordered; decisions persist+readback to sqlite).
- **Accessibility: no blockers** — strong contrast (all AA+), explicit focus states; one
  minor 11px-label polish note.
- **Playwright MCP unavailable**; relied on AppTest + existing `output/playwright/` screenshots.
