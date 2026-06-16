# Databricks notebook source
# MAGIC %md
# MAGIC # 06 · App Backend Queries
# MAGIC
# MAGIC Creates SQL **views** in `workspace.caregap_gold` that the Databricks App / dashboard
# MAGIC consume. Views are shaped to the columns `app/lib/data.py` expects so DB-4 can wire
# MAGIC the app to the warehouse with minimal mapping.
# MAGIC
# MAGIC | View | App tab | Purpose |
# MAGIC |---|---|---|
# MAGIC | `v_risk_map` | Risk Map | district risk + drivers + supply for the map/leaderboard |
# MAGIC | `v_intervention_recommender` | Interventions | ranked interventions per district |
# MAGIC | `v_provider_confidence` | Trust & conformal | per-facility confidence + conformal sets |
# MAGIC | `v_scenario_simulator` | Scenario lab | example before/after scenarios |
# MAGIC | `v_review_queue` | Decisions & feedback | prioritized verification queue |
# MAGIC
# MAGIC Plus a SQL UDF `fn_simulate_risk_after(...)` for live what-if simulation.
# MAGIC
# MAGIC Idempotent: `CREATE OR REPLACE VIEW` / `CREATE OR REPLACE FUNCTION`.

# COMMAND ----------

CATALOG = "workspace"
GOLD = f"{CATALOG}.caregap_gold"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `v_risk_map` — Risk Map tab
# MAGIC
# MAGIC One row per district with risk score, band, drivers, supply context, and confidence.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.v_risk_map AS
SELECT
  geography_id,
  geography_name,
  state,
  district,
  medical_desert_risk_score,
  risk_band,
  top_risk_drivers,
  provider_gap_score,
  travel_burden_score,
  vulnerability_score,
  confidence_score,
  provider_count_total,
  trustworthy_provider_count,
  district_uncertainty_level,
  planning_category,
  model_version,
  scored_at
FROM {GOLD}.medical_desert_scores
""")
print("created view v_risk_map")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `v_intervention_recommender` — Interventions tab
# MAGIC
# MAGIC Ranked interventions per district with EV, confidence, rationale, and data limits.
# MAGIC Telehealth never ranks #1; its limitation note is always populated.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.v_intervention_recommender AS
SELECT
  geography_id,
  state,
  district,
  rank,
  intervention_type,
  expected_impact_score,
  expected_access_gain,
  implementation_complexity_score,
  recommendation_confidence,
  p_addresses_need,
  p_wrong,
  trigger_signals,
  why_recommended,
  data_limitations,
  not_recommended_flag,
  not_recommended_reason,
  model_version,
  created_at
FROM {GOLD}.intervention_recommendations
""")
print("created view v_intervention_recommender")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `v_provider_confidence` — Trust & conformal tab
# MAGIC
# MAGIC Per-facility confidence score, band, conflict summary, and conformal prediction set.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.v_provider_confidence AS
SELECT
  canonical_provider_id,
  provider_name,
  facility_type,
  state,
  district,
  latitude,
  longitude,
  source_count,
  has_source_urls,
  has_contact_evidence,
  geo_valid_flag,
  pin_district_consistent_flag,
  contradicted_flag,
  needs_human_review,
  provider_confidence_score,
  confidence_band,
  validity_posterior,
  validity_action,
  conformal_set,
  conformal_decision,
  conflict_summary,
  last_verified_or_seen,
  source_urls,
  model_version,
  scored_at
FROM {GOLD}.provider_confidence
""")
print("created view v_provider_confidence")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `v_scenario_simulator` — Scenario lab tab
# MAGIC
# MAGIC Example before/after scenarios for high-risk districts.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.v_scenario_simulator AS
SELECT
  scenario_id,
  geography_id,
  state,
  district,
  intervention_type,
  assumptions_json,
  risk_score_before,
  risk_score_after,
  access_improvement_score,
  estimated_population_helped,
  confidence_band,
  model_version,
  created_at
FROM {GOLD}.scenario_simulations
""")
print("created view v_scenario_simulator")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `v_review_queue` — Decisions & feedback tab

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE VIEW {GOLD}.v_review_queue AS
SELECT
  canonical_provider_id,
  facility_name,
  facility_type,
  state,
  district,
  review_priority,
  primary_concern,
  confidence_band,
  provider_confidence_score,
  geo_quality,
  officialPhone,
  email,
  officialWebsite,
  source_urls,
  model_version,
  created_at
FROM {GOLD}.review_queue
ORDER BY review_priority DESC
""")
print("created view v_review_queue")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `fn_simulate_risk_after` — live what-if SQL UDF
# MAGIC
# MAGIC Deterministic sensitivity model the Scenario lab can call interactively:
# MAGIC each trustworthy primary-care unit added closes a capped fraction of the trust gap.
# MAGIC
# MAGIC Args: `risk_before` (0-100), `trustworthy_supply_rate` (0-1), `units_added` (int),
# MAGIC `per_unit_points` (risk points closed per unit, default tuned to ~6).
# MAGIC Returns the simulated risk score, floored at 0.

# COMMAND ----------

spark.sql(f"""
CREATE OR REPLACE FUNCTION {GOLD}.fn_simulate_risk_after(
  risk_before DOUBLE,
  trustworthy_supply_rate DOUBLE,
  units_added INT,
  per_unit_points DOUBLE DEFAULT 6.0
)
RETURNS DOUBLE
COMMENT 'Deterministic what-if: units_added trustworthy primary-care units close a capped fraction of the remaining trust gap.'
RETURN
  greatest(
    risk_before
    - least(
        coalesce(units_added, 0) * per_unit_points * (1.0 - coalesce(trustworthy_supply_rate, 0.0)),
        risk_before * 0.5  -- cap improvement at half the baseline (conservative)
      ),
    0.0
  )
""")
print("created function fn_simulate_risk_after")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify views

# COMMAND ----------

for v in ["v_risk_map", "v_intervention_recommender", "v_provider_confidence",
          "v_scenario_simulator", "v_review_queue"]:
    n = spark.sql(f"SELECT count(*) AS n FROM {GOLD}.{v}").collect()[0]["n"]
    print(f"{v}: {n:,} rows")

display(spark.sql(f"SHOW VIEWS IN {GOLD}"))
