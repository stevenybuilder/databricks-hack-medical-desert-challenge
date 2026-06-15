-- Creates a Databricks AI "janitor" table for geo validation.
-- Run after output/sql/geo_validation_candidates_create.sql.

CREATE OR REPLACE TABLE workspace.default.hackathon_geo_address_janitor AS
WITH model_raw AS (
  SELECT
    unique_id,
    facility_name,
    raw_india_address,
    ai_query(
      'databricks-gemini-3-5-flash',
      concat('You clean Indian healthcare facility addresses for geocoding.
Return only valid JSON with these keys:
door_or_plot, floor_or_unit, landmark_context, landmark_name, locality, city,
state, pincode, geocoder_query, confidence, notes.

Rules:
- Do not invent coordinates.
- Preserve useful landmarks such as Near, Opposite, Behind, Next to.
- Remove floor/room/delivery instructions from geocoder_query unless needed.
- Use a 6 digit Indian PIN only if present in the source text.
- Always keep the query India-specific.
- confidence is 0.0 to 1.0.
\nAddress text: ', raw_india_address)
    ) AS model_response
  FROM workspace.default.hackathon_geo_validation_candidates
),
json_ready AS (
  SELECT
    *,
    coalesce(
      nullif(regexp_extract(model_response, '(?s)(\\{.*\\})', 1), ''),
      model_response
    ) AS model_response_json
  FROM model_raw
)
SELECT
  unique_id,
  facility_name,
  raw_india_address,
  model_response,
  model_response_json,
  from_json(
    model_response_json,
    'door_or_plot STRING, floor_or_unit STRING, landmark_context STRING, landmark_name STRING, locality STRING, city STRING, state STRING, pincode STRING, geocoder_query STRING, confidence DOUBLE, notes STRING'
  ) AS parsed_address
FROM json_ready;
