# Databricks Tool Integration 1 — CareGap on the Lakehouse

_Date: 2026-06-15 · Scope: implement `databricks_tools_architecture.md` — connect the local CareGap app to a governed Databricks stack (Unity Catalog medallion, Feature Engineering, MLflow, gold tables, DABs, Jobs, Databricks App)._

## 1. Connection & environment

- **CLI:** Databricks CLI v1.3.0, authenticated to workspace `https://dbc-54942fa9-145a.cloud.databricks.com` (profile `7474647301321645`, user `stevenybusiness@gmail.com`).
- **Edition reality:** Databricks **Free Edition** — serverless compute only (no classic clusters), single writable catalog `workspace`. All work was designed around these constraints.
- **Source data discovered:** `databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.{facilities, india_post_pincode_directory, nfhs_5_district_health_indicators}` (raw FDR), plus the prior pipeline's cleaned tables in `workspace.default.hackathon_*` and the UC volume `workspace.default.hackathon_cleaned`.

## 2. Gap analysis (architecture doc vs. what existed)

| Target layer (doc) | Before | Delivered |
|---|---|---|
| Medallion UC namespace | 8 flat `workspace.default.hackathon_*` tables | `workspace.caregap_{bronze,silver,features,gold,models}` schemas |
| Bronze Delta + ingestion metadata | — | 8 bronze tables (raw FDR + cleaned) with `source_name/url, ingested_at, pipeline_run_id, raw_record_hash` |
| Silver normalized/crosswalk | — | 4 silver tables (`providers_normalized`, `provider_locations`, `geography_health_need`, `source_quality_metrics`) keyed by `canonical_provider_id` / `geography_id` |
| Feature Engineering in UC | — | 3 feature tables (`provider_confidence_features`, `geography_access_risk_features`, `intervention_input_features`) |
| MLflow tracking + Models in UC | none | experiment `caregap_scoring_policies` (6 runs) + registered model `workspace.caregap_models.caregap_scoring_policy` |
| Gold decision tables | local CSVs only | 5 gold tables + 5 app-facing views |
| DABs (IaC) | none | full bundle: variables, serverless job, app, experiment |
| Jobs/Workflows | none | serverless `caregap_medallion` job (6 chained notebooks) |
| App reads governed data | reads cleaned `default` tables | warehouse backend → gold tables/views, with OAuth auth |
| Monitoring/feedback | none | 4 governed feedback tables + write-back path |

## 3. What was built (4 parallel agents + central orchestration)

### DABs bundle (IaC)
- `databricks.yml` (bundle `caregap`, `dev` target, variables for catalog/schemas/warehouse, `sync.exclude` to keep the bundle small), `resources/caregap_medallion.job.yml`, `resources/caregap_app.app.yml`, `resources/caregap_experiment.experiment.yml`, `docs/databricks/UC_GOVERNANCE.md`.
- Job uses **serverless** notebook tasks (no classic clusters) with `environments:` blocks for pip deps (`databricks-feature-engineering`, `mapie`); weekly schedule shipped **PAUSED** (manual for hackathon).

### Medallion + feature notebooks (`databricks/notebooks/`)
- `01_ingest_bronze.py` → `02_clean_silver.py` → `03_build_features.py` → `04_track_scoring_policies.py` → `05_generate_gold_outputs.py` → `06_app_backend_queries.py`. Serverless/Spark-Connect-safe; idempotent (`CREATE OR REPLACE`).

