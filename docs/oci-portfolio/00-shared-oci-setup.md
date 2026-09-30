# 00 — Shared OCI Setup (Do This First)

Complete this once. Every portfolio project reuses these resources.

## What you will create

| Resource | Name (suggested) | Purpose |
|----------|------------------|---------|
| Compartment | `portfolio-data` | Isolate all lab resources |
| VCN | `portfolio-vcn` | Networking for GoldenGate / Data Integration |
| Vault | `portfolio-vault` | Store DB passwords |
| Autonomous DB (ATP) | `PORTFOLIO_ATP` | OLTP / source system |
| Autonomous DB (ADW) | `PORTFOLIO_ADW` | Data warehouse / analytics |
| Object Storage bucket | `portfolio-data-lake` | Data Pump dumps, Parquet, Bronze files |
| IAM group + policies | `portfolio-admins` | Least-privilege access |

---

## Step 1 — Create an OCI account

1. Go to [https://www.oracle.com/cloud/free/](https://www.oracle.com/cloud/free/).
2. Sign up for **Oracle Cloud Free Tier** (credit card for verification; Always Free resources do not consume credits if you stay within limits).
3. Note your **Home Region** (e.g. `sa-saopaulo-1`, `us-ashburn-1`). GoldenGate and some services are **region-specific** — do all lab work in one region.

---

## Step 2 — Create a compartment

1. Open the OCI Console → **Identity & Security** → **Compartments**.
2. Click **Create compartment**.
3. Name: `portfolio-data`
4. Description: `OCI Data Engineer portfolio lab`
5. Parent: root compartment (or your tenancy root)
6. Click **Create**.

Always select `portfolio-data` in the compartment dropdown before creating resources.

---

## Step 3 — Create a VCN

GoldenGate and OCI Data Integration need a **private subnet**.

1. **Networking** → **Virtual cloud networks** → **Start VCN wizard**.
2. Select **VCN with Internet Connectivity**.
3. Name: `portfolio-vcn`
4. Compartment: `portfolio-data`
5. Accept defaults (1 VCN, 1 public + 1 private subnet, Internet Gateway, NAT Gateway).
6. Click **Next** → **Create**.

Record these OCIDs (you will need them later):

- VCN OCID
- **Private subnet** OCID (e.g. `portfolio-vcn-private-subnet-sa-saopaulo-1`)

---

## Step 4 — Create a Vault and secrets

1. **Identity & Security** → **Vault** → **Create vault**.
   - Name: `portfolio-vault`
   - Compartment: `portfolio-data`
   - Vault type: **Default**
2. Open the vault → **Master encryption keys** → **Create key**
   - Name: `portfolio-master-key`
   - Protection mode: **Software**
3. **Secrets** → **Create secret**
   - Name: `atp-admin-password`
   - Secret type: **Plaintext**
   - Value: a strong password (save it in your password manager)
4. Repeat for `adw-admin-password` (can be same or different).

---

## Step 5 — Provision Autonomous Transaction Processing (ATP)

This is your **OLTP source** database.

1. **Oracle Database** → **Autonomous Database** → **Create autonomous database**.
2. Compartment: `portfolio-data`
3. Display name: `PORTFOLIO_ATP`
4. Database name: `PORTFATP` (max 14 chars)
5. Workload type: **Transaction Processing**
6. Deployment type: **Serverless**
7. Always Free: **enabled** (toggle ON if available in your region)
8. Version: latest 23ai or 19c
9. Administrator password: use the value from `atp-admin-password` secret (or enter manually and store in Vault)
10. Network access:
    - For lab simplicity: **Secure access from everywhere** (restrict in production)
    - For production-style lab: **Virtual cloud network** → select `portfolio-vcn` private subnet + add your IP to ACL
11. License: **License Included**
12. Click **Create autonomous database**.

Wait until state = **Available** (~5–10 minutes).

### Download wallet (ATP)

1. On the ATP details page → **Database connection**.
2. Click **Download wallet**.
3. Set a wallet password → download `Wallet_PORTFOLIOATP.zip`.
4. Store in `~/.oci/wallets/PORTFOLIO_ATP/` (do not commit to Git).

### Enable SQL Developer Web

1. ATP details → **Database actions** → **SQL** (opens SQL Developer Web).
2. Sign in as `ADMIN` with your password.

---

## Step 6 — Provision Autonomous Data Warehouse (ADW)

This is your **analytics / DWH** target.

1. **Autonomous Database** → **Create autonomous database**.
2. Display name: `PORTFOLIO_ADW`
3. Database name: `PORTFADW`
4. Workload type: **Data Warehouse**
5. Always Free: **enabled**
6. Same region, compartment, password strategy as ATP.
7. Network: same choice as ATP.
8. Click **Create**.

Download wallet to `~/.oci/wallets/PORTFOLIO_ADW/`.

---

## Step 7 — Create Object Storage bucket

1. **Storage** → **Buckets** → **Create bucket**.
2. Name: `portfolio-data-lake`
3. Compartment: `portfolio-data`
4. Default storage tier: **Standard**
5. Visibility: **Private**
6. Click **Create**.

### Create a pre-authenticated request (PAR) for Data Pump (optional)

For Data Pump to/from Object Storage you will use **DBMS_CLOUD** with credentials. Simpler lab path: use **SQL Developer Web** import/export wizards or `credential` objects (covered in Project 3).

---

## Step 8 — Install local tools (your laptop)

These connect **to** OCI; the database itself runs in the cloud.

### OCI CLI

```bash
brew install oci-cli          # macOS
# or: pip install oci-cli

oci setup config
# Follow prompts: tenancy OCID, user OCID, region, key pair
```

### SQLcl (recommended)

```bash
# Download from https://www.oracle.com/database/sqldeveloper/technologies/sqlcl/
# Or use SQL Developer bundled SQLcl

sql PORTFOLIO_ATP_admin@portfolio_atp_high
# Uses tnsnames.ora from wallet
```

### Python (for Object Storage / extract scripts)

```bash
pip install oracledb oci
```

### Wallet configuration

Unzip both wallets. Merge `tnsnames.ora` entries into one file or use separate wallet paths.

Example `tnsnames.ora` entries (names vary by region):

```
portfoli_atp_high = (description= ... service_name=...portfoli_atp_high.adb.oraclecloud.com ...)
portfoli_adw_high = (description= ... service_name=...portfoli_adw_high.adb.oraclecloud.com ...)
```

Connect:

```bash
export TNS_ADMIN=~/.oci/wallets/PORTFOLIO_ATP
sql admin/YourPassword@portfoli_atp_high
```

---

## Step 9 — Bootstrap schemas on ATP and ADW

Run on **PORTFOLIO_ATP** (SQL Developer Web or SQLcl):

```sql
-- OLTP application schema
CREATE USER oltp_shop IDENTIFIED BY "OltpShop#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE,
      CREATE SEQUENCE, CREATE TRIGGER TO oltp_shop;

-- Staging for inbound files
CREATE USER stg IDENTIFIED BY "Stg#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW TO stg;

-- ETL audit / tooling
CREATE USER etl_audit IDENTIFIED BY "Audit#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE TO etl_audit;
```

Run on **PORTFOLIO_ADW**:

```sql
-- Data warehouse schema
CREATE USER dwh IDENTIFIED BY "Dwh#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE TO dwh;

-- Analytics / marts (aligns with main repo oracle/ tables)
CREATE USER analytics IDENTIFIED BY "Analytics#2026Lab"
  DEFAULT TABLESPACE DATA QUOTA UNLIMITED ON DATA;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW TO analytics;

-- Allow DWH user to read OLTP via DB link later (optional)
-- GRANT CREATE DATABASE LINK TO dwh;
```

> **Security note:** These are lab passwords. In production use OCI Vault secrets and rotate regularly.

---

## Step 10 — IAM policy for your user

If resources fail with "not authorized", add a policy on compartment `portfolio-data`:

```text
Allow group portfolio-admins to manage all-resources in compartment portfolio-data
```

For least privilege in a real environment, split policies per service (ADB, Object Storage, goldenGate-family, data-integration-family).

---

## Step 11 — Tagging convention

Apply freeform tags to every resource:

| Tag | Value |
|-----|-------|
| `project` | `oci-data-engineer-portfolio` |
| `environment` | `lab` |
| `owner` | `your-github-handle` |

---

## Validation checklist

- [ ] ATP status = Available; SQL Developer Web login works as `ADMIN`
- [ ] ADW status = Available; SQL Developer Web login works as `ADMIN`
- [ ] Bucket `portfolio-data-lake` exists
- [ ] Vault secrets created
- [ ] Wallet downloaded for both ADBs
- [ ] `sqlcl` or SQL Developer connects to both databases
- [ ] `oci os ns get` returns your namespace (for Object Storage URLs)

---

## Cost control

| Resource | Always Free? | Action when done |
|----------|--------------|------------------|
| 2× Autonomous DB | Yes (2 max) | Stop manually if pausing weeks; run weekly `SELECT 1` to avoid idle reclaim |
| Object Storage | 20 GB free | Delete old dumps/Parquet |
| GoldenGate deployment | **No** | Delete deployment after Project 2 |
| Data Integration workspace | **No** | Pause/delete workspace after Project 1 |
| Data Flow applications | Pay per run | Delete applications after Project 5 |

---

## Next

→ [Project 1: Enterprise DWH with OCI Data Integration](./01-enterprise-dwh-oci-data-integration.md)
