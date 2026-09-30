{{ config(materialized='table') }}

-- Insight #1: margin and revenue by category over time.

select
    order_date,
    category_en,
    sum(units)                                                     as units,
    round(sum(revenue), 2)                                         as revenue,
    round(sum(cogs), 2)                                            as cogs,
    round(sum(gross_margin), 2)                                    as gross_margin,
    round(sum(gross_margin) / nullif(sum(revenue), 0), 4)          as margin_pct
from {{ ref('fct_daily_sales') }}
group by 1, 2
