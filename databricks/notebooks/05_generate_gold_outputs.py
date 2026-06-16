# Databricks notebook source
# MAGIC %md
# MAGIC # 05 · Generate Gold Outputs
# MAGIC
# MAGIC Materializes the **gold** tables in `workspace.caregap_gold` that the app reads.
# MAGIC Matches the doc's gold schemas AND `app/lib/data.py` expectations.
# MAGIC
# MAGIC | Gold table | Grain |
# MAGIC |---|---|
# MAGIC | `medical_desert_scores` | district (`geography_id`) |
# MAGIC | `intervention_recommendations` | district × intervention |
# MAGIC | `provider_confidence` | facility (`canonical_provider_id`) |
# MAGIC | `scenario_simulations` | scenario row (example high-risk districts) |
# MAGIC | `review_queue` | facility (prioritized) |
# MAGIC
# MAGIC Parity strategy:
# MAGIC - `intervention_recommendations`: prefer the uploaded volume CSV
# MAGIC   `/Volumes/workspace/default/hackathon_cleaned/intervention_recommendations.csv`;
# MAGIC   else recompute from features.
# MAGIC - `provider_confidence`: join `conformal_facility_sets.csv` posteriors if present.
# MAGIC
# MAGIC All tables carry `model_version` + `scored_at` / `created_at`.

# COMMAND ----------

from pyspark.sql import functions as F

CATALOG = "workspace"
SILVER = f"{CATALOG}.caregap_silver"
FEATURES = f"{CATALOG}.caregap_features"
GOLD = f"{CATALOG}.caregap_gold"
VOLUME = "/Volumes/workspace/default/hackathon_cleaned"

MODEL_VERSION = "caregap-rules-v1"
INTERVENTION_POLICY = "intervention-policy-v1"
CONFORMAL_VERSION = "conformal-proxy-v1"

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {GOLD}")


def volume_csv(name: str):
    """Read a CSV from the UC volume; return None if absent (graceful fallback)."""
    path = f"{VOLUME}/{name}"
    try:
        df = (
            spark.read.option("header", "true").option("inferSchema", "true")
            .option("multiLine", "true").option("escape", '"')
            .csv(path)
        )
        df.take(1)  # force read to surface missing-file errors here
        print(f"[ok] read volume CSV: {path}")
        return df
    except Exception as exc:  # noqa: BLE001
        print(f"[fallback] volume CSV not available: {path} ({type(exc).__name__})")
        return None


providers = spark.table(f"{SILVER}.providers_normalized")
locations = spark.table(f"{SILVER}.provider_locations")
quality = spark.table(f"{SILVER}.source_quality_metrics")
garf = spark.table(f"{FEATURES}.geography_access_risk_features")
iif = spark.table(f"{FEATURES}.intervention_input_features")
pcf = spark.table(f"{FEATURES}.provider_confidence_features")
geo = spark.table(f"{SILVER}.geography_health_need")

# COMMAND ----------

# MAGIC %md
# MAGIC ## `medical_desert_scores`

# COMMAND ----------

# top_risk_drivers as a JSON array of the strongest contributing signals.
drivers = F.to_json(F.array(
    F.struct(F.lit("provider_gap").alias("driver"),
             F.round(F.coalesce(F.col("care_gap_score"), F.lit(0.0)), 3).alias("value")),
    F.struct(F.lit("condition_burden").alias("driver"),
             F.round(F.coalesce(F.col("condition_burden_score"), F.lit(0.0)), 3).alias("value")),
    F.struct(F.lit("trust_gap").alias("driver"),
             F.round(F.coalesce(F.col("trust_gap_score"), F.lit(0.0)), 3).alias("value")),
))

mds = (
    garf.select(
        "geography_id",
        F.col("geography_name"),
        F.col("state_ut").alias("state"),
        F.col("district_name").alias("district"),
        F.round(F.col("medical_desert_risk_score"), 2).alias("medical_desert_risk_score"),
        F.col("risk_band"),
        drivers.alias("top_risk_drivers"),
        F.round(F.coalesce(F.col("care_gap_score"), F.lit(0.0)), 3).alias("provider_gap_score"),
        F.round(F.coalesce(F.col("trust_gap_score"), F.lit(0.0)), 3).alias("travel_burden_score"),
        F.round(F.coalesce(F.col("condition_burden_score"), F.lit(0.0)), 3).alias("vulnerability_score"),
        F.round(F.coalesce(F.col("district_data_quality_score"), F.lit(0.0)), 3).alias("confidence_score"),
        F.col("provider_count_total"),
        F.col("trustworthy_provider_count"),
        F.col("district_uncertainty_level"),
        F.col("planning_category"),
    )
    .withColumn("model_version", F.lit(MODEL_VERSION))
    .withColumn("scored_at", F.current_timestamp())
)

