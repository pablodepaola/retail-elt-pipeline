# Project 3 — ATP → ADW Migration on OCI (Assessment, Data Pump, Cutover)

Simulate an enterprise migration: move an OLTP + analytics workload from **Autonomous Transaction Processing** to a dedicated **Autonomous Data Warehouse** within OCI, using **Object Storage** as the transfer layer and a formal **cutover runbook**.

> Even though both databases are already "in the cloud," this is exactly how teams **split OLTP from analytics** on OCI — a very common real-world project type.

## Skills demonstrated

- Migration assessment and inventory
- **Data Pump** export/import with **Object Storage**
- **DBMS_CLOUD** credentials on Autonomous DB
- Cutover planning, validation, rollback
- Performance and cost comparison on OCI

## OCI services used

| Service | Role |
|---------|------|
| PORTFOLIO_ATP | Source (OLTP + legacy reporting schema) |
| PORTFOLIO_ADW | Migration target |
| Object Storage | Dump files, migration logs |
| Vault | Credentials |
| Resource Manager (optional) | Terraform IaC for target ADW |

## Prerequisites

- [00-shared-oci-setup.md](./00-shared-oci-setup.md)
- OLTP data from Project 1 or bootstrap scripts below

## Architecture

```text
PORTFOLIO_ATP ── Data Pump EXPDP ──► Object Storage (.dmp)
                                        │
                                        ▼
                              PORTFOLIO_ADW ◄── IMPDP
```

---

## Phase 1 — Migration assessment (Day 1)

### Step 1.1 — Create legacy reporting schema on ATP

Simulate "analytics running on OLTP" — a common pre-migration pain point.

On **PORTFOLIO_ATP** as `ADMIN`:

```sql
CREATE USER legacy_rpt IDENTIFIED BY "LegacyRpt#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE TO legacy_rpt;
```

As `LEGACY_RPT`:

```sql
CREATE TABLE daily_sales_summary AS
SELECT TRUNC(o.order_date) AS sales_date,
       p.category,
       SUM(oi.quantity * oi.unit_price) AS revenue,
       COUNT(DISTINCT o.order_id) AS order_count
FROM oltp_shop.orders o
JOIN oltp_shop.order_items oi ON oi.order_id = o.order_id
JOIN oltp_shop.products p ON p.product_id = oi.product_id
GROUP BY TRUNC(o.order_date), p.category;

CREATE INDEX ix_daily_sales_dt ON daily_sales_summary(sales_date);

CREATE OR REPLACE PROCEDURE refresh_daily_sales AS
BEGIN
  DELETE FROM daily_sales_summary;
  INSERT INTO daily_sales_summary
  SELECT TRUNC(o.order_date), p.category,
         SUM(oi.quantity * oi.unit_price), COUNT(DISTINCT o.order_id)
  FROM oltp_shop.orders o
  JOIN oltp_shop.order_items oi ON oi.order_id = o.order_id
  JOIN oltp_shop.products p ON p.product_id = oi.product_id
  GROUP BY TRUNC(o.order_date), p.category;
  COMMIT;
END;
/
```

### Step 1.2 — Inventory script

Run on ATP as `ADMIN` — save output to `docs/oci-portfolio/project-03/assessment-inventory.txt`:

```sql
SELECT owner, object_type, COUNT(*) cnt
FROM dba_objects
WHERE owner IN ('OLTP_SHOP', 'LEGACY_RPT', 'STG')
GROUP BY owner, object_type
ORDER BY 1, 2;

SELECT owner, segment_name, segment_type,
       ROUND(bytes/1024/1024, 2) mb
FROM dba_segments
WHERE owner IN ('OLTP_SHOP', 'LEGACY_RPT')
ORDER BY bytes DESC;

SELECT table_name, num_rows, last_analyzed
FROM dba_tables
WHERE owner = 'LEGACY_RPT';
```

### Step 1.3 — Write assessment document

Create `migration-assessment.md` with:

