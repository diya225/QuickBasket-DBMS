# QuickBasket feature walkthrough and test guide

This guide covers the working features in the project and gives a repeatable way to try them. For the course demonstration, follow the **MySQL Workbench + app** setup in `README.md`; SQLite is only a quick preview. Then open `http://127.0.0.1:5000`.

## Demo data and roles

The fresh database includes one Bengaluru dark store, three product categories, six products, shelf locations, two pickers, two delivery partners, and a customer. The catalog contains ordinary stock plus low stock examples: Tomatoes (4 available) and Basmati Rice (2 available).

| Role | Sign-in ID | Password |
| --- | --- | --- |
| Customer | `customer@demo.local` | `demo12345` |
| Picker | `9000000011` or `9000000012` | `demo12345` |
| Delivery partner | `9000000021` or `9000000022` | `demo12345` |
| Store manager | `admin` | `admin123` |

All passwords are stored as Werkzeug password hashes. The manager credentials can be changed with `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables. Set a non-demo `SECRET_KEY` when using MySQL or exposing the app beyond localhost.

## Lead with SQL in your presentation

The relational database is the main artifact for the course. `sql/schema.sql` defines the 10 normalized business entities from the brief plus `sql_activity`, the teaching journal. It includes primary/foreign keys, an order-line composite primary key, check constraints on stock/quantities, unique keys, and useful indexes. The app uses SQLAlchemy only as its database access layer; MySQL is the database of record for the recommended demonstration.

**Live Workbench demonstration:**

1. Run `sql/schema.sql` in MySQL Workbench, then start the Flask app with `DATABASE_URL` pointing to that same `darkstore` schema.
2. In Workbench open `sql/course_queries.sql` and execute query 3, **LIVE STOCK VIEW**. Note milk's `available_qty` and `reserved_qty`.
3. In the app, sign in as customer (`customer@demo.local` / `demo12345`), add two milk units, and place the order.
4. In Workbench run query 3 again. Available stock is down by two; reserved stock is up by two. Run query 2 to see the order and its price-snapshotted line item. Run query 4 to inspect the committed SQL journal rows.
5. In the app, sign in as manager and open **SQL lab**. It polls the same MySQL database every two seconds. Table row counts and activity entries update after a committed transaction. Expand an entry to show its SQL pattern and bound values.
6. Continue as the assigned picker and delivery partner. Run query 2 and query 4 after each status step to see order status updates and reservation release.

Workbench and the app must connect to the same MySQL server/database. The SQL lab's `CONNECTED DATABASE` indicator reports the active driver (`MYSQL` or `SQLITE`). For a teacher-facing live database demo, it must say `MYSQL`.

**Explain the transaction:** checkout starts a database transaction, selects each inventory row with `SELECT ... FOR UPDATE`, checks that enough stock remains, decreases available stock, increases reserved stock, inserts the order and its lines, records journal entries, and commits. If stock is insufficient, the transaction rolls back so none of those changes persist. The SQL file has a separate rollback-safe row-lock example for showing `FOR UPDATE` without changing stock permanently.

## Features and checks

### 1. Registration, login, and role separation

Customers can register with name, phone, email, password, delivery address, and coordinates. Picker and delivery accounts are seeded for the demo; managers use configured credentials. The sign-in form selects the workspace and accepts email for customers or phone for field staff. Signed-in users see only their own workspace, and protected routes reject other roles.

**Try it:** register a new customer with all required fields and a password of at least eight characters, sign out, then sign in. Try a wrong password and leave a required registration field blank; both should give a validation message. Sign in using the manager role, then try the picker role with the same `admin` identity; it should fail.

### 2. Store-radius matching and local catalog

The app calculates straight-line distance from a customer's saved coordinates and selects the closest store whose service radius contains the location. The product catalog only includes that store's inventory with positive available quantity. No in-radius store produces a not-serviceable message.

**Try it:** register using `12.9788` latitude and `77.6412` longitude. The Indiranagar store should appear with the six demo products. Register another user far away, for example `13.15`, `77.80`, and check that no store serves them. To test store extensibility, add a store from the manager screen and register a customer near its coordinates.

### 3. Cart and checkout with stock reservation

Customers add a quantity of an in-stock product to a session cart, remove cart lines, and see estimated totals. Checkout checks stock again inside a database transaction, locks each selected inventory row on MySQL, decreases `available_qty`, increases `reserved_qty`, snapshots each product's current price into the order item, creates the order, and assigns a free picker when one is available. SQL activity entries commit with the order and inventory changes. An unavailable quantity rejects the whole order and leaves inventory unchanged. SQLite demo checkout also serializes requests in a single application process.

**Try it:** add two units of milk, note the estimate, and place the order. Sign in as manager and check that available stock decreased by two and reserved stock increased by two. Try adding more units than remain, or change the cart quantity in the form before checkout; checkout should reject stale stock rather than oversell. Try checkout with an empty cart. The demo does not take payment.

**Concurrency check:** to test the production locking behavior, configure MySQL 8, prepare exactly one unit in a product's store inventory, then submit two one-unit checkouts at nearly the same time from two customer sessions. One should succeed and the other should receive the stock-changed message; available stock must remain zero, never negative. This is a manual load check; no automated test suite is bundled.

### 4. Products, categories, stores, and shelf inventory

The manager can add categories, products and stores. Inventory receiving creates or reuses a store bin identified by aisle, rack, and shelf, then adds units to that product's stock at the bin. The snapshot shows available and reserved quantities beside each location. Product setup includes a low-stock threshold.

**Try it:** sign in as manager. Add a category, then a product with a price and threshold, then receive units at a new bin such as aisle `03`, rack `02`, shelf `01`. Confirm the product and stock line appear in the inventory snapshot. Add a second store with a test address and coordinates; it should appear in the store selector and can serve customers within its configured radius.

### 5. Picker assignment and aisle-sorted pick lists

Checkout assigns the first free picker at the serving store. The manager can assign a free same-store picker to queued orders. The picker sees assigned active orders and can open a pick list sorted by aisle, rack, then shelf. A picker advances an order from placed to picking and then packed. Packing frees the picker and attempts to assign a free delivery partner.

**Try it:** place an order with at least two different products. Sign in as the assigned picker, open the order's pick list, and verify bin locations ascend by aisle/rack/shelf. Mark the order as picking, then packed. Try marking it packed before starting; the status guard should reject skipping the step. If no picker was available at checkout, assign one from the manager's order table.

### 6. Delivery assignment and status tracking

When an order is packed, the app assigns the first free partner for that store. The manager can assign a free partner to a packed order if no automatic assignment was possible. The partner sees their assigned orders and delivery address, then advances the order through out for delivery and delivered. Delivery releases the reserved quantity and frees the partner.

**Try it:** after packing an order, sign in as the assigned delivery partner. Start delivery, then confirm delivery. Check the customer order history and manager order table for `Delivered`. Check the inventory snapshot: reserved should return to its previous value; available stays reduced because those units were fulfilled. Try confirming delivery before starting it; the status guard should block the jump.

### 7. Low-stock and daily order reports

The manager dashboard summarizes active orders, low-stock lines, free pickers, and free partners. Low stock is based on `available_qty <= product.low_stock_threshold`. The daily report groups this month's orders by date. The inventory table gives a per-bin stock snapshot; the recent order table includes worker assignments and pick-list links.

**Try it:** on a fresh database, Tomatoes and Basmati Rice should appear in the low-stock section because their available quantity is below five. Receive more units of one of them above threshold and reload; that line should disappear from low stock. Place orders on the current date and check that the count appears in the daily report.

### 8. Validation and recoverable errors

Forms validate required values and numeric ranges. Duplicate customer email or phone and duplicate category names are rejected. Invalid roles, missing orders, unavailable assignments, and illegal status transitions show a message instead of silently updating the database.

**Try it:** register a duplicate email, add a duplicate category, submit a negative stock receipt, and attempt to assign an already busy picker. Each operation should report a validation error; existing inventory and assignments should remain intact.

### 9. SQL lab and SQL audit journal

The manager's **SQL lab** page shows table row counts from the configured database, polls every two seconds, and appends new committed activity. The `sql_activity` journal includes event type, actor, order/product IDs, a parameterized SQL pattern, JSON bind values (including before/after quantities when relevant), and a short explanation. The journal insert runs inside the same transaction as the associated business change, so a rolled-back checkout does not leave a success event behind.

The SQL lab is an application activity journal, not a capture of every internal MySQL statement or the server-wide general query log. Use MySQL Workbench and `sql/course_queries.sql` to demonstrate and execute the DDL, joins, reports, and current database values directly. The SQL lab offers manager-only downloads of both teaching SQL files.

**Try it:** open the SQL lab as manager, open Workbench on the same database, and keep both visible. Receive ten units of stock in the app. The `inventory` count updates if it was a new bin/product pair, and a `stock_received` activity appears; query 3 in Workbench shows the quantity. Then place a customer order and compare the available/reserved values before and after.

## Order lifecycle at a glance

`placed` → `picking` → `packed` → `out_for_delivery` → `delivered`

The customer view shows orders and current statuses. The manager view can inspect all recent orders and assign workers. Pickers and delivery partners can only update their own assigned orders.

## Resetting the local demo

Stop the Flask process, remove `instance/darkstore.db`, then start the app again. The empty schema and original demo records are recreated automatically. Do not remove that file if you need to retain orders created during your walkthrough.

## Scope notes

The brief explicitly excludes payment gateways, live maps, and a native mobile app. Location entry, service-radius calculations, order coordination, and status tracking are present; GPS/device location and real-world payment/route services are not connected.
