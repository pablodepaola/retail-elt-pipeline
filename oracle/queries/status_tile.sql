-- "Last refreshed / tests passing / data freshness" tile.
SELECT
    pipeline_health,
    TO_CHAR(last_refreshed_at, 'YYYY-MM-DD HH24:MI') AS last_refreshed,
    hours_since_refresh,
    tests_passed,
    tests_failed,
    TO_CHAR(data_through_date, 'YYYY-MM-DD')          AS data_through,
    last_rows_extracted
FROM mart_pipeline_status;
