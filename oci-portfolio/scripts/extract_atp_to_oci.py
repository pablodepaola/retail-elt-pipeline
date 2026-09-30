#!/usr/bin/env python3
"""Incremental extract: PORTFOLIO_ATP → OCI Object Storage Bronze (JSONL).

Usage:
  export ATP_WALLET_DIR=~/.oci/wallets/PORTFOLIO_ATP
  export ATP_DSN=portfoli_atp_high
  export ATP_PASSWORD='...'
  export OCI_NAMESPACE=$(oci os ns get --query data --raw-output)
  export OCI_REGION=sa-saopaulo-1
  python extract_atp_to_oci.py

See: docs/oci-portfolio/05-hybrid-lakehouse-oci.md
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

try:
    import oracledb
    import oci
except ImportError:
    sys.exit("Install dependencies: pip install oracledb oci")

QUERIES = {
    "orders": """
        SELECT order_id, customer_id, order_date, status, last_updated_at
        FROM orders
        WHERE last_updated_at > :wm
    """,
    "order_items": """
        SELECT order_item_id, order_id, product_id, quantity, unit_price, last_updated_at
        FROM order_items
        WHERE last_updated_at > :wm
    """,
}


def _require_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"Missing environment variable: {name}")
    return val


def main() -> None:
    wallet_dir = _require_env("ATP_WALLET_DIR")
    dsn = _require_env("ATP_DSN")
    password = _require_env("ATP_PASSWORD")
    namespace = _require_env("OCI_NAMESPACE")
    region = _require_env("OCI_REGION")
    bucket = os.environ.get("OCI_BUCKET", "portfolio-data-lake")

    os.environ["TNS_ADMIN"] = wallet_dir
    conn = oracledb.connect(user="OLTP_SHOP", password=password, dsn=dsn)

    object_storage = oci.object_storage.ObjectStorageClient(
        oci.config.from_file(),
        service_endpoint=f"https://objectstorage.{region}.oraclecloud.com",
    )

    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ingest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    for dataset, sql in QUERIES.items():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_watermark FROM etl_audit.extract_watermark WHERE dataset_name = :ds",
                {"ds": dataset},
            )
            row = cur.fetchone()
            if row is None:
                print(f"{dataset}: no watermark row — run extract_watermark DDL first")
                continue
            wm = row[0]

            cur.execute(sql, {"wm": wm})
            columns = [d[0].lower() for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        if not rows:
            print(f"{dataset}: no new rows since {wm}")
            continue

        body = "\n".join(json.dumps(r, default=str) for r in rows).encode()
        object_name = f"bronze/{dataset}/ingest_date={ingest_date}/batch_{batch_id}.jsonl"
        object_storage.put_object(namespace, bucket, object_name, body)
        print(f"Uploaded {len(rows)} rows → oci://{bucket}@{namespace}/{object_name}")

        max_wm = max(r["last_updated_at"] for r in rows)
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE etl_audit.extract_watermark
                SET last_watermark = :wm, last_batch_id = :bid, updated_at = SYSTIMESTAMP
                WHERE dataset_name = :ds
                """,
                {"wm": max_wm, "bid": batch_id, "ds": dataset},
            )
        conn.commit()

    conn.close()


if __name__ == "__main__":
    main()
