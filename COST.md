# COST.md — How this stays $0

This project is designed to run **entirely on free tiers**. Below is the warehouse
size, run frequency, and the cost posture of every component, plus the paid-risk
flags to watch.

## TL;DR

| Component | Tier | Cost | Notes |
|---|---|---|---|
| GitHub Actions (orchestration, CI/CD) | Free (public repo) | **$0** | Unlimited minutes on public repos |
| DuckDB (warehouse engine) | OSS | **$0** | Embedded, no server |
| dbt-core + dbt-duckdb | OSS | **$0** | |
| Great Expectations | OSS | **$0** | |
| Warehouse persistence | GitHub Releases | **$0** | `.duckdb` + watermark stored as a release asset |
| dbt docs + lineage | GitHub Pages | **$0** | Static site |
| Oracle Autonomous DB + APEX (serving) | Oracle **Always Free** | **$0** | 2 ADBs, 20 GB each, APEX included |
| Kaggle dataset (optional) | Free API token | **$0** | Only needed for the real dataset |

**Total recurring cost: $0.**

## Warehouse size & run profile

- **Engine size:** DuckDB single-file database. Sample run ≈ a few MB; the full
  Olist dataset (~100K orders, ~112K order items) yields a `.duckdb` in the **tens
  of MB** range — comfortably inside GitHub Release asset limits (2 GB/asset) and
  Oracle Always Free storage (20 GB).
- **Rows processed:** incremental, ~1–2K rows per simulated business day on the
  sample; the full dataset backfills to ~100K orders / ~112K items total.
- **Run time:** the dbt build + tests complete in **~1 second** on the sample; a
  full CD job (restore → extract → load → GE → dbt → publish → persist) is a couple
  of minutes — well within free Actions limits.
- **Run frequency:** **daily** cron (`17 6 * * *` UTC). Backfills are on-demand via
  `workflow_dispatch`. Daily × a few minutes ≈ negligible.

## How each piece stays free

- **GitHub Actions:** keep the repo **public** → minutes are unlimited and free.
  (Private repos get 2,000 free minutes/month; this pipeline would still fit, but
  public is the safe $0 choice.)
- **State between runs:** instead of a paid object store, the updated warehouse and
  watermark are tarred and pushed to the **`warehouse-latest` GitHub Release**, then
  restored at the start of the next run. No external storage bill.
- **Serving:** Oracle **Always Free** Autonomous Database includes APEX at no cost.
  Marts are tiny daily snapshots (full TRUNCATE+INSERT), so storage and compute stay
  trivial.

## Paid-risk flags (watch these)

1. **Oracle Always Free idle reclaim.** Always Free ADB **auto-stops after 7 idle
   days** and can be **reclaimed after ~90 days** of inactivity. *Mitigation:* the
   daily CD run writes to it (keeps it active); if you pause the schedule, add a
   weekly keep-alive `SELECT 1`.
2. **Private repo minutes.** If you make the repo private, you consume the 2,000
   min/month allotment. Stay public to keep it unlimited.
3. **GitHub Release asset limits.** Single asset limit is large (2 GB); the full
   Olist warehouse is far smaller. If you scale the data 100×, switch persistence to
   MotherDuck free tier or object storage.
4. **Kaggle token = secret.** If you wire the real dataset, the Kaggle token is a
   GH secret (free), never committed.
5. **Cold start cost.** A full historical backfill processes ~2 years of data; run
   it once via `workflow_dispatch` with `full_refresh=true`, then daily increments
   are cheap.

## If you outgrow free

- **Warehouse:** DuckDB → MotherDuck (free tier) → BigQuery/Snowflake (paid) — the
  dbt models are portable; mostly a profile change.
- **Orchestration:** GitHub Actions → Prefect/Dagster/Airflow when you need richer
  scheduling, retries, and a backfill UI.
- **Serving:** Oracle APEX scales up within paid Autonomous DB shapes if concurrency
  grows.
