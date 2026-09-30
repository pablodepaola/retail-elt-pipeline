"""Publish marts from DuckDB into Oracle Autonomous DB so the Oracle APEX exec
dashboard can read them live.

Why a separate serving store? APEX reads from an Oracle DB, not from DuckDB. We
keep DuckDB+dbt as the ELT engine and treat Oracle as the thin serving layer:
small, daily mart snapshots are full-refreshed (TRUNCATE+INSERT) -> idempotent.

Connectivity: python-oracledb in THIN mode (no Oracle client install) using an
Always-Free wallet. Credentials come from env / GH Actions secrets:
    ORACLE_USER, ORACLE_PASSWORD, ORACLE_DSN,
    ORACLE_WALLET_DIR (TNS_ADMIN), ORACLE_WALLET_PASSWORD

Use --dry-run to export marts to CSV (data/exports/) with no Oracle account.
"""
from __future__ import annotations

import logging
import os

from . import config, load

log = logging.getLogger("elt.oracle")

# Mart relation in DuckDB -> Oracle target table. Oracle tables are created once
# via oracle/01_create_mart_tables.sql.
PUBLISH_MAP: dict[str, str] = {
    "main_marts.mart_exec_kpis": "MART_EXEC_KPIS",
    "main_marts.mart_sales_by_category": "MART_SALES_BY_CATEGORY",
    "main_marts.mart_inventory_health": "MART_INVENTORY_HEALTH",
    "main_marts.fct_daily_sales": "FCT_DAILY_SALES",
    "main_marts.dim_product": "DIM_PRODUCT",
    "main_marts.mart_pipeline_status": "MART_PIPELINE_STATUS",
}


def export_csv() -> dict[str, int]:
    """Dry-run path: dump each mart to CSV for inspection (no Oracle needed)."""
    config.EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    con = load.connect(read_only=True)
    counts: dict[str, int] = {}
    try:
        for relation, target in PUBLISH_MAP.items():
            try:
                df = con.execute(f"SELECT * FROM {relation}").fetch_df()
            except Exception as exc:  # mart not built yet
                log.warning("skip %s (%s)", relation, exc)
                continue
            out = config.EXPORTS_DIR / f"{target}.csv"
            df.to_csv(out, index=False)
            counts[target] = len(df)
            log.info("exported %-26s rows=%d -> %s", target, len(df), out.name)
    finally:
        con.close()
    return counts


def _connect_oracle():
    import oracledb  # local import so dry-run never requires the driver runtime

    user = os.environ["ORACLE_USER"]
    password = os.environ["ORACLE_PASSWORD"]
    dsn = os.environ["ORACLE_DSN"]
    wallet_dir = os.getenv("ORACLE_WALLET_DIR")
    wallet_pw = os.getenv("ORACLE_WALLET_PASSWORD")

    kwargs = {"user": user, "password": password, "dsn": dsn}
    if wallet_dir:
        kwargs.update(
            config_dir=wallet_dir,
            wallet_location=wallet_dir,
            wallet_password=wallet_pw,
        )
    return oracledb.connect(**kwargs)


def publish() -> dict[str, int]:
    """Full-refresh each mart into Oracle (TRUNCATE + executemany INSERT)."""
    ora = _connect_oracle()
    duck = load.connect(read_only=True)
    counts: dict[str, int] = {}
    try:
        cur = ora.cursor()
        for relation, target in PUBLISH_MAP.items():
            try:
                df = duck.execute(f"SELECT * FROM {relation}").fetch_df()
            except Exception as exc:
                log.warning("skip %s (%s)", relation, exc)
                continue

            cols = list(df.columns)
            placeholders = ", ".join(f":{i+1}" for i in range(len(cols)))
            col_list = ", ".join(c.upper() for c in cols)
            rows = [tuple(None if _isna(v) else _coerce(v) for v in rec)
                    for rec in df.itertuples(index=False, name=None)]

            cur.execute(f"TRUNCATE TABLE {target}")
            if rows:
                cur.executemany(
                    f"INSERT INTO {target} ({col_list}) VALUES ({placeholders})", rows
                )
            ora.commit()
            counts[target] = len(rows)
            log.info("published %-26s rows=%d", target, len(rows))
    finally:
        duck.close()
        ora.close()
    return counts


def _isna(v) -> bool:
    try:
        import pandas as pd

        return bool(pd.isna(v))
    except (TypeError, ValueError):
        return v is None


def _coerce(v):
    # numpy/pandas scalars -> native python for the Oracle driver
    if hasattr(v, "item"):
        try:
            return v.item()
        except Exception:
            return v
    return v
