{{ config(materialized='table') }}

-- Single-row observability tile: "last refreshed / tests passing / data through".
-- Reads the operational audit table (ensured by on-run-start) + data freshness
-- from the fact. Robust to an empty audit table (cold start) -> nulls, one row.

with last_pass as (
    select *
    from meta.pipeline_runs
    where status = 'PASS'
    order by run_finished_at desc
    limit 1
),

data_fresh as (
    select max(order_date) as data_through_date
    from {{ ref('fct_daily_sales') }}
)

select
    (select run_finished_at  from last_pass)                       as last_refreshed_at,
    (select rows_extracted   from last_pass)                       as last_rows_extracted,
    coalesce((select dbt_tests_passed from last_pass), 0)          as tests_passed,
    coalesce((select dbt_tests_failed from last_pass), 0)          as tests_failed,
    (select data_through_date from data_fresh)                     as data_through_date,
    date_diff('hour', (select run_finished_at from last_pass), now()) as hours_since_refresh,
    case
        when (select run_finished_at from last_pass) is null then 'UNKNOWN'
        when coalesce((select dbt_tests_failed from last_pass), 0) = 0 then 'PASSING'
        else 'FAILING'
    end                                                            as pipeline_health
