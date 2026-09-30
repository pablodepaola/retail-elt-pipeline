with src as (
    select * from {{ source('raw', 'products') }}
),

deduped as (
    select *
    from src
    qualify row_number() over (
        partition by product_id
        order by _ingest_date desc, _loaded_at desc
    ) = 1
)

select
    product_id,
    nullif(product_category_name, '')       as category_pt,
    try_cast(product_weight_g as integer)   as product_weight_g,
    try_cast(product_photos_qty as integer) as product_photos_qty
from deduped
