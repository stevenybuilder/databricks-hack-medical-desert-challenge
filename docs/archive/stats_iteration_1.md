# Stats Iteration 1 — Enhancements Summary

_Date: 2026-06-15 · Scope: implement `docs/archive/Bayesian_stats_product_strategy.md` + `docs/archive/tricky_fields.md` against the existing Medical Desert Navigator app._

## 1. How this was approached

The project was **already mature** before this iteration. A lead-DS audit (Google Maps lens — geospatial validity, statistical rigor, no fabricated signals) confirmed the following were **already built** and were left intact:

- Medical Desert Risk Map (H3 hexbins, click-to-fly, cited facility detail)
- Top Care Gaps leaderboard with `planning_category` routing (Deploy/Verify/Fix/Refer/Monitor)
- Data-confidence layer: `data_readiness_score`, `semantic_data_quality_score`, trust signals
- Wilson + Jeffreys-Beta confidence intervals on district/facility rates
- Hierarchical capacity / doctor-count estimates with p10–p90 intervals
- Geo-validation pipeline (LLM janitor → geocoder → India fallback → H3 → uncertainty queue)
- Active-learning queues (value-of-information ranking) and a rule-baseline model that abstains without gold labels

### Gaps identified (vision vs. build)

| # | Gap | Source doc | Status before |
|---|---|---|---|
| 1 | **Intervention Recommender** ("Next Best Health Access Intervention") | Bayesian §3 Feature 2 | ❌ only coarse planning_category |
| 2 | **What-If Scenario Simulator** + best/most-likely/worst-case bands | Bayesian Feature 4; tricky idea 4 | ❌ missing |
| 3 | **Bayesian record-validity posterior + conformal sets + trust decomposition** | Bayesian Concepts 1 & 3; tricky idea 1 | ❌ marked "not yet" |
| 4 | **Decision persistence + conflict resolution + human-feedback loop** | tricky Core Req + idea 3; Bayesian §7 | ❌ missing (core hackathon requirement) |

### Lead-DS guardrail enforced across all work

The strategy doc references **broadband, elderly-share, and real travel-time** signals that **do not exist** in this dataset. No agent was allowed to fabricate them. Where the doc named a missing signal, the nearest *real* NFHS/FDR proxy was substituted and **explicitly labeled as a proxy**, and telehealth is pinned to **low confidence** everywhere with the note "broadband not in dataset."

## 2. Execution model

Four enhancements were built **in parallel by four isolated agents**, each owning only new files (zero shared-file conflicts). Integration into `app/app.py` was done in a single careful pass afterward. Every module exposes a self-contained `render_*(facilities, districts, specialty)` Streamlit function plus pure, testable compute functions.

## 3. What shipped

### Enhancement 1 — Intervention Recommender
- **Files:** `app/lib/interventions.py`, `scripts/build_intervention_recommendations.py`
- **Artifacts:** `output/data/intervention_recommendations.csv` (3,458 rows = 491 districts × 7 candidates), `intervention_recommendations_summary.json`
- Transparent **expected-value engine**: `EV = P(addresses_need)·benefit − P(wrong)·harm·0.6 − cost·0.6`. `benefit` scales with `health_need_score` × need-gap; `P(wrong)` scales with `district_uncertainty_level`, small samples, review rate, and wide supply CIs.
- Catalog mapped only to **real columns**: mobile primary care, capacity expansion, CHW outreach, pharmacy NCD screening, maternal/prenatal referral (proxy-labeled), insurance enrollment (PM-JAY style, via `hh_member_covered_health_insurance_pct`), telehealth (low-confidence default).
- Per-district output mirrors the doc's "Recommended / Reason / Confidence" format with firing trigger signals and cited `sample_source_urls`. **Telehealth never ranks #1** (flagged not-recommended in 414/494 districts).
- **App view:** "Interventions".

