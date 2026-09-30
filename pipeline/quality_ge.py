"""Great Expectations gate at the RAW boundary.

Division of labour (documented as a trade-off in the README):
  * Great Expectations  -> validates RAW landed data the moment it enters the
    warehouse (column presence, not-null keys, value ranges, accepted sets).
    This is the "is the producer's data even sane?" gate, decoupled from SQL.
  * dbt tests           -> validate MODELED data (uniqueness, referential
    integrity, freshness, business rules) where the relationships live.

Any failed expectation raises -> the orchestrated run fails by design.
"""
from __future__ import annotations

import logging
import os

os.environ.setdefault("TQDM_DISABLE", "1")  # silence GE metric progress bars

import great_expectations as gx
import pandas as pd
from great_expectations import expectations as gxe

from . import load

# GE is chatty; keep our logs readable.
logging.getLogger("great_expectations").setLevel(logging.WARNING)

log = logging.getLogger("elt.ge")


def _suite_for(table: str) -> gx.ExpectationSuite:
    suite = gx.ExpectationSuite(name=f"raw_{table}")
    if table == "orders":
        suite.add_expectation(gxe.ExpectColumnToExist(column="order_id"))
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="order_id"))
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="customer_id"))
        suite.add_expectation(
            gxe.ExpectColumnValuesToNotBeNull(column="order_purchase_timestamp")
        )
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeInSet(
                column="order_status",
                value_set=[
                    "delivered",
                    "shipped",
                    "canceled",
                    "unavailable",
                    "invoiced",
                    "processing",
                    "created",
                    "approved",
                ],
            )
        )
    elif table == "order_items":
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="order_id"))
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="product_id"))
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeBetween(column="price", min_value=0, max_value=1_000_000)
        )
        suite.add_expectation(
            gxe.ExpectColumnValuesToBeBetween(
                column="freight_value", min_value=0, max_value=1_000_000
            )
        )
    elif table == "products":
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="product_id"))
    elif table == "customers":
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="customer_id"))
        suite.add_expectation(gxe.ExpectColumnValuesToNotBeNull(column="customer_state"))
    elif table == "category_translation":
        suite.add_expectation(
            gxe.ExpectColumnValuesToNotBeNull(column="product_category_name")
        )
    return suite


def _validate_df(table: str, df: pd.DataFrame) -> list[dict]:
    # numeric coercion so range expectations are meaningful (raw lands as strings)
    for col in ("price", "freight_value"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    context = gx.get_context(mode="ephemeral")
    ds = context.data_sources.add_pandas(f"raw_{table}_src")
    asset = ds.add_dataframe_asset(name=table)
    batch_def = asset.add_batch_definition_whole_dataframe("batch")
    batch = batch_def.get_batch(batch_parameters={"dataframe": df})

    failures: list[dict] = []
    for expectation in _suite_for(table).expectations:
        result = batch.validate(expectation)
        if not result.success:
            failures.append(
                {
                    "table": table,
                    "expectation": type(expectation).__name__,
                    "column": getattr(expectation, "column", None),
                    "result": result.result,
                }
            )
    return failures


def validate_raw() -> None:
    """Validate every raw table currently loaded in DuckDB. Raise on any failure."""
    con = load.connect(read_only=True)
    all_failures: list[dict] = []
    try:
        for table in ("orders", "order_items", "products", "customers", "category_translation"):
            df = con.execute(f"SELECT * FROM {load.RAW_SCHEMA}.{table}").fetch_df()
            failures = _validate_df(table, df)
            status = "PASS" if not failures else "FAIL"
            log.info("GE raw.%-20s %s", table, status)
            all_failures.extend(failures)
    finally:
        con.close()

    if all_failures:
        for f in all_failures:
            log.error(
                "GE FAIL %s.%s [%s]", f["table"], f["column"], f["expectation"]
            )
        raise RuntimeError(
            f"Great Expectations gate failed: {len(all_failures)} expectation(s) "
            f"violated at the raw boundary. Run failed by design."
        )
    log.info("Great Expectations raw gate: ALL PASS")