### MLflow scoring policies (`04`)
- 6 runs: `provider_confidence_policy`, `medical_desert_risk_policy`, `intervention_recommender_policy`, `conformal_uncertainty_wrapper`, plus the **hillclimbing pair** `v1.2_baseline` vs `v1.3_telehealth_penalty`.
- Real metrics sourced from the stats-iteration artifacts (e.g. conformal coverage 0.918, human-review rate 0.682, telehealth-not-recommended 0.838). All tagged **proxy decision-support, not gold-label accuracy**.
- Hillclimbing: recommendation-agreement (telehealth correctly not #1) **75.7% → 98.8%** (v1.2→v1.3), logged as a **proposal pending human approval** (governed, not auto-deployed).
- Registered pyfunc model `workspace.caregap_models.caregap_scoring_policy`.

### App warehouse wiring (`app/lib/data.py`, `app/app.yaml`)
- Gold loaders (`load_gold_interventions`, `load_gold_provider_confidence`, `load_gold_scenario_simulations`, `load_medical_desert_scores`) + feedback write-back (`append_reviewer_feedback`, `append_recommendation_override`); all degrade gracefully to local CSV / empty, never raise to the UI.
- **`_wh_connect()`** added: works with a static token (local) **and Databricks Apps service-principal OAuth** (no token) via the Databricks SDK — required for the deployed app.

## 4. Cloud execution & verification

- Created the 5 `caregap_*` schemas; uploaded full-schema cleaned CSVs to the UC volume.
- `databricks bundle validate --strict` ✅ → `databricks bundle deploy` ✅ (fixed a 21 MB workspace-file overflow via `sync.exclude`).
- Ran `caregap_medallion` — **all 6 tasks SUCCESS**. Two runtime bugs found and fixed along the way:
  1. **Stale 102-column CSV** in the volume (teammate's reduced version) shadowed the full 144-column file → silver couldn't resolve `capacity_status`. Fixed by overwriting the volume CSVs and re-sourcing bronze from them.
  2. **Wrong join alias** in `05` (`f.join_confidence` → `l.join_confidence`) → fixed.
- **Verified row counts:** `medical_desert_scores` = **494**, `intervention_recommendations` = **3,458**, `provider_confidence` = **10,077**, `review_queue` = **9,807**; 5 views present; registered model + MLflow experiment confirmed.

## 5. Databricks App deployment

- App resource `caregap-app` bound to the serverless SQL warehouse (`CAN_USE`); `app.yaml` set to `DATA_BACKEND=warehouse` with `DATABRICKS_SERVER_HOSTNAME` + warehouse http_path; auth via app SP OAuth.
- Granted the app's service principal (`app-19d6u2 caregap-app`) `USE CATALOG` + `USE SCHEMA`/`SELECT` on `workspace.default` and `workspace.caregap_gold` (+ `MODIFY` on gold for feedback write-back).
- Created 4 governed feedback tables (`reviewer_feedback`, `provider_corrections`, `recommendation_overrides`, `intervention_outcomes`).
- **App URL:** **https://caregap-app-7474647301321645.aws.databricksapps.com** — **status: RUNNING** ✅ (Uvicorn serving on `:8000`).
- **Startup fix:** Databricks Apps does **not** shell-expand `${DATABRICKS_APP_PORT:-8000}` in the command array (Streamlit received the literal string and crashed). Hardcoded `--server.port 8000` (the standard Apps port). `databricks-sdk` + sklearn/scipy installed cleanly in the app build.
- Data loads on first authenticated browser session: core facilities/districts from `workspace.default.hackathon_*` (with the `_WAREHOUSE_FALLBACKS` column reconstruction) + governed gold loaders, all via the app SP OAuth (`_wh_connect`).
- **Loading-hang fix:** the app got stuck on "Loading facilities…" because **CloudFetch** result download to `*.storage.cloud.databricks.com` is blocked by Databricks Apps egress. Fixed by setting **`use_cloud_fetch=False`** in `_wh_connect()` so results return **inline** over the SQL connection (verified: inline `SELECT count(*)` → 10,077).
- **Sharing:** granted **`users` group → CAN_USE** on the app (admins CAN_MANAGE), so any member of this workspace can open it. Databricks Apps have **no anonymous public access**; on Free Edition you typically can't add external users — teammates either run locally, view via screen-share, or get invited if moved to a paid/Team workspace (the `users`-group grant then covers them automatically).

## 6. Cloud deep links

- **Workspace:** https://dbc-54942fa9-145a.cloud.databricks.com
- **App:** https://caregap-app-7474647301321645.aws.databricksapps.com
- **Job (`caregap_medallion`):** https://dbc-54942fa9-145a.cloud.databricks.com/?o=7474647301321645#job/366643825748761
- **Catalog (gold):** Catalog Explorer → `workspace.caregap_gold`
- **MLflow experiment:** `/Users/stevenybusiness@gmail.com/caregap_scoring_policies`
- **Registered model:** `workspace.caregap_models.caregap_scoring_policy`

## 7. Files added/changed

**New:** `databricks.yml`; `resources/caregap_{medallion.job,app.app,experiment.experiment}.yml`; `databricks/notebooks/0{1..6}_*.py`; `databricks/sql/monitoring_tables.sql`; `docs/databricks/{UC_GOVERNANCE,APP_WAREHOUSE_WIRING}.md`; `databricks_tool_integration_1.md`.
**Changed:** `app/lib/data.py` (gold loaders, feedback write-back, `_wh_connect` OAuth); `app/app.yaml` (warehouse mode + hostname); `app/requirements.txt` (`databricks-sdk`).

## 8. Notes & follow-ups

- Free Edition has no classic compute; everything runs serverless. The medallion job's weekly schedule is paused — trigger with `databricks bundle run caregap_medallion`.
- Gold/feature tables and the conformal/MLflow metrics are **proxy decision-support**, not gold-label-validated accuracy — labeled as such throughout (consistent with `STATISTICAL_DECISION_FRAMEWORK.md`).
- The app reads governed gold; if a gold object is ever missing it falls back gracefully (empty/compute-on-the-fly), so the UI never crashes.
