# Build Plan — DAIS 2026 Virtue Foundation Hackathon

_Last updated: 2026-06-15_

See `PRODUCT_SPEC.md` for the product, `DATASET_REFERENCE.md` for data/connection,
and **`DATA_SOURCES_ANALYSIS.md` for the computed analysis + build implications**
(§10 there is a checklist the app must honor: outlier-cap `numberDoctors`/`capacity`,
log-scale heavy-tailed fields, geo-quality badges, show CIs/uncertainty, drive
recommendation chips from `planning_category`, cite `sample_source_urls`, treat NFHS
as district context, label gap scores as proxies). See
`STATISTICAL_VERIFICATION_STRATEGY.md` for the no-human-label active uncertainty
strategy.

## Key finding: the analytical backbone already exists

A teammate has already produced cleaned, district-grain analysis under
`output/data/` (see DATASET_REFERENCE.md). **We do not need to rebuild the
trust/need/gap model or the recommendation taxonomy — they exist.** The immediate
work is the **visual, doctor-facing Databricks App**; the next modeling extension
is a source-corroborated golden facility prediction layer.

Already done:
- Cleaned facility↔health join with uncertainty fields (`facility_health_cleaned.csv`)
- District-level table (494 rows) with need, trustworthy supply (+CIs), gap scores,
  `planning_category` (build/verify/refer taxonomy), uncertainty, service signals,
  evidence samples (`district_health_facility_cleaned.csv`)
- Pre-computed insight plots and `actual_insights_summary.json` (top care gaps, etc.)
- State/district crosswalk + pincode bridge (join traps like Maharastra→MAHARASHTRA handled)

## What's left to build

1. **Databricks App (Free Edition)** — the VF-Match-style front end.
2. **Proxy trust and uncertainty engine** for facility/district evidence.
3. **Persistence** of user actions (shortlists/notes) to a Delta table.
4. **Active uncertainty queue** so doctors see which facility/district evidence is
   fragile, estimated, contradictory, or worth source enrichment.
5. **Golden facility prediction engine** for newly selected map locations, trained
   only after source-corroborated facility labels exist.

## Tech stack

- **App:** Streamlit (fastest path to non-technical UI + persistence on Free Edition).
- **Map:** `pydeck` (deck.gl) **H3HexagonLayer** — the same primitive VF Match uses. `h3` python lib for binning.
- **Right panel (Insight Layers):** `st.selectbox` (specialty) + toggles + histogram range sliders, mirroring VF Match.
- **Data access:** read cleaned tables from Unity Catalog / Delta via the default warehouse; precompute Gold-layer Delta tables for the app.
- **LLM:** Databricks Foundation Model API (claim verification + optional "Ask AI").
- **Persistence:** Delta table for shortlists/notes/overrides.

## Build order (fast-fallback first — always demoable)

1. ✅ **Skeleton map** — H3 hexbin map (deck.gl `H3HexagonLayer`) over Carto basemap,
   specialty filter, map-layer selector (care-gap / need / supply / count), hex-size,
   honest KPI panel, gradient legend. Light VF-Match theme.
2. ✅ **Map facilities + Top Care Gaps + region detail** —
   - Map tab: clickable facility points colored by trust status, hover tooltips,
     **click-to-fly** recenter, facility detail card with cited `source_urls`/`claim_text`,
     basemap selector (Voyager / Positron / Dark Matter), reset view.
   - Top care gaps tab: specialty-aware leaderboard (need × low trustworthy supply),
     `planning_category` recommendation chips, row-click → region detail with
     patient-condition profile (NFHS), supply/uncertainty metrics, cited evidence.
3. ✅ **Active uncertainty workflow** — generated facility and district queues rank
   rows by clinical impact, semantic uncertainty, contradiction risk, decision
   leverage, sparse-segment coverage, and rate/estimate interval width.
   - Geo fix subflow: Databricks `ai_query` parses messy Indian addresses, Google
     Maps/Mappls validates coordinates, and only approximate/conflicting outcomes
     route to the uncertainty queue. The generated batch now includes external
     validation actions, source-agreement reason codes, and pre-geocode
     uncertainty bands. See `GEO_VALIDATION_CLI.md`.
4. ⬜ **Persistence** — shortlist + notes/overrides/review decisions to Delta tables
   in `workspace.default`.
5. ⬜ **Golden facility prediction engine** — build `golden_facility_training_set`
   by matching cleaned FDR rows against HFR, Overture/OSM/Healthsites, India Post,
   government directories, and cited facility sources. Train supervised models to
   predict facility type, service signals, trust posture, capacity/doctor bands,
   and review action for newly selected map locations. See
   `GOLDEN_FACILITY_PREDICTION_PHASE.md`.
6. ⬜ **Polish + deploy + demo** — deploy as Databricks App (`DATA_BACKEND=warehouse`),
   ocean-hospital + cancer-screening hooks, git repo, 3-min demo; freeze.

App structure: `app/app.py` (tabs: Map / Top care gaps / Uncertainty), `app/lib/config.py`
(paths, specialty maps, metrics, basemaps, colors), `app/lib/data.py` (load +
hexbin + facility points + districts + leaderboard + active uncertainty queues),
`app/lib/ui.py` (CSS, header, facility card, region detail, uncertainty detail,
legend). Theme in `.streamlit/config.toml`.

