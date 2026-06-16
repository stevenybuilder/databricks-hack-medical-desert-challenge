# CareGap — Unity Catalog Governance

This document defines the Unity Catalog (UC) namespace, tagging plan, and
governance posture for the CareGap medical-desert intelligence app.

## Environment constraints (Databricks Free Edition)

- **Serverless compute only.** No classic clusters / `new_cluster` /
  `node_type_id`. All jobs and the app run on serverless.
- **Single catalog: `workspace`.** New catalogs cannot be created on Free
  Edition, so every CareGap schema lives under `workspace`.
- Profile: `DEFAULT` (host `dbc-54942fa9-145a.cloud.databricks.com`).

## Namespace

Catalog: **`workspace`** (bundle variable `${var.catalog}`).

| Schema | Bundle variable | Tier | Purpose |
|---|---|---|---|
| `caregap_bronze` | `${var.bronze_schema}` | bronze | Raw ingested Delta tables, original columns + ingestion metadata. |
| `caregap_silver` | `${var.silver_schema}` | silver | Normalized providers, locations, crosswalk, geography demographics, source quality. |
| `caregap_features` | `${var.features_schema}` | features | Feature Engineering in UC tables (provider confidence, geography access risk, intervention inputs). |
| `caregap_gold` | `${var.gold_schema}` | gold | App-facing scored outputs, recommendations, confidence, scenarios + serving views. |
| `caregap_models` | `${var.models_schema}` | models | Registered scoring policies / models. |

Schemas are created centrally by the orchestrator; the bundle references them
via variables (it does not create catalogs or schemas).

Fully-qualified example:

```
workspace.caregap_bronze.raw_hospital_directory
workspace.caregap_silver.providers_normalized
workspace.caregap_features.provider_confidence_features
workspace.caregap_gold.medical_desert_scores
workspace.caregap_models.medical_desert_scoring_policy
```

## Governance posture: no PHI, aggregate-only

- CareGap deliberately uses **facility-, district-, PIN/ZIP- and aggregate
  demographic data only**. There is **no patient-level data and no PHI**.
- Every governed table carries `contains_phi=false`.
- Provider records describe facilities (public directories, HFR, PM-JAY), not
  patients. Demographic signals are aggregate (Census / NFHS / HMIS).
- This keeps the project inside a safe, auditable governance envelope while
  still demonstrating UC lineage, tagging, and feature/model governance.

## Per-table UC tag plan

Every CareGap table should be tagged with the following keys (from the target
architecture). Tags drive discovery, lineage filtering, and the "governed data"
story for judges.

| Tag | Values | Meaning |
|---|---|---|
| `domain` | `healthcare_access` | Business domain (constant across CareGap). |
| `data_tier` | `bronze` / `silver` / `gold` (also `features`, `models`) | Medallion tier of the asset. |
| `source_authority` | `government` / `civic` / `derived` | Provenance class. Raw gov directories = `government`; OSM/civic = `civic`; anything computed downstream = `derived`. |
| `refresh_cadence` | `one_time` / `daily` / `weekly` / `manual` | Expected refresh. Hackathon tables are `manual` (job runs on demand; weekly schedule shipped PAUSED). |
| `contains_phi` | `false` | PHI posture. Always `false` for CareGap. |
| `hackathon_feature` | `risk_map` / `recommender` / `confidence` / `simulator` | Which product feature the table backs. |

### Tag-by-tier defaults

| Tier | `data_tier` | `source_authority` | `refresh_cadence` |
|---|---|---|---|
| bronze raw tables | `bronze` | `government` (or `civic` for OSM-type sources) | `manual` |
| silver normalized | `silver` | `derived` | `manual` |
| features | `bronze`→ use `gold`? no → `silver`-derived → tag `derived` | `derived` | `manual` |
| gold outputs | `gold` | `derived` | `manual` |

> Note: feature and model tables are derived assets; tag `source_authority=derived`.

## `ALTER TABLE ... SET TAGS` examples (gold tables)

Run these (e.g. from notebook `06_app_backend_queries.py` or a governance cell)
once the gold tables exist. UC tags are set with `SET TAGS (...)`.

```sql
-- gold.medical_desert_scores (risk map)
ALTER TABLE workspace.caregap_gold.medical_desert_scores SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'gold',
  'source_authority'  = 'derived',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'risk_map'
);

-- gold.intervention_recommendations (recommender)
ALTER TABLE workspace.caregap_gold.intervention_recommendations SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'gold',
  'source_authority'  = 'derived',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'recommender'
);

-- gold.provider_confidence (confidence layer)
ALTER TABLE workspace.caregap_gold.provider_confidence SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'gold',
  'source_authority'  = 'derived',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'confidence'
);

-- gold.scenario_simulations (what-if simulator)
ALTER TABLE workspace.caregap_gold.scenario_simulations SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'gold',
  'source_authority'  = 'derived',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'simulator'
);
```

### Bronze / silver examples

```sql
ALTER TABLE workspace.caregap_bronze.raw_hospital_directory SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'bronze',
  'source_authority'  = 'government',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'risk_map'
);

ALTER TABLE workspace.caregap_silver.providers_normalized SET TAGS (
  'domain'            = 'healthcare_access',
  'data_tier'         = 'silver',
  'source_authority'  = 'derived',
  'refresh_cadence'   = 'manual',
  'contains_phi'      = 'false',
  'hackathon_feature' = 'confidence'
);
```

To inspect tags later:

```sql
SELECT * FROM workspace.information_schema.table_tags
WHERE schema_name LIKE 'caregap_%';
```

## Where governance is enforced

- **Bundle** (`databricks.yml` + `resources/*.yml`): pins catalog/schema via
  variables; deploys the medallion job, app, and MLflow experiment as governed,
  source-controlled UC assets.
- **Notebooks** (authored by other agents): write Delta tables into the
  schemas above and apply the `SET TAGS` statements.
- **MLflow experiment** (`caregap_scoring_policies`): governs scoring-policy
  versioning and lineage for the confidence/risk/recommender logic.
