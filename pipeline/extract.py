"""Extract: idempotent, incremental, watermark-driven landing into an immutable
raw zone.

Design notes (the "production realism" bits):
  * Incremental by business event date (order_purchase_timestamp).
  * Overlapping re-scan window (LATE_ARRIVING_LOOKBACK_DAYS) so late-arriving
    rows are re-captured; downstream staging dedups by natural key taking the
    latest ingest partition (CDC-style).
  * Immutable raw: each run writes data/raw/<table>/ingest_date=YYYY-MM-DD/.
    Re-running the same date is deterministic (same input -> same bytes),
    so re-runs and backfills never double count.
  * Schema-drift detection BEFORE landing: violations quarantine the snapshot
    and raise, failing the run.
"""
from __future__ import annotations

import logging
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from . import config
from .contracts import SchemaDriftError, validate_table
from .state import Watermark

log = logging.getLogger("elt.extract")

# Bound how many business days a single scheduled run will advance, so a cold
# start doesn't try to process two years in one job. Backfills override via range.
MAX_DAYS_PER_RUN = int(__import__("os").getenv("ELT_MAX_DAYS_PER_RUN", "7"))

# Source tables that are reference/dimension snapshots (landed in full each run)
# vs. event tables (sliced by the watermark window).
SNAPSHOT_TABLES = {"products", "customers", "category_translation"}
EVENT_TABLES = {"orders", "order_items"}


# --------------------------------------------------------------------------- #
# Source IO
# --------------------------------------------------------------------------- #
def _source_path(table: str, use_sample: bool) -> Path:
    stem = next(s for s, name in config.SOURCE_TABLES.items() if name == table)
    return config.source_root(use_sample) / f"{stem}.csv"


def read_source_table(table: str, use_sample: bool) -> pd.DataFrame:
    path = _source_path(table, use_sample)
    if not path.exists():
        raise FileNotFoundError(
            f"Source file for '{table}' not found at {path}. "
            f"Run with --sample for the committed demo data, or place the Olist "
            f"CSVs in {config.SOURCE_DIR} (see README: 'Getting the data')."
        )
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])


def source_event_bounds(use_sample: bool) -> tuple[date, date]:
    df = read_source_table(config.WATERMARK_TABLE, use_sample)
    ts = pd.to_datetime(df[config.WATERMARK_COLUMN], errors="coerce")
    return ts.min().date(), ts.max().date()


# --------------------------------------------------------------------------- #
# Window planning
# --------------------------------------------------------------------------- #
def plan_window(
    wm: Watermark,
    use_sample: bool,
    start: date | None,
    end: date | None,
    max_days: int = MAX_DAYS_PER_RUN,
) -> list[date]:
    """Return the ordered list of business days to process this run."""
    src_min, src_max = source_event_bounds(use_sample)

    if start is None:
        last = wm.last_loaded
        start = src_min if last is None else last + timedelta(days=1)
    if end is None:
        end = min(start + timedelta(days=max_days - 1), src_max)

    start = max(start, src_min)
    end = min(end, src_max)

    if start > end:
        return []
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


# --------------------------------------------------------------------------- #
# Drift + quarantine
# --------------------------------------------------------------------------- #
def _quarantine(table: str, business_day: date, df: pd.DataFrame, problems: list[str]) -> None:
    dest = config.QUARANTINE_DIR / table / f"ingest_date={business_day.isoformat()}"
    dest.mkdir(parents=True, exist_ok=True)
    df.to_parquet(dest / "data.parquet", index=False)
    (dest / "DRIFT.txt").write_text(
        f"Schema drift quarantined at {datetime.now(timezone.utc).isoformat()}Z\n"
        f"table={table} business_day={business_day}\n" + "\n".join(problems) + "\n"
    )
    log.error("SCHEMA DRIFT on %s (%s): %s", table, business_day, "; ".join(problems))


def _enforce_contract(table: str, business_day: date, df: pd.DataFrame) -> None:
    problems = validate_table(table, list(df.columns))
    if problems:
        _quarantine(table, business_day, df, problems)
        raise SchemaDriftError(
            f"Schema drift on '{table}' for {business_day}: {'; '.join(problems)}. "
            f"Snapshot quarantined; run failed by design."
        )


# --------------------------------------------------------------------------- #
# Landing
# --------------------------------------------------------------------------- #
def _land(table: str, business_day: date, df: pd.DataFrame) -> Path:
    df = df.copy()
    df["_ingest_date"] = business_day.isoformat()
    df["_loaded_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    dest_dir = config.RAW_DIR / table / f"ingest_date={business_day.isoformat()}"
    if dest_dir.exists():
        shutil.rmtree(dest_dir)  # deterministic re-write -> idempotent
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / "data.parquet"
    df.to_parquet(out, index=False)
    log.info("landed %-20s ingest_date=%s rows=%d", table, business_day, len(df))
    return out


def extract_day(business_day: date, use_sample: bool) -> dict[str, int]:
    """Land all source tables for one business day. Returns rows landed per table."""
    lookback = config.LATE_ARRIVING_LOOKBACK_DAYS
    window_start = business_day - timedelta(days=lookback)

    orders = read_source_table("orders", use_sample)
    _enforce_contract("orders", business_day, orders)
    ts = pd.to_datetime(orders[config.WATERMARK_COLUMN], errors="coerce").dt.date
    # Overlap re-scan window captures late-arriving rows; staging dedups later.
    mask = (ts >= window_start) & (ts <= business_day)
    orders_slice = orders.loc[mask]

    order_ids = set(orders_slice["order_id"])
    items = read_source_table("order_items", use_sample)
    _enforce_contract("order_items", business_day, items)
    items_slice = items[items["order_id"].isin(order_ids)]

    counts: dict[str, int] = {}
    counts["orders"] = len(orders_slice)
    counts["order_items"] = len(items_slice)
    _land("orders", business_day, orders_slice)
    _land("order_items", business_day, items_slice)

    # Reference/dimension snapshots: land full current snapshot for this day.
    for table in SNAPSHOT_TABLES:
        df = read_source_table(table, use_sample)
        _enforce_contract(table, business_day, df)
        _land(table, business_day, df)
        counts[table] = len(df)

    return counts


def run_extract(
    wm: Watermark,
    use_sample: bool,
    start: date | None = None,
    end: date | None = None,
) -> dict:
    days = plan_window(wm, use_sample, start, end)
    if not days:
        log.info("nothing to extract (watermark up to date)")
        return {"days": [], "rows": {}, "high_water": None}

    log.info("extract window: %s .. %s (%d day(s))", days[0], days[-1], len(days))
    totals: dict[str, int] = {}
    for d in days:
        counts = extract_day(d, use_sample)
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v

    return {"days": [d.isoformat() for d in days], "rows": totals, "high_water": days[-1]}
