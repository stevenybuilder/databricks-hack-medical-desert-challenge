# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Clean Silver
# MAGIC
# MAGIC Builds the governed **silver** tables in `workspace.caregap_silver` by selecting /
# MAGIC renaming from the already-cleaned hackathon tables. **Heavy cleaning was done locally**
# MAGIC — this notebook governs the data and maps columns onto the documented silver contract.
# MAGIC
# MAGIC Silver tables:
# MAGIC - `providers_normalized` — one row per facility (PK `canonical_provider_id`)
# MAGIC - `provider_locations` — geo / address per facility
# MAGIC - `geography_health_need` — one row per district (PK `geography_id`)
# MAGIC - `source_quality_metrics` — provenance / trust signals per facility
# MAGIC
# MAGIC Keys:
# MAGIC - `canonical_provider_id` = `unique_id`
# MAGIC - `geography_id` = `concat(state_ut, '|', district_name)`
# MAGIC
# MAGIC Source: prefers bronze (`caregap_bronze.raw_*_cleaned`); falls back to
# MAGIC `workspace.default.hackathon_*` if bronze not yet built.
# MAGIC
# MAGIC > Claims-not-truth posture: facility fields are extracted web claims, not verified facts.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOG = "workspace"
BRONZE = f"{CATALOG}.caregap_bronze"
SILVER = f"{CATALOG}.caregap_silver"
DEFAULT = f"{CATALOG}.default"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SILVER}")

# COMMAND ----------


def first_existing(*fqns: str):
    """Return the first table that exists, else raise."""
    for fqn in fqns:
        try:
            spark.sql(f"DESCRIBE TABLE {fqn}")
            return fqn
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(f"None of these source tables exist: {fqns}")


FACILITY_SRC = first_existing(
    f"{BRONZE}.raw_facility_health_cleaned",
    f"{DEFAULT}.hackathon_facility_health_cleaned",
)
DISTRICT_SRC = first_existing(
    f"{BRONZE}.raw_district_health_cleaned",
    f"{DEFAULT}.hackathon_district_health_facility_cleaned",
)
print("facility source :", FACILITY_SRC)
print("district source :", DISTRICT_SRC)

fac = spark.table(FACILITY_SRC)
dist = spark.table(DISTRICT_SRC)

