# Project 2 — Real-Time CDC with OCI GoldenGate (ATP → ADW)

Replicate transactional changes from **Autonomous Transaction Processing (ATP)** to **Autonomous Data Warehouse (ADW)** in near real time using **OCI GoldenGate**.

## Skills demonstrated

- Change Data Capture (CDC)
- **OCI GoldenGate** deployments, connections, Extract/Replicat
- Initial load + incremental synchronization
- Operational monitoring (lag, statistics, restart)

## OCI services used

| Service | Role |
|---------|------|
| PORTFOLIO_ATP | Source OLTP |
| PORTFOLIO_ADW | CDC landing / mirror schema |
| OCI GoldenGate | Managed GoldenGate deployment |
| Object Storage | Data Pump initial load dump (optional) |
| Vault | DB credentials for connections |

## Cost warning

OCI GoldenGate deployments are **not Always Free**. Use **Development/testing** shape (minimum 1 OCPU) and **delete the deployment** when finished. Budget ~$1–3/hour depending on region and shape.

## Prerequisites

- [00-shared-oci-setup.md](./00-shared-oci-setup.md) completed
- Project 1 OLTP tables on ATP (or run Phase 1 DDL below)
- VCN private subnet OCID recorded

## Architecture

```text
PORTFOLIO_ATP (OLTP_SHOP) ── Extract ──► Trail ──► Replicat ──► PORTFOLIO_ADW (CDC_LANDING)
```

---

## Phase 1 — Prepare source and target schemas (Day 1)

### Step 1.1 — Enable supplemental logging on ATP

Connect to **PORTFOLIO_ATP** as `ADMIN`:

```sql
ALTER DATABASE ADD SUPPLEMENTAL LOG DATA;
ALTER DATABASE ENABLE GOLDENGATE REPLICATION;
```

For each replicated table as `OLTP_SHOP`:

```sql
ALTER TABLE oltp_shop.customers ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
ALTER TABLE oltp_shop.orders ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
ALTER TABLE oltp_shop.order_items ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
ALTER TABLE oltp_shop.products ADD SUPPLEMENTAL LOG DATA (ALL) COLUMNS;
```

### Step 1.2 — Create CDC landing schema on ADW

Connect to **PORTFOLIO_ADW** as `ADMIN`:

```sql
CREATE USER cdc_landing IDENTIFIED BY "CdcLanding#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE TO cdc_landing;

-- Mirror tables (same structure as source + CDC metadata)
CREATE TABLE cdc_landing.customers (
    customer_id      NUMBER PRIMARY KEY,
    full_name        VARCHAR2(200),
    email            VARCHAR2(200),
    city             VARCHAR2(100),
    country          VARCHAR2(2),
    status           VARCHAR2(20),
    created_at       TIMESTAMP,
    updated_at       TIMESTAMP,
    gg_op_type       VARCHAR2(10),   -- INSERT/UPDATE/DELETE
    gg_op_ts         TIMESTAMP,
    gg_pos           VARCHAR2(128)
);

CREATE TABLE cdc_landing.orders (
    order_id         VARCHAR2(32) PRIMARY KEY,
    customer_id      NUMBER,
    order_date       DATE,
    status           VARCHAR2(20),
    last_updated_at  TIMESTAMP,
    gg_op_type       VARCHAR2(10),
    gg_op_ts         TIMESTAMP,
    gg_pos           VARCHAR2(128)
);

-- Repeat for order_items, products
```

### Step 1.3 — Create GoldenGate admin user on ATP

```sql
CREATE USER ggadmin IDENTIFIED BY "GgAdmin#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;

GRANT CREATE SESSION TO ggadmin;
EXEC DBMS_GOLDENGATE_AUTH.GRANT_ADMIN_PRIVILEGE('GGADMIN');
GRANT SELECT ANY TABLE TO ggadmin;
GRANT INSERT ANY TABLE TO ggadmin;
GRANT UPDATE ANY TABLE TO ggadmin;
GRANT DELETE ANY TABLE TO ggadmin;
GRANT ALTER ANY TABLE TO ggadmin;
```

