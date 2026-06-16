# CareGap — Enhancements Round 3

**Date:** 2026-06-16
**Track:** Medical Desert Planner
**Primary goal:** reduce bottom-section noise in Top Care Gaps and Copilot, make the product usable for a non-technical planner deciding where to deploy doctors, and add clear facility/provider claim context without overstating verification.

## Source Criteria

**Devpost / hackathon brief**
- Public Devpost brief: https://dais-for-good-2026.devpost.com/
- Local PDF brief used during analysis: `Databricks Apps & Agents for Good Hackathon.pdf`
- User and workflow requirement: help a non-technical healthcare planner, NGO coordinator, or analyst turn messy facility records into trustworthy decisions.
- Core requirements: clear non-technical workflow, cited facility text for important claims/recommendations/scores/rankings, honest uncertainty, and persisted actions.
- Medical Desert Planner prompt: identify highest-risk care gaps and confidence that those gaps are real.
- Judging criteria: Product judgment, Evidence and Uncertainty, Technical Execution, Ambition.

**VFMatch reference**
- Reference URL: https://vfmatch.org/explore
- Comparison screenshots: `output/playwright/enh3_vfmatch.png` plus director-agent captures in `output/playwright/`.
- Useful pattern to borrow: image/card-first browsing, simple CTAs, progressive disclosure, and scannable detail cards.
- Pattern not to copy: VFMatch is a volunteer marketplace. CareGap needs a planner deployment workflow and evidence/uncertainty trust layer.

## Director Debate

**Director of UX Design**
- VFMatch gives a clear start and uses card browsing: image, type badge, organization, short description, location/demand chips, then richer detail.
- CareGap was too analyst-facing: controls, tables, charts, and score math appeared before the deployment decision.
- Top UX risks: unclear workflow, weak citation display, insufficient visible claim verification, and too much detail in default views.
- Recommended first view: choose service -> pick district -> verify facility/service claims -> decide deployment -> save plan.
- Caution: use real facility images only if sourced. Otherwise use map thumbnails, type icons, or neutral placeholders.

**Director of Product**
- Medium-high judging risk if demoed as-is: ambition is strong, but judges may see analytics complexity instead of a planner workflow.
- Biggest product risk: `nan` evidence/citation output undermines the Evidence and Uncertainty criterion.
- Top Care Gaps should become the demo home: one recommendation, top reasons, provider claims, save action.
- Technical depth should remain, but behind "why we trust this" drawers, not in the default planner path.
- Demo narrative should start with a specific district, explain why doctors should deploy there, verify provider claims, choose clinical focus, and persist the plan.

**Resolved Direction**
- Keep analytical depth available, but make the default UI decisional.
- Use checkmarks for `Passed checks`, not `Verified`, because these are automated checks rather than human/authoritative verification.
- Do not fake facility photos. Add visual facility tiles with initials and explicit copy that the dataset has claim text and source URLs, not real photos.

## Prioritized Enhancements

**P0 — judging-critical**
- Remove visible `nan` evidence/citation output and replace missing evidence with an honest absence statement.
- Make Top Care Gaps a guided doctor-deployment shortlist, not a dense leaderboard.
- Collapse full tables, charts, score formulas, and methodology behind opt-in detail expanders.
- Add provider cards with visual identity, location, source domain, service chips, claim excerpt, and `✓ Passed checks` / `Needs verification` badges.
- Make Copilot a guided action hub instead of a bottom-heavy chat/free-text surface.

**P1 — planner clarity**
- Add a visible four-step planner path: Pick service, Choose district, Check claims, Save plan.
- Add plain-English condition cards that explain what medical-condition gaps mean for doctor deployment.
- Add explicit checkmark explanation: passed automated checks means source text/URL evidence and no human-review, contradiction, or invalid-geography flag.
- Keep optional charts and raw data available, but only after planner intent.

