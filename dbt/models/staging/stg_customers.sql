with src as (
    select * from {{ source('raw', 'customers') }}
),

deduped as (
    select *
    from src
    qualify row_number() over (
        partition by customer_id
        order by _ingest_date desc, _loaded_at desc
    ) = 1
)

select
    customer_id,
    customer_unique_id,
    upper(customer_state) as customer_state,
    customer_city
from deduped
