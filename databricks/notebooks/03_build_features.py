# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Build Features
# MAGIC
# MAGIC Computes the three feature tables from silver and registers them with
# MAGIC **Feature Engineering in Unity Catalog**. If the FE client is unavailable on Free
# MAGIC Edition, falls back to `CREATE OR REPLACE TABLE` + a PRIMARY KEY constraint (which is
# MAGIC sufficient to make a UC table feature-lookup-eligible) and logs a note.
# MAGIC
# MAGIC | Feature table | PK | Purpose |
# MAGIC |---|---|---|
# MAGIC | `provider_confidence_features` | `canonical_provider_id` | per-facility trust signals |
# MAGIC | `geography_access_risk_features` | `geography_id` | per-district supply/need/desert risk |
# MAGIC | `intervention_input_features` | `geography_id` | per-district intervention fit scores |
# MAGIC
# MAGIC > Telehealth viability is pinned **low/uncertain** — broadband is NOT in the dataset.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOG = "workspace"
SILVER = f"{CATALOG}.caregap_silver"
FEATURES = f"{CATALOG}.caregap_features"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {FEATURES}")

# Try to obtain a Feature Engineering client; degrade gracefully on Free Edition.
try:
    from databricks.feature_engineering import FeatureEngineeringClient

    fe = FeatureEngineeringClient()
    FE_AVAILABLE = True
    print("[ok] FeatureEngineeringClient available")
except Exception as exc:  # noqa: BLE001
    fe = None
    FE_AVAILABLE = False
    print(f"[fallback] FE client unavailable ({type(exc).__name__}: {exc}); "
          "using CREATE TABLE + PRIMARY KEY constraint instead")

# COMMAND ----------


def register_feature_table(name: str, df, primary_keys, description: str):
    """Register a feature table via FE client if available, else plain Delta + PK.

    Both paths produce a governed UC table with a primary key, which is the part
    downstream lookups depend on.
    """
    fqn = f"{FEATURES}.{name}"
    pks = primary_keys if isinstance(primary_keys, list) else [primary_keys]

    if FE_AVAILABLE:
        try:
            spark.sql(f"DROP TABLE IF EXISTS {fqn}")
            fe.create_table(
                name=fqn,
                primary_keys=pks,
                df=df,
                description=description,
            )
            print(f"[ok] FE create_table: {fqn} (pk={pks})")
            return
        except Exception as exc:  # noqa: BLE001
            print(f"[fallback] FE create_table failed for {fqn} "
                  f"({type(exc).__name__}: {exc}); writing plain Delta + PK")

    # Fallback path: plain managed Delta table with a PK constraint.
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fqn)
    for pk in pks:
        spark.sql(f"ALTER TABLE {fqn} ALTER COLUMN {pk} SET NOT NULL")
    cols = ", ".join(pks)
    spark.sql(
        f"ALTER TABLE {fqn} ADD CONSTRAINT pk_{name} PRIMARY KEY ({cols})"
    )
    spark.sql(f"COMMENT ON TABLE {fqn} IS '{description}'")
    print(f"[ok] Delta + PK: {fqn} (pk={pks})")


providers = spark.table(f"{SILVER}.providers_normalized")
locations = spark.table(f"{SILVER}.provider_locations")
quality = spark.table(f"{SILVER}.source_quality_metrics")
geo = spark.table(f"{SILVER}.geography_health_need")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `provider_confidence_features` — PK `canonical_provider_id`
# MAGIC
# MAGIC Composite confidence from existing readiness / supply-confidence / trust signals.

# COMMAND ----------

