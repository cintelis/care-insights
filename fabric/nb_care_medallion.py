# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "{{LAKEHOUSE_ID}}",
# META       "default_lakehouse_name": "{{LAKEHOUSE_NAME}}",
# META       "default_lakehouse_workspace_id": "{{WORKSPACE_ID}}"
# META     }
# META   }
# META }

# MARKDOWN ********************

# # Care Insights - medallion pipeline
#
# Reads raw source files from ADLS Gen2 and writes **bronze / silver / gold Delta tables back to ADLS Gen2**.
# Fabric is the compute; the data never has to live in OneLake.
#
# | Lakehouse path | Is a OneLake shortcut to |
# |---|---|
# | `Files/raw`  | `abfss://raw@<account>.dfs.core.windows.net/`  (landing zone) |
# | `Files/lake` | `abfss://lake@<account>.dfs.core.windows.net/` (Delta tables + pipeline SQL) |
#
# The transformation logic lives in plain Spark SQL files under `Files/lake/_pipeline/sql`, the same
# files the local DuckDB test runner uses, so logic is tested before it reaches Fabric.

# PARAMETERS CELL ********************

as_of_date = "2026-10-18"   # last day with actuals; the scheduled run passes today's date
raw_root = "Files/raw"
lake_root = "Files/lake"

# CELL ********************

import json
from pyspark.sql import functions as F

pipeline_root = f"{lake_root}/_pipeline"

def read_text(path: str) -> str:
    return spark.read.text(path, wholetext=True).first()[0]

def write_delta(df, layer: str, name: str):
    path = f"{lake_root}/{layer}/{name}"
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").save(path))
    # re-read from Delta so later steps don't recompute the whole lineage
    spark.read.format("delta").load(path).createOrReplaceTempView(f"{layer}_{name}")
    return spark.table(f"{layer}_{name}").count()

# CELL ********************

# ---------- Bronze: raw files -> Delta, as-is (strings), plus lineage columns ----------
sources = {k: v for k, v in json.loads(read_text(f"{pipeline_root}/bronze_sources.json")).items() if not k.startswith("_")}

for name, src in sources.items():
    path = f"{raw_root}/{src['path']}"
    if src["format"] == "csv":
        df = spark.read.option("header", True).option("inferSchema", False).csv(path)
    else:
        df = spark.read.json(path)
    df = (df.withColumn("_source_file", F.col("_metadata.file_path"))
            .withColumn("_ingested_at", F.current_timestamp()))
    print(f"bronze_{name:<14} {write_delta(df, 'bronze', name):>8} rows")

# CELL ********************

# ---------- Silver + Gold: run the SQL files in order ----------
for layer in ("silver", "gold"):
    files = sorted(f.name for f in notebookutils.fs.ls(f"{pipeline_root}/sql/{layer}") if f.name.endswith(".sql"))
    for fname in files:
        name = fname[:-4].split("_", 1)[1]          # 07_visits.sql -> visits
        sql = read_text(f"{pipeline_root}/sql/{layer}/{fname}").replace("{{AS_OF_DATE}}", as_of_date)
        print(f"{layer}_{name:<22} {write_delta(spark.sql(sql), layer, name):>8} rows")

# CELL ********************

# ---------- Quick health check ----------
display(spark.sql("""
  SELECT quarter, budget_status, COUNT(*) AS participants, ROUND(SUM(est_funds_lost_aud)) AS funds_at_risk_aud
  FROM gold_budget_utilisation GROUP BY quarter, budget_status ORDER BY quarter, budget_status
"""))
