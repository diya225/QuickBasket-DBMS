# QuickBasket — SQL-first dark store system

A database systems course project built around a normalized relational schema, MySQL 8 transactions, row locking, and inspectable live data changes. The Flask pages are a thin client for exercising those database operations. Use **MySQL Workbench** beside the app to inspect the same rows changing in real time.

## Recommended course demo: MySQL Workbench + app

Requirements: Python 3.10+, MySQL 8 Community Server, MySQL Workbench, and a browser.

1. Open MySQL Workbench and connect to your local MySQL 8 server.
2. Open `sql/schema.sql` and run it. This creates the `darkstore` database and its 11 InnoDB tables, including primary keys, foreign keys, checks, and indexes.
3. In the VS Code terminal, install and configure the app:

```powershell
cd "C:\Users\DIYA MANU\dbms"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "mysql+pymysql://root:YOUR_MYSQL_PASSWORD@127.0.0.1:3306/darkstore"
$env:SECRET_KEY = "replace-with-a-long-random-value"
python app.py
```

Replace `YOUR_MYSQL_PASSWORD` with the password for your MySQL user. If that user is not `root`, give it access to the `darkstore` database and use its username/password in the URL. The app connects to that same database, creates any missing tables, and inserts the demo records on first launch.

4. Open <http://127.0.0.1:5000>, sign in as the Store Manager (`admin` / `admin123`), and open **SQL lab** in the top bar.
5. In Workbench, open `sql/course_queries.sql`. Run the live stock query, place an order in the app as a customer, then run the same query again. The available quantity decreases and reserved quantity increases. The order header, line items, and journal rows are committed in that same transaction.

The SQL lab page polls the connected database every two seconds and shows live row counts and committed transaction activity. Expand an event to inspect its parameterized SQL pattern and before/after values. Workbench is the place to show and run the actual DDL and SELECT statements; it must connect to the same server and schema shown in the app's SQL lab.

## Demo accounts

| Workspace | Email / phone / username | Password |
| --- | --- | --- |
| Customer | `customer@demo.local` | `demo12345` |
| Picker | `9000000011` (Aarav) or `9000000012` (Maya) | `demo12345` |
| Delivery partner | `9000000021` (Ravi) or `9000000022` (Isha) | `demo12345` |
| Store manager | `admin` | `admin123` |

Customer registration defaults to the sample store's Bengaluru coordinates (`12.9784, 77.6408`). Use nearby coordinates for the local catalog. Demo manager credentials can be overridden through `ADMIN_USERNAME` and `ADMIN_PASSWORD` environment variables.

## Quick preview without MySQL

For a quick local preview, leave `DATABASE_URL` unset. The app falls back to SQLite and creates `instance/darkstore.db`. SQLite supports the project workflows, but use MySQL 8 for the course demonstration of InnoDB row locks and Workbench live queries. The SQLite checkout lock only serializes requests in a single Flask process.

## SQL teaching materials

- `sql/schema.sql` — runnable MySQL 8 DDL for all normalized entities and constraints.
- `sql/course_queries.sql` — joins, catalog, inventory, low-stock and daily reports, audit queries, and a rollback-safe transaction/row-lock demo.
- SQL lab in the manager workspace — live row counts and committed business SQL activity.
- `WALKTHROUGH.md` — app workflows and a teacher-friendly order-to-SQL demonstration script.

The checkout uses `SELECT ... FOR UPDATE` on inventory rows, verifies stock, reserves inventory, inserts `orders` and `order_item` rows, and commits atomically. The `sql_activity` table records a durable teaching journal in the same transaction. It stores parameterized SQL patterns and bound values for business operations; it is not MySQL's server-wide general query log.

## Project structure

- `app.py` — Flask routes, ORM mapping, transaction logic, role checks, seed data, and live SQL activity API.
- `sql/` — MySQL schema DDL and course queries.
- `templates/` and `static/` — customer, picker, delivery, manager, and SQL lab pages.
- `requirements.txt` — Python dependencies, including the MySQL PyMySQL driver.
- `.env.example` — configuration reference. Set environment variables in the terminal before `python app.py`; it is not loaded automatically.

Payment gateways, live maps/GPS, and native mobile clients are outside the project scope. The app uses entered latitude/longitude to choose a serviceable store.
