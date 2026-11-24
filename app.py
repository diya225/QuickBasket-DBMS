"""Dark store inventory and hyper-local fulfillment demo."""
from __future__ import annotations

import os
import threading
import json
from datetime import datetime, date
from math import asin, cos, radians, sin, sqrt
from functools import wraps

from flask import Flask, flash, g, redirect, render_template, request, send_file, session, url_for
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-only-change-me")
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///darkstore.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True}
db = SQLAlchemy(app)
# SQLite serializes checkout placement within this demo process. MySQL additionally
# uses SELECT ... FOR UPDATE so separate workers cannot reserve the same units.
sqlite_checkout_lock = threading.Lock()


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False, unique=True)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    orders = db.relationship("Order", back_populates="customer")


class DarkStore(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    store_name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    service_radius_km = db.Column(db.Float, nullable=False, default=8)
    bins = db.relationship("BinLocation", back_populates="store")


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_name = db.Column(db.String(80), nullable=False, unique=True)
    products = db.relationship("Product", back_populates="category")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)
    category = db.relationship("Category", back_populates="products")


class BinLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    aisle_no = db.Column(db.String(20), nullable=False)
    rack_no = db.Column(db.String(20), nullable=False)
    shelf_no = db.Column(db.String(20), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("dark_store.id"), nullable=False)
    store = db.relationship("DarkStore", back_populates="bins")


class Inventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    available_qty = db.Column(db.Integer, nullable=False, default=0)
    reserved_qty = db.Column(db.Integer, nullable=False, default=0)
    bin_id = db.Column(db.Integer, db.ForeignKey("bin_location.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    __table_args__ = (db.UniqueConstraint("bin_id", "product_id"), db.CheckConstraint("available_qty >= 0"), db.CheckConstraint("reserved_qty >= 0"))
    bin = db.relationship("BinLocation")
    product = db.relationship("Product")


class Picker(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="free")
    store_id = db.Column(db.Integer, db.ForeignKey("dark_store.id"), nullable=False)


class DeliveryPartner(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="free")
    store_id = db.Column(db.Integer, db.ForeignKey("dark_store.id"), nullable=False)


class Order(db.Model):
    __tablename__ = "orders"
    id = db.Column(db.Integer, primary_key=True)
    order_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status = db.Column(db.String(24), nullable=False, default="placed")
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    store_id = db.Column(db.Integer, db.ForeignKey("dark_store.id"), nullable=False)
    picker_id = db.Column(db.Integer, db.ForeignKey("picker.id"))
    partner_id = db.Column(db.Integer, db.ForeignKey("delivery_partner.id"))
    customer = db.relationship("Customer", back_populates="orders")
    store = db.relationship("DarkStore")
    picker = db.relationship("Picker")
    partner = db.relationship("DeliveryPartner")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), primary_key=True)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False)
    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product")


class SQLActivity(db.Model):
    """Committed business changes, with the SQL shape and bind values for teaching."""
    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)
    event_type = db.Column(db.String(40), nullable=False, index=True)
    actor = db.Column(db.String(120), nullable=False)
    order_id = db.Column(db.Integer)
    product_id = db.Column(db.Integer)
    sql_text = db.Column(db.Text, nullable=False)
    parameters_json = db.Column(db.Text, nullable=False, default="{}")
    explanation = db.Column(db.String(255), nullable=False)


def record_sql_activity(event_type, actor, sql_text, parameters, explanation, order_id=None, product_id=None):
    db.session.add(SQLActivity(
        event_type=event_type, actor=actor, sql_text=sql_text,
        parameters_json=json.dumps(parameters, default=str), explanation=explanation,
        order_id=order_id, product_id=product_id,
    ))


def current_user():
    if not session.get("role"):
        return None
    model = {"customer": Customer, "picker": Picker, "delivery": DeliveryPartner}.get(session["role"])
    if model:
        return db.session.get(model, session.get("user_id"))
    return {"name": session.get("name", "Store Manager"), "role": "manager"}