Store `ggadmin` password in Vault secret `ggadmin-password`.

---

## Phase 2 — Create OCI GoldenGate deployment (Day 1)

### Step 2.1 — Create deployment

1. Console → **Oracle Database** → **GoldenGate** → **Deployments** → **Create deployment**.
2. Name: `portfolio-gg-deployment`
3. Compartment: `portfolio-data`
4. Deployment type: **Data replication**
5. Technology: **Oracle Autonomous Database**
6. Profile: **Development or testing** (1 OCPU)
7. VCN: `portfolio-vcn` → **private subnet**
8. Click **Create** (15–20 minutes until **Active**).

### Step 2.2 — Create source connection (ATP)

1. GoldenGate → **Connections** → **Create connection**.
2. Type: **Autonomous Database**
3. Name: `conn-atp-source`
4. **Select database**: choose `PORTFOLIO_ATP`
5. Username: `GGADMIN`
6. Password: from Vault
7. Traffic routing: **Shared endpoint** (lab) or **Dedicated endpoint** (production-style)
8. Test → **Successful**.

### Step 2.3 — Create target connection (ADW)

1. Create connection `conn-adw-target`
2. Select `PORTFOLIO_ADW`
3. Username: `CDC_LANDING` (or `GGADMIN` with grants on target)
4. Test → **Successful**.

### Step 2.4 — Assign connections to deployment

1. Open `portfolio-gg-deployment` → **Assigned connections**.
2. Assign both `conn-atp-source` and `conn-adw-target`.

### Step 2.5 — Open GoldenGate console

1. Deployment details → **Launch console**.
2. Sign in with deployment credentials (set during create).

---

## Phase 3 — Initial load (Day 2)

You need target tables populated before CDC starts (or use GoldenGate initial load workflow).

### Option A — Data Pump via Object Storage (recommended)

**On ATP (SQL Developer Web as ADMIN):**

1. Create directory mapping to Object Storage (Autonomous supports `DBMS_CLOUD`):

```sql
BEGIN
  DBMS_CLOUD.CREATE_CREDENTIAL(
    credential_name => 'OBJ_STORE_CRED',
    username        => 'your-oci-identity-api-key-fingerprint-or-token',
    password        => 'your-auth-token'
  );
END;
/
```

> For Autonomous, Oracle recommends **resource principal** or **pre-authenticated request**. Simpler lab path: use **SQL Developer Web** → **Load** from Object Storage wizard.

2. Export schema:

```sql
-- Run via DBMS_DATAPUMP or Cloud Console Data Pump export to bucket:
-- portfolio-data-lake/dumps/oltp_initial.dmp
```

**On ADW:** Import into `CDC_LANDING` schema from same dump.

### Option B — Manual copy for small lab data

```sql
-- On ADW as CDC_LANDING (one-time)
INSERT INTO cdc_landing.customers
SELECT customer_id, full_name, email, city, country, status, created_at, updated_at,
       'INSERT', SYSTIMESTAMP, 'INIT'
FROM customers@atp_dblink;  -- if DB link configured
COMMIT;
```

For portfolio without DB link: run `INSERT SELECT` via a one-off **OCI Data Integration** task or SQLcl script copying ~100 rows.

---

## Phase 4 — Configure replication (Day 2–3)

In the **GoldenGate deployment console**:

### Step 4.1 — Add Extract (integrated)

1. **Overview** → **Create** → **Extract**.
2. Name: `EXT_OLTP`
3. Source connection: `conn-atp-source`
4. Type: **Integrated** (for Oracle AD)
5. Source tables: `OLTP_SHOP.CUSTOMERS`, `ORDERS`, `ORDER_ITEMS`, `PRODUCTS`
6. Trail: `ET` (auto-created)
7. Register extract → **Start**.

### Step 4.2 — Add Replicat

1. **Create** → **Replicat**.
2. Name: `REP_ADW`
3. Target connection: `conn-adw-target`
4. Source trail: `ET`
5. Map definitions:

