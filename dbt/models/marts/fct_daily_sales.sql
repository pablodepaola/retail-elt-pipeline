{{
    config(
        materialized='incremental',
        unique_key=['order_date', 'product_id'],
        incremental_strategy='delete+insert',
        on_schema_change='fail'
    )
}}

-- Grain: one row per (order_date, product_id). Incremental + idempotent:
-- on a normal run we reprocess only a trailing window of business days and
-- delete+insert by unique_key, so re-runs and late-arriving rows never double
-- count. A full refresh (--full-refresh) rebuilds the whole history.

select
    order_date,
    product_id,
    category_pt,
    category_en,
    cast(units_sold as bigint)                                     as units,
    cast(round(revenue, 2) as double)                              as revenue,
    cast(round(cogs, 2) as double)                                 as cogs,
    cast(round(gross_margin, 2) as double)                         as gross_margin,
    cast(round(case when revenue > 0 then gross_margin / revenue else 0 end, 4) as double) as margin_pct
from {{ ref('int_daily_product_sales') }}

{% if is_incremental() %}
where order_date >= (
    select coalesce(max(order_date), date '1900-01-01') from {{ this }}
) - interval '{{ var("late_reprocess_days") }}' day
{% endif %}