mds.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.medical_desert_scores"
)
print("medical_desert_scores:", spark.table(f"{GOLD}.medical_desert_scores").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `intervention_recommendations` (prefer volume CSV for parity)

# COMMAND ----------

GEO_ID = F.concat_ws("|", F.col("state_ut"), F.col("district_name"))
ir_csv = volume_csv("intervention_recommendations.csv")

if ir_csv is not None:
    ir = (
        ir_csv.select(
            GEO_ID.alias("geography_id"),
            F.col("state_ut").alias("state"),
            F.col("district_name").alias("district"),
            F.col("rank").cast("int").alias("rank"),
            F.col("intervention").alias("intervention_type"),
            F.col("ev_score").cast("double").alias("expected_impact_score"),
            F.col("expected_access_gain").cast("double").alias("expected_access_gain"),
            F.col("est_cost_tier").alias("implementation_complexity_score"),
            F.col("confidence").alias("recommendation_confidence"),
            F.col("p_addresses_need").cast("double").alias("p_addresses_need"),
            F.col("p_wrong").cast("double").alias("p_wrong"),
            F.col("trigger_signals"),
            F.col("rationale").alias("why_recommended"),
            F.col("not_recommended_flag"),
            F.col("not_recommended_reason"),
        )
        .withColumn(
            "data_limitations",
            F.when(F.lower(F.col("intervention_type")).contains("telehealth"),
                   F.lit("Telehealth viability uncertain: broadband / digital-access signal NOT in dataset."))
             .otherwise(F.coalesce(F.col("not_recommended_reason"),
                                   F.lit("Scores derived from extracted claims, not verified facility audits."))),
        )
    )
    src_note = "from volume CSV (parity)"
else:
    # Fallback: recompute a ranked recommendation set from intervention_input_features.
    fit_cols = [
        ("Mobile primary care clinic", "mobile_clinic_fit_score"),
        ("Transportation vouchers", "transport_voucher_fit_score"),
        ("Pharmacy-based chronic care screening", "pharmacy_care_fit_score"),
        ("AAM / HWC upgrade", "aam_upgrade_fit_score"),
        ("PM-JAY / insurance enrollment support", "pmjay_enrollment_fit_score"),
        ("FQHC partnership / referral route", "fqhc_partner_fit_score"),
        ("Telehealth-first program", "telehealth_viability_score"),
    ]
    stacked = None
    for itype, col in fit_cols:
        part = iif.select(
            "geography_id", F.col("state_ut").alias("state"),
            F.col("district_name").alias("district"),
            F.lit(itype).alias("intervention_type"),
            F.round(F.col(col), 4).alias("expected_impact_score"),
        )
        stacked = part if stacked is None else stacked.unionByName(part)

    from pyspark.sql.window import Window

    w = Window.partitionBy("geography_id").orderBy(F.col("expected_impact_score").desc())
    ir = (
        stacked
        .withColumn("rank", F.row_number().over(w))
        .withColumn("expected_access_gain", F.col("expected_impact_score"))
        .withColumn("implementation_complexity_score",
                    F.when(F.col("intervention_type").contains("Mobile"), F.lit("high"))
                     .when(F.col("intervention_type").contains("FQHC"), F.lit("high"))
                     .otherwise(F.lit("medium")))
        .withColumn("recommendation_confidence",
                    F.when(F.col("intervention_type").contains("Telehealth"), F.lit("Low"))
                     .when(F.col("expected_impact_score") >= 0.5, F.lit("Medium"))
                     .otherwise(F.lit("Low")))
        .withColumn("p_addresses_need", F.col("expected_impact_score"))
        .withColumn("p_wrong", F.round(F.lit(1.0) - F.col("expected_impact_score"), 4))
        .withColumn("trigger_signals", F.lit("recomputed from intervention_input_features"))
        .withColumn("why_recommended",
                    F.concat(F.lit("Fit score "), F.col("expected_impact_score").cast("string"),
                             F.lit(" for "), F.col("intervention_type")))
        .withColumn("not_recommended_flag",
                    F.col("intervention_type").contains("Telehealth"))
        .withColumn("not_recommended_reason",
                    F.when(F.col("intervention_type").contains("Telehealth"),
                           F.lit("broadband not in dataset")).otherwise(F.lit(None).cast("string")))
        .withColumn("data_limitations",
                    F.when(F.col("intervention_type").contains("Telehealth"),
                           F.lit("Telehealth viability uncertain: broadband NOT in dataset."))
                     .otherwise(F.lit("Scores derived from extracted claims, not verified facility audits.")))
    )
    src_note = "recomputed from features (volume CSV absent)"

ir = (
    ir.withColumn("model_version", F.lit(INTERVENTION_POLICY))
      .withColumn("created_at", F.current_timestamp())
)
ir.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.intervention_recommendations"
)
print(f"intervention_recommendations ({src_note}):",
      spark.table(f"{GOLD}.intervention_recommendations").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `provider_confidence` (join conformal posteriors if present)

# COMMAND ----------

conformal = volume_csv("conformal_facility_sets.csv")

base = (
    pcf.alias("f")
    .join(providers.select("canonical_provider_id", "facility_name", "facility_type",
                           "state_ut", "district_name").alias("p"),
          "canonical_provider_id", "left")
    .join(locations.select("canonical_provider_id", "latitude", "longitude").alias("l"),
          "canonical_provider_id", "left")
    .join(quality.select("canonical_provider_id", "source_urls", "recency_status").alias("q"),
          "canonical_provider_id", "left")
    .select(
        "canonical_provider_id",
        F.col("facility_name").alias("provider_name"),
        F.col("facility_type"),
        F.col("state_ut").alias("state"),
        F.col("district_name").alias("district"),
        F.col("latitude"),
        F.col("longitude"),
        F.col("f.has_source_urls"),
        F.col("f.has_contact_evidence"),
        F.col("f.source_count"),
        F.col("f.geo_valid_flag"),
        F.col("f.pin_district_consistent_flag"),
        F.col("f.contradicted_flag"),
        F.col("f.needs_human_review"),
        F.col("f.provider_confidence_score"),
        F.col("f.confidence_band"),
        F.col("f.recency_status").alias("last_verified_or_seen"),
        F.col("source_urls"),
    )
    # conflict_summary: human-readable note from the flags.
    .withColumn(
        "conflict_summary",
        F.concat_ws("; ",
            F.when(F.col("contradicted_flag"), F.lit("contradicted/geo-invalid")),
            F.when(~F.col("geo_valid_flag"), F.lit("coordinates outside India bbox")),
            F.when(~F.col("pin_district_consistent_flag"), F.lit("ambiguous PIN/region")),
            F.when(~F.col("has_source_urls"), F.lit("no source URL")),
            F.when(F.col("needs_human_review"), F.lit("flagged for review")),
        ),
    )
)

if conformal is not None:
    conf = conformal.select(
        F.col("unique_id").alias("canonical_provider_id"),
        F.col("validity_posterior").cast("double").alias("validity_posterior"),
        F.col("validity_action"),
        F.col("conformal_set"),
        F.col("conformal_decision"),
    )
    pc = base.join(conf, "canonical_provider_id", "left")
    conf_note = "with conformal posteriors"
else:
    pc = (
        base.withColumn("validity_posterior", F.col("provider_confidence_score"))
            .withColumn("validity_action",
                        F.when(F.col("confidence_band") == "high", F.lit("auto-accept"))
                         .when(F.col("confidence_band") == "medium", F.lit("merge-or-review"))
                         .otherwise(F.lit("human-review")))
            .withColumn("conformal_set", F.lit(None).cast("string"))
            .withColumn("conformal_decision", F.lit(None).cast("string"))
    )
    conf_note = "conformal CSV absent — posterior = confidence score"

pc = (
    pc.withColumn("model_version", F.lit(CONFORMAL_VERSION))
      .withColumn("scored_at", F.current_timestamp())
)
pc.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.provider_confidence"
)
print(f"provider_confidence ({conf_note}):",
      spark.table(f"{GOLD}.provider_confidence").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `scenario_simulations` — example what-if rows for high-risk districts
# MAGIC
# MAGIC Deterministic sensitivity model: adding trustworthy primary-care supply lowers risk.
# MAGIC One scenario per top-N high-risk district (conservative assumptions).

# COMMAND ----------

TOP_N = 25
high_risk = (
    garf.orderBy(F.col("medical_desert_risk_score").desc()).limit(TOP_N)
)

# Conservative deterministic levers: +1 mobile clinic reduces risk by a capped fraction
# of the trust gap; population-helped is a coarse proxy (no population in data, so use
# observed-facility-row-weighted estimate and label as estimate).
clinics_added = F.lit(1)
risk_before = F.col("medical_desert_risk_score")
# improvement scales with remaining trust gap (1 - trustworthy_supply_rate), capped at 18 pts.
improvement = F.least(
    (F.lit(1.0) - F.coalesce(F.col("trustworthy_supply_rate"), F.lit(0.0))) * F.lit(20.0),
    F.lit(18.0),
)
risk_after = F.greatest(risk_before - improvement, F.lit(0.0))

scen = (
    high_risk.select(
        F.concat_ws("::", F.lit("scn"), F.col("geography_id"),
                    F.lit("mobile_clinic_x1")).alias("scenario_id"),
        "geography_id",
        F.col("state_ut").alias("state"),
        F.col("district_name").alias("district"),
        F.lit("Mobile primary care clinic").alias("intervention_type"),
        F.to_json(F.struct(
            clinics_added.alias("clinics_added"),
            F.lit("monthly").alias("cadence"),
            F.lit(150).alias("assumed_monthly_capacity"),
            F.lit(0.6).alias("assumed_adoption"),
            F.lit("conservative").alias("assumption_profile"),
        )).alias("assumptions_json"),
        F.round(risk_before, 2).alias("risk_score_before"),
        F.round(risk_after, 2).alias("risk_score_after"),
        F.round(improvement, 2).alias("access_improvement_score"),
        # estimated_population_helped: proxy = monthly capacity * adoption * 12 (label as estimate).
        F.round(F.lit(150) * F.lit(0.6) * F.lit(12), 0).cast("int").alias("estimated_population_helped"),
        F.when(F.col("district_uncertainty_level") == "higher", F.lit("low"))
         .otherwise(F.lit("medium")).alias("confidence_band"),
    )
    .withColumn("model_version", F.lit(MODEL_VERSION))
    .withColumn("created_at", F.current_timestamp())
)

scen.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.scenario_simulations"
)
print("scenario_simulations:", spark.table(f"{GOLD}.scenario_simulations").count())

