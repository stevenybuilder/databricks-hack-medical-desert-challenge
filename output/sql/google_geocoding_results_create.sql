-- Schema-only template. Row-level Google Maps geocoding load SQL is generated
-- locally as output/sql/google_geocoding_results_generated.sql and ignored by git.
-- Run scripts/run_google_geocoding_validation.py to regenerate current results.

CREATE TABLE IF NOT EXISTS workspace.default.hackathon_google_geocoding_results (
  unique_id STRING,
  facility_name STRING,
  requested_address STRING,
  google_status STRING,
  google_error_message STRING,
  google_result_count INT,
  formatted_address STRING,
  place_id STRING,
  location_type STRING,
  partial_match BOOLEAN,
  google_latitude DOUBLE,
  google_longitude DOUBLE,
  google_types STRING,
  plus_code_global STRING,
  plus_code_compound STRING,
  expected_pincode STRING,
  expected_state STRING,
  expected_city STRING,
  pincode_match BOOLEAN,
  state_match BOOLEAN,
  city_match BOOLEAN,
  distance_km_current_to_google DOUBLE,
  prior_geo_quality STRING,
  prior_fuzzy_precheck_status STRING,
  prior_reconciliation_status STRING,
  external_validation_action STRING,
  google_validation_status STRING
);
