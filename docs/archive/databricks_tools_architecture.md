# Databricks Tools & Architecture for CareGap Agent

## Purpose

This document is an implementation-focused architecture brief for building the **CareGap Agent** hackathon project on Databricks.

Project concept:

> A Databricks-native medical desert intelligence app that identifies underserved healthcare access gaps, recommends interventions, quantifies data confidence, and simulates what-if scenarios using governed healthcare access data.

Selected product features:

1. **Medical Desert Risk Map**
2. **Intervention Recommender**
3. **Data Quality Confidence Layer**
4. **What-If Scenario Simulator**

Optional later extension:

- Human verification / provider verification workbench
- Voice agent verification is explicitly out of MVP scope

---

## Recommended Databricks Stack

| Layer | Databricks tool | Purpose |
|---|---|---|
| Data storage | Delta Lake | Store bronze, silver, gold healthcare access tables |
| Governance | Unity Catalog | Govern tables, features, functions, models, lineage, and access |
| ETL / pipelines | Lakeflow / Delta Live Tables / Workflows | Ingest, clean, transform, and refresh datasets |
| Feature engineering | Feature Engineering in Unity Catalog | Store reusable data-quality and access-risk features |
| Model tracking | MLflow Tracking | Track experiments, parameters, metrics, artifacts, and model runs |
| Model registry | Models in Unity Catalog / MLflow Registry | Register risk and recommender models with lineage and governance |
| Batch inference | Databricks Jobs / Workflows | Score geographies and providers on schedule |
| Serving | Databricks Model Serving | Serve risk-scoring or recommendation models if needed |
| App UI | Databricks Apps | Build interactive dashboard / map / recommender interface |
| Agent layer | Mosaic AI Agent Framework / Databricks Apps agent template | Optional natural-language assistant over the data |
| Monitoring | Lakehouse Monitoring / inference tables | Monitor data quality, prediction drift, and model behavior |
| BI / visualization | Databricks SQL dashboards | Risk map, provider confidence, intervention comparisons |

Relevant docs:

- MLflow on Databricks: https://docs.databricks.com/aws/en/mlflow/
- MLflow Tracking: https://docs.databricks.com/aws/en/mlflow/tracking
- Models in Unity Catalog: https://docs.databricks.com/aws/en/machine-learning/manage-model-lifecycle/
- Feature Store / Feature Engineering in Unity Catalog: https://docs.databricks.com/aws/en/machine-learning/feature-store/
- Feature governance and lineage: https://docs.databricks.com/aws/en/machine-learning/feature-store/concepts
- Unity Catalog: https://docs.databricks.com/aws/en/data-governance/unity-catalog/
- Model Serving: https://docs.databricks.com/aws/en/machine-learning/model-serving/
- Databricks Apps agent template: https://docs.databricks.com/aws/en/generative-ai/agent-framework/author-agent
- Databricks AI agent tools: https://docs.databricks.com/aws/en/generative-ai/agent-framework/agent-tool
- Lakehouse Monitoring / ML monitoring overview: https://docs.databricks.com/aws/en/machine-learning/

---

## High-Level Architecture

```text
External datasets
  - ABDM Health Facility Registry / HFR where available
  - data.gov.in Hospital Directory / National Health Portal
  - All India Health Centres Directory
  - PM-JAY empanelled hospitals
  - Ayushman Arogya Mandir / AB-HWC data
  - HMIS / NFHS / Census / socioeconomic datasets
  - Optional OpenStreetMap or OpenCity civic health datasets

        ↓ ingestion

Bronze Delta tables
  - raw_provider_records
  - raw_facility_directory
  - raw_pmjay_hospitals
  - raw_health_centres
  - raw_demographics
  - raw_disease_burden
  - raw_transport_geography

        ↓ cleaning / normalization

Silver Delta tables
  - silver_providers_normalized
  - silver_provider_locations
  - silver_provider_crosswalk
  - silver_geography_population
  - silver_access_supply
  - silver_demand_vulnerability
  - silver_source_quality

        ↓ feature engineering

Feature tables in Unity Catalog
  - feature_provider_confidence
  - feature_geography_access_risk
  - feature_intervention_inputs
  - feature_scenario_assumptions

        ↓ models / scoring

MLflow-tracked models
  - medical_desert_risk_model
  - intervention_recommender_model
  - provider_confidence_model or scoring function
  - optional conformal uncertainty wrapper

        ↓ scored outputs

Gold Delta tables
  - gold_medical_desert_scores
  - gold_intervention_recommendations
  - gold_provider_confidence
  - gold_scenario_simulations
  - gold_review_queue

        ↓ product

Databricks App / SQL Dashboard
  - Risk map
  - Intervention recommender
  - Data confidence explanations
  - What-if simulator
```

