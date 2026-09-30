{{ config(materialized='view') }}

-- SYNTHETIC inventory ledger (Olist has no inventory). Fully deterministic using
-- window arithmetic only (no recursion): opening stock + a step-function
-- scheduled replenishment - cumulative sales = on-hand. Documented as a proxy.

with bounds as (
    select min(order_date) as d0, max(order_date) as d1
    from {{ ref('int_daily_product_sales') }}
),

spine as (
    select unnest(generate_series(d0, d1, interval 1 day))::date as inv_date
    from bounds
),

products as (
    select distinct product_id, category_pt, category_en
    from {{ ref('int_daily_product_sales') }}
),

grid as (
    select p.product_id, p.category_pt, p.category_en, s.inv_date
    from products p
    cross join spine s
),

joined as (
    select
        g.product_id,
        g.category_pt,
        g.category_en,
        g.inv_date,
        coalesce(ds.units_sold, 0) as units_sold,
        coalesce(ds.revenue, 0)    as revenue
    from grid g
    left join {{ ref('int_daily_product_sales') }} ds
        on g.product_id = ds.product_id
       and g.inv_date   = ds.order_date
),

calc as (
    select
        *,
        sum(units_sold) over w                                   as cum_units,
        (row_number() over w) - 1                                as days_elapsed,
        greatest(avg(units_sold) over (partition by product_id), 0.1) as expected_daily_demand
    from joined
    window w as (
        partition by product_id
        order by inv_date
        rows between unbounded preceding and current row
    )
),

factored as (
    select
        *,
        -- Deterministic per-product supply factor in ~[0.2, 2.0]. Spreads SKUs
        -- across the stockout/overstock spectrum so the proxy is realistic even
        -- on a short window. Stable function of product_id (synthetic).
        0.2 + 1.8 * ((hash(product_id) % 1000) / 1000.0) as stock_factor
    from calc
),

ledger as (
    select
        product_id,
        category_pt,
        category_en,
        inv_date,
        units_sold,
        revenue,
        cum_units,
        expected_daily_demand,
        greatest({{ var('min_opening_stock') }},
                 ceil(expected_daily_demand * {{ var('opening_stock_days') }} * stock_factor))::int as opening_stock,
        greatest(1,
                 ceil(expected_daily_demand * {{ var('restock_cover_days') }} * stock_factor))::int as restock_qty,
        floor(days_elapsed / {{ var('restock_interval_days') }})::int                 as n_restocks,
        ceil(expected_daily_demand * {{ var('reorder_point_days') }})::int            as reorder_point
    from factored
)

select
    product_id,
    category_pt,
    category_en,
    inv_date,
    cast(units_sold as bigint)                                 as units_sold,
    cast(revenue as double)                                    as revenue,
    cast(cum_units as bigint)                                  as cum_units,
    cast(expected_daily_demand as double)                      as expected_daily_demand,
    cast(opening_stock as bigint)                              as opening_stock,
    cast(restock_qty as bigint)                                as restock_qty,
    cast(n_restocks * restock_qty as bigint)                   as cum_replenishment,
    cast(opening_stock + (n_restocks * restock_qty) - cum_units as bigint) as on_hand,
    cast(greatest(opening_stock + (n_restocks * restock_qty) - cum_units, 0) as bigint) as on_hand_units,
    cast(reorder_point as bigint)                              as reorder_point,
    cast(opening_stock + (n_restocks * restock_qty) as bigint) as total_supply,
    cast(round(
        greatest(opening_stock + (n_restocks * restock_qty) - cum_units, 0)
        / expected_daily_demand, 1) as double)                 as days_of_supply,
    (opening_stock + (n_restocks * restock_qty) - cum_units) <= reorder_point as is_stockout_risk,
    (opening_stock + (n_restocks * restock_qty) - cum_units) <= 0             as is_stockout,
    cast(round(
        greatest(opening_stock + (n_restocks * restock_qty) - cum_units, 0)
        / expected_daily_demand, 1) as double) > {{ var('overstock_days') }} as is_overstock,
    cast(round(
        case when (opening_stock + (n_restocks * restock_qty)) > 0
             then cum_units::double / (opening_stock + (n_restocks * restock_qty))
             else 0 end, 4) as double)                         as sell_through_rate
from ledger