**P2 — polish / next pass**
- Add nested service filters beyond the existing service lens: maternal, NCD/chronic, emergency/surgery, diagnostics, preventive screening.
- Add richer image-like tiles from real source thumbnails only if legally/source-available; otherwise keep honest placeholders.
- Clean demo seed data in My Plan before judging, but do not delete persisted user actions without approval.
- Consider a single "Demo path" CTA: top district -> provider claims -> condition focus -> save plan.

## Implemented Changes

**Top Care Gaps**
- Changed the tab from `Care-gap leaderboard` to `Doctor deployment shortlist`.
- Added a four-card guide: Pick a service, Choose a district, Check claims, Save the plan.
- Reworded the top stat to planner language: the worst districts have no verified supply and should form the doctor-deployment shortlist.
- Replaced the default `ui.region_detail` chart-heavy drilldown with a compact planner brief.
- Added plain-English condition cards for the selected district, e.g. institutional births, anaemia, and health insurance coverage with deployment implications.
- Added provider evidence cards using facility records:
  - visual placeholder tile/initials;
  - facility name, type, city/state;
  - `✓ Passed checks` or `Needs verification`;
  - service chips for Maternity, Emergency, Diagnostics, NCD;
  - short claim description extracted from `claim_text`;
  - source domain link.
- Added an explicit explainer that checkmarks mean automated source/evidence/geography checks, not human verification.
- Moved full ranking, condition chart, method/caveats, and My Plan into collapsed detail sections.
- Updated stale My Plan wording from "sub-view" to "section."

**Copilot**
- Reframed Copilot as `Guided actions for deciding where to deploy doctors`.
- Added guided Start / Select / Verify / Save steps.
- Renamed chips to planner actions: Find deployment districts, Choose doctor specialty, Build deployment plan, Test clinic scenario, Explain evidence.
- Moved the desert quadrant chart behind `Open chart and full evidence view`.
- Reduced the deployment table from eight rows to five for a calmer default answer.
- Replaced default condition chart with plain-English condition cards and moved the chart behind `Open condition chart`.
- Moved free-text routing into a collapsed optional section instead of a persistent bottom chat input.

**Evidence / shared UI**
- Added reusable CSS primitives for guide steps, provider cards, and condition cards.
- Suppressed `nan`, `none`, and `null` display strings in facility evidence and district evidence sections.
- Fixed the Map district detail citation so zero-facility districts say they are grounded in NFHS-5 district indicators and absence of mapped facility records rather than rendering fake facility text.

## Verification

**Commands**
- `.venv/bin/python -m py_compile app/app.py app/lib/tab_gaps.py app/lib/copilot.py app/lib/ui.py`
- Local app HTTP check: `curl -I --max-time 5 http://127.0.0.1:8501` returned `HTTP/1.1 200 OK`.
- Data smoke test loaded `10077` facilities and `706` districts.

**Playwright screenshots**
- `output/playwright/enh3_vfmatch.png`
- `output/playwright/enh3_top_care_gaps.png`
- `output/playwright/enh3_copilot_deployment.png`
- `output/playwright/enh3_copilot_conditions.png`

**Observed live UI after changes**
- Top Care Gaps now opens with the four-step guide, a short deployment queue, selected-district planner brief, condition explanation cards, provider claim cards, and collapsed detail sections.
- Copilot now opens as a guided action hub. Its condition mode shows condition cards before charts, and the optional question box is collapsed.
- No Python compile errors.

## Remaining Risks

- Provider cards use visual initials, not real facility photos, because the dataset does not expose real image URLs. This is intentional and documented in the UI.
- `✓ Passed checks` is automated evidence verification, not human verification. The language was adjusted to avoid overclaiming.
- Existing persisted My Plan data may include prior QA/test entries. I did not delete or hide persisted user actions without explicit approval.
- Some deeper Copilot modes (`Build deployment plan`, `Explain evidence`) may still expose technical language. They are now secondary, but a future pass should simplify those internals too.

## CPO Audit — Latest Map District Detail Feedback