---

## MVP Build Order

### Phase 1 — Data ingestion and bronze tables

Goal: Load India healthcare-access datasets into raw Delta tables.

Suggested inputs:

| Dataset | Role |
|---|---|
| ABDM Health Facility Registry | Canonical verification source where available |
| data.gov.in Hospital Directory | Public/private hospital/provider seed list |
| All India Health Centres Directory | PHC/CHC/sub-centre/district hospital geography |
| PM-JAY hospitals | Insurance-affordability access signal |
| Ayushman Arogya Mandir / HWC | Primary-care availability signal |
| HMIS / NFHS / Census | Demand, vulnerability, population, disease burden |

Bronze table examples:

```sql
bronze.raw_hospital_directory
bronze.raw_health_centres
bronze.raw_pmjay_hospitals
bronze.raw_hfr_facilities
bronze.raw_district_demographics
bronze.raw_health_indicators
```

Implementation notes:

- Use Delta Lake for all persisted tables.
- Preserve original raw columns.
- Add ingestion metadata:
  - `source_name`
  - `source_url`
  - `ingested_at`
  - `source_last_updated`
  - `raw_record_hash`
  - `pipeline_run_id`

---

### Phase 2 — Silver cleaning and normalization

Goal: Convert messy provider and geography data into normalized, joinable tables.

Core cleaning steps:

1. Normalize facility names.
2. Normalize state, district, block, village, city, PIN code.
3. Standardize ownership type: public, private, nonprofit, unknown.
4. Standardize facility type: hospital, PHC, CHC, sub-centre, clinic, diagnostic centre, pharmacy, unknown.
5. Validate coordinates.
6. Validate PIN/state/district consistency.
7. Deduplicate providers using fuzzy matching and geospatial proximity.
8. Crosswalk records across HFR, PM-JAY, data.gov.in, and health-centre sources.

Silver table examples:

```sql
silver.providers_normalized
silver.provider_locations
silver.provider_source_crosswalk
silver.facility_type_taxonomy
silver.geography_demographics
silver.geography_health_need
silver.source_quality_metrics
```

Provider crosswalk fields:

| Field | Description |
|---|---|
| `canonical_provider_id` | Internal stable provider ID |
| `source_provider_id` | Original source ID if available |
| `source_name` | Source dataset |
| `hfr_id` | ABDM HFR ID if matched |
| `pmjay_id` | PM-JAY ID if matched |
| `match_method` | exact, fuzzy_name_address, geo_proximity, manual |
| `match_confidence` | 0-1 confidence score |
| `conflict_flag` | Whether sources disagree materially |

---

## Unity Catalog Design

Use Unity Catalog for governance, discovery, lineage, and model ownership.

Recommended namespace:

```text
caregap
  bronze
  silver
  features
  models
  gold
  app
```

Example table names:

```sql
caregap.bronze.raw_hospital_directory
caregap.silver.providers_normalized
caregap.features.provider_confidence_features
caregap.gold.medical_desert_scores
caregap.gold.intervention_recommendations
```

Recommended Unity Catalog tags:

| Tag | Example values |
|---|---|
| `domain` | healthcare_access |
| `data_tier` | bronze, silver, gold |
| `source_authority` | government, civic, derived |
| `refresh_cadence` | one_time, daily, weekly, manual |
| `contains_phi` | false |
| `hackathon_feature` | risk_map, recommender, confidence, simulator |

Important note:

