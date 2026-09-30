{{ config(materialized='table') }}

-- Insight #2 & #3: latest inventory position per product -> stockout risk,
-- overstock/markdown risk, days-of-supply, and sell-through.

with latest as (
    select *
    from {{ ref('int_inventory_position') }}
    qualify row_number() over (
        partition by product_id order by inv_date desc
    ) = 1
)

select
    l.product_id,
    l.category_en,
    l.inv_date                       as as_of_date,
    l.on_hand_units,
    l.reorder_point,
    l.days_of_supply,
    l.sell_through_rate,
    l.is_stockout,
    l.is_stockout_risk,
    l.is_overstock,
    case
        when l.is_stockout            then 'STOCKOUT'
        when l.is_stockout_risk       then 'REORDER_NOW'
        when l.is_overstock           then 'OVERSTOCK'
        else 'HEALTHY'
    end                              as inventory_status
from latest l
