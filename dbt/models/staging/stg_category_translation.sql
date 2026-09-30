with src as (
    select * from {{ source('raw', 'category_translation') }}
),

deduped as (
    select *
    from src
    qualify row_number() over (
        partition by product_category_name
        order by _ingest_date desc, _loaded_at desc
    ) = 1
)

select
    product_category_name            as category_pt,
    product_category_name_english    as category_en
from deduped