- The MVP should avoid patient-level data and PHI.
- Use facility, district, ZIP/PIN, and aggregate demographic data.

---

## Feature Engineering in Unity Catalog

Although the user-facing product features are risk map, recommender, confidence layer, and simulator, the implementation should still create reusable ML features.

### Feature table: `provider_confidence_features`

Primary key:

```text
canonical_provider_id
```

Candidate columns:

| Feature | Description |
|---|---|
| `source_count` | Number of sources where provider appears |
| `hfr_match_flag` | Matched to ABDM HFR |
| `pmjay_match_flag` | Matched to PM-JAY |
| `gov_directory_match_flag` | Appears in government directory |
| `geo_valid_flag` | Coordinates pass validation |
| `pin_district_consistent_flag` | PIN/district/state consistency check |
| `facility_type_confidence` | Confidence in facility type classification |
| `source_conflict_count` | Number of conflicting fields across sources |
| `staleness_days` | Days since source was updated or verified |
| `provider_confidence_score` | Composite 0-1 confidence score |

### Feature table: `geography_access_risk_features`

Primary key:

```text
geography_id
```

Candidate columns:

| Feature | Description |
|---|---|
| `population_total` | Population of geography |
| `rural_population_share` | Rural share |
| `elderly_share` | Elderly population share |
| `poverty_proxy_score` | Socioeconomic vulnerability proxy |
| `uninsured_or_low_access_proxy` | Affordability/access proxy |
| `provider_count_total` | All nearby providers |
| `primary_care_provider_count` | PHC/clinic/primary-care providers |
| `hospital_count` | Hospitals nearby |
| `pmjay_provider_count` | PM-JAY empanelled providers nearby |
| `aam_hwc_count` | Ayushman Arogya Mandir / HWC count |
| `nearest_primary_care_distance_km` | Distance to nearest primary care |
| `nearest_hospital_distance_km` | Distance to nearest hospital |
| `provider_per_10k_population` | Supply density |
| `condition_burden_score` | Need/demand score |
| `transport_burden_score` | Travel difficulty proxy |
| `medical_desert_risk_score` | Composite desert score |

### Feature table: `intervention_input_features`

Primary key:

```text
geography_id
```

Candidate columns:

| Feature | Description |
|---|---|
| `telehealth_viability_score` | Broadband/phone/digital viability proxy |
| `mobile_clinic_fit_score` | Need and geography fit for mobile clinic |
| `transport_voucher_fit_score` | Fit for transportation support |
| `pharmacy_care_fit_score` | Fit for pharmacy-based screenings |
| `aam_upgrade_fit_score` | Fit for upgrading existing primary-care point |
| `fqhc_partner_fit_score` | Fit for formal partnership/referral route |
| `high_confidence_provider_gap` | Gap after filtering low-confidence providers |
| `service_gap_primary_care` | Primary care gap |
| `service_gap_maternal` | Maternal care gap if data available |
| `service_gap_chronic_care` | Chronic disease support gap |

---

## MLflow Tracking Plan

Use MLflow for experiment tracking across:

1. Provider confidence scoring
2. Medical desert risk scoring
3. Intervention recommendation ranking
4. Optional conformal uncertainty wrapper
5. Scenario simulator assumptions

MLflow should log:

### Parameters

```text
model_type
feature_table_version
risk_score_weights
provider_distance_radius_km
staleness_penalty_weight
source_reliability_weight
intervention_thresholds
train_test_split_strategy
```

### Metrics

```text
provider_match_precision
provider_match_recall
duplicate_detection_precision
gold_source_agreement_rate
calibration_error
conformal_coverage
recommendation_agreement_with_rules
human_review_rate
low_confidence_provider_rate
scenario_rank_stability
```

### Artifacts

```text
feature_importance.csv
risk_score_distribution.png
confusion_matrix.png
calibration_curve.png
provider_match_samples.csv
recommendation_examples.json
scenario_simulation_outputs.csv
```

### Models to log

Recommended MVP models:

1. **Rule-based baseline**
   - Weighted scoring function
   - Easy to explain
   - No training data required

2. **CatBoost or LightGBM classifier/ranker**
   - Use if labels or pseudo-labels are available
   - Good for tabular data

