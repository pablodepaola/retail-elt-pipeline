# Project 5 — Hybrid Lakehouse on OCI (ATP + Object Storage + Data Flow)

Build a **medallion architecture** (Bronze → Silver → Gold) where **Autonomous ATP** remains the system of record, data lands in **OCI Object Storage**, transforms run on **OCI Data Flow** (managed Spark), and curated metrics sync back to **Autonomous ADW** for serving.

This project extends your main repo (`pipeline/`, `dbt/`, `oracle_publish.py`) into a full OCI-native pattern.

## Skills demonstrated

- Incremental extraction from **Autonomous DB**
- **Object Storage** data lake (Bronze/Silver/Gold)
- **OCI Data Flow** PySpark batch processing
- Data contracts, reconciliation, quarantine
- Reverse sync to **ADW** analytics schema

## OCI services used

| Service | Role |
|---------|------|
| PORTFOLIO_ATP | System of record |
| PORTFOLIO_ADW | Gold serving layer |
| Object Storage | Bronze/Silver/Gold Parquet |
| OCI Data Flow | Spark transformations |
| OCI Functions + Events (optional) | Trigger on new Bronze files |
| Vault | DB credentials |

## Cost note

- Object Storage: cheap / Always Free tier
- **Data Flow**: pay per OCPU-minute — delete applications when done
- ADB: Always Free

## Prerequisites

- [00-shared-oci-setup.md](./00-shared-oci-setup.md)
- Projects 1–2 helpful but not required
- Python 3.10+ locally for extract script testing

## Architecture

```text
PORTFOLIO_ATP ──incremental extract──► Object Storage /bronze/
                                              │
                                              ▼
                                    OCI Data Flow (Spark)
                                              │
                         ┌────────────────────┼────────────────────┐
                         ▼                    ▼                    ▼
                    /silver/              /gold/            quarantine/
                         │                    │
                         └──────────► PORTFOLIO_ADW.analytics.*
```

---

## Phase 1 — Data contracts & bucket layout (Day 1)

### Step 1.1 — Object Storage prefixes

In bucket `portfolio-data-lake`, create logical prefixes (folders):

```text
bronze/orders/ingest_date=YYYY-MM-DD/
bronze/order_items/ingest_date=YYYY-MM-DD/
silver/orders/
silver/order_items/
gold/daily_sales/
gold/customer_metrics/
quarantine/
_audit/reconciliation/
```

### Step 1.2 — Data contract YAML

Create `docs/oci-portfolio/project-05/contracts/orders.yaml`:

```yaml
dataset: orders
version: 1
primary_key: [order_id]
freshness_sla_hours: 24
schema:
  order_id: { type: string, required: true }
  customer_id: { type: integer, required: true }
  order_date: { type: date, required: true }
  status: { type: string, allowed: [COMPLETED, PENDING, CANCELLED] }
quality_rules:
  - name: not_null_order_id
    rule: order_id IS NOT NULL
  - name: valid_status
    rule: status IN ('COMPLETED','PENDING','CANCELLED')
```

Repeat for `order_items.yaml`.

---

## Phase 2 — Incremental extract from ATP (Day 1–2)

### Step 2.1 — Watermark table on ATP

```sql
CREATE TABLE etl_audit.extract_watermark (
    dataset_name    VARCHAR2(100) PRIMARY KEY,
    last_watermark  TIMESTAMP,
    last_batch_id   VARCHAR2(50),
    updated_at      TIMESTAMP DEFAULT SYSTIMESTAMP
);

INSERT INTO etl_audit.extract_watermark VALUES ('orders', TIMESTAMP '1900-01-01', NULL, SYSTIMESTAMP);
INSERT INTO etl_audit.extract_watermark VALUES ('order_items', TIMESTAMP '1900-01-01', NULL, SYSTIMESTAMP);
COMMIT;
```

### Step 2.2 — Python extract script

Create `oci-portfolio/scripts/extract_atp_to_oci.py`:

```python
#!/usr/bin/env python3
"""Incremental extract: PORTFOLIO_ATP → Object Storage Bronze (Parquet)."""
import json
import os
from datetime import datetime, timezone

import oracledb
import oci

CONFIG = {
    "tns_admin": os.environ["ATP_WALLET_DIR"],
    "dsn": os.environ["ATP_DSN"],           # e.g. portfoli_atp_high
    "user": "OLTP_SHOP",
    "password": os.environ["ATP_PASSWORD"],
    "bucket": "portfolio-data-lake",
    "namespace": os.environ["OCI_NAMESPACE"],
    "region": os.environ["OCI_REGION"],
}

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

def main():
    batch_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ingest_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    os.environ["TNS_ADMIN"] = CONFIG["tns_admin"]
    conn = oracledb.connect(user=CONFIG["user"], password=CONFIG["password"], dsn=CONFIG["dsn"])

    object_storage = oci.object_storage.ObjectStorageClient(
        oci.config.from_file(), service_endpoint=f"https://objectstorage.{CONFIG['region']}.oraclecloud.com"
    )

    for dataset, sql in QUERIES.items():
        with conn.cursor() as cur:
            cur.execute(
                "SELECT last_watermark FROM etl_audit.extract_watermark WHERE dataset_name = :ds",
                {"ds": dataset},
            )
            wm = cur.fetchone()[0]

            cur.execute(sql, {"wm": wm})
            columns = [d[0].lower() for d in cur.description]
            rows = [dict(zip(columns, r)) for r in cur.fetchall()]

        if not rows:
            print(f"{dataset}: no new rows")
            continue

        # Serialize to JSON lines (simple Bronze; Data Flow reads JSON or convert to Parquet locally)
        body = "\n".join(json.dumps(r, default=str) for r in rows).encode()
        object_name = f"bronze/{dataset}/ingest_date={ingest_date}/batch_{batch_id}.jsonl"

        object_storage.put_object(CONFIG["namespace"], CONFIG["bucket"], object_name, body)
        print(f"Uploaded {len(rows)} rows → {object_name}")

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
```

### Step 2.3 — Run extract locally

```bash
export ATP_WALLET_DIR=~/.oci/wallets/PORTFOLIO_ATP
export ATP_DSN=portfoli_atp_high
export ATP_PASSWORD='...'
export OCI_NAMESPACE=$(oci os ns get --query data --raw-output)
export OCI_REGION=sa-saopaulo-1

python oci-portfolio/scripts/extract_atp_to_oci.py
```

Verify files in Console → Object Storage.

### Step 2.4 — Schedule extract (optional)

- Run from **OCI Resource Scheduler** + **Functions**, or
- GitHub Actions cron calling the script (aligns with your main repo CD pattern)

---

## Phase 3 — OCI Data Flow Spark jobs (Day 3–5)

### Step 3.1 — Upload Spark application

Create `oci-portfolio/spark/bronze_to_silver.py`:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, current_timestamp, to_date

spark = SparkSession.builder.appName("bronze_to_silver").getOrCreate()

namespace = spark.conf.get("spark.oci.namespace")
bucket = "portfolio-data-lake"
base = f"oci://{bucket}@{namespace}"

# Read Bronze JSONL (all batches)
orders = spark.read.json(f"{base}/bronze/orders/")
items = spark.read.json(f"{base}/bronze/order_items/")

# Silver: cleanse + dedupe
orders_silver = (
    orders.dropDuplicates(["order_id"])
    .filter(col("order_id").isNotNull())
    .withColumn("processed_at", current_timestamp())
)

items_silver = (
    items.dropDuplicates(["order_item_id"])
    .filter(col("order_id").isNotNull() & col("quantity").isNotNull())
    .withColumn("processed_at", current_timestamp())
)

orders_silver.write.mode("overwrite").parquet(f"{base}/silver/orders/")
items_silver.write.mode("overwrite").parquet(f"{base}/silver/order_items/")

spark.stop()
```

Create `oci-portfolio/spark/silver_to_gold.py`:

```python
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum as _sum, countDistinct

spark = SparkSession.builder.appName("silver_to_gold").getOrCreate()

