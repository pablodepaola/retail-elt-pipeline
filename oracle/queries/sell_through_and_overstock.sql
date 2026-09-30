-- Insight #3 -- Sell-through leaders/laggards + overstock (markdown risk) flag.
SELECT
    product_id,
    category_en,
    ROUND(sell_through_rate * 100, 1) AS sell_through_pct,
    on_hand_units,
    days_of_supply,
    inventory_status,
    CASE WHEN is_overstock = 1 THEN 'YES' ELSE 'NO' END AS overstock_markdown_risk
FROM mart_inventory_health
ORDER BY sell_through_rate DESC;

-- Donut: inventory status breakdown across the catalog.
-- SELECT inventory_status, COUNT(*) AS skus
-- FROM mart_inventory_health GROUP BY inventory_status;
