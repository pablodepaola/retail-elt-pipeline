"""Load: mirror the immutable raw parquet lake into a self-contained DuckDB
`raw` schema that dbt reads as sources.

Raw is rebuilt from the full lake each run (cheap, columnar). Incrementality and
idempotency are guaranteed upstream by which partitions exist in the lake and
downstream by dbt incremental MERGEs -- so this step is a faithful, deterministic
mirror with no double-count risk. `union_by_name` tolerates additive schema
evolution across partitions.
"""
from __future__ import annotations

import logging

import duckdb

from . import config

log = logging.getLogger("elt.load")

RAW_SCHEMA = "raw"
META_SCHEMA = "meta"


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    config.WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(config.DUCKDB_PATH), read_only=read_only)


def _glob_for(table: str) -> str:
    return str(config.RAW_DIR / table / "**" / "*.parquet")


def load_raw(con: duckdb.DuckDBPyConnection) -> dict[str, int]:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {RAW_SCHEMA}")
    counts: dict[str, int] = {}
    for table in config.SOURCE_TABLES.values():
        glob = _glob_for(table)
        con.execute(
            f"""
            CREATE OR REPLACE TABLE {RAW_SCHEMA}.{table} AS
            SELECT * FROM read_parquet(?, hive_partitioning = 1, union_by_name = 1)
            """,
            [glob],
        )
        n = con.execute(f"SELECT count(*) FROM {RAW_SCHEMA}.{table}").fetchone()[0]
        counts[table] = n
        log.info("raw.%-20s rows=%d", table, n)
    return counts


def ensure_meta(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(f"CREATE SCHEMA IF NOT EXISTS {META_SCHEMA}")
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {META_SCHEMA}.pipeline_runs (
            run_id            VARCHAR,
            run_started_at    TIMESTAMP,
            run_finished_at   TIMESTAMP,
            mode              VARCHAR,
            window_start      DATE,
            window_end        DATE,
            rows_extracted    BIGINT,
            dbt_tests_passed  INTEGER,
            dbt_tests_failed  INTEGER,
            status            VARCHAR
        )
        """
    )


def record_run(con: duckdb.DuckDBPyConnection, row: dict) -> None:
    ensure_meta(con)
    con.execute(
        f"""
        INSERT INTO {META_SCHEMA}.pipeline_runs
        (run_id, run_started_at, run_finished_at, mode, window_start, window_end,
         rows_extracted, dbt_tests_passed, dbt_tests_failed, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            row.get("run_id"),
            row.get("run_started_at"),
            row.get("run_finished_at"),
            row.get("mode"),
            row.get("window_start"),
            row.get("window_end"),
            row.get("rows_extracted"),
            row.get("dbt_tests_passed"),
            row.get("dbt_tests_failed"),
            row.get("status"),
        ],
    )
