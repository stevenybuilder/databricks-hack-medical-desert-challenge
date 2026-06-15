-- Reconciles LLM-parsed addresses with the existing pincode/district fuzzy signals.
-- Run after output/sql/geo_address_janitor_ai_query.sql.

CREATE OR REPLACE TABLE workspace.default.hackathon_geo_fuzzy_reconciliation AS
WITH joined AS (
  SELECT
    c.*,
    j.model_response,
    j.parsed_address,
    regexp_replace(lower(coalesce(j.parsed_address.city, '')), '[^a-z0-9]+', '') AS parsed_city_norm,
    regexp_replace(lower(coalesce(j.parsed_address.state, '')), '[^a-z0-9]+', '') AS parsed_state_norm,
    regexp_extract(cast(j.parsed_address.pincode AS STRING), '([1-9][0-9]{5})', 1) AS parsed_pincode_clean
  FROM workspace.default.hackathon_geo_validation_candidates c
  LEFT JOIN workspace.default.hackathon_geo_address_janitor j USING (unique_id)
),
scored AS (
  SELECT
    *,
    CASE
      WHEN parsed_city_norm = '' OR pincode_district_norm_review = '' THEN NULL
      ELSE ROUND(
        1.0 - (
          levenshtein(parsed_city_norm, pincode_district_norm_review)
          / CAST(greatest(length(parsed_city_norm), length(pincode_district_norm_review), 1) AS DOUBLE)
        ),
        3
      )
    END AS parsed_city_pincode_district_similarity,
    CASE
      WHEN parsed_state_norm = '' OR pincode_state_norm_review = '' THEN 'missing'
      WHEN parsed_state_norm = pincode_state_norm_review THEN 'match'
      ELSE 'conflict'
    END AS parsed_state_pincode_state_match,
    CASE
      WHEN coalesce(parsed_pincode_clean, '') = '' OR coalesce(pincode_extracted_clean, '') = '' THEN 'missing'
      WHEN parsed_pincode_clean = pincode_extracted_clean THEN 'match'
      ELSE 'conflict'
    END AS parsed_pin_match
  FROM joined
)
SELECT
  *,
  CASE
    WHEN parsed_address IS NULL OR parsed_address.geocoder_query IS NULL OR parsed_address.confidence IS NULL THEN 'llm_parse_missing'
    WHEN parsed_pin_match = 'conflict' THEN 'parsed_pin_conflict'
    WHEN parsed_state_pincode_state_match = 'conflict' THEN 'parsed_state_conflict'
    WHEN parsed_city_pincode_district_similarity < 0.72 THEN 'parsed_city_district_conflict'
    WHEN coalesce(parsed_address.confidence, 0) < 0.65 THEN 'low_llm_parse_confidence'
    WHEN fuzzy_precheck_status != 'fuzzy_ok' THEN 'pre_geocoder_review'
    ELSE 'ready_for_geocoder'
  END AS reconciliation_status,
  concat(
    'https://maps.googleapis.com/maps/api/geocode/json?address=',
    url_encode(coalesce(parsed_address.geocoder_query, raw_india_address)),
    '&components=country:IN&key=$GOOGLE_MAPS_API_KEY'
  ) AS cleaned_google_geocode_url_template
FROM scored;