```text
MAP OLTP_SHOP.CUSTOMERS, TARGET CDC_LANDING.CUSTOMERS;
MAP OLTP_SHOP.ORDERS, TARGET CDC_LANDING.ORDERS;
MAP OLTP_SHOP.ORDER_ITEMS, TARGET CDC_LANDING.ORDER_ITEMS;
MAP OLTP_SHOP.PRODUCTS, TARGET CDC_LANDING.PRODUCTS;
```

6. **Start** replicat.

### Step 4.3 — Handle conflicts (lab)

For mirror tables with identical keys, use **INSERTAPPEND** or **MERGE** mode in replicat parameters. Document choice in README.

---

## Phase 5 — Test CDC scenarios (Day 3)

Run on **ATP** as `OLTP_SHOP`:

### Test 1 — Insert

```sql
INSERT INTO customers (full_name, email, city) VALUES ('Diego Ferreira', 'diego@email.com', 'Porto Alegre');
COMMIT;
```

Verify on ADW within ~30 seconds:

```sql
SELECT * FROM cdc_landing.customers WHERE full_name = 'Diego Ferreira';
```

### Test 2 — Update

```sql
UPDATE customers SET city = 'Brasília', updated_at = SYSTIMESTAMP WHERE full_name = 'Ana Silva';
COMMIT;
```

### Test 3 — Delete

```sql
DELETE FROM order_items WHERE order_id = 'O1001' AND product_id = 'P001';
COMMIT;
```

### Test 4 — Burst load

```sql
BEGIN
  FOR i IN 1..500 LOOP
    INSERT INTO orders VALUES ('O' || (1000+i), 1, SYSDATE, 'COMPLETED', SYSTIMESTAMP);
  END LOOP;
  COMMIT;
END;
/
```

### Step 5.1 — Check GoldenGate statistics

In deployment console:

1. Click **EXT_OLTP** → **Statistics** → verify insert/update counts.
2. Click **REP_ADW** → **Statistics** → matching apply counts.
3. Note **lag** on Overview page.

---

## Phase 6 — Monitoring package on ADW (Day 4)

```sql
CREATE TABLE cdc_landing.cdc_monitor_log (
    checked_at       TIMESTAMP DEFAULT SYSTIMESTAMP,
    table_name       VARCHAR2(100),
    source_count     NUMBER,
    target_count     NUMBER,
    lag_seconds      NUMBER
);

-- Schedule via DBMS_SCHEDULER: compare counts every 5 minutes
-- (Source count via ATP DB link or store last known extract SCN)
```

Create a simple **OCI Monitoring alarm** on GoldenGate deployment health (optional).

### Operational runbook (document in repo)

| Scenario | Action |
|----------|--------|
| Replicat stopped | Check error in GG console → fix mapping → restart |
| Lag > 60s | Check ATP load; scale GG deployment OCPU temporarily |
| Extract abended | Reattach extract per Oracle doc for AD |

---

## Phase 7 — Portfolio deliverables

```text
docs/oci-portfolio/project-02/
├── architecture-cdc.png
├── gg-parameter-notes.md
├── test-results.md          # 4 tests with timestamps + lag
└── runbook.md
```

### CV bullets

- Implemented **OCI GoldenGate** CDC from **Autonomous ATP** to **Autonomous ADW** with integrated Extract/Replicat.
- Executed initial load via **Data Pump + Object Storage** and validated near-real-time replication under burst traffic.
- Authored operational runbook for lag monitoring, failure recovery, and reconciliation.

---

## Teardown (important)

1. Stop Extract and Replicat in GG console.
2. Console → GoldenGate → **Delete deployment** `portfolio-gg-deployment`.
3. Delete connections if unused.
4. Keep ATP/ADW schemas for demo queries or drop `CDC_LANDING`.

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Extract registration fails | Verify `ENABLE GOLDENGATE REPLICATION` and supplemental logging |
| Replicat discards | Check key constraints on target; use `HANDLECOLLISIONS` only in lab |
| Connection timeout | Verify private subnet security lists allow GG ingress |
| Wallet auth errors | Recreate connection selecting ATP/ADW from picker (auto-wallet) |

---

## Next

→ [Project 3: ATP → ADW Migration](./03-atp-to-adw-migration-oci.md)
