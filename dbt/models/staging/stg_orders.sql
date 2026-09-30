with src as (
    select * from {{ source('raw', 'orders') }}
),

-- Dedup overlapping late-arriving snapshots: keep the most recently ingested
-- version of each order_id (CDC-style "latest wins").
deduped as (
    select *
    from src
    qualify row_number() over (
        partition by order_id
        order by _ingest_date desc, _loaded_at desc
    ) = 1
)

select
    order_id,
    customer_id,
    lower(order_status)                                   as order_status,
    cast(order_purchase_timestamp as timestamp)          as order_purchased_at,
    cast(cast(order_purchase_timestamp as timestamp) as date) as order_date,
    try_cast(order_approved_at as timestamp)             as order_approved_at,
    try_cast(order_delivered_customer_date as timestamp) as order_delivered_at,
    try_cast(order_estimated_delivery_date as timestamp) as order_estimated_at,
    cast(_ingest_date as date)                            as ingest_date,
    try_cast(_loaded_at as timestamp)                     as loaded_at
from deduped
