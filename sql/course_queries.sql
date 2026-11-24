-- QuickBasket: live queries for a Database Systems course demonstration.
-- Select the darkstore schema first. The application writes to this same database.

-- 1. Confirm the relational schema and foreign keys.
SHOW TABLES;
DESCRIBE inventory;
SHOW CREATE TABLE orders;
SHOW CREATE TABLE order_item;

-- 2. Check normalized rows: order header, customer/store and line items.
SELECT o.id AS order_id, o.order_time, o.status,
       c.name AS customer, s.store_name,
       p.product_name, oi.quantity, oi.unit_price,
       (oi.quantity * oi.unit_price) AS line_total
FROM orders AS o
JOIN customer AS c ON c.id = o.customer_id
JOIN dark_store AS s ON s.id = o.store_id
JOIN order_item AS oi ON oi.order_id = o.id
JOIN product AS p ON p.id = oi.product_id
ORDER BY o.id DESC, p.product_name;

-- 3. LIVE STOCK VIEW. Run this query before and after a checkout.
SELECT s.store_name, p.id AS product_id, p.product_name,
       b.aisle_no, b.rack_no, b.shelf_no,
       i.available_qty, i.reserved_qty
FROM inventory AS i
JOIN product AS p ON p.id = i.product_id
JOIN bin_location AS b ON b.id = i.bin_id
JOIN dark_store AS s ON s.id = b.store_id
ORDER BY s.store_name, p.product_name, b.aisle_no, b.rack_no;

-- 4. Reservation journal: compare before/after quantities and SQL patterns.
SELECT id, created_at, event_type, actor, order_id, product_id,
       sql_text, parameters_json, explanation
FROM sql_activity
ORDER BY id DESC
LIMIT 30;

-- 5. Low-stock report using the product's configured threshold.
SELECT s.store_name, p.product_name, i.available_qty,
       p.low_stock_threshold, b.aisle_no, b.rack_no, b.shelf_no
FROM inventory AS i
JOIN product AS p ON p.id = i.product_id
JOIN bin_location AS b ON b.id = i.bin_id
JOIN dark_store AS s ON s.id = b.store_id
WHERE i.available_qty <= p.low_stock_threshold
ORDER BY i.available_qty, p.product_name;

-- 6. Orders per day (current month).
SELECT DATE(order_time) AS order_day, COUNT(*) AS orders_placed
FROM orders
WHERE order_time >= DATE_FORMAT(CURRENT_DATE, '%Y-%m-01')
GROUP BY DATE(order_time)
ORDER BY order_day DESC;

-- 7. Safe row-lock teaching demo. This transaction is rolled back at the end,
-- so it demonstrates SELECT ... FOR UPDATE without retaining a stock change.
SET @demo_inventory_id := (SELECT id FROM inventory ORDER BY available_qty DESC LIMIT 1);
START TRANSACTION;
SELECT id, available_qty, reserved_qty
FROM inventory WHERE id = @demo_inventory_id FOR UPDATE;
UPDATE inventory
SET available_qty = available_qty - 1, reserved_qty = reserved_qty + 1
WHERE id = @demo_inventory_id AND available_qty >= 1;
SELECT id, available_qty, reserved_qty
FROM inventory WHERE id = @demo_inventory_id;
ROLLBACK;

-- 8. Verify the demo transaction rolled back (compare with query 3).
SELECT id, available_qty, reserved_qty
FROM inventory WHERE id = @demo_inventory_id;
