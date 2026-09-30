{{ config(materialized='view') }}

-- Line-level fact: revenue is real (Olist price); COGS/margin are SYNTHETIC,
-- derived from the category cost-ratio seed (documented proxy).

with items as (
    select * from {{ ref('stg_order_items') }}
),
orders as (
    select * from {{ ref('stg_orders') }}
),
products as (
    select * from {{ ref('stg_products') }}
),
cats as (
    select * from {{ ref('stg_category_translation') }}
),
cost as (
    select * from {{ ref('seed_category_cost_ratio') }}
)

select
    i.order_id,
    i.order_item_id,
    i.product_id,
    o.order_date,
    o.order_status,
    o.order_status in ('{{ var("valid_sale_statuses") | join("','") }}') as is_valid_sale,
    coalesce(p.category_pt, 'unknown')               as category_pt,
    coalesce(c.category_en, p.category_pt, 'unknown') as category_en,
    i.units,
    i.item_price                                      as revenue,
    round(i.item_price
          * coalesce(cr.cost_ratio, {{ var('default_cost_ratio') }}), 2) as cogs,
    round(i.item_price
          - i.item_price
          * coalesce(cr.cost_ratio, {{ var('default_cost_ratio') }}), 2) as gross_margin
from items i
inner join orders   o  on i.order_id = o.order_id
left  join products p  on i.product_id = p.product_id
left  join cats     c  on p.category_pt = c.category_pt
left  join cost     cr on p.category_pt = cr.product_category_name
