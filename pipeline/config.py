"""Central configuration: paths, source mode, and the (clearly labeled) synthetic
business parameters used to turn the Olist proxy dataset into a sales+inventory
warehouse.

Everything here is deterministic so that re-runs and backfills are reproducible.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"

# Real Olist CSVs go here (gitignored); the committed CI/demo sample lives in data/sample.
SOURCE_DIR = DATA_DIR / "source"
SAMPLE_DIR = DATA_DIR / "sample"

# Immutable raw landing zone (partitioned by ingest_date), the DuckDB file, and exports.
RAW_DIR = DATA_DIR / "raw"
QUARANTINE_DIR = RAW_DIR / "_quarantine"
WAREHOUSE_DIR = DATA_DIR / "warehouse"
EXPORTS_DIR = DATA_DIR / "exports"

DUCKDB_PATH = WAREHOUSE_DIR / "retail.duckdb"
STATE_PATH = PROJECT_ROOT / "pipeline" / "state" / "watermark.json"

DBT_DIR = PROJECT_ROOT / "dbt"


def source_root(use_sample: bool) -> Path:
    """Where the Olist CSVs are read from. The committed sample mirrors the real
    schema exactly so CI never needs Kaggle credentials."""
    return SAMPLE_DIR if use_sample else SOURCE_DIR


# --------------------------------------------------------------------------- #
# Source tables we extract (Olist file stem -> logical table name).
# These are the tables that drive the sales + (synthetic) inventory marts.
# --------------------------------------------------------------------------- #
SOURCE_TABLES: dict[str, str] = {
    "olist_orders_dataset": "orders",
    "olist_order_items_dataset": "order_items",
    "olist_products_dataset": "products",
    "olist_customers_dataset": "customers",
    "product_category_name_translation": "category_translation",
}

# Event-time column used as the incremental watermark (business date of the order).
WATERMARK_TABLE = "orders"
WATERMARK_COLUMN = "order_purchase_timestamp"

# Natural keys used for idempotent merges downstream (no double counting on re-run).
NATURAL_KEYS: dict[str, list[str]] = {
    "orders": ["order_id"],
    "order_items": ["order_id", "order_item_id"],
    "products": ["product_id"],
    "customers": ["customer_id"],
    "category_translation": ["product_category_name"],
}

# --------------------------------------------------------------------------- #
# Late-arriving data: how many days of event-time we re-scan on every run so that
# delivery/payment/late order records that land after their business date are
# still captured. dbt incremental MERGE dedups by natural key.
# --------------------------------------------------------------------------- #
LATE_ARRIVING_LOOKBACK_DAYS = int(os.getenv("ELT_LATE_LOOKBACK_DAYS", "3"))


@dataclass(frozen=True)
class SyntheticParams:
    """SYNTHETIC business parameters (Olist has no cost or inventory). All values
    are deterministic functions of stable keys so marts are reproducible. These
    are clearly documented as a proxy in the README and data dictionary."""

    # Gross margin target band by category tier; actual cost is derived per product
    # from a hash of product_id so it is stable but varied.
    base_margin_pct: float = 0.38
    margin_jitter: float = 0.12  # +/- band applied deterministically per product

    # Inventory simulation (step-function replenishment -> no recursion needed).
    opening_stock_days: int = 45      # opening stock ~= 45 days of expected demand
    restock_interval_days: int = 14   # scheduled replenishment cadence
    restock_cover_days: int = 21      # each restock brings ~21 days of cover
    reorder_point_days: int = 10      # reorder threshold in days-of-supply
    overstock_days: int = 60          # > this days-of-supply == overstock/markdown risk
    min_opening_stock: int = 5        # floor so low-velocity SKUs still have stock


SYNTH = SyntheticParams()
