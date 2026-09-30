{{ config(materialized='view') }}

-- Daily realized sales per product (valid statuses only).

select
    order_date,
    product_id,
    category_pt,
    category_en,
    sum(units)         as units_sold,
    sum(revenue)       as revenue,
    sum(cogs)          as cogs,
    sum(gross_margin)  as gross_margin
from {{ ref('int_order_items_enriched') }}
where is_valid_sale
group by 1, 2, 3, 4