| Section | Content |
|---------|---------|
| Scope | Schemas: `LEGACY_RPT` (move), `OLTP_SHOP` (stay on ATP) |
| Dependencies | Procedures reading OLTP tables |
| Risks | Cross-schema joins after migration |
| Strategy | **Replatform** — move reporting to ADW; OLTP stays on ATP |
| Downtime window | 2 hours Sunday 02:00–04:00 UTC |
| Rollback | Keep ATP schema 7 days; re-point BI tool |

---

## Phase 2 — Prepare Object Storage credentials (Day 1)

### Step 2.1 — Create IAM policy for ADW to read Object Storage

```text
Allow service autonomousdatabase to manage objects in compartment portfolio-data
Allow service autonomousdatabase to read buckets in compartment portfolio-data
```

### Step 2.2 — Create credential on ATP and ADW

On **both** databases as `ADMIN`:

```sql
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name   => 'MIGRATION_CRED',
    username          => 'your-object-storage-api-signing-user',
    password          => 'your-auth-token'  -- from OCI user auth token
  );
END;
/
```

> **Autonomous recommended approach:** Console → ATP/ADW → **Data Load** → use guided export to Object Storage (creates credential automatically). Use that for the lab if `DBMS_CLOUD` auth is cumbersome.

Record Object Storage URL format:

```text
https://objectstorage.<region>.oraclecloud.com/n/<namespace>/b/portfolio-data-lake/o/migration/
```

---

## Phase 3 — Export from ATP (Day 2)

### Step 3.1 — Export LEGACY_RPT schema

**Method A — OCI Console (easiest)**

1. ATP details → **Tools** → **Export** (or Database Actions → Data Pump Export).
2. Schema: `LEGACY_RPT`
3. Destination: bucket `portfolio-data-lake`, prefix `migration/expdmp/legacy_rpt_%U.dmp`
4. Compression: enabled
5. Start job → monitor until **COMPLETED**.

**Method B — PL/SQL on Autonomous**

```sql
DECLARE
  h1 NUMBER;
BEGIN
  h1 := DBMS_DATAPUMP.OPEN(
    operation   => 'EXPORT',
    job_mode    => 'SCHEMA',
    job_name    => 'EXP_LEGACY_RPT',
    version     => 'LATEST'
  );
  DBMS_DATAPUMP.ADD_FILE(
    handle    => h1,
    filename  => 'legacy_rpt_%U.dmp',
    directory => 'DATA_PUMP_DIR',
    credential=> 'MIGRATION_CRED'
  );
  DBMS_DATAPUMP.METADATA_FILTER(h1, 'SCHEMA_EXPR', 'IN (''LEGACY_RPT'')');
  DBMS_DATAPUMP.START_JOB(h1);
END;
/
```

> On Autonomous, directory maps to Object Storage via cloud integration — use Console wizard if PL/SQL path errors.

### Step 3.2 — Validate dump in bucket

Console → Object Storage → verify `.dmp` files exist and size > 0.

---

## Phase 4 — Import to ADW (Day 2)

### Step 4.1 — Create target schema on ADW

```sql
CREATE USER legacy_rpt IDENTIFIED BY "LegacyRpt#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE TO legacy_rpt;
```

### Step 4.2 — Import

**Console:** ADW → Import from Object Storage → select dump files → target schema `LEGACY_RPT`.

**Verify:**

```sql
SELECT table_name, num_rows FROM user_tables;

SELECT sales_date, SUM(revenue) FROM legacy_rpt.daily_sales_summary
GROUP BY sales_date ORDER BY 1;
```

Row counts must match ATP export inventory.

---

## Phase 5 — Refactor cross-database dependencies (Day 3)

After migration, reporting on ADW must read OLTP data without local copies where possible.

### Option A — Replicate OLTP tables via GoldenGate (Project 2)

Use `CDC_LANDING` on ADW as read-only source for refreshed marts.

### Option B — Scheduled incremental pull (lab)

Create on ADW:

```sql
CREATE TABLE staging_orders AS SELECT * FROM oltp_shop.orders WHERE 1=0;

-- OCI Data Integration task: ATP.ORDERS → ADW.STAGING_ORDERS (incremental)
```

Rebuild `daily_sales_summary` on ADW from staging + dimension tables.

