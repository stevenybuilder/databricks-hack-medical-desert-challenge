# Build Plan — DAIS 2026 Virtue Foundation Hackathon

_Last updated: 2026-06-15_

See `PRODUCT_SPEC.md` for the product, `DATASET_REFERENCE.md` for data/connection,
and **`DATA_SOURCES_ANALYSIS.md` for the computed analysis + build implications**
(§9 there is a checklist the app must honor: outlier-cap `numberDoctors`/`capacity`,
log-scale heavy-tailed fields, geo-quality badges, show CIs/uncertainty, drive
recommendation chips from `planning_category`, cite `sample_source_urls`, treat NFHS
as district context, label gap scores as proxies).

## Key finding: the analytical backbone already exists

A teammate has already produced cleaned, district-grain analysis under
`output/data/` (see DATASET_REFERENCE.md). **We do not need to rebuild the
trust/need/gap model or the recommendation taxonomy — they exist.** The
remaining work is the **visual, doctor-facing Databricks App**.

Already done:
- Cleaned facility↔health join with uncertainty fields (`facility_health_cleaned.csv`)
- District-level table (494 rows) with need, trustworthy supply (+CIs), gap scores,
  `planning_category` (build/verify/refer taxonomy), uncertainty, service signals,
  evidence samples (`district_health_facility_cleaned.csv`)
- Pre-computed insight plots and `actual_insights_summary.json` (top care gaps, etc.)
- State/district crosswalk + pincode bridge (join traps like Maharastra→MAHARASHTRA handled)

## What's left to build

1. **Databricks App (Free Edition)** — the VF-Match-style front end.
2. **Predictive trust engine** for new facilities (the novel core).
3. **Persistence** of user actions (shortlists/notes) to a Delta table.

## Tech stack

- **App:** Streamlit (fastest path to non-technical UI + persistence on Free Edition).
- **Map:** `pydeck` (deck.gl) **H3HexagonLayer** — the same primitive VF Match uses. `h3` python lib for binning.
- **Right panel (Insight Layers):** `st.selectbox` (specialty) + toggles + histogram range sliders, mirroring VF Match.
- **Data access:** read cleaned tables from Unity Catalog / Delta via the default warehouse; precompute a gold Delta table for the app.
- **LLM:** Databricks Foundation Model API (claim verification + optional "Ask AI").
- **Persistence:** Delta table for shortlists/notes/overrides.

## Build order (fast-fallback first — always demoable)

1. **Skeleton map (today):** load `district_health_facility_cleaned.csv` → H3 hexbin map colored by `care_gap_score`, specialty dropdown, render in Streamlit. Get *something* on screen.
2. **Leaderboard + region detail:** "Top Care Gaps for <specialty>" list; region panel with patient-condition profile (NFHS columns), facilities, cited evidence, `planning_category` chip, uncertainty band.
3. **Persistence:** shortlist + notes to Delta.
4. **Predictive engine:** train on per-facility trust labels in `facility_health_cleaned.csv`; calibrate; holdout reliability curve; "score a new facility" view.
5. **Polish + demo:** the ocean-hospital + cancer-screening hooks; freeze.

## Predictive trust engine (the novel core)

- **Goal:** when a *new* facility is crawled, predict per-claim/facility trust with calibrated confidence + citations — automating the manual human review (host's stated "novel" ask).
- **Labels:** reuse existing per-facility signals as (weak) labels — `data_readiness_score`, `join_confidence`, `needs_human_review`, `plausible_geo`, `trustworthy_supply` flags. Small hand-labeled gold set for calibration/validation.
- **Features (available at crawl time):** provenance (source count/types/authority, official website/phone), digital footprint (social presence, logo, staff, engagement, recency), internal consistency (facility type vs capacity/#doctors/#specialties), geo-validity, claim specificity / text features.
- **Output:** calibrated probability + credible interval; 3-state verdict (verified / unverified / contradicted).
- **Calibration (intuit move):** isotonic/Platt on the gold set; show a reliability curve.
- **Demo proof:** hold out a slice of the 10k as "new/unseen", predict, validate against held-out labels.

## Data gaps / risks (be honest — intuit discipline)

- **Population normalization:** NFHS `households_surveyed` is a survey sample, not population. For per-capita / "population underserved" either ingest **WorldPop India** (open raster) or use density framing qualitatively. Default: proxy first, WorldPop upgrade if time.
- **Travel-time accessibility:** VF Match uses real isochrones; approximate with haversine distance to nearest trustworthy facility for the hackathon.
- **District grain:** NFHS is district-level context, never a facility fact. Preserve `join_strategy`/`join_confidence`/`district_uncertainty_level` wherever rankings use it.
- **Selection bias (intuit):** never collapse "unverified" into "false". Keep the 3-state distinction everywhere.

## Intuit winning behaviors applied (from /Users/stevenyang/Documents/intuit-hackathon)

1. Be impossible to penalize across the whole surface (4 criteria + 6 core reqs as a checklist).
2. Calibration is the product, not a garnish (reliability curve on a gold set).
3. Separate evidence types (corroboration vs internal plausibility), don't smush opaquely.
4. Selection bias: unverified ≠ false (3-state verdict).
5. Validator-clean = runs as a Databricks App, cites sources, persists actions.
6. Demo/writeup as a model-risk defense; lead with the failure you catch (ocean hospital).
7. Always keep a fast fallback (heuristic map before the predictive engine).
8. Freeze rule: stop adding once it demos cleanly; polish the narrative.