namespace = spark.conf.get("spark.oci.namespace")
bucket = "portfolio-data-lake"
base = f"oci://{bucket}@{namespace}"

orders = spark.read.parquet(f"{base}/silver/orders/")
items = spark.read.parquet(f"{base}/silver/order_items/")

enriched = items.join(orders, "order_id", "inner").withColumn(
    "revenue", col("quantity") * col("unit_price")
)

daily_sales = (
    enriched.groupBy(to_date("order_date").alias("order_date"))
    .agg(
        _sum("revenue").alias("revenue"),
        _sum("quantity").alias("units"),
        countDistinct("order_id").alias("orders"),
    )
)

daily_sales.write.mode("overwrite").parquet(f"{base}/gold/daily_sales/")

spark.stop()
```

Zip and upload:

```bash
cd oci-portfolio/spark && zip -r ../dataflow-apps.zip .
oci os object put -bn portfolio-data-lake --file ../dataflow-apps.zip --name apps/dataflow-apps.zip
```

### Step 3.2 — Create Data Flow application (Console)

1. **Analytics & AI** → **Data Flow** → **Applications** → **Create application**.
2. Name: `app-bronze-to-silver`
3. Spark version: latest supported
4. Archive URI: `oci://portfolio-data-lake@<namespace>/apps/dataflow-apps.zip`
5. Main class/file: `bronze_to_silver.py`
6. Arguments: configure `spark.oci.namespace`
7. Logs: bucket `portfolio-data-lake`, prefix `logs/dataflow/`

Repeat for `app-silver-to-gold`.

### Step 3.3 — Run jobs

1. **Run** `app-bronze-to-silver` → wait **SUCCESS**.
2. **Run** `app-silver-to-gold` → wait **SUCCESS**.
3. Verify Parquet under `silver/` and `gold/` in Object Storage.

---

## Phase 4 — Reconciliation (Day 5)

### Step 4.1 — Reconciliation script

`oci-portfolio/scripts/reconcile.py`:

```python
"""Compare ATP row counts vs Gold aggregates."""
# 1. Query COUNT(*) from ATP orders for watermark window
# 2. Read gold/daily_sales Parquet row counts / sums via PyArrow or Spark
# 3. Write result JSON to _audit/reconciliation/run_<batch_id>.json
# 4. Exit non-zero if mismatch > threshold
```

### Step 4.2 — Quarantine bad batches

In `bronze_to_silver.py`, route records failing contract rules:

```python
bad = orders.filter(~col("status").isin("COMPLETED", "PENDING", "CANCELLED"))
bad.write.mode("append").json(f"{base}/quarantine/orders/")
```

---

## Phase 5 — Load Gold into ADW (Day 6)

### Step 5.1 — External table on ADW pointing to Gold Parquet

On **PORTFOLIO_ADW** as `ADMIN`:

```sql
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name => 'OBJ_STORE_CRED',
    username        => '...',
    password        => '...'
  );
END;
/

BEGIN
  DBMS_CLOUD.CREATE_EXTERNAL_TABLE(
    table_name      => 'EXT_DAILY_SALES',
    credential_name => 'OBJ_STORE_CRED',
    file_uri_list   => 'https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/portfolio-data-lake/o/gold/daily_sales/*.parquet',
    format          => JSON_OBJECT('type' VALUE 'parquet')
  );
END;
/
```

> Parquet external tables on ADW: verify format support for your DB version; alternative — use `DBMS_CLOUD.COPY_DATA` to load into native table.

### Step 5.2 — Native analytics table (matches main repo)

```sql
CREATE TABLE analytics.mart_exec_kpis AS
SELECT order_date,
       NULL AS active_skus,
       units,
       revenue,
       NULL AS gross_margin,
       NULL AS margin_pct
FROM EXT_DAILY_SALES
WHERE 1=0;

-- Scheduled MERGE or TRUNCATE+INSERT from external table
```

Align with `oracle/01_create_mart_tables.sql` in the main repo for APEX dashboard compatibility.

### Step 5.3 — Publish procedure