### Step 5.1 — Rewrite procedure on ADW

```sql
CREATE OR REPLACE PROCEDURE legacy_rpt.refresh_daily_sales AS
BEGIN
  DELETE FROM legacy_rpt.daily_sales_summary;
  INSERT INTO legacy_rpt.daily_sales_summary
  SELECT TRUNC(o.order_date), p.category,
         SUM(oi.quantity * oi.unit_price), COUNT(DISTINCT o.order_id)
  FROM staging_orders o
  JOIN staging_order_items oi ON oi.order_id = o.order_id
  JOIN staging_products p ON p.product_id = oi.product_id
  GROUP BY TRUNC(o.order_date), p.category;
  COMMIT;
END;
/
```

---

## Phase 6 — Performance benchmark (Day 3)

Run the same query on ATP vs ADW:

```sql
-- Heavy aggregation
SELECT category,
       EXTRACT(YEAR FROM sales_date) yr,
       SUM(revenue) rev,
       SUM(order_count) orders
FROM daily_sales_summary
GROUP BY category, EXTRACT(YEAR FROM sales_date);
```

Record in `benchmark-results.md`:

| Metric | ATP (LEGACY_RPT) | ADW (LEGACY_RPT) |
|--------|------------------|------------------|
| Elapsed time | ? sec | ? sec |
| CPU time | ? | ? |
| Buffer gets | ? | ? |

Enable **Result Cache** or **Materialized View** on ADW for additional win:

```sql
CREATE MATERIALIZED VIEW legacy_rpt.mv_daily_category
BUILD IMMEDIATE REFRESH COMPLETE ON DEMAND AS
SELECT * FROM legacy_rpt.daily_sales_summary;
```

---

## Phase 7 — Cutover runbook (Day 4)

Document `cutover-runbook.md`:

### T-7 days
- [ ] Freeze schema changes on `LEGACY_RPT` at ATP
- [ ] Final assessment sign-off

### T-1 day
- [ ] Full export + import rehearsal (measure duration)
- [ ] Validate row counts checksum

### T-0 (cutover window)

| Time | Step |
|------|------|
| 02:00 | Disable `refresh_daily_sales` job on ATP |
| 02:05 | Final incremental export (changed rows only if using GG) |
| 02:20 | Import delta to ADW |
| 02:40 | Run validation queries |
| 02:50 | Re-point BI connection strings to ADW wallet |
| 03:00 | Smoke test dashboards |
| 03:30 | Go/No-Go decision |

### T+1
- [ ] Monitor ADW performance
- [ ] Keep ATP `LEGACY_RPT` read-only for rollback

### Rollback plan
- Re-point BI to ATP within 15 minutes if validation fails
- Document failure criteria: row count mismatch > 0.1%, query timeout > 2× benchmark

---

## Phase 8 — Cost analysis (Day 4)

Fill `cost-comparison.md`:

| Item | ATP only (before) | ATP + ADW (after) |
|------|-------------------|-------------------|
| ADB compute | 1× Always Free | 2× Always Free (still $0 if both free tier) |
| Storage GB | ? | ? |
| ETL runtime cost | high on OLTP | offloaded to ADW |
| Object Storage | — | pennies for dumps |

---

## Portfolio deliverables

```text
docs/oci-portfolio/project-03/
├── migration-assessment.md
├── cutover-runbook.md
├── benchmark-results.md
├── cost-comparison.md
└── validation-queries.sql
```

### CV bullets

- Led **ATP → ADW migration** on OCI using **Data Pump** and **Object Storage**, with formal cutover and rollback planning.
- Performed schema inventory, dependency analysis, and post-migration performance benchmarking on **Autonomous Database**.
- Refactored reporting workloads off OLTP onto **Autonomous Data Warehouse**, reducing analytics load on transactional systems.

---

## Teardown

- Delete `.dmp` files from `portfolio-data-lake/migration/` when no longer needed
- Drop duplicate `LEGACY_RPT` on ATP if you only want ADW copy

---

## Next

→ [Project 4: PL/SQL Tuning on Autonomous DB](./04-plsql-tuning-autonomous-db-oci.md)