## Proxy trust and uncertainty engine (the novel core)

- **Goal:** when a *new* facility is crawled, score evidence quality, uncertainty,
  and decision fragility with citations. This does not claim verified truth.
- **Labels:** programmatic labels are weak/proxy labels, not gold. Existing signals
  (`data_readiness_score`, `join_confidence`, `needs_human_review`,
  `plausible_geo`, `trustworthy_supply_signal`, source/contact evidence) can rank
  and pre-score records, but they cannot prove accuracy.
- **Features (available at crawl time):** provenance (source count/types/authority, official website/phone), digital footprint (social presence, logo, staff, engagement, recency), internal consistency (facility type vs capacity/#doctors/#specialties), geo-validity, claim specificity / text features.
- **Output:** proxy trust/readiness score, confidence intervals or uncertainty bands,
  3-state evidence posture (`passed_checks` / `needs_review` / `contradicted_or_geo_invalid`),
  and active uncertainty rank.
- **Confidence intervals (Intuit move):** Wilson intervals for district rates,
  empirical p10-p90 prediction intervals for missing capacity/doctors, and clearly
  labeled heuristic uncertainty bands for proxy trust scores.
- **Active uncertainty queue:** rank facilities/districts by clinical impact,
  uncertainty, contradiction risk, decision leverage, sparse-segment coverage, and
  confidence-interval width.
- **Geo uncertainty reducer:** run the generated CLI batch in `GEO_VALIDATION_CLI.md`
  to create geo-validation candidates, parse Indian address strings with a Databricks
  foundation model, then validate against a real geocoder with `components=country:IN`.
  Google/Mappls/HFR/PM-JAY/OSM evidence narrows or widens proxy bands only when
  name, pincode, district/state, and provider metadata agree.
- **Fuzzy/DLT stance:** reuse the existing pincode/state/district normalization and
  fuzzy-match signals now; keep the generated Lakeflow SQL template for scheduled
  production refresh rather than provisioning DLT for the demo.
- **Missingness stance:** enrich identity/contact/service gaps from HFR, PM-JAY,
  India Post/data.gov, Overture, OSM/Healthsites, and source pages. Estimate only
  capacity/doctor counts with intervals; everything else remains unknown/review
  until corroborated.
- **Demo proof:** show a district recommendation, expose the interval/uncertainty
  behind it, then open the active uncertainty queue to show what evidence is driving
  the fragility.

## Golden facility prediction engine (Phase 5)

- **Goal:** when a user selects a new map location, predict likely facility
  attributes and the safest next action: recommend, verify first, enrich sources,
  or abstain.
- **Training labels:** use a source-tiered golden dataset, not weak proxy labels.
  Tier A is HFR/authoritative registry agreement where accessible. Tier B is
  open-data corroboration from Overture, OSM/Healthsites, government directories,
  and source URLs. Google/Mappls can reduce runtime uncertainty but should not be
  used as durable training labels without license review.
- **Model outputs:** facility type, service-signal probabilities, existence/trust
  posture, capacity and doctor-count bands, location/admin confidence, evidence
  tier, confidence, and abstain/review reason.
- **Databricks tables:** `golden_facility_source_matches`,
  `golden_facility_training_set`, `facility_prediction_features`,
  `facility_prediction_outputs`, and `trust_uncertainty_model_versions`.
- **Acceptance test:** the app can score a new map-selected point and show a
  prediction card with evidence tier, confidence, source links, and abstention
  when sources are sparse or conflicting.

## Data gaps / risks (be honest — intuit discipline)

- **Population normalization:** NFHS `households_surveyed` is a survey sample, not population. For per-capita / "population underserved" either ingest **WorldPop India** (open raster) or use density framing qualitatively. Default: proxy first, WorldPop upgrade if time.
- **Travel-time accessibility:** VF Match uses real isochrones; approximate with haversine distance to nearest trustworthy facility for the hackathon.
- **District grain:** NFHS is district-level context, never a facility fact. Preserve `join_strategy`/`join_confidence`/`district_uncertainty_level` wherever rankings use it.
- **Selection bias (intuit):** never collapse "unverified" into "false". Keep the 3-state distinction everywhere.
- **No human labels:** without verified labels, do not claim supervised accuracy,
  Brier score, ECE, or calibrated reliability. Use proxy confidence intervals,
  sensitivity analysis, and source-quality explanations instead.
- **External data is not magic truth:** geocoder and registry hits become
  source-agreement features with visible uncertainty bands; conflicts keep rows in
  the active queue.
- **Informative missingness:** missing capacity/doctors/equipment/recency is not random. Preserve semantic missingness flags as model features and show estimated fields as estimates with intervals.

## Intuit winning behaviors applied (from /Users/stevenyang/Documents/intuit-hackathon)

1. Be impossible to penalize across the whole surface (4 criteria + 6 core reqs as a checklist).
2. Confidence intervals are the product, not a garnish.
3. Separate evidence types (source corroboration vs internal plausibility vs estimates), don't smush opaquely.
4. Selection bias: unverified ≠ false (3-state verdict).
5. Validator-clean = runs as a Databricks App, cites sources, persists actions.
6. Demo/writeup as a model-risk defense; lead with the failure you catch (ocean hospital).
7. Always keep a fast fallback (heuristic map before the predictive engine).
8. Freeze rule: stop adding once it demos cleanly; polish the narrative.