### Enhancement 2 — What-If Scenario Simulator
- **File:** `app/lib/simulator.py`
- `scenario_bands(...)` → **best / most-likely / worst-case** supply bands (facility count + capacity interval), derived from observed-vs-estimated counts, `trustworthy_supply_rate` + its Wilson CI, and per-facility capacity intervals.
- `simulate_interventions(...)` → live what-if levers (add N mobile clinics, +X% capacity, telehealth adoption) compared on Access improvement / Cost / Confidence / Rank, exactly matching the doc's example table. Reproduces the **demo moment**: telehealth-first ranks last (#5) vs. mobile clinic (#1) in low-evidence deserts.
- **App view:** "Scenario lab".

### Enhancement 3 — Bayesian posterior + conformal calibration + trust decomposition
- **Files:** `app/lib/trust.py`, `scripts/build_conformal_calibration.py`
- **Artifacts:** `output/data/conformal_calibration.json` (α=0.1, q̂=0.080, empirical coverage 0.918 on proxy, n=2008, provisional=true), `conformal_facility_sets.csv` (10,077 rows)
- `facility_validity_posterior(...)` → **P(record valid | evidence)** via auditable log-odds update over a documented `EVIDENCE_WEIGHTS` dict (geo plausibility, join confidence, source URL, recency, semantic completeness as positive likelihoods; contradiction / geo-outside / extreme outliers as negative). Emits `validity_action` (auto-accept / merge-or-review / quarantine-or-verify / human-review) per the doc's Concept 1 table.
- `conformal_label_sets(...)` → split-conformal **prediction sets** (`{valid}`, `{valid, uncertain}`, `{valid, stale, uncertain}`) — the app knows when **not to overclaim** (Concept 3).
- `trust_decomposition(...)` → additive 8-dimension breakdown (components **sum** to the 0–100 score) like tricky-fields' "Uncertainty 65/100" example.
- **Honesty posture:** calibrated against the automated proxy pseudo-label `trustworthy_supply_signal`, **not** human-verified ground truth — labeled provisional in JSON, docstrings, and UI, consistent with `STATISTICAL_DECISION_FRAMEWORK.md`.
- **App view:** "Trust & conformal".

### Enhancement 4 — Persistence + conflict resolution + feedback loop
- **File:** `app/lib/decisions.py`
- **Storage:** SQLite at `output/data/planner_decisions.sqlite` (stdlib only) — tables `facility_decisions`, `shortlist`, `scenario_assumptions`. Graceful fallback to `st.session_state` on read-only filesystems.
- Four sub-sections: **Facility review & override** (note/override/verify/reject with reviewer + history), **Conflict resolution** (choose a planning assumption from the model's value range — low/median/high/custom, persisted), **Shortlist** (add/remove + CSV download), **Feedback / improvement center** (proposals *derived* from persisted decisions, rendered as "policy v1.x · awaiting approval" with Approve/Dismiss — **never auto-deployed**, matching Bayesian §7).
- **App view:** "Decisions & feedback".

## 4. Integration & verification

- `app/app.py` navigation extended from 3 → **7 views**; imports added for the 4 new modules.
- **Headless `AppTest` across all 7 views: ALL PASS** (no exceptions).
- Both build scripts are idempotent and were run to produce the artifacts above.
- Pure compute functions verified directly against the real CSVs (494 districts, 10,077 facilities).

## 5. Known follow-ups (handed to the visual iteration)

- A new module still emits the `use_container_width` Streamlit deprecation warning (non-fatal) → switch to `width="stretch"`.
- 7 top-level segments may need grouping/visual hierarchy → deferred to the UX/frontend pass (`visual_enhancements_1.md`).
- `.venv` (Py 3.9) is **missing `scikit-learn`/`scipy`** despite `requirements.txt` listing scikit-learn; conformal was implemented numpy-only to stay runnable. Install before relying on the supervised trainer.

## 6. Files changed

**New:** `app/lib/{interventions,simulator,trust,decisions}.py`, `scripts/{build_intervention_recommendations,build_conformal_calibration}.py`, `output/data/{intervention_recommendations.csv, intervention_recommendations_summary.json, conformal_calibration.json, conformal_facility_sets.csv}`
**Modified:** `app/app.py` (imports + 4 new views wired into navigation)
