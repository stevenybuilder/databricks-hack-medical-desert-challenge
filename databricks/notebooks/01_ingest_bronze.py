# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Ingest Bronze
# MAGIC
# MAGIC Registers **bronze** Delta tables in `workspace.caregap_bronze` from:
# MAGIC
# MAGIC - the raw FDR source tables (`databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.*`), and
# MAGIC - the already-cleaned hackathon tables in `workspace.default.*` (prior local pipeline).
# MAGIC
# MAGIC Each bronze table **preserves the raw columns** and adds ingestion-metadata columns:
# MAGIC `source_name`, `source_url`, `ingested_at`, `pipeline_run_id`, `raw_record_hash`.
# MAGIC
# MAGIC Idempotent: `CREATE SCHEMA IF NOT EXISTS` + `CREATE OR REPLACE TABLE`.
# MAGIC
# MAGIC > Free Edition: serverless only. `spark` is pre-injected. No `sc` / RDD / `dbutils.fs` mounts.

# COMMAND ----------

import uuid

from pyspark.sql import functions as F

CATALOG = "workspace"
BRONZE = f"{CATALOG}.caregap_bronze"

# Stable id for this ingestion run (re-derived each run; lineage lives in ingested_at).
PIPELINE_RUN_ID = "bronze-ingest-" + uuid.uuid4().hex[:12]

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {BRONZE}")
print("pipeline_run_id =", PIPELINE_RUN_ID)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Helpers

# COMMAND ----------


def table_exists(fqn: str) -> bool:
    try:
        spark.sql(f"DESCRIBE TABLE {fqn}")
        return True
    except Exception as exc:  # noqa: BLE001 — Free-Edition friendly: skip absent sources
        print(f"[skip] source not available: {fqn} ({type(exc).__name__})")
        return False


def add_ingestion_metadata(df, source_name: str, source_url: str):
    """Append the bronze provenance columns required by the contract."""
    # raw_record_hash = sha2 over all original columns BEFORE metadata columns are added.
    raw_cols = [F.coalesce(F.col(c).cast("string"), F.lit("∅")) for c in df.columns]
    return (
        df.withColumn("source_name", F.lit(source_name))
        .withColumn("source_url", F.lit(source_url))
        .withColumn("ingested_at", F.current_timestamp())
        .withColumn("pipeline_run_id", F.lit(PIPELINE_RUN_ID))
        .withColumn("raw_record_hash", F.sha2(F.concat_ws("||", *raw_cols), 256))
    )


def ingest(target: str, source_fqn: str, source_name: str, source_url: str):
    """Read a source table, add metadata, and write a bronze Delta table."""
    if not table_exists(source_fqn):
        print(f"[skip] {target}: source {source_fqn} missing")
        return False
    df = add_ingestion_metadata(spark.table(source_fqn), source_name, source_url)
    (
        df.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{BRONZE}.{target}")
    )
    n = spark.table(f"{BRONZE}.{target}").count()
    print(f"[ok]  {BRONZE}.{target}: {n:,} rows")
    return True


def ingest_csv(target: str, csv_path: str, source_name: str, source_url: str):
    """Read a cleaned CSV from the UC volume (full derived schema), add metadata,
    and write a bronze Delta table. Serverless-safe Spark Connect read options."""
    df = (
        spark.read.option("header", True)
        .option("multiLine", True)
        .option("escape", '"')
        .option("inferSchema", True)
        .csv(csv_path)
    )
    df = add_ingestion_metadata(df, source_name, source_url)
    (
        df.write.mode("overwrite")
        .option("overwriteSchema", "true")
        .saveAsTable(f"{BRONZE}.{target}")
    )
    n = spark.table(f"{BRONZE}.{target}").count()
    print(f"[ok]  {BRONZE}.{target}: {n:,} rows (from volume CSV)")
    return True


# COMMAND ----------

# MAGIC %md
# MAGIC ## Raw FDR source tables

# COMMAND ----------

FDR = "databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset"

ingest(
    "raw_facilities",
    f"{FDR}.facilities",
    "virtue_foundation_fdr_facilities",
    "https://www.databricks.com/blog/databricks-good-and-virtue-foundation",
)
ingest(
    "raw_pincode_directory",
    f"{FDR}.india_post_pincode_directory",
    "india_post_pincode_directory",
    "https://www.data.gov.in/resource/all-india-pincode-directory-till-last-month",
)
ingest(
    "raw_nfhs_indicators",
    f"{FDR}.nfhs_5_district_health_indicators",
    "nfhs_5_district_health_indicators",
    "https://dhsprogram.com/publications/publication-OF43-Other-Fact-Sheets.cfm",
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Already-cleaned hackathon tables (prior local pipeline)
# MAGIC
# MAGIC These are registered into bronze for governance/lineage; silver maps them to the
# MAGIC documented contract. Cleaning was already performed locally — bronze just preserves
# MAGIC them with provenance metadata.
# MAGIC
# MAGIC The two primary cleaned tables (`raw_facility_health_cleaned`,
# MAGIC `raw_district_health_cleaned`) are sourced from the **full-schema cleaned CSVs** on the
# MAGIC UC volume (144 / 137 columns incl. all derived `*_status`, semantic, supply, and
# MAGIC estimate columns). The reduced-schema `workspace.default.hackathon_*` tables do NOT
# MAGIC carry these derived columns, which is why silver previously failed to resolve them.

# COMMAND ----------

DEFAULT = f"{CATALOG}.default"
VOLUME = "/Volumes/workspace/default/hackathon_cleaned"

# Full-schema cleaned facility/district tables: source from the volume CSVs.
ingest_csv(
    "raw_facility_health_cleaned",
    f"{VOLUME}/facility_health_cleaned.csv",
    "hackathon_facility_health_cleaned",
    "local_pipeline://facility_health_cleaned",
)
ingest_csv(
    "raw_district_health_cleaned",
    f"{VOLUME}/district_health_facility_cleaned.csv",
    "hackathon_district_health_facility_cleaned",
    "local_pipeline://district_health_facility_cleaned",
)

# Remaining cleaned helper tables stay as UC-table reads (unchanged).
# (target, source_table, source_name, source_url) — optional tables skipped gracefully.
CLEANED_SOURCES = [
    ("raw_geo_validation_candidates", "hackathon_geo_validation_candidates",
     "hackathon_geo_validation_candidates", "local_pipeline://geo_validation_candidates"),
    ("raw_pincode_bridge", "hackathon_pincode_bridge",
     "hackathon_pincode_bridge", "local_pipeline://pincode_bridge"),
    ("raw_google_geocoding_results", "hackathon_google_geocoding_results",
     "hackathon_google_geocoding_results", "local_pipeline://google_geocoding_results"),
]

for target, src, sname, surl in CLEANED_SOURCES:
    ingest(target, f"{DEFAULT}.{src}", sname, surl)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary

# COMMAND ----------

display(spark.sql(f"SHOW TABLES IN {BRONZE}"))
