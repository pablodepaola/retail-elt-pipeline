-- ===========================================================================
-- Oracle Autonomous DB: serving tables for the APEX exec dashboard.
-- Run ONCE in your APEX workspace schema (SQL Workshop > SQL Commands, or
-- SQLcl). The Python publisher (pipeline/oracle_publish.py) then TRUNCATE+INSERTs
-- these on every successful pipeline run (idempotent full refresh).
--
-- Column names/types mirror the dbt marts exactly. Booleans -> NUMBER(1) since
-- Oracle has no native boolean in older clients; APEX handles 0/1 cleanly.
-- ===========================================================================

CREATE TABLE mart_exec_kpis (
    order_date     DATE,
    active_skus    NUMBER,
    units          NUMBER,
    revenue        NUMBER,
    gross_margin   NUMBER,
    margin_pct     NUMBER
);

CREATE TABLE mart_sales_by_category (
    order_date     DATE,
    category_en    VARCHAR2(120),
    units          NUMBER,
    revenue        NUMBER,
    cogs           NUMBER,
    gross_margin   NUMBER,
    margin_pct     NUMBER
);

CREATE TABLE mart_inventory_health (
    product_id        VARCHAR2(64),
    category_en       VARCHAR2(120),
    as_of_date        DATE,
    on_hand_units     NUMBER,
    reorder_point     NUMBER,
    days_of_supply    NUMBER,
    sell_through_rate NUMBER,
    is_stockout       NUMBER(1),
    is_stockout_risk  NUMBER(1),
    is_overstock      NUMBER(1),
    inventory_status  VARCHAR2(20)
);

CREATE TABLE fct_daily_sales (
    order_date     DATE,
    product_id     VARCHAR2(64),
    category_pt    VARCHAR2(120),
    category_en    VARCHAR2(120),
    units          NUMBER,
    revenue        NUMBER,
    cogs           NUMBER,
    gross_margin   NUMBER,
    margin_pct     NUMBER
);

CREATE TABLE dim_product (
    product_id     VARCHAR2(64),
    category_pt    VARCHAR2(120),
    category_en    VARCHAR2(120),
    cost_ratio     NUMBER
);

CREATE TABLE mart_pipeline_status (
    last_refreshed_at    TIMESTAMP,
    last_rows_extracted  NUMBER,
    tests_passed         NUMBER,
    tests_failed         NUMBER,
    data_through_date    DATE,
    hours_since_refresh  NUMBER,
    pipeline_health      VARCHAR2(20)
);

-- Helpful indexes for the dashboard filters/joins.
CREATE INDEX ix_fct_daily_sales_date ON fct_daily_sales (order_date);
CREATE INDEX ix_sales_by_cat_date    ON mart_sales_by_category (order_date);
CREATE INDEX ix_inv_status           ON mart_inventory_health (inventory_status);
