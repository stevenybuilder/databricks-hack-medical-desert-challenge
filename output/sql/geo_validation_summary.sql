-- Read-only geo-quality summary.
SELECT
  geo_quality,
  contradicted_or_geo_invalid_signal,
  COUNT(*) AS rows,
  ROUND(AVG(geo_distance_km_to_pincode_centroid), 1) AS avg_distance_km,
  ROUND(MAX(geo_distance_km_to_pincode_centroid), 1) AS max_distance_km
FROM workspace.default.hackathon_facility_health_cleaned
GROUP BY geo_quality, contradicted_or_geo_invalid_signal
ORDER BY rows DESC;
	