3. **Conformal wrapper**
   - Optional
   - Wrap around classification probabilities or risk estimates

For the hackathon, start with the rule-based baseline and add ML if time allows.

---

## Model Design

### Model 1: Provider Confidence Score

Type:

```text
Weighted scoring function first; ML classifier later
```

Inputs:

- source count
- government-source match flags
- geospatial validity
- staleness
- field conflicts
- facility-type certainty

Output:

```text
provider_confidence_score: 0-1
provider_confidence_band: high / medium / low
```

Example rule:

```text
score =
  0.25 * hfr_match_flag
+ 0.20 * pmjay_match_flag
+ 0.15 * gov_directory_match_flag
+ 0.15 * geo_valid_flag
+ 0.10 * source_count_normalized
- 0.10 * staleness_penalty
- 0.05 * conflict_penalty
```

### Model 2: Medical Desert Risk Score

Type:

```text
Composite index first; ML model later if labels exist
```

Inputs:

- provider density
- nearest provider distance
- primary care supply
- PM-JAY access
- demographic vulnerability
- disease burden
- transportation burden
- provider confidence adjustment

Output:

```text
medical_desert_risk_score: 0-100
risk_band: low / medium / high / severe
risk_drivers: ranked explanation list
```

Important adjustment:

> Medical desert risk should increase when nearby providers are low-confidence, stale, not primary-care relevant, or not financially accessible.

### Model 3: Intervention Recommender

Type:

```text
Rules/ranker first; learning-to-rank later
```

Candidate interventions:

| Intervention | When recommended |
|---|---|
| Mobile primary care clinic | High travel burden + low primary-care density |
| Transportation vouchers | Providers exist but travel burden is high |
| Telehealth support | High provider gap + adequate digital access |
| AAM / HWC upgrade | Existing primary-care node nearby but capacity likely insufficient |
| PM-JAY enrollment/navigation | Providers exist but affordability barrier is high |
| Pharmacy-based screening | Pharmacy access exists + chronic disease burden high |
| CHW outreach | Low digital access + high vulnerability |

Output:

```text
recommended_intervention
intervention_rankings
expected_impact_score
implementation_complexity
confidence_score
explanation
```

### Model 4: What-If Scenario Simulator

Type:

```text
Deterministic simulation / sensitivity model
```

Inputs:

- geography
- selected intervention
- number of clinics/mobile visits/providers added
- assumed capacity
- assumed adoption
- cost proxy

Outputs:

```text
risk_score_before
risk_score_after
estimated_population_helped
access_improvement_score
cost_complexity_score
confidence_band
```

Example scenarios:

```text
Add one monthly mobile clinic
Add one PM-JAY navigation center
Add transport vouchers to nearest PHC
Upgrade one AAM/HWC site
Improve telehealth access by 20%
```

---

## Gold Tables for the App

### `gold.medical_desert_scores`

| Column | Description |
|---|---|
| `geography_id` | District / PIN / block ID |
| `geography_name` | Human-readable name |
| `state` | State |
| `district` | District |
| `population_total` | Population |
| `medical_desert_risk_score` | 0-100 score |
| `risk_band` | low / medium / high / severe |
| `top_risk_drivers` | JSON list of explanations |
| `provider_gap_score` | Supply gap component |
| `travel_burden_score` | Distance / transport component |
| `vulnerability_score` | Demographic need component |
| `confidence_score` | Confidence in score |
| `model_version` | MLflow model version or scoring policy version |
| `scored_at` | Timestamp |

### `gold.intervention_recommendations`

| Column | Description |
|---|---|
| `geography_id` | Geography ID |
| `rank` | Recommendation rank |
| `intervention_type` | Mobile clinic, telehealth, etc. |
| `expected_impact_score` | Impact estimate |
| `implementation_complexity_score` | Complexity estimate |
| `recommendation_confidence` | Confidence score |
| `why_recommended` | Explanation text |
| `data_limitations` | Known caveats |
| `model_version` | MLflow model or policy version |
| `created_at` | Timestamp |

### `gold.provider_confidence`

