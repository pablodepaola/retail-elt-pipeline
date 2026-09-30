-- Insight #2 -- Interactive Report: products at stockout risk (reorder now first).
SELECT
    product_id,
    category_en,
    inventory_status,
    on_hand_units,
    reorder_point,
    days_of_supply,
    ROUND(sell_through_rate * 100, 1) AS sell_through_pct,
    as_of_date
FROM mart_inventory_health
WHERE inventory_status IN ('STOCKOUT', 'REORDER_NOW')
ORDER BY days_of_supply ASC, on_hand_units ASC;
