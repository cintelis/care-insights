"""
Run the medallion pipeline locally with DuckDB, using the *same* Spark SQL files the
Fabric notebook runs (transpiled to DuckDB with sqlglot). Lets you test the logic with
no cloud at all, and produces local gold parquet the dashboard can read.

  python transform/run_local.py [--as-of 2026-10-18]
"""
import argparse
import json
from pathlib import Path

import duckdb
import sqlglot

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
LAKE = ROOT / "data" / "lake"
SQL = Path(__file__).resolve().parent / "sql"


def sql_files():
    for layer in ("silver", "gold"):
        for f in sorted((SQL / layer).glob("*.sql")):
            yield layer, f"{layer}_{f.stem.split('_', 1)[1]}", f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of", default="2026-10-18")
    a = ap.parse_args()
    con = duckdb.connect()

    for name, src in json.loads((Path(__file__).parent / "bronze_sources.json").read_text()).items():
        if name.startswith("_"):
            continue
        path = (RAW / src["path"]).as_posix()
        reader = (f"read_csv('{path}', header=true, all_varchar=true, filename=true)" if src["format"] == "csv"
                  else f"read_json('{path}', format='newline_delimited', filename=true)")
        con.execute(f"CREATE OR REPLACE TABLE bronze_{name} AS SELECT * EXCLUDE (filename), filename AS _source_file, now() AS _ingested_at FROM {reader}")
        print(f"bronze_{name:<14} {con.execute(f'SELECT count(*) FROM bronze_{name}').fetchone()[0]:>7} rows")

    for layer, table, f in sql_files():
        spark_sql = f.read_text().replace("{{AS_OF_DATE}}", a.as_of)
        duck_sql = sqlglot.transpile(spark_sql, read="spark", write="duckdb")[0]
        try:
            con.execute(f"CREATE OR REPLACE TABLE {table} AS {duck_sql}")
        except Exception as e:
            raise SystemExit(f"\n{f} failed in DuckDB:\n{e}\n--- transpiled SQL ---\n{duck_sql}")
        out = LAKE / layer / f"{table.split('_', 1)[1]}.parquet"
        out.parent.mkdir(parents=True, exist_ok=True)
        con.execute(f"COPY {table} TO '{out.as_posix()}' (FORMAT parquet)")
        print(f"{table:<26} {con.execute(f'SELECT count(*) FROM {table}').fetchone()[0]:>7} rows")


if __name__ == "__main__":
    main()
