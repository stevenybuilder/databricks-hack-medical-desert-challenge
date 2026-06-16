-- CareGap monitoring / feedback layer (governed gold).
--
-- Idempotent DDL for the "self-improving but governed" story: the Streamlit app's
-- local SQLite decisions module writes back into these governed Unity Catalog tables
-- via lib/data.append_reviewer_feedback() / append_recommendation_override() when
-- DATA_BACKEND=warehouse.
--
-- Free Edition: serverless, single catalog `workspace`, schema `caregap_gold`.
-- Run in a SQL warehouse (id 1b331b704066b677) or a notebook bound to it.
-- Override the schema with the same CAREGAP_CATALOG / CAREGAP_GOLD_SCHEMA values the
-- app uses if you materialize the gold layer elsewhere.

CREATE SCHEMA IF NOT EXISTS workspace.caregap_gold;

-- Generic reviewer feedback. feedback_type is one of:
--   provider_correction | recommendation_override | outcome_data | data_quality_flag
-- status lifecycle: pending -> approved | dismissed.
CREATE TABLE IF NOT EXISTS workspace.caregap_gold.reviewer_feedback (
  feedback_id     STRING    DEFAULT uuid(),
  geography_id    STRING    COMMENT 'District / PIN / block ID (or provider id for provider-scoped feedback)',
  feedback_type   STRING    COMMENT 'provider_correction | recommendation_override | outcome_data | data_quality_flag',
  payload         STRING    COMMENT 'Optional structured JSON payload',
  notes           STRING    COMMENT 'Free-text reviewer note',
  reviewer        STRING    COMMENT 'Reviewer identity (email / app)',
  status          STRING    DEFAULT 'pending' COMMENT 'pending | approved | dismissed',
  policy_version  STRING    COMMENT 'Scoring/recommender policy version this feedback targets',
  created_at      TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
COMMENT 'Reviewer feedback captured from the CareGap app; drives the governed hillclimbing loop.';

-- Provider-level corrections (e.g. "clinic no longer open").
CREATE TABLE IF NOT EXISTS workspace.caregap_gold.provider_corrections (
  correction_id        STRING    DEFAULT uuid(),
  canonical_provider_id STRING   COMMENT 'Provider ID from gold.provider_confidence',
  geography_id         STRING    COMMENT 'District / PIN / block context',
  field               STRING    COMMENT 'Corrected field (e.g. open_status, address, facility_type)',
  corrected_value     STRING    COMMENT 'New value asserted by the reviewer',
  notes               STRING    COMMENT 'Free-text justification / evidence',
  reviewer            STRING,
  status              STRING    DEFAULT 'pending' COMMENT 'pending | approved | dismissed',
  policy_version      STRING,
  created_at          TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
COMMENT 'Provider-level corrections (existence, status, identity, location).';

-- Recommendation overrides (reviewer picked a different intervention).
CREATE TABLE IF NOT EXISTS workspace.caregap_gold.recommendation_overrides (
  override_id            STRING    DEFAULT uuid(),
  geography_id           STRING    COMMENT 'Geography ID from gold.intervention_recommendations',
  original_intervention  STRING    COMMENT 'Intervention the recommender proposed',
  chosen_intervention    STRING    COMMENT 'Intervention the reviewer chose instead',
  notes                  STRING    COMMENT 'Why the override was made',
  reviewer               STRING,
  status                 STRING    DEFAULT 'pending' COMMENT 'pending | approved | dismissed',
  policy_version         STRING    COMMENT 'Recommender policy version overridden',
  created_at             TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
COMMENT 'Reviewer overrides of recommended interventions; regression examples for the next policy version.';

-- Realized intervention outcomes (e.g. "mobile clinic served 300 patients").
CREATE TABLE IF NOT EXISTS workspace.caregap_gold.intervention_outcomes (
  outcome_id             STRING    DEFAULT uuid(),
  geography_id           STRING    COMMENT 'Geography ID',
  intervention_type      STRING    COMMENT 'Intervention that was deployed',
  outcome_metric         STRING    COMMENT 'Metric name (e.g. patients_served, access_gain)',
  outcome_value          DOUBLE    COMMENT 'Observed numeric outcome',
  notes                  STRING    COMMENT 'Context / data source',
  reviewer               STRING,
  status                 STRING    DEFAULT 'pending' COMMENT 'pending | approved | dismissed',
  policy_version         STRING,
  observed_at            TIMESTAMP COMMENT 'When the outcome was observed in the field',
  created_at             TIMESTAMP DEFAULT current_timestamp()
)
USING DELTA
COMMENT 'Realized outcomes from deployed interventions; validates expected-impact estimates.';
