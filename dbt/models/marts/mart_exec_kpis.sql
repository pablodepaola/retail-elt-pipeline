{{ config(materialized='table') }}

-- Daily executive KPI line for the APEX dashboard headline tiles + trend.

select
    order_date,
    cast(count(distinct product_id) as bigint)                 as active_skus,
    cast(sum(units) as bigint)                                 as units,
    cast(round(sum(revenue), 2) as double)                     as revenue,
    cast(round(sum(gross_margin), 2) as double)                as gross_margin,
    cast(round(sum(gross_margin) / nullif(sum(revenue), 0), 4) as double) as margin_pct
from {{ ref('fct_daily_sales') }}
group by 1
