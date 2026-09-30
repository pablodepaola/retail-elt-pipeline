"""Generate a small, deterministic sample that mirrors the Olist schema EXACTLY.

This committed sample lets CI (and a local demo) run the whole pipeline with no
Kaggle credentials. It is NOT the real dataset -- it is a tiny stand-in with the
identical column layout so the same code path runs end to end.

Run:  python -m pipeline.generate_sample
"""
from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta
from pathlib import Path

from . import config

SEED = 42
N_DAYS = 12
ORDERS_PER_DAY = (6, 14)
START = datetime(2018, 1, 1, 9, 0, 0)

CATEGORIES = {
    "cama_mesa_banho": "bed_bath_table",
    "beleza_saude": "health_beauty",
    "esporte_lazer": "sports_leisure",
    "informatica_acessorios": "computers_accessories",
    "relogios_presentes": "watches_gifts",
}

# product_id -> (category, base_price)
PRODUCTS = {
    "prod_0001": ("cama_mesa_banho", 89.90),
    "prod_0002": ("cama_mesa_banho", 129.90),
    "prod_0003": ("beleza_saude", 39.90),
    "prod_0004": ("beleza_saude", 59.90),
    "prod_0005": ("esporte_lazer", 199.90),
    "prod_0006": ("esporte_lazer", 249.90),
    "prod_0007": ("informatica_acessorios", 149.90),
    "prod_0008": ("informatica_acessorios", 349.90),
    "prod_0009": ("relogios_presentes", 299.90),
    "prod_0010": ("relogios_presentes", 79.90),
}
SELLERS = ["sell_01", "sell_02", "sell_03"]
STATES = ["SP", "RJ", "MG", "RS", "PR"]
STATUSES = ["delivered", "delivered", "delivered", "shipped", "invoiced", "canceled"]


def _w(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(header)
        wr.writerows(rows)


def generate() -> None:
    rnd = random.Random(SEED)
    out = config.SAMPLE_DIR

    orders, items, customers = [], [], []
    item_seq = 0

    for day in range(N_DAYS):
        purchase_day = START + timedelta(days=day)
        n_orders = rnd.randint(*ORDERS_PER_DAY)
        for _ in range(n_orders):
            oid = f"ord_{day:02d}_{rnd.randint(10000, 99999)}"
            cid = f"cust_{rnd.randint(100000, 999999)}"
            cuid = f"u_{rnd.randint(1000, 9999)}"
            state = rnd.choice(STATES)
            status = rnd.choice(STATUSES)
            purchase = purchase_day + timedelta(minutes=rnd.randint(0, 600))
            approved = purchase + timedelta(hours=rnd.randint(1, 12))
            # Delivery/estimate land days later -> genuine late-arriving events.
            delivered = purchase + timedelta(days=rnd.randint(2, 12))
            estimated = purchase + timedelta(days=rnd.randint(5, 15))

            customers.append([cid, cuid, f"{rnd.randint(1000, 99999):05d}",
                              "sao paulo", state])
            orders.append([
                oid, cid, status,
                purchase.strftime("%Y-%m-%d %H:%M:%S"),
                approved.strftime("%Y-%m-%d %H:%M:%S"),
                (purchase + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                delivered.strftime("%Y-%m-%d %H:%M:%S") if status == "delivered" else "",
                estimated.strftime("%Y-%m-%d %H:%M:%S"),
            ])

            for line in range(rnd.randint(1, 3)):
                item_seq += 1
                pid = rnd.choice(list(PRODUCTS))
                base = PRODUCTS[pid][1]
                price = round(base * rnd.uniform(0.9, 1.1), 2)
                freight = round(rnd.uniform(8, 30), 2)
                ship_limit = purchase + timedelta(days=rnd.randint(1, 5))
                items.append([
                    oid, line + 1, pid, rnd.choice(SELLERS),
                    ship_limit.strftime("%Y-%m-%d %H:%M:%S"),
                    f"{price:.2f}", f"{freight:.2f}",
                ])

    _w(out / "olist_orders_dataset.csv",
       ["order_id", "customer_id", "order_status", "order_purchase_timestamp",
        "order_approved_at", "order_delivered_carrier_date",
        "order_delivered_customer_date", "order_estimated_delivery_date"],
       orders)

    _w(out / "olist_order_items_dataset.csv",
       ["order_id", "order_item_id", "product_id", "seller_id",
        "shipping_limit_date", "price", "freight_value"],
       items)

    _w(out / "olist_customers_dataset.csv",
       ["customer_id", "customer_unique_id", "customer_zip_code_prefix",
        "customer_city", "customer_state"],
       customers)

    product_rows = []
    for pid, (cat, _price) in PRODUCTS.items():
        product_rows.append([pid, cat, 50, 800, 3, rnd.randint(200, 5000),
                             rnd.randint(10, 60), rnd.randint(5, 40),
                             rnd.randint(5, 40)])
    _w(out / "olist_products_dataset.csv",
       ["product_id", "product_category_name", "product_name_lenght",
        "product_description_lenght", "product_photos_qty", "product_weight_g",
        "product_length_cm", "product_height_cm", "product_width_cm"],
       product_rows)

    _w(out / "product_category_name_translation.csv",
       ["product_category_name", "product_category_name_english"],
       [[k, v] for k, v in CATEGORIES.items()])

    print(f"sample written to {out}  (orders={len(orders)} items={len(items)} "
          f"customers={len(customers)} products={len(product_rows)})")


if __name__ == "__main__":
    generate()