# geography_id key expression, reused everywhere.
GEO_ID = F.concat_ws("|", F.col("state_ut"), F.col("district_name"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## `providers_normalized` — PK `canonical_provider_id`

# COMMAND ----------

providers = fac.select(
    F.col("unique_id").alias("canonical_provider_id"),
    "facility_name",
    F.col("organization_type"),
    F.col("facilityTypeId").alias("facility_type"),
    F.col("operatorTypeId").alias("operator_type"),
    "state_ut",
    "district_name",
    GEO_ID.alias("geography_id"),
    # supply claims (claims-not-truth: keep observed + estimate side by side)
    "capacity_num", "capacity_status", "capacity_estimate",
    "capacity_estimate_interval_low", "capacity_estimate_interval_high",
    "capacity_confidence", "capacity_is_estimated", "capacity_display_value",
    "number_doctors_num", "doctor_count_status", "doctor_count_estimate",
    "doctor_count_estimate_interval_low", "doctor_count_estimate_interval_high",
    "doctor_count_confidence", "doctor_count_is_estimated", "doctor_count_display_value",
    "year_established_num", "year_established_status",
    # service-line signals (from claim text)
    "has_maternity_care_signal", "has_emergency_care_signal",
    "has_diagnostic_signal", "has_ncd_care_signal",
    "has_description", "has_specialties", "has_procedure",
    "has_equipment", "has_capability",
    # outlier / dedup
    "capacity_num_extreme_outlier", "number_doctors_num_extreme_outlier",
    "source_unique_id_occurrences", "source_duplicate_unique_id",
    "claim_text",
).withColumn("silver_built_at", F.current_timestamp())

providers.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{SILVER}.providers_normalized"
)
spark.sql(
    f"ALTER TABLE {SILVER}.providers_normalized "
    "ALTER COLUMN canonical_provider_id SET NOT NULL"
)
spark.sql(
    f"ALTER TABLE {SILVER}.providers_normalized "
    "ADD CONSTRAINT pk_providers PRIMARY KEY (canonical_provider_id)"
)
print("providers_normalized:", spark.table(f"{SILVER}.providers_normalized").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `provider_locations` — PK `canonical_provider_id`

# COMMAND ----------

locations = fac.select(
    F.col("unique_id").alias("canonical_provider_id"),
    GEO_ID.alias("geography_id"),
    "address_line1", "address_line2", "address_line3",
    "address_city", "address_stateOrRegion", "address_zipOrPostcode",
    F.col("pincode_extracted"),
    "pincode_primary_district", "pincode_primary_state",
    "pincode_is_ambiguous", "pincode_region_is_ambiguous",
    F.col("facility_latitude").alias("latitude"),
    F.col("facility_longitude").alias("longitude"),
    "geo_in_india_bbox",
    "pincode_centroid_latitude", "pincode_centroid_longitude",
    "geo_distance_km_to_pincode_centroid",
    "geo_quality",
    "join_strategy", "join_confidence", "join_match_score", "join_uncertainty_reason",
    "state_ut", "district_name",
).withColumn("silver_built_at", F.current_timestamp())

locations.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{SILVER}.provider_locations"
)
spark.sql(
    f"ALTER TABLE {SILVER}.provider_locations "
    "ALTER COLUMN canonical_provider_id SET NOT NULL"
)
spark.sql(
    f"ALTER TABLE {SILVER}.provider_locations "
    "ADD CONSTRAINT pk_locations PRIMARY KEY (canonical_provider_id)"
)
print("provider_locations:", spark.table(f"{SILVER}.provider_locations").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `source_quality_metrics` — PK `canonical_provider_id`
# MAGIC
# MAGIC Provenance + trust signals used downstream by `provider_confidence_features`.

# COMMAND ----------

quality = fac.select(
    F.col("unique_id").alias("canonical_provider_id"),
    GEO_ID.alias("geography_id"),
    "data_readiness_score",
    "supply_data_confidence_score",
    "semantic_data_quality_score",
    "semantic_missing_critical_count",
    "critical_supply_gap_flag",
    "needs_human_review",
    "trustworthy_supply_signal",
    "contradicted_or_geo_invalid_signal",
    "has_source_urls",
    "has_contact_evidence",
    "recency_status", "recency_valid_signal", "recency_confidence",
    "source_unique_id_occurrences",
    "source_duplicate_unique_id",
    "source_urls",
    "officialWebsite", "officialPhone", "email", "source_content_id",
).withColumn("silver_built_at", F.current_timestamp())

quality.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{SILVER}.source_quality_metrics"
)
spark.sql(
    f"ALTER TABLE {SILVER}.source_quality_metrics "
    "ALTER COLUMN canonical_provider_id SET NOT NULL"
)
spark.sql(
    f"ALTER TABLE {SILVER}.source_quality_metrics "
    "ADD CONSTRAINT pk_quality PRIMARY KEY (canonical_provider_id)"
)
print("source_quality_metrics:", spark.table(f"{SILVER}.source_quality_metrics").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `geography_health_need` — PK `geography_id`
# MAGIC
# MAGIC One row per district. NFHS need indicators + district supply/trust aggregates.

# COMMAND ----------

geo = dist.select(
    GEO_ID.alias("geography_id"),
    "state_ut", "district_name",
    F.concat_ws(", ", F.col("district_name"), F.col("state_ut")).alias("geography_name"),
    # need / demand
    "health_need_score",
    "district_medical_desert_priority_score",
    "care_gap_score",
    "trust_gap_score",
    "best_care_signal_score",
    "planning_category",
    # supply observed
    "observed_facility_rows", "unique_facility_ids", "unique_pincodes_observed",
    "trustworthy_supply_rows", "trustworthy_supply_rate",
    "trustworthy_supply_rate_ci_low", "trustworthy_supply_rate_ci_high",
    "needs_human_review_rows", "needs_human_review_rate",
    "critical_supply_gap_rate",
    "contradicted_or_geo_invalid_rate",
    # service-specific rates
    "maternity_signal_rate", "emergency_signal_rate",
    "diagnostic_signal_rate", "ncd_signal_rate",
    # data quality
    "district_data_quality_score", "district_uncertainty_level",
    "avg_join_confidence", "avg_data_readiness_score",
    "source_url_rate", "contact_evidence_rate",
    # capacity context
    "observed_capacity_sum", "observed_capacity_median",
    "observed_doctors_sum", "observed_doctors_median",
    # citations
    "sample_facility_names", "sample_claim_evidence", "sample_source_urls",
    "facility_supply_warning",
    # NFHS condition burden indicators (need-side context)
    "hh_member_covered_health_insurance_pct",
    "institutional_birth_5y_pct",
    "births_attended_by_skilled_hp_5y_10_pct",
    "births_delivered_by_csection_5y_pct",
    "all_w15_49_who_are_anaemic_pct",
    "w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct",
    "w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    "m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct",
    "women_age_30_49_years_ever_undergone_a_cervical_screen_pct",
    "women_age_30_49_years_ever_undergone_a_breast_exam_pct",
    "women_age_30_49_years_ever_undergone_an_oral_cancer_exam_pct",
).withColumn("silver_built_at", F.current_timestamp())

geo.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{SILVER}.geography_health_need"
)
spark.sql(
    f"ALTER TABLE {SILVER}.geography_health_need ALTER COLUMN geography_id SET NOT NULL"
)
spark.sql(
    f"ALTER TABLE {SILVER}.geography_health_need "
    "ADD CONSTRAINT pk_geo_need PRIMARY KEY (geography_id)"
)
print("geography_health_need:", spark.table(f"{SILVER}.geography_health_need").count())

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {SILVER}"))
