with src as (
    select * from {{ source('raw', 'order_items') }}
),

deduped as (
    select *
    from src
    qualify row_number() over (
        partition by order_id, order_item_id
        order by _ingest_date desc, _loaded_at desc
    ) = 1
)

select
    order_id,
    cast(order_item_id as integer)            as order_item_id,
    product_id,
    seller_id,
    try_cast(shipping_limit_date as timestamp) as shipping_limit_at,
    cast(price as double)                      as item_price,
    cast(freight_value as double)              as freight_value,
    1                                          as units,  -- Olist: one row == one unit
    cast(_ingest_date as date)                 as ingest_date
from deduped
