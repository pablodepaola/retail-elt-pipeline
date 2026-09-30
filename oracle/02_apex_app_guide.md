# Oracle APEX Exec Dashboard — Build Guide

This guide turns the published marts into a live **Oracle APEX** application for the
head of merchandising / finance. It is 100% free on **Oracle Cloud Always Free**.

> The ELT (DuckDB + dbt) is the engine. Oracle is a thin **serving** layer: the
> pipeline full-refreshes a handful of small mart tables, and APEX reads them live.

---

## 0. Paid-risk flags (read first)

- **Always Free Autonomous Database** is $0, but it **auto-stops after 7 days idle**
  and can be **reclaimed after ~90 days of inactivity**. Mitigation: the daily CD
  pipeline writes to it (keeps it active), and you can add a tiny keep-alive query.
- Signup requires a credit card for **identity verification only**; Always Free
  resources do not incur charges. Stay within: 2 ADBs, 20 GB storage each.
- Keep the GitHub repo **public** so Actions minutes stay unlimited/free.

---

## 1. Provision the database (one-time, ~10 min)

1. Create a free account at <https://www.oracle.com/cloud/free/>.
2. Console → **Autonomous Database** → **Create Autonomous Database**.
   - Workload type: **Data Warehouse** (or Transaction Processing — either works).
   - Choose **Always Free** toggle. Set an ADMIN password.
3. When provisioned, open **Database Actions** → note your connection details.
4. Download the **wallet** (Database connection → Download Wallet). You'll get a
   `Wallet_xxx.zip`. Keep it secret.

## 2. Create the APEX workspace + serving tables

1. Database Actions → **APEX** → create a workspace (e.g. `RETAIL`) on a schema
   (e.g. `RETAIL_APP`).
2. In APEX → **SQL Workshop → SQL Commands**, paste and run
   [`01_create_mart_tables.sql`](01_create_mart_tables.sql).

## 3. Wire up the GitHub Actions publisher

Add these repo secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
|---|---|
| `ORACLE_USER` | the APEX schema user (e.g. `RETAIL_APP`) |
| `ORACLE_PASSWORD` | that user's password |
| `ORACLE_DSN` | a TNS alias from `tnsnames.ora` in the wallet (e.g. `myadb_high`) |
| `ORACLE_WALLET_B64` | base64 of the wallet zip: `base64 -i Wallet_xxx.zip` |
| `ORACLE_WALLET_PASSWORD` | wallet password (if you set one) |

The CD workflow decodes the wallet to `oracle/wallet/`, sets `ORACLE_WALLET_DIR`,
and runs `python -m pipeline.cli run --publish`. `python-oracledb` connects in
**thin mode** (no Oracle client install needed).

> No Oracle account yet? Run `python -m pipeline.cli --sample run --dry-run` to
> emit `data/exports/*.CSV`, then **APEX → SQL Workshop → Utilities → Data Load**
> to load them manually. Same dashboard, manual refresh.

## 4. Build the app (App Builder → Create App → 1 page, blank)

Add these regions. SQL for each lives in [`queries/`](queries/).

| Region | Type | Source SQL |
|---|---|---|
| Status tile (last refreshed / tests passing / data through) | **Cards** or Display-only | [`status_tile.sql`](queries/status_tile.sql) |
| Headline KPIs (revenue, margin, margin %, units) | **Cards** | [`kpi_headline.sql`](queries/kpi_headline.sql) |
| Revenue & margin % trend | **Chart → Line (dual axis)** | [`revenue_margin_trend.sql`](queries/revenue_margin_trend.sql) |
| Margin by category (Insight #1) | **Chart → Bar** | [`margin_by_category.sql`](queries/margin_by_category.sql) |
| Stockout risk (Insight #2) | **Interactive Report** | [`stockout_risk.sql`](queries/stockout_risk.sql) |
| Sell-through & overstock (Insight #3) | **Interactive Report** + Donut | [`sell_through_and_overstock.sql`](queries/sell_through_and_overstock.sql) |

Tips:
- Color the `inventory_status` / `pipeline_health` columns with **Highlight** rules
  (STOCKOUT red, REORDER_NOW amber, OVERSTOCK blue, HEALTHY green; PASSING green).
- Add a date range page item and reference `:P1_FROM` / `:P1_TO` in the trend query
  for interactivity.

## 5. Publish & share

App Builder → **Run** → copy the app URL. In APEX **Shared Components →
Authentication**, you can set the page to public (read-only) for the evaluator,
or keep auth and share a guest login. Put the final URL in:
- the repo `README.md` badge row, and
- the dbt exposure `models/marts/_exposures.yml` (`url:`).

## 6. Keep-alive (avoid the 7-day idle stop)

The daily CD run already touches the DB. If you pause the schedule, add a GitHub
Actions cron that runs a trivial `SELECT 1` weekly, or log into the console.