```sql
CREATE OR REPLACE PROCEDURE analytics.refresh_from_lake AS
BEGIN
  EXECUTE IMMEDIATE 'TRUNCATE TABLE analytics.mart_exec_kpis';
  INSERT INTO analytics.mart_exec_kpis (order_date, units, revenue)
  SELECT order_date, units, revenue FROM EXT_DAILY_SALES;
  COMMIT;
END;
/
```

Schedule with **DBMS_SCHEDULER** after Data Flow completes.

---

## Phase 6 — Orchestration (Day 7)

### Option A — OCI Data Integration master pipeline

```text
1. TASK_EXTRACT (call Function or note: run script externally)
2. TASK_BRONZE_SILVER (trigger Data Flow run via REST API)
3. TASK_SILVER_GOLD
4. TASK_RECONCILE
5. TASK_REFRESH_ADW (SQL task on ADW)
```

### Option B — GitHub Actions (fits your repo)

```yaml
# .github/workflows/oci-lakehouse.yml (conceptual)
jobs:
  extract:
    runs-on: ubuntu-latest
    steps:
      - run: python oci-portfolio/scripts/extract_atp_to_oci.py
  dataflow:
    needs: extract
    steps:
      - run: oci data-flow run create --application-id ...
  publish:
    needs: dataflow
    steps:
      - run: sqlplus ... @refresh_adw.sql
```

### Option C — OCI Events

Object Storage emit event on `bronze/` put → trigger **Function** → start Data Flow run.

---

## Phase 7 — End-to-end test (Day 8)

| Step | Action | Verify |
|------|--------|--------|
| 1 | Insert 10 new orders on ATP | Bronze JSONL file appears |
| 2 | Run bronze→silver | Silver Parquet row count increases |
| 3 | Run silver→gold | Gold daily_sales updated |
| 4 | Reconciliation | Audit JSON shows `passed: true` |
| 5 | `refresh_from_lake` | ADW `mart_exec_kpis` has new dates |
| 6 | APEX dashboard | Charts refresh (if wired from main repo) |

---

## Portfolio deliverables

```text
docs/oci-portfolio/project-05/
├── architecture-lakehouse.png
├── contracts/
├── runbook.md
└── e2e-test-results.md

oci-portfolio/
├── scripts/
│   ├── extract_atp_to_oci.py
│   └── reconcile.py
└── spark/
    ├── bronze_to_silver.py
    └── silver_to_gold.py
```

### CV bullets

- Built **medallion lakehouse** on OCI integrating **Autonomous ATP**, **Object Storage**, and **OCI Data Flow** (Spark).
- Implemented incremental extraction, **data contracts**, quarantine handling, and source-to-gold reconciliation.
- Published curated **Gold** datasets to **Autonomous ADW** for executive analytics and APEX dashboards.

---

## Teardown

1. Delete Data Flow applications.
2. Delete Bronze/Silver/Gold prefixes (or lifecycle policy).
3. Drop external tables on ADW.
4. Keep ATP/ADW Always Free instances.

---

## Link to your existing repo

| Main repo component | OCI Project 5 role |
|--------------------|-------------------|
| `pipeline/extract.py` | Replace/local equivalent → `extract_atp_to_oci.py` |
| DuckDB + dbt transforms | Replaced by Data Flow Silver/Gold (or keep dbt on exported Parquet) |
| `pipeline/oracle_publish.py` | `analytics.refresh_from_lake` procedure |
| `oracle/01_create_mart_tables.sql` | ADW `analytics` schema target tables |
| APEX dashboard | Unchanged — reads ADW marts |

**Hybrid portfolio story:** *"Batch ELT with dbt on DuckDB for CI/CD; production pattern on OCI with ATP + Object Storage + Data Flow + ADW."*

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Data Flow can't read bucket | IAM policy for Data Flow service + correct `oci://` path |
| Spark OOM | Increase executor memory; reduce file size per batch |
| External table Parquet errors | Use `DBMS_CLOUD.COPY_DATA` into native table instead |
| Wallet connection from Functions | Use Instance Principal or Vault secrets in Function |

---

## Complete portfolio

You now have five OCI-native projects. Return to [README](./README.md) for the overview.
