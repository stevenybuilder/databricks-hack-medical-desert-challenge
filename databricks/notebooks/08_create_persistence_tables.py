# Databricks notebook source
# MAGIC %md
# MAGIC # 08 · Persistence Tables (App Write-Back)
# MAGIC
# MAGIC Creates the governed **gold Delta write-back tables** in `workspace.caregap_gold`
# MAGIC that the deployed Databricks App writes reviewer decisions into. The app-side code in
# MAGIC `app/lib/data.py` does parameterized `INSERT`s into these tables; if the tables don't
# MAGIC exist the insert fails and the app silently degrades to **session-only** persistence.
# MAGIC This notebook makes that persistence real and durable in the cloud.
# MAGIC
# MAGIC These are the human-feedback write-back tables — reviewer notes, recommendation
# MAGIC overrides / shortlists, saved what-if scenarios, and review decisions.
# MAGIC
# MAGIC | Table | `app/lib/data.py` writer | Purpose |
# MAGIC |---|---|---|
# MAGIC | `reviewer_feedback` | `append_reviewer_feedback()` | reviewer notes & feedback (provider corrections, outcome data, data-quality flags) |
# MAGIC | `recommendation_overrides` | `append_recommendation_override()` | planner overrides of the recommended intervention |
# MAGIC | `scenario_decisions` | `append_scenario_decision()` | saved what-if scenario assumptions / decisions |
# MAGIC
# MAGIC The app reads them back via `load_reviewer_feedback()` / `load_scenario_decisions()`
# MAGIC with `ORDER BY created_at DESC`.
# MAGIC
# MAGIC ## ⚠️ APPEND-ONLY — NEVER REPLACE
# MAGIC These tables **ACCUMULATE** reviewer feedback across every job run. We use
# MAGIC `CREATE TABLE IF NOT EXISTS` *on purpose*. Do **NOT** change these to
# MAGIC `CREATE OR REPLACE TABLE` or `saveAsTable(mode="overwrite")` — that would wipe
# MAGIC every saved decision on each run. (Notebook 06 uses `CREATE OR REPLACE` for
# MAGIC **views**, which is fine for views but must never be copied here for these tables.)
# MAGIC
# MAGIC ## Schema note
# MAGIC Every column is `STRING`. All values are `str()`-coerced by the app, and `created_at`
# MAGIC is an ISO-8601 string (`pd.Timestamp.utcnow().isoformat()`) which sorts correctly
# MAGIC lexicographically. `STRING` guarantees the parameterized `INSERT` never fails a type
# MAGIC cast (a failed insert is exactly what degrades the app to session-only).

# COMMAND ----------

CATALOG = "workspace"
GOLD = f"{CATALOG}.caregap_gold"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `reviewer_feedback` — written by `append_reviewer_feedback()`
# MAGIC
# MAGIC Append-only reviewer feedback rows. Columns match the app's INSERT order exactly:
# MAGIC `geography_id, feedback_type, payload, notes, reviewer, status, policy_version, created_at`.

# COMMAND ----------

# NOTE: CREATE TABLE IF NOT EXISTS — append-only. NEVER CREATE OR REPLACE (would wipe saved feedback).
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.reviewer_feedback (
  geography_id   STRING COMMENT 'District / geography identifier the feedback applies to',
  feedback_type  STRING COMMENT 'Feedback category (e.g. provider_correction, recommendation_override, outcome_data, data_quality_flag)',
  payload        STRING COMMENT 'Serialized feedback payload (e.g. JSON) carrying the structured detail',
  notes          STRING COMMENT 'Free-text reviewer notes',
  reviewer       STRING COMMENT 'Reviewer identity (app user or CAREGAP_REVIEWER env)',
  status         STRING COMMENT 'Workflow status (e.g. pending, accepted, rejected)',
  policy_version STRING COMMENT 'Scoring policy version in effect when feedback was given',
  created_at     STRING COMMENT 'ISO-8601 UTC timestamp string; sorts lexicographically for ORDER BY created_at DESC'
)
USING DELTA
COMMENT 'App write-back: append-only reviewer feedback. Written by app/lib/data.py::append_reviewer_feedback(). NEVER replace — accumulates across job runs.'
""")
print("ensured table reviewer_feedback")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `recommendation_overrides` — written by `append_recommendation_override()`
# MAGIC
# MAGIC Append-only intervention overrides. Columns match the app's INSERT order exactly:
# MAGIC `geography_id, original_intervention, chosen_intervention, notes, reviewer, status, policy_version, created_at`.

# COMMAND ----------

# NOTE: CREATE TABLE IF NOT EXISTS — append-only. NEVER CREATE OR REPLACE (would wipe saved overrides).
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.recommendation_overrides (
  geography_id          STRING COMMENT 'District / geography identifier the override applies to',
  original_intervention STRING COMMENT 'Intervention the model originally recommended',
  chosen_intervention   STRING COMMENT 'Intervention the reviewer chose instead',
  notes                 STRING COMMENT 'Free-text reviewer rationale for the override',
  reviewer              STRING COMMENT 'Reviewer identity (app user or CAREGAP_REVIEWER env)',
  status                STRING COMMENT 'Workflow status (e.g. pending, accepted, rejected)',
  policy_version        STRING COMMENT 'Scoring policy version in effect when override was made',
  created_at            STRING COMMENT 'ISO-8601 UTC timestamp string; sorts lexicographically for ORDER BY created_at DESC'
)
USING DELTA
COMMENT 'App write-back: append-only recommendation overrides. Written by app/lib/data.py::append_recommendation_override(). NEVER replace — accumulates across job runs.'
""")
print("ensured table recommendation_overrides")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `scenario_decisions` — written by `append_scenario_decision()`
# MAGIC
# MAGIC Append-only saved what-if scenarios. Columns match the app's INSERT order exactly:
# MAGIC `geography_id, assumptions, notes, reviewer, status, policy_version, created_at`.

# COMMAND ----------

# NOTE: CREATE TABLE IF NOT EXISTS — append-only. NEVER CREATE OR REPLACE (would wipe saved scenarios).
spark.sql(f"""
CREATE TABLE IF NOT EXISTS {GOLD}.scenario_decisions (
  geography_id   STRING COMMENT 'District / geography identifier the scenario applies to',
  assumptions    STRING COMMENT 'Serialized scenario levers / planning assumptions (e.g. JSON)',
  notes          STRING COMMENT 'Free-text reviewer notes on the saved scenario',
  reviewer       STRING COMMENT 'Reviewer identity (app user or CAREGAP_REVIEWER env)',
  status         STRING COMMENT 'Workflow status (e.g. saved)',
  policy_version STRING COMMENT 'Scoring policy version in effect when scenario was saved',
  created_at     STRING COMMENT 'ISO-8601 UTC timestamp string; sorts lexicographically for ORDER BY created_at DESC'
)
USING DELTA
COMMENT 'App write-back: append-only saved what-if scenarios. Written by app/lib/data.py::append_scenario_decision(). NEVER replace — accumulates across job runs.'
""")
print("ensured table scenario_decisions")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Verify tables exist
# MAGIC
# MAGIC A run visibly proves the tables exist and shows accumulated row counts (preserved
# MAGIC across runs because these are append-only).

# COMMAND ----------

for t in ["reviewer_feedback", "recommendation_overrides", "scenario_decisions"]:
    n = spark.sql(f"SELECT count(*) AS n FROM {GOLD}.{t}").collect()[0]["n"]
    print(f"{t}: {n:,} rows")

display(spark.sql(f"SHOW TABLES IN {GOLD}"))