pcf = (
    quality.alias("q")
    .join(locations.select("canonical_provider_id", "geo_in_india_bbox",
                           "join_confidence", "geo_quality",
                           "pincode_is_ambiguous", "pincode_region_is_ambiguous",
                           "district_name", "state_ut").alias("l"),
          "canonical_provider_id", "left")
    .select(
        "canonical_provider_id",
        F.col("q.geography_id").alias("geography_id"),
        # source breadth
        F.coalesce(F.col("source_unique_id_occurrences"), F.lit(1)).alias("source_count"),
        # validity flags
        F.coalesce(F.col("geo_in_india_bbox"), F.lit(False)).cast("boolean").alias("geo_valid_flag"),
        (
            ~F.coalesce(F.col("pincode_is_ambiguous"), F.lit(False))
            & ~F.coalesce(F.col("pincode_region_is_ambiguous"), F.lit(False))
        ).alias("pin_district_consistent_flag"),
        F.coalesce(F.col("has_source_urls"), F.lit(False)).cast("boolean").alias("has_source_urls"),
        F.coalesce(F.col("has_contact_evidence"), F.lit(False)).cast("boolean").alias("has_contact_evidence"),
        F.coalesce(F.col("contradicted_or_geo_invalid_signal"), F.lit(False)).cast("boolean").alias("contradicted_flag"),
        F.coalesce(F.col("needs_human_review"), F.lit(False)).cast("boolean").alias("needs_human_review"),
        # staleness proxy: recency invalid/stale -> penalize. We lack exact days, so use a 0/1 staleness flag.
        (~F.coalesce(F.col("recency_valid_signal"), F.lit(False))).cast("int").alias("staleness_flag"),
        F.col("recency_status"),
        # underlying readiness / supply confidence
        F.coalesce(F.col("data_readiness_score"), F.lit(0.0)).alias("data_readiness_score"),
        F.coalesce(F.col("supply_data_confidence_score"), F.lit(0.0)).alias("supply_data_confidence_score"),
        F.coalesce(F.col("semantic_data_quality_score"), F.lit(0.0)).alias("semantic_data_quality_score"),
        F.coalesce(F.col("trustworthy_supply_signal"), F.lit(False)).cast("boolean").alias("trustworthy_supply_signal"),
        F.coalesce(F.col("semantic_missing_critical_count"), F.lit(0)).alias("semantic_missing_critical_count"),
    )
)

# Composite provider_confidence_score in [0,1]: transparent weighted blend of existing
# trust signals (claims-not-truth: this is evidence quality, not verified accuracy).
score = (
    0.35 * F.col("data_readiness_score")
    + 0.25 * F.col("supply_data_confidence_score")
    + 0.10 * F.col("semantic_data_quality_score")
    + 0.10 * F.col("geo_valid_flag").cast("double")
    + 0.05 * F.col("has_source_urls").cast("double")
    + 0.05 * F.col("has_contact_evidence").cast("double")
    + 0.10 * F.least(F.col("source_count").cast("double") / F.lit(3.0), F.lit(1.0))
    - 0.15 * F.col("staleness_flag").cast("double")
    - 0.25 * F.col("contradicted_flag").cast("double")
)
pcf = pcf.withColumn(
    "provider_confidence_score",
    F.round(F.greatest(F.lit(0.0), F.least(F.lit(1.0), score)), 4),
).withColumn(
    "confidence_band",
    F.when(F.col("provider_confidence_score") >= 0.66, F.lit("high"))
     .when(F.col("provider_confidence_score") >= 0.40, F.lit("medium"))
     .otherwise(F.lit("low")),
).withColumn("feature_built_at", F.current_timestamp())

