import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sku             TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    category        TEXT    NOT NULL,
    price_cents     INTEGER NOT NULL,
    weight_grams    INTEGER NOT NULL,
    lead_time_days  INTEGER NOT NULL,
    created_at      REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS stock_movements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    delta       INTEGER NOT NULL,
    reason      TEXT    NOT NULL CHECK (reason IN ('receipt', 'sale', 'adjustment')),
    order_id    INTEGER REFERENCES orders(id),
    created_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_email      TEXT    NOT NULL,
    postcode            TEXT    NOT NULL,
    subtotal_cents      INTEGER NOT NULL,
    shipping_cents      INTEGER NOT NULL,
    carrier_service     TEXT    NOT NULL,
    created_at          REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS order_items (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id            INTEGER NOT NULL REFERENCES orders(id),
    product_id          INTEGER NOT NULL REFERENCES products(id),
    quantity            INTEGER NOT NULL CHECK (quantity > 0),
    unit_price_cents    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_movements_product_created ON stock_movements(product_id, created_at);
CREATE INDEX IF NOT EXISTS idx_movements_reason_created ON stock_movements(reason, created_at);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items(order_id);
"""


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str) -> None:
    conn = connect(db_path)
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