@app.context_processor
def inject_user():
    return {"current_user": current_user(), "current_role": session.get("role")}


def login_required(role=None):
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            if not session.get("role"):
                flash("Sign in to continue.", "warning")
                return redirect(url_for("login"))
            if role and session.get("role") not in ([role] if isinstance(role, str) else role):
                flash("That workspace is not available for your account.", "danger")
                return redirect(url_for("dashboard"))
            return fn(*args, **kwargs)
        return wrapped
    return decorate


def distance_km(lat1, lon1, lat2, lon2):
    dlat, dlon = radians(lat2-lat1), radians(lon2-lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    return 6371 * 2 * asin(sqrt(a))


def serving_store(lat, lon):
    candidates = [(distance_km(lat, lon, s.latitude, s.longitude), s) for s in DarkStore.query.all()]
    candidates = [(d, s) for d, s in candidates if d <= s.service_radius_km]
    return min(candidates, key=lambda pair: pair[0])[1] if candidates else None


def cart_rows(store_id):
    rows = []
    for key, qty in session.get("cart", {}).items():
        product_id = int(key)
        product = db.session.get(Product, product_id)
        inv = Inventory.query.join(BinLocation).filter(BinLocation.store_id == store_id, Inventory.product_id == product_id).first()
        if product and inv:
            rows.append({"product": product, "inventory": inv, "quantity": int(qty), "subtotal": product.price * int(qty)})
    return rows


@app.get("/")
def index():
    return redirect(url_for("dashboard") if session.get("role") else url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name, phone, email = request.form.get("name", "").strip(), request.form.get("phone", "").strip(), request.form.get("email", "").strip().lower()
        password, address = request.form.get("password", ""), request.form.get("address", "").strip()
        try:
            lat, lon = float(request.form.get("latitude", "")), float(request.form.get("longitude", ""))
        except ValueError:
            lat, lon = 999, 999
        if not all([name, phone, email, password, address]) or len(password) < 8 or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            flash("Complete every field, use a password of 8+ characters, and enter valid coordinates.", "danger")
        else:
            db.session.add(Customer(name=name, phone=phone, email=email, password_hash=generate_password_hash(password), address=address, latitude=lat, longitude=lon))
            try:
                db.session.commit()
                flash("Account created. Sign in to browse your local catalog.", "success")
                return redirect(url_for("login"))
            except IntegrityError:
                db.session.rollback()
                flash("That email or phone number is already registered.", "danger")
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role, identity, password = request.form.get("role", "customer"), request.form.get("identity", "").strip(), request.form.get("password", "")
        user = None
        if role == "customer":
            user = Customer.query.filter(func.lower(Customer.email) == identity.lower()).first()
        elif role in ("picker", "delivery"):
            model = Picker if role == "picker" else DeliveryPartner
            user = model.query.filter_by(phone=identity).first()
        elif role == "manager" and identity == os.getenv("ADMIN_USERNAME", "admin") and check_password_hash(generate_password_hash(os.getenv("ADMIN_PASSWORD", "admin123")), password):
            session.clear(); session.update(role="manager", name="Store Manager")
            return redirect(url_for("dashboard"))
        if user and check_password_hash(user.password_hash, password):
            session.clear(); session.update(role=role, user_id=user.id, name=user.name)
            return redirect(url_for("dashboard"))
        flash("The role, email/phone, or password did not match.", "danger")
    return render_template("login.html")


@app.get("/logout")
def logout():
    session.clear(); flash("You have signed out.", "success")
    return redirect(url_for("login"))


@app.get("/dashboard")
@login_required()
def dashboard():
    role = session["role"]
    if role == "customer":
        user = current_user(); store = serving_store(user.latitude, user.longitude)
        products = []
        if store:
            products = Inventory.query.join(BinLocation).join(Product).filter(BinLocation.store_id == store.id, Inventory.available_qty > 0).order_by(Product.product_name).all()
        orders = Order.query.filter_by(customer_id=user.id).order_by(Order.order_time.desc()).limit(10).all()
        return render_template("customer.html", store=store, products=products, orders=orders, cart=cart_rows(store.id) if store else [], cart_total=sum((r["subtotal"] for r in cart_rows(store.id)), start=0))
    if role == "picker":
        orders = Order.query.filter_by(picker_id=session["user_id"]).filter(Order.status.in_(["placed", "picking", "packed"])).order_by(Order.order_time).all()
        return render_template("worker.html", kind="Picker", orders=orders)
    if role == "delivery":
        orders = Order.query.filter_by(partner_id=session["user_id"]).filter(Order.status.in_(["packed", "dispatched", "out_for_delivery", "delivered"])).order_by(Order.order_time.desc()).all()
        return render_template("worker.html", kind="Delivery Partner", orders=orders)
    return redirect(url_for("manager"))


@app.post("/cart/add/<int:product_id>")
@login_required("customer")
def add_to_cart(product_id):
    user = current_user(); store = serving_store(user.latitude, user.longitude)
    product = db.session.get(Product, product_id)
    inv = Inventory.query.join(BinLocation).filter(BinLocation.store_id == (store.id if store else -1), Inventory.product_id == product_id).first()
    qty = request.form.get("quantity", type=int)
    if not store or not product or not inv or not qty or qty < 1 or qty > inv.available_qty:
        flash("Choose a valid quantity within the available stock.", "danger")
    else:
        cart = session.get("cart", {}); cart[str(product_id)] = min(int(cart.get(str(product_id), 0)) + qty, inv.available_qty); session["cart"] = cart
        flash(f"{product.product_name} added to your cart.", "success")
    return redirect(url_for("dashboard"))


@app.post("/cart/remove/<int:product_id>")
@login_required("customer")
def remove_from_cart(product_id):
    cart = session.get("cart", {}); cart.pop(str(product_id), None); session["cart"] = cart
    flash("Item removed from cart.", "success"); return redirect(url_for("dashboard"))


def checkout_impl(user):
    cart = session.get("cart", {})
    if not cart:
        flash("Your cart is empty.", "warning"); return redirect(url_for("dashboard"))
    store = serving_store(user.latitude, user.longitude)
    if not store:
        flash("Your address is outside all delivery areas.", "danger"); return redirect(url_for("dashboard"))
    try:
        # Lock inventory in a stable order to avoid deadlocks in multi-line carts.
        # Finish the read transaction opened while finding the customer's store.
        db.session.commit()
        with db.session.begin():
            locked = {}
            for product_id in sorted(map(int, cart)):
                inv = db.session.execute(select(Inventory).join(BinLocation).where(BinLocation.store_id == store.id, Inventory.product_id == product_id).with_for_update()).scalar_one_or_none()
                if not inv or inv.available_qty < int(cart[str(product_id)]):
                    raise ValueError("Stock changed while you were shopping. Refresh the catalog and adjust your cart.")
                locked[product_id] = inv
            for product_id, inv in locked.items():
                qty = int(cart[str(product_id)])
                before_available, before_reserved = inv.available_qty, inv.reserved_qty
                inv.available_qty -= qty; inv.reserved_qty += qty
                record_sql_activity(
                    "stock_reserved", f"Customer #{user.id}",
                    "UPDATE inventory SET available_qty = available_qty - :quantity, reserved_qty = reserved_qty + :quantity WHERE id = :inventory_id;",
                    {"quantity": qty, "inventory_id": inv.id, "before_available": before_available, "after_available": inv.available_qty, "before_reserved": before_reserved, "after_reserved": inv.reserved_qty},
                    "Checkout reserves stock while the inventory row is locked.", product_id=product_id,
                )
            picker = db.session.execute(select(Picker).where(Picker.store_id == store.id, Picker.status == "free").with_for_update().order_by(Picker.id)).scalars().first()
            order = Order(customer_id=user.id, store_id=store.id, status="placed", picker_id=picker.id if picker else None)
            db.session.add(order); db.session.flush()
            record_sql_activity(
                "order_created", f"Customer #{user.id}",
                "INSERT INTO orders (order_time, status, customer_id, store_id, picker_id, partner_id) VALUES (:order_time, :status, :customer_id, :store_id, :picker_id, NULL);",
                {"order_time": order.order_time.isoformat(), "status": order.status, "customer_id": user.id, "store_id": store.id, "picker_id": order.picker_id},
                "The order header is inserted in the same transaction as stock reservation.", order_id=order.id,
            )
            for product_id, inv in locked.items():
                product = db.session.get(Product, product_id)
                qty = int(cart[str(product_id)])
                db.session.add(OrderItem(order_id=order.id, product_id=product_id, quantity=qty, unit_price=product.price))
                record_sql_activity(
                    "order_item_created", f"Customer #{user.id}",
                    "INSERT INTO order_item (order_id, product_id, quantity, unit_price) VALUES (:order_id, :product_id, :quantity, :unit_price);",
                    {"order_id": order.id, "product_id": product_id, "quantity": qty, "unit_price": str(product.price)},
                    "The line item stores the price at order time.", order_id=order.id, product_id=product_id,
                )
            if picker: picker.status = "busy"
        session["cart"] = {}
        flash(f"Order #{order.id} placed. Stock reserved and {('picker assigned' if picker else 'order queued for a picker')}.", "success")
    except ValueError as exc:
        db.session.rollback(); flash(str(exc), "danger")
    except Exception:
        db.session.rollback(); app.logger.exception("Checkout failed")
        flash("We could not place that order. Please retry.", "danger")
    return redirect(url_for("dashboard"))


@app.post("/checkout")
@login_required("customer")
def checkout():
    if db.engine.dialect.name == "sqlite":
        with sqlite_checkout_lock:
            return checkout_impl(current_user())
    return checkout_impl(current_user())


@app.post("/orders/<int:order_id>/status")
@login_required(["picker", "delivery"])
def update_order_status(order_id):
    order = db.session.get(Order, order_id); role = session["role"]; status = request.form.get("status", "")
    if not order or (role == "picker" and order.picker_id != session["user_id"]) or (role == "delivery" and order.partner_id != session["user_id"]):
        flash("Order not found in your assigned queue.", "danger"); return redirect(url_for("dashboard"))
    allowed = {"picker": {"picking": "picking", "packed": "packed"}, "delivery": {"out_for_delivery": "out_for_delivery", "delivered": "delivered"}}[role]
    if status not in allowed or (role == "picker" and status == "packed" and order.status != "picking") or (role == "delivery" and status == "delivered" and order.status != "out_for_delivery"):
        flash("Complete the previous step before advancing this order.", "warning")
    else:
        previous_status = order.status
        order.status = status
        if status == "delivered":
            if order.partner: order.partner.status = "free"
            for item in order.items:
                inv = Inventory.query.join(BinLocation).filter(BinLocation.store_id == order.store_id, Inventory.product_id == item.product_id).first()
                if inv:
                    before_reserved = inv.reserved_qty
                    inv.reserved_qty = max(0, inv.reserved_qty - item.quantity)
                    record_sql_activity(
                        "reservation_released", f"Delivery partner #{session['user_id']}",
                        "UPDATE inventory SET reserved_qty = reserved_qty - :quantity WHERE id = :inventory_id;",
                        {"quantity": item.quantity, "inventory_id": inv.id, "before_reserved": before_reserved, "after_reserved": inv.reserved_qty},
                        "Delivery completion releases the reserved quantity.", order_id=order.id, product_id=item.product_id,
                    )
        if status == "packed":
            partner = DeliveryPartner.query.filter_by(store_id=order.store_id, status="free").order_by(DeliveryPartner.id).first()
            if partner: partner.status = "busy"; order.partner_id = partner.id
            else: flash("Order packed. No delivery partner is free yet.", "warning")
        if status == "packed" and order.picker: order.picker.status = "free"
        record_sql_activity(
            "order_status_changed", f"{role.title()} #{session['user_id']}",
            "UPDATE orders SET status = :new_status WHERE order_id = :order_id;",
            {"previous_status": previous_status, "new_status": status, "order_id": order.id},
            "The order lifecycle advances through a role-authorized transition.", order_id=order.id,
        )
        db.session.commit(); flash(f"Order #{order.id} updated to {status.replace('_', ' ')}.", "success")
    return redirect(url_for("dashboard"))


@app.get("/orders/<int:order_id>/pick-list")
@login_required(["picker", "manager"])
def pick_list(order_id):
    order = db.session.get(Order, order_id)
    if not order or (session["role"] == "picker" and order.picker_id != session["user_id"]):
        flash("Order not found in your queue.", "danger"); return redirect(url_for("dashboard"))
    items = []
    for item in order.items:
        inv = Inventory.query.join(BinLocation).filter(BinLocation.store_id == order.store_id, Inventory.product_id == item.product_id).first()
        if inv: items.append((inv.bin.aisle_no, inv.bin.rack_no, inv.bin.shelf_no, item, inv))
    return render_template("pick_list.html", order=order, items=sorted(items, key=lambda x: (x[0], x[1], x[2])))


@app.get("/manager")
@login_required("manager")
def manager():
    stores = DarkStore.query.order_by(DarkStore.store_name).all(); categories = Category.query.order_by(Category.category_name).all(); products = Product.query.order_by(Product.product_name).all()
    inventory = Inventory.query.join(BinLocation).join(Product).order_by(Product.product_name).all()
    low_stock = Inventory.query.join(BinLocation).join(Product).filter(Inventory.available_qty <= Product.low_stock_threshold).order_by(Inventory.available_qty).all()
    today = date.today(); daily = db.session.query(func.date(Order.order_time), func.count(Order.id)).filter(Order.order_time >= datetime.combine(today.replace(day=1), datetime.min.time())).group_by(func.date(Order.order_time)).order_by(func.date(Order.order_time).desc()).all()
    recent_orders = Order.query.order_by(Order.order_time.desc()).limit(15).all()
    active_orders = Order.query.filter(Order.status != "delivered").count()
    return render_template("manager.html", stores=stores, categories=categories, products=products, inventory=inventory, low_stock=low_stock, daily=daily, recent_orders=recent_orders, active_orders=active_orders, pickers=Picker.query.all(), partners=DeliveryPartner.query.all())


@app.get("/database")
@login_required("manager")
def database_lab():
    tables = [
        ("customer", Customer.query.count()), ("dark_store", DarkStore.query.count()),
        ("category", Category.query.count()), ("product", Product.query.count()),
        ("bin_location", BinLocation.query.count()), ("inventory", Inventory.query.count()),
        ("picker", Picker.query.count()), ("delivery_partner", DeliveryPartner.query.count()),
        ("orders", Order.query.count()), ("order_item", OrderItem.query.count()),
        ("sql_activity", SQLActivity.query.count()),
    ]
    activity = SQLActivity.query.order_by(SQLActivity.created_at.desc(), SQLActivity.id.desc()).limit(30).all()
    return render_template("database.html", tables=tables, activity=activity, dialect=db.engine.dialect.name)


@app.get("/database/schema.sql")
@login_required("manager")
def download_schema():
    return send_file(os.path.join(app.root_path, "sql", "schema.sql"), as_attachment=True)


@app.get("/database/course-queries.sql")
@login_required("manager")
def download_course_queries():
    return send_file(os.path.join(app.root_path, "sql", "course_queries.sql"), as_attachment=True)


@app.get("/database/activity")
@login_required("manager")
def database_activity():
    after_id = request.args.get("after", type=int) or 0
    rows = SQLActivity.query.filter(SQLActivity.id > after_id).order_by(SQLActivity.id).limit(100).all()
    return {"activity": [{
        "id": row.id, "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "event_type": row.event_type, "actor": row.actor, "order_id": row.order_id,
        "product_id": row.product_id, "sql_text": row.sql_text,
        "parameters_json": row.parameters_json, "explanation": row.explanation,
    } for row in rows], "counts": {
        "customer": Customer.query.count(), "dark_store": DarkStore.query.count(),
        "category": Category.query.count(), "product": Product.query.count(),
        "bin_location": BinLocation.query.count(), "inventory": Inventory.query.count(),
        "picker": Picker.query.count(), "delivery_partner": DeliveryPartner.query.count(),
        "orders": Order.query.count(), "order_item": OrderItem.query.count(),
        "sql_activity": SQLActivity.query.count(),
    }}


@app.post("/manager/category")
@login_required("manager")
def add_category():
    name = request.form.get("category_name", "").strip()
    if not name: flash("Category name is required.", "danger")
    else:
        db.session.add(Category(category_name=name))
        try: db.session.commit(); flash("Category added.", "success")
        except IntegrityError: db.session.rollback(); flash("That category already exists.", "warning")
    return redirect(url_for("manager"))


@app.post("/manager/store")
@login_required("manager")
def add_store():
    try:
        name, address = request.form["store_name"].strip(), request.form["address"].strip(); lat=float(request.form["latitude"]); lon=float(request.form["longitude"]); radius=float(request.form["service_radius_km"])
        if not name or not address or not (-90 <= lat <= 90 and -180 <= lon <= 180 and radius > 0): raise ValueError()
        db.session.add(DarkStore(store_name=name,address=address,latitude=lat,longitude=lon,service_radius_km=radius)); db.session.commit(); flash("Dark store added.", "success")
    except (ValueError, KeyError): db.session.rollback(); flash("Enter a name, address, valid coordinates, and positive radius.", "danger")
    return redirect(url_for("manager"))


@app.post("/manager/product")
@login_required("manager")
def add_product():
    try:
        product=Product(product_name=request.form["product_name"].strip(),price=float(request.form["price"]),category_id=int(request.form["category_id"]),low_stock_threshold=int(request.form["low_stock_threshold"] or 5))
        if not product.product_name or product.price < 0 or product.low_stock_threshold < 0: raise ValueError()
        db.session.add(product); db.session.commit(); flash("Product added. Add its bin and starting stock below.", "success")
    except (ValueError, KeyError): db.session.rollback(); flash("Enter a product name, valid category, non-negative price and threshold.", "danger")
    return redirect(url_for("manager"))


@app.post("/manager/inventory")
@login_required("manager")
def update_inventory():
    try:
        store_id=int(request.form["store_id"]); product_id=int(request.form["product_id"]); qty=int(request.form["available_qty"])
        if qty < 0: raise ValueError()
        binloc=BinLocation.query.filter_by(store_id=store_id,aisle_no=request.form["aisle_no"].strip(),rack_no=request.form["rack_no"].strip(),shelf_no=request.form["shelf_no"].strip()).first()
        if not binloc:
            binloc=BinLocation(store_id=store_id,aisle_no=request.form["aisle_no"].strip(),rack_no=request.form["rack_no"].strip(),shelf_no=request.form["shelf_no"].strip()); db.session.add(binloc); db.session.flush()
        inv=Inventory.query.filter_by(bin_id=binloc.id,product_id=product_id).first()
        if inv:
            before = inv.available_qty
            inv.available_qty += qty
            statement = "UPDATE inventory SET available_qty = available_qty + :quantity WHERE id = :inventory_id;"
            parameters = {"quantity": qty, "inventory_id": inv.id, "before_available": before, "after_available": inv.available_qty}
        else:
            inv = Inventory(bin_id=binloc.id,product_id=product_id,available_qty=qty,reserved_qty=0)
            db.session.add(inv); db.session.flush()
            statement = "INSERT INTO inventory (available_qty, reserved_qty, bin_id, product_id) VALUES (:available_qty, 0, :bin_id, :product_id);"
            parameters = {"available_qty": qty, "bin_id": binloc.id, "product_id": product_id, "inventory_id": inv.id}
        record_sql_activity("stock_received", "Store manager", statement, parameters,
                            "Stock receipt is written against the selected store bin.", product_id=product_id)
        db.session.commit(); flash("Stock received and bin location saved.", "success")
    except (ValueError, KeyError): db.session.rollback(); flash("Choose a store and product, enter a non-negative quantity, and complete all bin fields.", "danger")
    return redirect(url_for("manager"))


@app.post("/manager/assign")
@login_required("manager")
def assign_worker():
    try:
        order=db.session.get(Order,int(request.form["order_id"])); role=request.form["role"]; worker_id=int(request.form["worker_id"])
        if not order: raise ValueError()
        if role == "picker":
            worker=Picker.query.filter_by(id=worker_id,store_id=order.store_id,status="free").first()
            if not worker: raise ValueError()
            if order.picker and order.picker.id != worker.id: order.picker.status="free"
            order.picker=worker; worker.status="busy"
        elif role == "delivery":
            worker=DeliveryPartner.query.filter_by(id=worker_id,store_id=order.store_id,status="free").first()
            if not worker or order.status != "packed": raise ValueError()
            order.partner=worker; worker.status="busy"
        else: raise ValueError()
        record_sql_activity("worker_assigned", "Store manager",
                            f"UPDATE orders SET {'picker_id' if role == 'picker' else 'partner_id'} = :worker_id WHERE id = :order_id;",
                            {"worker_id": worker.id, "order_id": order.id, "role": role},
                            "A free worker at this store was assigned to the order.", order_id=order.id)
        db.session.commit(); flash(f"{role.title()} assigned to order #{order.id}.", "success")
    except (ValueError, KeyError): db.session.rollback(); flash("Select an available worker at the same store and a compatible order.", "danger")
    return redirect(url_for("manager"))


def seed_demo():
    """Create repeatable demo data on a fresh database."""
    if DarkStore.query.first(): return
    store=DarkStore(store_name="Indiranagar Dark Store",address="100 Feet Road, Bengaluru",latitude=12.9784,longitude=77.6408,service_radius_km=8); db.session.add(store)
    categories=[Category(category_name=n) for n in ("Fresh Produce","Dairy & Eggs","Pantry")]; db.session.add_all(categories); db.session.flush()
    products=[Product(product_name=n,price=p,category_id=categories[c].id,low_stock_threshold=5) for n,p,c in [("Bananas (6 pcs)",42,0),("Farm Fresh Milk 1L",68,1),("Brown Bread",45,2),("Tomatoes 500g",38,0),("Free-range Eggs (6)",72,1),("Basmati Rice 1kg",110,2)]]; db.session.add_all(products); db.session.flush()
    for i,p in enumerate(products):
        b=BinLocation(aisle_no=f"{1+i//2:02}",rack_no=f"{1+i%3:02}",shelf_no=f"{1+i%2:02}",store_id=store.id); db.session.add(b); db.session.flush(); db.session.add(Inventory(available_qty=[22,18,14,4,10,2][i],reserved_qty=0,bin_id=b.id,product_id=p.id))
    demo_hash=generate_password_hash("demo12345")
    db.session.add_all([Picker(name="Aarav Kumar",phone="9000000011",password_hash=demo_hash,status="free",store_id=store.id),Picker(name="Maya Shah",phone="9000000012",password_hash=demo_hash,status="free",store_id=store.id),DeliveryPartner(name="Ravi Nair",phone="9000000021",password_hash=demo_hash,status="free",store_id=store.id),DeliveryPartner(name="Isha Rao",phone="9000000022",password_hash=demo_hash,status="free",store_id=store.id)])
    customer=Customer(name="Demo Customer",phone="9000000001",email="customer@demo.local",password_hash=generate_password_hash("demo12345"),address="12 100 Feet Road, Bengaluru",latitude=12.9788,longitude=77.6412); db.session.add(customer); db.session.commit()


with app.app_context():
    db.create_all()
    seed_demo()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")