# COMMAND ----------

# MAGIC %md
# MAGIC ## `review_queue` — prioritized facilities needing verification

# COMMAND ----------

review = (
    pcf.alias("f")
    .join(providers.select("canonical_provider_id", "facility_name", "facility_type",
                           "state_ut", "district_name").alias("p"),
          "canonical_provider_id", "left")
    .join(locations.select("canonical_provider_id", "geo_quality",
                           "join_confidence").alias("l"),
          "canonical_provider_id", "left")
    .join(quality.select("canonical_provider_id", "officialPhone", "email",
                         "officialWebsite", "source_urls").alias("q"),
          "canonical_provider_id", "left")
    .withColumn(
        "review_priority",
        F.round(
            F.col("f.contradicted_flag").cast("double") * 35
            + F.col("f.needs_human_review").cast("double") * 25
            + (F.lit(1.0) - F.col("f.data_readiness_score")) * 20
            + (~F.col("f.has_source_urls")).cast("double") * 8
            + (~F.col("f.has_contact_evidence")).cast("double") * 6
            + F.col("f.staleness_flag").cast("double") * 6,
            1,
        ),
    )
    .withColumn(
        "primary_concern",
        F.when(F.col("f.contradicted_flag"), F.lit("Contradicted or invalid geography"))
         .when(F.col("l.join_confidence").isNull() | (F.col("l.join_confidence") < 0.75),
               F.lit("Weak district/PIN join"))
         .when(~F.col("f.has_source_urls"), F.lit("No source URL citation"))
         .when(~F.col("f.has_contact_evidence"), F.lit("No contact evidence"))
         .when(F.col("f.needs_human_review"), F.lit("Manual review flag"))
         .otherwise(F.lit("Positive control candidate")),
    )
    .select(
        "canonical_provider_id",
        F.col("facility_name"),
        F.col("facility_type"),
        F.col("state_ut").alias("state"),
        F.col("district_name").alias("district"),
        "review_priority",
        "primary_concern",
        F.col("f.confidence_band"),
        F.col("f.provider_confidence_score"),
        F.col("l.geo_quality"),
        F.col("officialPhone"), F.col("email"), F.col("officialWebsite"),
        F.col("source_urls"),
    )
    .filter(F.col("review_priority") > 0)
    .withColumn("model_version", F.lit(MODEL_VERSION))
    .withColumn("created_at", F.current_timestamp())
)

review.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{GOLD}.review_queue"
)
print("review_queue:", spark.table(f"{GOLD}.review_queue").count())

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {GOLD}"))
