# App ↔ Warehouse Wiring (governed gold + feedback)

How the Streamlit app reads the governed gold layer and writes monitoring feedback,
and the guarantees that keep local development unaffected.

## TL;DR

- `DATA_BACKEND` controls everything. Unset or `csv` (the default) = local CSV reads,
  no warehouse, no feedback writes. `warehouse` = read governed gold + enable feedback.
- The gold loaders **never raise to the UI**. On any warehouse failure they fall back
  to a local CSV artifact, and if that is missing they return an empty DataFrame.
- `load_facilities()` / `load_districts()` behavior is unchanged: identical columns and
  shapes in csv-mode as before this change.

## Environment variables

| Var | Default | Purpose |
|---|---|---|
| `DATA_BACKEND` | `csv` | `csv` (local) or `warehouse` (governed reads + feedback writes) |
| `DATABRICKS_WAREHOUSE_ID` | `1b331b704066b677` | Free-Edition serverless SQL warehouse id |
| `DATABRICKS_HTTP_PATH` | `/sql/1.0/warehouses/1b331b704066b677` | SQL connector http_path |
| `DATABRICKS_SERVER_HOSTNAME` | (resource binding) | Workspace host; injected by the App's warehouse resource |
| `DATABRICKS_TOKEN` | (resource binding) | Auth token; injected at deploy time — never hardcode |
| `CAREGAP_CATALOG` | `workspace` | Catalog for gold + monitoring tables |
| `CAREGAP_GOLD_SCHEMA` | `caregap_gold` | Schema for gold + monitoring tables |
| `CAREGAP_POLICY_VERSION` | `v0` | Stamped on feedback rows for the hillclimbing loop |
| `CAREGAP_REVIEWER` | `app` | Default reviewer identity on feedback rows |

These live in `app/app.yaml`. To enable the warehouse on deploy, set `DATA_BACKEND=warehouse`
(and ensure the warehouse resource provides `DATABRICKS_SERVER_HOSTNAME` / `DATABRICKS_TOKEN`).

## Read path

When `DATA_BACKEND=warehouse`, gold loaders prefer a **view**, fall back to its backing
**table**, then fall back to a **local CSV**, then to an **empty DataFrame**:

| Loader | View → table (in `workspace.caregap_gold`) | Local CSV fallback |
|---|---|---|
| `load_medical_desert_scores()` | `v_risk_map` → `medical_desert_scores` | `output/data/medical_desert_scores.csv` |
| `load_gold_interventions()` | `v_intervention_recommender` → `intervention_recommendations` | `output/data/intervention_recommendations.csv` |
| `load_gold_provider_confidence()` | `v_provider_confidence` → `provider_confidence` | `output/data/conformal_facility_sets.csv` |
| `load_gold_scenario_simulations()` | `v_scenario_simulator` → `scenario_simulations` | `output/data/scenario_simulations.csv` |

`load_facilities()` and `load_districts()` are unchanged — they read the cleaned tables in
`workspace.default` (warehouse mode) or the cleaned CSVs (csv-mode), with the existing
`_WAREHOUSE_FALLBACKS` column-projection mechanism.

Fully-qualified names come from `_gold(name)` = `{CAREGAP_CATALOG}.{CAREGAP_GOLD_SCHEMA}.{name}`.

## Graceful-fallback guarantee

Each gold loader is wrapped so that:
1. In warehouse mode it tries the view, then the table (catching exceptions per object).
2. If both fail it reads the local CSV.
3. If the CSV is absent it returns an empty DataFrame.

No code path raises to the UI — a missing or not-yet-materialized gold object degrades to
local data or an empty table, never an app crash. This lets the app ship before DB-2's
gold layer is finalized.

## Feedback write-back

When `DATA_BACKEND=warehouse`, the decisions module writes governed feedback via
parameterized `INSERT`s; in csv-mode these are no-ops returning `False`.

- `append_reviewer_feedback(geography_id, feedback_type, notes="", reviewer=None, payload="", status="pending", policy_version=None) -> bool`
- `append_recommendation_override(geography_id, original_intervention, chosen_intervention, notes="", reviewer=None, status="pending", policy_version=None) -> bool`

Targets are the monitoring tables defined in `databricks/sql/monitoring_tables.sql`:
`reviewer_feedback`, `provider_corrections`, `recommendation_overrides`, `intervention_outcomes`.
Writes are best-effort and never raise.

## Provisioning the monitoring tables

Run once against the warehouse (id `1b331b704066b677`) or a bound notebook:

```sql
-- databricks/sql/monitoring_tables.sql  (idempotent CREATE TABLE IF NOT EXISTS)
```

## Assumptions DB-2 must satisfy (gold column names)

The app reads gold tables with `SELECT *`, so it tolerates extra columns, but the
decisions/UI layer expects these names (per `docs/archive/databricks_tools_architecture.md`):

- `intervention_recommendations`: `geography_id`, `rank`, `intervention_type`,
  `expected_impact_score`, `recommendation_confidence`, `why_recommended`, `data_limitations`, `model_version`, `created_at`.
- `medical_desert_scores`: `geography_id`, `geography_name`, `state`, `district`,
  `medical_desert_risk_score`, `risk_band`, `confidence_score`, `model_version`, `scored_at`.
- `provider_confidence`: `canonical_provider_id`, `provider_confidence_score`, `confidence_band`,
  `hfr_match_flag`, `pmjay_match_flag`, `conflict_summary`.
- `scenario_simulations`: `scenario_id`, `geography_id`, `intervention_type`,
  `risk_score_before`, `risk_score_after`, `estimated_population_helped`, `confidence_band`.
- Monitoring tables must expose `geography_id`, `feedback_type`/`*_intervention`, `notes`,
  `reviewer`, `status`, `policy_version`, `created_at` so the parameterized inserts match.
