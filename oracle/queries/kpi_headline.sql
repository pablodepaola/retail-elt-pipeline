-- KPI cards (Cards region or Display-only items). One row of headline numbers.
SELECT
    SUM(revenue)                                            AS total_revenue,
    SUM(gross_margin)                                       AS total_gross_margin,
    ROUND(SUM(gross_margin) / NULLIF(SUM(revenue), 0), 4)   AS margin_pct,
    SUM(units)                                              AS total_units,
    SUM(active_skus)                                        AS sku_day_count
FROM mart_exec_kpis;