As CPO at VFMatch, the Map district detail panel still had gaps for a planner deciding where to deploy doctors: trust was too score-forward, uncertainty was not explained at the moment of decision, local facility evidence was not clearly separated from district-level indicators, dense charts competed with the deployment task, and image-like placeholders risked implying real photos.

These matter because a planner must quickly answer: "Can I trust this district signal, what local facility claims exist, and what doctor deployment action should follow?" Overstated precision, unclear evidence provenance, or fake visual cues can create false confidence in high-stakes placement decisions.

Intended fixes now being implemented:
- Show trust as `Low`, `Medium`, or `High` by default, with the numeric score visible on hover only.
- Add a Bayesian/Wilson hover banner so uncertainty is explained without crowding the main panel.
- Show facility claim cards when local records exist, or an explicit no-local-records state when they do not.
- Move heavy charts behind expanders so the default view stays planner-first.
- Use no fake photos; only honest facility initials/placeholders unless real source images exist.

## CPO Audit Fixes Implemented — Map District Detail

- Rebuilt the Map district detail panel in `app/lib/ui.py` as a planner-first brief: recommendation, three concise decision cards, top condition driver, facility evidence, and action buttons.
- Replaced the blank `Trustworthy supply` metric with categorical trust: `Low trust`, `Medium trust`, or `High trust`.
- Kept the numeric trust score hidden until hover over the trust label/info icon. The hover banner explains the Bayesian validity posterior plus Wilson confidence interval logic and explicitly handles `0/0` observed-facility denominators.
- Added local facility evidence cards when records exist, including facility initials, service chips, `✓ Passed checks`, concise claim text, and source links.
- Added an explicit no-local-records card for zero-facility districts so the UI does not imply fake providers or fake photos.
- Moved condition charts, score formula, recommendation breakdown, and raw evidence into collapsed `More detail` sections.
- Removed the visible sqlite persistence note from the planner decision surface.
- Wired `app/lib/tab_map.py` to pass the facility dataframe into `ui.region_detail(...)`, with a compatibility fallback for older signatures.
- Kept Top Care Gaps provider-card polish from the parallel worker: `No real photo` disclosure, source links, concise claim/evidence line, and checkmark only for automated passed checks.

**Additional verification**
- `.venv/bin/python -m py_compile app/app.py app/lib/ui.py app/lib/tab_map.py app/lib/tab_gaps.py app/lib/copilot.py`
- `git diff --check -- app/lib/ui.py app/lib/tab_map.py app/lib/tab_gaps.py enhancements_3.md`
- `curl http://127.0.0.1:8501` returned `200`.
- Playwright verified zero-facility district state: `Low trust`, no blank metric, no-local-records card, charts collapsed.
- Playwright verified hover state: trust score and Bayesian/Wilson explanation appear on hover and disappear after moving away.
- Playwright verified facility-backed district state using Gurgaon: provider cards show descriptions, service chips, `✓ Passed checks`, source links, and `No real photo`.

**New screenshots**
- `output/playwright/map_detail_clean.png`
- `output/playwright/map_trust_hover.png`
- `output/playwright/map_facility_cards.png`

## CPO + Google Engineering Audit — Final Feedback Pass

**Gaps identified**
- The district detail still sounded too data-internal. `No local facility records` left planners asking what it meant, and the old zero trust score implied false precision when the real signal was "gap confidence is high, local supply evidence is absent."
- Provider examples in Top Care Gaps looked static because districts without mapped provider claims fell back directly to state examples. That could mislead judges into thinking examples were local district evidence.
- Photo language still implied broken/missing images. The right product behavior is not to fake photos and not to show "no real photo"; use source/initial cards until a matched place listing is available.
- Cloud/GitHub deploy readiness had hygiene gaps: public markdown had a local path, Cloud Run upload context included too many local output artifacts, and Databricks deploy must not auto-select a profile.

