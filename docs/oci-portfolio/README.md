# Oracle Cloud (OCI) Data Engineer Portfolio — Tutorials

Five hands-on portfolio projects built **entirely on Oracle Cloud Infrastructure**. No local Oracle database required.

| # | Project | Primary OCI services | Est. time |
|---|---------|----------------------|-----------|
| 0 | [Shared OCI setup](./00-shared-oci-setup.md) | IAM, VCN, Compartment, Vault, ADB | 2–3 hrs |
| 1 | [Enterprise DWH + ETL](./01-enterprise-dwh-oci-data-integration.md) | 2× Autonomous DB, OCI Data Integration | 1–2 weeks |
| 2 | [Real-time CDC](./02-goldengate-cdc-oci.md) | ATP, ADW, OCI GoldenGate, Object Storage | 1 week |
| 3 | [ATP → ADW migration](./03-atp-to-adw-migration-oci.md) | Data Pump, Object Storage, Resource Manager | 1 week |
| 4 | [PL/SQL performance tuning](./04-plsql-tuning-autonomous-db-oci.md) | Autonomous DB, SQL Developer Web, Performance Hub | 3–5 days |
| 5 | [Hybrid lakehouse](./05-hybrid-lakehouse-oci.md) | ATP, Object Storage, OCI Data Flow, Functions | 1–2 weeks |

## Domain

All projects use a **retail e-commerce** scenario (orders, customers, products) — compatible with the Olist-style data in the main repo (`pipeline/`, `dbt/`).

## Cost posture

- **Always Free:** 2 Autonomous Databases (20 GB each), Object Storage (20 GB), Vault secrets.
- **Paid if left running:** OCI GoldenGate deployment, OCI Data Integration workspace, Data Flow runs, Compute VMs. Each tutorial includes a **teardown** section.

Start with [00-shared-oci-setup.md](./00-shared-oci-setup.md) before any project.
