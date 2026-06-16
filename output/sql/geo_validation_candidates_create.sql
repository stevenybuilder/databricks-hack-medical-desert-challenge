-- Creates the candidate table for geo validation.
-- Run with:
-- databricks experimental aitools tools query --profile 7474647301321645 \
--   --warehouse 1b331b704066b677 --file output/sql/geo_validation_candidates_create.sql

CREATE OR REPLACE TABLE workspace.default.hackathon_geo_validation_candidates AS
WITH base AS (
  SELECT
    unique_id,
    facility_name,
    facilityTypeId,
    pincode_extracted,
    pincode_primary_district,
    pincode_primary_state,
    pincode_n_districts,
    pincode_n_states,
    pincode_is_ambiguous,
    district_name,
    state_ut,
    address_line1,
    address_line2,
    address_line3,
    address_city,
    address_stateOrRegion,
    address_zipOrPostcode,
    facility_latitude,
    facility_longitude,
    geo_quality,
    geo_distance_km_to_pincode_centroid,
    contradicted_or_geo_invalid_signal,
    join_strategy,
    join_confidence,
    join_match_score,
    join_uncertainty_reason,
    data_readiness_score,
    health_need_score,
    CAST(NULL AS DOUBLE) AS semantic_data_quality_score,
    CAST(NULL AS DOUBLE) AS supply_data_confidence_score,
    medical_desert_priority_score,
    regexp_extract(concat(coalesce(cast(pincode_extracted AS STRING), ''), ' ', coalesce(address_zipOrPostcode, '')), '([1-9][0-9]{5})', 1) AS pincode_extracted_clean,
    regexp_replace(lower(coalesce(address_city, '')), '[^a-z0-9]+', '') AS facility_city_norm_review,
    regexp_replace(lower(coalesce(address_stateOrRegion, '')), '[^a-z0-9]+', '') AS facility_state_norm_review,
    regexp_replace(lower(coalesce(pincode_primary_district, '')), '[^a-z0-9]+', '') AS pincode_district_norm_review,
    regexp_replace(lower(coalesce(pincode_primary_state, '')), '[^a-z0-9]+', '') AS pincode_state_norm_review,
    concat_ws(', ',
      facility_name,
      address_line1,
      address_line2,
      address_line3,
      address_city,
      address_stateOrRegion,
      address_zipOrPostcode,
      'India'
    ) AS raw_india_address
  FROM workspace.default.hackathon_facility_health_cleaned
  WHERE contradicted_or_geo_invalid_signal
     OR lower(geo_quality) RLIKE 'outside|far|moderate|missing'
     OR facility_latitude IS NULL
     OR facility_longitude IS NULL
  ORDER BY
    CASE WHEN contradicted_or_geo_invalid_signal THEN 1 ELSE 0 END DESC,
    coalesce(geo_distance_km_to_pincode_centroid, 0) DESC
  LIMIT 250
),
scored AS (
  SELECT
    *,
    CASE
      WHEN facility_state_norm_review = '' OR pincode_state_norm_review = '' THEN 'missing'
      WHEN facility_state_norm_review = pincode_state_norm_review THEN 'match'
      ELSE 'conflict'
    END AS state_pincode_state_match,
    CASE
      WHEN facility_city_norm_review = '' OR pincode_district_norm_review = '' THEN NULL
      ELSE ROUND(
        1.0 - (
          levenshtein(facility_city_norm_review, pincode_district_norm_review)
          / CAST(greatest(length(facility_city_norm_review), length(pincode_district_norm_review), 1) AS DOUBLE)
        ),
        3
      )
    END AS city_pincode_district_similarity
  FROM base
)
SELECT
  *,
  concat_ws(';',
    CASE WHEN pincode_extracted_clean = '' THEN 'missing_or_unparseable_pin' END,
    CASE WHEN coalesce(pincode_is_ambiguous, false) THEN 'ambiguous_pin_bridge' END,
    CASE WHEN state_pincode_state_match = 'conflict' THEN 'state_pin_conflict' END,
    CASE WHEN city_pincode_district_similarity < 0.72 THEN 'city_pin_district_conflict' END,
    CASE WHEN coalesce(join_confidence, 0) < 0.8 THEN 'weak_health_join' END
  ) AS fuzzy_precheck_reasons,
  CASE
    WHEN pincode_extracted_clean = '' THEN 'missing_or_unparseable_pin'
    WHEN coalesce(pincode_is_ambiguous, false) THEN 'ambiguous_pin_bridge'
    WHEN state_pincode_state_match = 'conflict' THEN 'state_pin_conflict'
    WHEN city_pincode_district_similarity < 0.72 THEN 'city_pin_district_conflict'
    WHEN coalesce(join_confidence, 0) < 0.8 THEN 'weak_health_join'
    ELSE 'fuzzy_ok'
  END AS fuzzy_precheck_status,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN 'replace_coordinate_with_external_geocode'
    WHEN lower(geo_quality) LIKE '%missing%' THEN 'geocode_missing_coordinate'
    WHEN lower(geo_quality) LIKE '%far%' THEN 'geocode_and_compare_pincode_district'
    WHEN lower(geo_quality) LIKE '%moderate%' AND coalesce(medical_desert_priority_score, 0) >= 0.6 THEN 'high_impact_geocode_precision_check'
    WHEN lower(geo_quality) LIKE '%moderate%' THEN 'batch_geocode_precision_check'
    WHEN contradicted_or_geo_invalid_signal THEN 'external_source_contradiction_check'
    ELSE 'monitor'
  END AS external_validation_action,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN 50.0
    WHEN lower(geo_quality) LIKE '%far%' THEN 10.0
    WHEN lower(geo_quality) LIKE '%moderate%' THEN 2.0
    WHEN lower(geo_quality) LIKE '%missing%' THEN 10.0
    WHEN contradicted_or_geo_invalid_signal THEN 5.0
    ELSE 0.1
  END AS pre_geocode_uncertainty_band_low_km,
  CASE
    WHEN lower(geo_quality) LIKE '%outside%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 250.0), 250.0), 5000.0)
    WHEN lower(geo_quality) LIKE '%far%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 50.0), 50.0), 2500.0)
    WHEN lower(geo_quality) LIKE '%moderate%' THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 10.0), 10.0), 250.0)
    WHEN lower(geo_quality) LIKE '%missing%' THEN 250.0
    WHEN contradicted_or_geo_invalid_signal THEN least(greatest(coalesce(geo_distance_km_to_pincode_centroid, 25.0), 25.0), 1000.0)
    ELSE 5.0
  END AS pre_geocode_uncertainty_band_high_km,
  'Store status, formatted_address, place_id, geometry.location, geometry.location_type, partial_match, plus_code, provider, and timestamp.' AS google_response_fields_to_store,
  concat(
    'https://maps.googleapis.com/maps/api/geocode/json?address=',
    url_encode(raw_india_address),
    '&components=country:IN&key=$GOOGLE_MAPS_API_KEY'
  ) AS google_geocode_url_template
FROM scored;
