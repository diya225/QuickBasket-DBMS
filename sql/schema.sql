-- QuickBasket normalized schema for MySQL 8 / InnoDB.
-- Run this script in MySQL Workbench before starting the Flask application.
CREATE DATABASE IF NOT EXISTS darkstore
  CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE darkstore;

CREATE TABLE IF NOT EXISTS customer (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  phone VARCHAR(30) NOT NULL UNIQUE,
  email VARCHAR(120) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  address VARCHAR(255) NOT NULL,
  latitude DOUBLE NOT NULL,
  longitude DOUBLE NOT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS dark_store (
  id INT AUTO_INCREMENT PRIMARY KEY,
  store_name VARCHAR(100) NOT NULL,
  address VARCHAR(255) NOT NULL,
  latitude DOUBLE NOT NULL,
  longitude DOUBLE NOT NULL,
  service_radius_km DOUBLE NOT NULL DEFAULT 8
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS category (
  id INT AUTO_INCREMENT PRIMARY KEY,
  category_name VARCHAR(80) NOT NULL UNIQUE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS product (
  id INT AUTO_INCREMENT PRIMARY KEY,
  product_name VARCHAR(120) NOT NULL,
  price DECIMAL(10,2) NOT NULL,
  category_id INT NOT NULL,
  low_stock_threshold INT NOT NULL DEFAULT 5,
  CONSTRAINT fk_product_category FOREIGN KEY (category_id) REFERENCES category(id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS bin_location (
  id INT AUTO_INCREMENT PRIMARY KEY,
  aisle_no VARCHAR(20) NOT NULL,
  rack_no VARCHAR(20) NOT NULL,
  shelf_no VARCHAR(20) NOT NULL,
  store_id INT NOT NULL,
  CONSTRAINT fk_bin_store FOREIGN KEY (store_id) REFERENCES dark_store(id),
  INDEX ix_bin_store (store_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS inventory (
  id INT AUTO_INCREMENT PRIMARY KEY,
  available_qty INT NOT NULL DEFAULT 0,
  reserved_qty INT NOT NULL DEFAULT 0,
  bin_id INT NOT NULL,
  product_id INT NOT NULL,
  CONSTRAINT uq_inventory_bin_product UNIQUE (bin_id, product_id),
  CONSTRAINT ck_inventory_available_nonnegative CHECK (available_qty >= 0),
  CONSTRAINT ck_inventory_reserved_nonnegative CHECK (reserved_qty >= 0),
  CONSTRAINT fk_inventory_bin FOREIGN KEY (bin_id) REFERENCES bin_location(id),
  CONSTRAINT fk_inventory_product FOREIGN KEY (product_id) REFERENCES product(id),
  INDEX ix_inventory_product (product_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS picker (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  phone VARCHAR(30) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'free',
  store_id INT NOT NULL,
  CONSTRAINT fk_picker_store FOREIGN KEY (store_id) REFERENCES dark_store(id),
  INDEX ix_picker_available (store_id, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS delivery_partner (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  phone VARCHAR(30) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status VARCHAR(20) NOT NULL DEFAULT 'free',
  store_id INT NOT NULL,
  CONSTRAINT fk_partner_store FOREIGN KEY (store_id) REFERENCES dark_store(id),
  INDEX ix_partner_available (store_id, status)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS orders (
  id INT AUTO_INCREMENT PRIMARY KEY,
  order_time DATETIME NOT NULL,
  status VARCHAR(24) NOT NULL DEFAULT 'placed',
  customer_id INT NOT NULL,
  store_id INT NOT NULL,
  picker_id INT NULL,
  partner_id INT NULL,
  CONSTRAINT fk_order_customer FOREIGN KEY (customer_id) REFERENCES customer(id),
  CONSTRAINT fk_order_store FOREIGN KEY (store_id) REFERENCES dark_store(id),
  CONSTRAINT fk_order_picker FOREIGN KEY (picker_id) REFERENCES picker(id),
  CONSTRAINT fk_order_partner FOREIGN KEY (partner_id) REFERENCES delivery_partner(id),
  INDEX ix_orders_status_time (status, order_time),
  INDEX ix_orders_customer_time (customer_id, order_time)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS order_item (
  order_id INT NOT NULL,
  product_id INT NOT NULL,
  quantity INT NOT NULL,
  unit_price DECIMAL(10,2) NOT NULL,
  PRIMARY KEY (order_id, product_id),
  CONSTRAINT ck_order_item_quantity CHECK (quantity > 0),
  CONSTRAINT fk_item_order FOREIGN KEY (order_id) REFERENCES orders(id),
  CONSTRAINT fk_item_product FOREIGN KEY (product_id) REFERENCES product(id)
) ENGINE=InnoDB;

-- Teaching journal: committed business changes, SQL patterns, and bind values.
CREATE TABLE IF NOT EXISTS sql_activity (
  id INT AUTO_INCREMENT PRIMARY KEY,
  created_at DATETIME NOT NULL,
  event_type VARCHAR(40) NOT NULL,
  actor VARCHAR(120) NOT NULL,
  order_id INT NULL,
  product_id INT NULL,
  sql_text TEXT NOT NULL,
  parameters_json TEXT NOT NULL,
  explanation VARCHAR(255) NOT NULL,
  INDEX ix_activity_created (created_at),
  INDEX ix_activity_event (event_type)
) ENGINE=InnoDB;