register_feature_table(
    "provider_confidence_features",
    pcf,
    "canonical_provider_id",
    "Per-facility data-confidence features (claims-not-truth evidence quality, not verified accuracy).",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## `geography_access_risk_features` — PK `geography_id`
# MAGIC
# MAGIC Provider counts/density + NFHS condition-burden + medical-desert risk.

# COMMAND ----------

# Per-district provider counts from silver providers (joined on geography_id).
prov_counts = providers.groupBy("geography_id").agg(
    F.count("*").alias("provider_count_total"),
    F.sum(F.col("has_maternity_care_signal").cast("int")).alias("maternity_provider_count"),
    F.sum(F.col("has_emergency_care_signal").cast("int")).alias("emergency_provider_count"),
    F.sum(F.col("has_diagnostic_signal").cast("int")).alias("diagnostic_provider_count"),
    F.sum(F.col("has_ncd_care_signal").cast("int")).alias("ncd_provider_count"),
)

# NFHS condition-burden score: average of normalized "bad" indicators where higher = more burden.
# anaemia, high BP (w+m), high blood sugar (w+m), and LOW insurance coverage / LOW institutional birth.
burden = (
    F.coalesce(F.col("all_w15_49_who_are_anaemic_pct"), F.lit(0.0))
    + F.coalesce(F.col("w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"), F.lit(0.0))
    + F.coalesce(F.col("m15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct"), F.lit(0.0))
    + F.coalesce(F.col("w15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct"), F.lit(0.0))
    + F.coalesce(F.col("m15_plus_with_high_or_very_high_gt_140_mg_dl_blood_sugar_or_pct"), F.lit(0.0))
    + (F.lit(100.0) - F.coalesce(F.col("hh_member_covered_health_insurance_pct"), F.lit(0.0)))
    + (F.lit(100.0) - F.coalesce(F.col("institutional_birth_5y_pct"), F.lit(0.0)))
) / F.lit(7.0)

garf = (
    geo.join(prov_counts, "geography_id", "left")
    .select(
        "geography_id", "state_ut", "district_name", "geography_name",
        F.coalesce(F.col("provider_count_total"), F.lit(0)).alias("provider_count_total"),
        F.coalesce(F.col("maternity_provider_count"), F.lit(0)).alias("maternity_provider_count"),
        F.coalesce(F.col("emergency_provider_count"), F.lit(0)).alias("emergency_provider_count"),
        F.coalesce(F.col("diagnostic_provider_count"), F.lit(0)).alias("diagnostic_provider_count"),
        F.coalesce(F.col("ncd_provider_count"), F.lit(0)).alias("ncd_provider_count"),
        F.col("observed_facility_rows"),
        F.col("trustworthy_supply_rows").alias("trustworthy_provider_count"),
        F.col("trustworthy_supply_rate"),
        F.col("trustworthy_supply_rate_ci_low"),
        F.col("trustworthy_supply_rate_ci_high"),
        F.col("health_need_score"),
        F.round(burden, 3).alias("condition_burden_score"),
        # medical_desert_risk_score from district priority score (0-1), scaled to 0-100.
        F.round(F.coalesce(F.col("district_medical_desert_priority_score"), F.lit(0.0)) * F.lit(100.0), 2)
         .alias("medical_desert_risk_score"),
        F.col("care_gap_score"),
        F.col("trust_gap_score"),
        F.col("planning_category"),
        F.col("district_data_quality_score"),
        F.col("district_uncertainty_level"),
        F.col("critical_supply_gap_rate"),
        F.col("needs_human_review_rate"),
        # NFHS indicators kept for downstream explanation
        F.col("hh_member_covered_health_insurance_pct"),
        F.col("institutional_birth_5y_pct"),
        F.col("all_w15_49_who_are_anaemic_pct"),
    )
    # supply density proxy: trustworthy providers per observed-facility row (no population in data).
    .withColumn(
        "provider_density_proxy",
        F.round(
            F.coalesce(F.col("trustworthy_provider_count"), F.lit(0)).cast("double")
            / F.greatest(F.col("observed_facility_rows").cast("double"), F.lit(1.0)),
            4,
        ),
    )
    .withColumn(
        "risk_band",
        F.when(F.col("medical_desert_risk_score") >= 75, F.lit("severe"))
         .when(F.col("medical_desert_risk_score") >= 50, F.lit("high"))
         .when(F.col("medical_desert_risk_score") >= 25, F.lit("medium"))
         .otherwise(F.lit("low")),
    )
    .withColumn("feature_built_at", F.current_timestamp())
)

register_feature_table(
    "geography_access_risk_features",
    garf,
    "geography_id",
    "Per-district access-risk features: provider counts, density proxy, NFHS condition burden, medical-desert risk.",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## `intervention_input_features` — PK `geography_id`
# MAGIC
# MAGIC Fit scores per intervention type, consistent with the local interventions module.
# MAGIC `telehealth_viability_score` is pinned LOW because broadband is NOT in the dataset.

# COMMAND ----------

g = garf.alias("g")

# Normalize need to 0-1 (health_need_score is already roughly percentile-style).
need01 = F.least(F.greatest(F.coalesce(F.col("g.health_need_score"), F.lit(0.0)), F.lit(0.0)), F.lit(1.0))
trust_rate = F.coalesce(F.col("g.trustworthy_supply_rate"), F.lit(0.0))
care_gap = F.coalesce(F.col("g.care_gap_score"), F.lit(0.0))
ins_cov = F.coalesce(F.col("g.hh_member_covered_health_insurance_pct"), F.lit(50.0)) / F.lit(100.0)
mat_cov = F.coalesce(F.col("g.institutional_birth_5y_pct"), F.lit(50.0)) / F.lit(100.0)
ncd_burden = F.coalesce(F.col("g.all_w15_49_who_are_anaemic_pct"), F.lit(0.0)) / F.lit(100.0)
data_quality = F.coalesce(F.col("g.district_data_quality_score"), F.lit(0.5))

iif = g.select(
    "geography_id", "state_ut", "district_name", "geography_name",
    F.col("g.health_need_score"),
    F.col("g.care_gap_score"),
    F.col("g.medical_desert_risk_score"),
    F.col("g.planning_category"),
    F.col("g.provider_count_total"),
    F.col("g.trustworthy_provider_count"),
    F.col("g.district_uncertainty_level"),
    # high-confidence provider gap: need that remains after trustworthy supply is counted.
    F.round(need01 * (F.lit(1.0) - trust_rate), 4).alias("high_confidence_provider_gap"),
    # primary-care service gap: need x low overall trustworthy supply.
    F.round(need01 * (F.lit(1.0) - trust_rate), 4).alias("service_gap_primary_care"),
    F.round(need01 * (F.lit(1.0) - mat_cov), 4).alias("service_gap_maternal"),
    F.round(need01 * ncd_burden, 4).alias("service_gap_chronic_care"),
    # --- intervention fit scores (0-1) ---
    # Mobile primary care: high need + low trustworthy supply.
    F.round(F.least(need01 * (F.lit(1.0) - trust_rate) * F.lit(1.2), F.lit(1.0)), 4)
     .alias("mobile_clinic_fit_score"),
    # Transport voucher: providers exist but care gap persists.
    F.round(F.least(F.col("g.provider_density_proxy") * care_gap * F.lit(1.5), F.lit(1.0)), 4)
     .alias("transport_voucher_fit_score"),
    # Pharmacy NCD screening: chronic burden present.
    F.round(F.least(ncd_burden * F.lit(1.5), F.lit(1.0)), 4)
     .alias("pharmacy_care_fit_score"),
    # AAM/HWC upgrade: some primary-care presence but capacity insufficient.
    F.round(F.least((F.lit(1.0) - trust_rate) * need01, F.lit(1.0)), 4)
     .alias("aam_upgrade_fit_score"),
    # PM-JAY enrollment: affordability barrier (low insurance coverage) + need.
    F.round(F.least((F.lit(1.0) - ins_cov) * need01 * F.lit(1.3), F.lit(1.0)), 4)
     .alias("pmjay_enrollment_fit_score"),
    # FQHC partner: high need + decent data quality so partnership is actionable.
    F.round(F.least(need01 * data_quality, F.lit(1.0)), 4)
     .alias("fqhc_partner_fit_score"),
    # Telehealth: PINNED LOW — broadband NOT in dataset. Capped at 0.25 with uncertainty flag.
    F.round(F.least(need01 * F.lit(0.25), F.lit(0.25)), 4)
     .alias("telehealth_viability_score"),
    F.lit("low").alias("telehealth_confidence"),
    F.lit("broadband / digital-access signal NOT in dataset; telehealth viability is uncertain")
     .alias("telehealth_data_limitation"),
).withColumn("feature_built_at", F.current_timestamp())

register_feature_table(
    "intervention_input_features",
    iif,
    "geography_id",
    "Per-district intervention fit scores. Telehealth pinned low/uncertain (no broadband data).",
)

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {FEATURES}"))