| Column | Description |
|---|---|
| `canonical_provider_id` | Provider ID |
| `provider_name` | Normalized name |
| `facility_type` | Facility type |
| `state` | State |
| `district` | District |
| `latitude` | Latitude |
| `longitude` | Longitude |
| `hfr_match_flag` | HFR match |
| `pmjay_match_flag` | PM-JAY match |
| `source_count` | Number of sources |
| `provider_confidence_score` | 0-1 confidence |
| `confidence_band` | high / medium / low |
| `conflict_summary` | Key conflicts |
| `last_verified_or_seen` | Latest source timestamp |

### `gold.scenario_simulations`

| Column | Description |
|---|---|
| `scenario_id` | Scenario ID |
| `geography_id` | Geography ID |
| `intervention_type` | Intervention tested |
| `assumptions_json` | Input assumptions |
| `risk_score_before` | Baseline score |
| `risk_score_after` | Simulated score |
| `estimated_population_helped` | Estimate |
| `confidence_band` | high / medium / low |
| `created_at` | Timestamp |

---

## Databricks App UX

Build a simple Databricks App with four tabs.

### Tab 1: Medical Desert Risk Map

Displays:

- Map by district/PIN/block
- Risk score
- Risk band
- Top drivers
- Confidence score
- Provider count and nearest provider distance

Minimum implementation:

- If geospatial map is hard, use ranked table + simple Plotly map/scatter.
- Prioritize clarity over perfect cartography.

### Tab 2: Intervention Recommender

User selects a geography.

Shows:

- Top 3 recommended interventions
- Expected impact
- Implementation complexity
- Confidence
- Explanation
- Data limitations

### Tab 3: Data Confidence Layer

Shows:

- Provider confidence distribution
- Low-confidence providers affecting the recommendation
- Source evidence by provider
- Conflicting fields
- Staleness warnings

This is the trust differentiator.

### Tab 4: What-If Scenario Simulator

User chooses:

- Geography
- Intervention type
- Number of sites/visits/providers
- Capacity assumption

Outputs:

- Before/after risk score
- Expected access improvement
- Confidence band
- Sensitivity notes

---

## Optional Agent Layer

The core MVP does not require an LLM agent. If time permits, add an agent interface using Databricks Apps / Mosaic AI Agent Framework.

Agent questions:

```text
Which districts are most underserved?
Why is this district high risk?
What intervention should we prioritize?
What data sources support this recommendation?
What happens if we add one mobile clinic?
Which provider records are low-confidence?
```

Agent tools:

1. SQL query tool over gold tables
2. Provider confidence lookup tool
3. Scenario simulation tool
4. Recommendation explanation tool

Agent guardrails:

- Do not provide medical diagnosis.
- Do not provide patient-specific advice.
- Only answer from structured tables.
- Cite table/source evidence in every answer.
- Show uncertainty and data limitations.

---

## Monitoring and Feedback Loop

Use monitoring as part of the “self-improving but governed” story.

Feedback tables:

```sql
caregap.gold.reviewer_feedback
caregap.gold.provider_corrections
caregap.gold.recommendation_overrides
caregap.gold.intervention_outcomes
```

Feedback examples:

| Feedback type | Example |
|---|---|
| Provider correction | Clinic no longer open |
| Recommendation override | Reviewer chose mobile clinic over telehealth |
| Outcome data | Mobile clinic served 300 patients |
| Data quality flag | PM-JAY listing conflicts with HFR address |

Hillclimbing pattern:

```text
Observe feedback
→ detect failure pattern
→ propose scoring/recommender update
→ validate in MLflow against regression examples
→ human approves
→ deploy new scoring policy/model version
```

For MVP, implement as a narrative and one small example:

- Reviewer flags that telehealth is overrecommended where digital access is low.
- Create a new recommender policy version with stronger telehealth penalty.
- Log both versions in MLflow.
- Show improvement in recommendation agreement on sample cases.

---

## Implementation Checklist for Claude

### Notebook 1: `01_ingest_bronze.py`

Tasks:

- Load CSV/API/manual datasets.
- Write raw Delta tables.
- Add ingestion metadata.

