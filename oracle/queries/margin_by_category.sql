-- Insight #1 -- Bar chart: gross margin and margin % by category.
SELECT
    category_en,
    SUM(revenue)                                          AS revenue,
    SUM(gross_margin)                                     AS gross_margin,
    ROUND(SUM(gross_margin) / NULLIF(SUM(revenue), 0) * 100, 1) AS margin_pct
FROM mart_sales_by_category
GROUP BY category_en
ORDER BY gross_margin DESC;
