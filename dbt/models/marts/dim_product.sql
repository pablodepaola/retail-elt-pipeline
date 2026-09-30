{{ config(materialized='table') }}

select
    p.product_id,
    coalesce(p.category_pt, 'unknown')                as category_pt,
    coalesce(c.category_en, p.category_pt, 'unknown') as category_en,
    coalesce(cr.cost_ratio, {{ var('default_cost_ratio') }}) as cost_ratio
from {{ ref('stg_products') }} p
left join {{ ref('stg_category_translation') }} c
    on p.category_pt = c.category_pt
left join {{ ref('seed_category_cost_ratio') }} cr
    on p.category_pt = cr.product_category_name