**Reasoning**
- The hackathon brief rewards clear decision support, evidence, and uncertainty. A planner should see `where to deploy`, `why`, `what to call/verify`, and `what evidence exists`; they should not infer meaning from empty denominators or data-engineering terms.
- Google Places photos require a separate, policy-aware enrichment flow. Official Google docs require field masks for Text Search/Place Details and separate Place Photos calls, and API keys should be restricted. Photos therefore cannot be safely pulled inside every Streamlit render.
- VFMatch-style cards are useful, but CareGap must preserve evidence integrity. Reference examples should be visibly secondary when no district-mapped provider claims exist.

**Fixes implemented**
- Replaced the zero-style trust metric with `Gap confidence` and `Supply evidence`. Zero-provider districts now show `No mapped claims` with a short call-first next step, not `Trust score: 0.00`.
- Shortened the Map no-supply card to one sentence plus action: no source-backed provider claim is mapped yet; use this as a supply-gap signal and call nearby providers before staffing.
- Hid state/national provider examples behind `Show state reference examples` when a district has no mapped provider claims, so dynamic fallback examples no longer look like local evidence.
- Replaced `Photo pending` / no-photo language with initials/source-card tiles. Real images are only shown if pre-enriched photo metadata is available.
- Added `app/lib/photo_enrichment.py` as a feature-flagged metadata reader and `scripts/run_google_places_photo_enrichment.py` as a dry-run-first Google Places batch enrichment job. It writes sanitized Place ID/photo-availability metadata, not API keys, photo names, photo URLs, or image bytes.
- Tightened `.gitignore`, `.dockerignore`, and `.gcloudignore` for Google Places outputs, raw/debug files, notebooks, local caches, `.DS_Store`, and oversized output artifacts.
- Changed Databricks `app/app.yaml` to use `${DATABRICKS_APP_PORT:-8000}`.

**Deployment readiness**
- GitHub: safe path is feature branch + PR, not direct push to public default branch. A local absolute path in this file was removed. Regex/manual secret scans found no high-confidence API key/token/private-key hits, but full secret scanners were not installed.
- Databricks: CLI/auth are available and profile `7474647301321645` is valid, but deployment is blocked until a profile is explicitly approved. The next safe command is `databricks apps validate -t dev --profile 7474647301321645`.
- Google Cloud: existing Cloud Run service is `caregap-app` in project `project-flash-490419`, region `us-central1`. Upload context is now reduced to app code plus the minimal public aggregate data subset. Actual redeploy should wait until unrelated plaintext Cloud Run env secrets in the project are rotated/moved to Secret Manager.

**Final verification**
- `.venv/bin/python -m py_compile app/app.py app/lib/ui.py app/lib/tab_map.py app/lib/tab_gaps.py app/lib/copilot.py app/lib/interventions.py app/lib/simulator.py app/lib/photo_enrichment.py scripts/run_google_places_photo_enrichment.py`
- `git diff --check` across modified app, deploy, script, and markdown files.
- `scripts/run_google_places_photo_enrichment.py --limit 3` dry-run completed without API calls.
- `curl http://127.0.0.1:8501` returned `200`.
- `gcloud meta list-files-for-upload` now shows app code plus selected aggregate artifacts only.
- Playwright screenshots:
  - `output/playwright/map_final_gap_confidence.png`
  - `output/playwright/top_care_gaps_final.png`
  - `output/playwright/copilot_final.png`
- Playwright rendered-text scan across Map, Top Care Gaps, and Copilot found no occurrences of the banned phrases: no `No local facility records`, no `Photo pending`, no `No real photo`, no `dataset`, no `field-check`, and no `Trust score:`.

**Residual risks**
- Real facility photos are not active by default. They require an explicit Google Places enrichment run and a policy-safe serving path with attribution and restricted API keys.
- A transient Streamlit/Vega console error appeared during rapid Playwright tab switching (`Unrecognized data set`), but the app remained responsive. Re-test after any chart changes.
- Cloud Run redeploy remains blocked on external project secret hygiene, not app code.