### Notebook 2: `02_clean_silver.py`

Tasks:

- Normalize names, geographies, facility types.
- Validate coordinates.
- Create provider crosswalk.
- Create normalized provider/location tables.

### Notebook 3: `03_build_features.py`

Tasks:

- Compute provider confidence features.
- Compute geography access-risk features.
- Compute intervention input features.
- Save feature tables in Unity Catalog.

### Notebook 4: `04_train_or_score_models.py`

Tasks:

- Build rule-based baseline scores.
- Train optional CatBoost/LightGBM model if labels exist.
- Log params, metrics, artifacts to MLflow.
- Register model/scoring policy in Unity Catalog if possible.

### Notebook 5: `05_generate_gold_outputs.py`

Tasks:

- Generate medical desert scores.
- Generate intervention rankings.
- Generate provider confidence output.
- Generate scenario simulation examples.

### Notebook 6: `06_app_backend_queries.py`

Tasks:

- Create SQL views for app tabs.
- Create functions for scenario simulation.
- Create explanation fields.

### App: `caregap_app`

Tasks:

- Build Streamlit/Dash/Databricks App UI.
- Tabs:
  1. Risk Map
  2. Intervention Recommender
  3. Confidence Layer
  4. Scenario Simulator

---

## Recommended Model Strategy

### MVP-first approach

Use **rules + weighted scoring** first.

Why:

- Faster to implement
- More explainable to judges
- Does not require clean labels
- Works well with public health decision logic
- Easy to log and compare in MLflow

### ML enhancement

Add CatBoost/LightGBM only if there is enough labeled or pseudo-labeled data.

Possible labels:

```text
high_risk_medical_desert
low_risk_medical_desert
auto_accept_provider
low_confidence_provider
best_intervention_mobile_clinic
best_intervention_transport
best_intervention_telehealth
```

Where labels may come from:

- Heuristic pseudo-labels
- Known high/low access districts
- Source verification status
- Human review sample

### Conformal prediction

Use only if time permits.

Best use:

- Wrap intervention classifier or risk-band classifier.
- Output prediction sets like:

```text
{mobile_clinic}
{mobile_clinic, transport_vouchers}
{telehealth, CHW_outreach, mobile_clinic}
```

This shows calibrated uncertainty.

---

## Product Metrics to Show Judges

| Metric | Why it matters |
|---|---|
| Number of provider records cleaned | Data engineering value |
| Duplicate providers merged | Data quality value |
| % providers with high/medium/low confidence | Trust layer |
| Number of high-risk geographies identified | Social-impact relevance |
| Top 10 underserved districts/PINs | Demo clarity |
| Recommendation confidence distribution | Avoids overclaiming |
| Scenario risk reduction estimate | Decision support |
| MLflow run comparison | Technical depth |
| Source agreement rate | Verification quality |
| Staleness penalty impact | Shows real-world messiness |

---

## Suggested Demo Script

1. **Start with the problem.**

   > Medical desert decisions depend on messy provider directories, stale facility data, and uneven health-access indicators.

2. **Show the risk map.**

   > The app ranks geographies by medical desert risk, but also shows confidence and top drivers.

3. **Click a high-risk geography.**

   > This area has low primary-care density, high travel burden, and high vulnerability.

4. **Show the intervention recommender.**

   > The top recommendation is mobile primary care, not telehealth, because the digital-access and provider-confidence signals are weak.

5. **Show the confidence layer.**

   > The nearby providers reduce risk only if they are verified. Low-confidence providers are discounted.

6. **Run what-if simulation.**

   > Adding one monthly mobile clinic reduces the risk score from 86 to 71 under conservative assumptions.

7. **End with Databricks thesis.**

   > Databricks gives us the lakehouse, governed features, MLflow evaluation, model lineage, and app layer needed to turn messy public-health data into an auditable agentic decision system.

---

## Final One-Liner

> CareGap Agent is a Databricks-native medical desert intelligence app that uses governed healthcare-access data, MLflow-tracked scoring policies, reusable feature tables, and uncertainty-aware recommendations to help public-health teams decide where to intervene first.
