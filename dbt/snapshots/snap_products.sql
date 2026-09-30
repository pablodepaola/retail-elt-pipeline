{% snapshot snap_products %}
{{
    config(
        unique_key='product_id',
        strategy='check',
        check_cols=['category_pt'],
        invalidate_hard_deletes=True
    )
}}

-- SCD2 history of the product master. If a product's category changes (or drifts)
-- across snapshots, we keep the full history with valid-from/valid-to, which lets
-- the warehouse reason about late/changing reference data instead of overwriting.
select
    product_id,
    category_pt
from {{ ref('stg_products') }}

{% endsnapshot %}
