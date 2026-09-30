-- Line/combo chart: daily revenue and margin % trend.
SELECT
    order_date,
    revenue,
    gross_margin,
    margin_pct * 100 AS margin_pct
FROM mart_exec_kpis
ORDER BY order_date;
