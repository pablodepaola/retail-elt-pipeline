"""Source data contracts + schema-drift detection.

A real team treats the producer->consumer boundary as a contract. Before any raw
file is landed we assert its columns match the registered contract. On drift we
QUARANTINE the offending snapshot and raise, so the run fails loudly instead of
silently corrupting the warehouse.
"""
from __future__ import annotations

from dataclasses import dataclass


class SchemaDriftError(Exception):
    """Raised when an incoming source snapshot violates its registered contract."""


@dataclass(frozen=True)
class TableContract:
    name: str
    required_columns: frozenset[str]
    # Columns we are allowed to see appear/disappear without failing the run.
    optional_columns: frozenset[str] = frozenset()

    def validate(self, observed_columns: list[str]) -> list[str]:
        """Return a list of human-readable drift violations (empty == OK)."""
        observed = set(observed_columns)
        problems: list[str] = []

        missing = self.required_columns - observed
        if missing:
            problems.append(f"missing required columns: {sorted(missing)}")

        allowed = self.required_columns | self.optional_columns
        unexpected = observed - allowed
        if unexpected:
            problems.append(f"unexpected new columns (possible drift): {sorted(unexpected)}")

        return problems


# Registered contracts for the Olist source tables we consume. Required columns are
# what the downstream staging models depend on; everything else is optional.
CONTRACTS: dict[str, TableContract] = {
    "orders": TableContract(
        name="orders",
        required_columns=frozenset(
            {
                "order_id",
                "customer_id",
                "order_status",
                "order_purchase_timestamp",
            }
        ),
        optional_columns=frozenset(
            {
                "order_approved_at",
                "order_delivered_carrier_date",
                "order_delivered_customer_date",
                "order_estimated_delivery_date",
            }
        ),
    ),
    "order_items": TableContract(
        name="order_items",
        required_columns=frozenset(
            {
                "order_id",
                "order_item_id",
                "product_id",
                "seller_id",
                "price",
                "freight_value",
            }
        ),
        optional_columns=frozenset({"shipping_limit_date"}),
    ),
    "products": TableContract(
        name="products",
        required_columns=frozenset({"product_id", "product_category_name"}),
        optional_columns=frozenset(
            {
                "product_name_lenght",
                "product_description_lenght",
                "product_photos_qty",
                "product_weight_g",
                "product_length_cm",
                "product_height_cm",
                "product_width_cm",
            }
        ),
    ),
    "customers": TableContract(
        name="customers",
        required_columns=frozenset(
            {"customer_id", "customer_unique_id", "customer_state"}
        ),
        optional_columns=frozenset({"customer_zip_code_prefix", "customer_city"}),
    ),
    "category_translation": TableContract(
        name="category_translation",
        required_columns=frozenset(
            {"product_category_name", "product_category_name_english"}
        ),
    ),
}


def validate_table(table: str, observed_columns: list[str]) -> list[str]:
    contract = CONTRACTS.get(table)
    if contract is None:
        # No contract registered == we don't consume it; nothing to enforce.
        return []
    return contract.validate(observed_columns)
