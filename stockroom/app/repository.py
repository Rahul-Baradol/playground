from typing import Any
import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class Product:
    id: int
    sku: str
    name: str
    category: str
    price_cents: int
    weight_grams: int
    lead_time_days: int
    created_at: float


@dataclass(frozen=True)
class StockMovement:
    id: int
    product_id: int
    delta: int
    reason: str
    order_id: int | None
    created_at: float


@dataclass(frozen=True)
class OrderLine:
    product_id: int
    sku: str
    quantity: int
    unit_price_cents: int


@dataclass(frozen=True)
class Order:
    id: int
    customer_email: str
    postcode: str
    subtotal_cents: int
    shipping_cents: int
    carrier_service: str
    created_at: float
    lines: list[OrderLine]


_PRODUCT_COLUMNS = "id, sku, name, category, price_cents, weight_grams, lead_time_days, created_at"


def _row_to_product(row: sqlite3.Row) -> Product:
    return Product(**{key: row[key] for key in row.keys()})


class ProductRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        sku: str,
        name: str,
        category: str,
        price_cents: int,
        weight_grams: int,
        lead_time_days: int,
        created_at: float,
    ) -> Product:
        cur = self.conn.execute(
            """
            INSERT INTO products (sku, name, category, price_cents, weight_grams,
                                  lead_time_days, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (sku, name, category, price_cents, weight_grams, lead_time_days, created_at),
        )
        self.conn.commit()
        return Product(
            cur.lastrowid, sku, name, category, price_cents, weight_grams,
            lead_time_days, created_at,
        )

    def sku_exists(self, sku: str) -> bool:
        return self.conn.execute("SELECT 1 FROM products WHERE sku = ?", (sku,)).fetchone() is not None

    def get_by_sku(self, sku: str) -> Product | None:
        row = self.conn.execute(
            f"SELECT {_PRODUCT_COLUMNS} FROM products WHERE sku = ?", (sku,)
        ).fetchone()
        return _row_to_product(row) if row else None

    def get_many_by_sku(self, skus: list[str]) -> dict[str, Product]:
        if not skus:
            return {}
        placeholders = ",".join("?" * len(skus))
        rows = self.conn.execute(
            f"SELECT {_PRODUCT_COLUMNS} FROM products WHERE sku IN ({placeholders})", skus
        ).fetchall()
        return {r["sku"]: _row_to_product(r) for r in rows}

    def list_page(self, category: str | None, limit: int, offset: int) -> list[Product]:
        if category is None:
            rows = self.conn.execute(
                f"SELECT {_PRODUCT_COLUMNS} FROM products ORDER BY id LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        else:
            rows = self.conn.execute(
                f"""
                SELECT {_PRODUCT_COLUMNS} FROM products
                WHERE category = ?
                ORDER BY id LIMIT ? OFFSET ?
                """,
                (category, limit, offset),
            ).fetchall()
        return [_row_to_product(r) for r in rows]

    def list_all(self) -> list[Product]:
        rows = self.conn.execute(f"SELECT {_PRODUCT_COLUMNS} FROM products ORDER BY id").fetchall()
        return [_row_to_product(r) for r in rows]


class StockRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(
        self,
        product_id: int,
        delta: int,
        reason: str,
        created_at: float,
        order_id: int | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO stock_movements (product_id, delta, reason, order_id, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (product_id, delta, reason, order_id, created_at),
        )
        self.conn.commit()

    def on_hand(self, product_id: int) -> int:
        row = self.conn.execute(
            "SELECT COALESCE(SUM(delta), 0) AS n FROM stock_movements WHERE product_id = ?",
            (product_id,),
        ).fetchone()
        return row["n"]

    def on_hand_for(self, product_ids: list[int]) -> dict[int, int]:
        if not product_ids:
            return {}
        placeholders = ",".join("?" * len(product_ids))
        rows = self.conn.execute(
            f"""
            SELECT product_id, SUM(delta) AS n
            FROM stock_movements
            WHERE product_id IN ({placeholders})
            GROUP BY product_id
            """,
            product_ids,
        ).fetchall()
        levels = {r["product_id"]: r["n"] for r in rows}
        return {pid: levels.get(pid, 0) for pid in product_ids}

    def on_hand_all(self) -> dict[int, int]:
        rows = self.conn.execute(
            "SELECT product_id, SUM(delta) AS n FROM stock_movements GROUP BY product_id"
        ).fetchall()
        return {r["product_id"]: r["n"] for r in rows}

    def sales_since(self, since: float) -> list[StockMovement]:
        rows = self.conn.execute(
            """
            SELECT id, product_id, delta, reason, order_id, created_at
            FROM stock_movements
            WHERE reason = 'sale' AND created_at >= ?
            """,
            (since,),
        ).fetchall()
        return [StockMovement(**{key: r[key] for key in r.keys()}) for r in rows]

    def units_sold_per_product(self, since) -> list[dict[str, int]]:
        rows = self.conn.execute(
            """
            SELECT  sm.product_id as id, 
                    SUM(sm.delta) as units_sold, 
                    MAX(sm.created_at) as last_sold_at, 
                    p.lead_time_days as lead_time_days, 
                    p.sku as sku, 
                    p.name as name
            FROM    stock_movements as sm
            LEFT JOIN products as p ON sm.product_id = p.id
            WHERE   sm.reason = 'sale' 
                    AND sm.created_at >= ?
            GROUP BY sm.product_id
            """,
            (since,),
        ).fetchall()
        return [
            {
                "id": row["id"],
                "units_sold": row["units_sold"],
                "last_sold_at": row["last_sold_at"],
                "lead_time_days": row["lead_time_days"],
                "sku": row["sku"],
                "name": row["name"]
            } for row in rows
        ]


class OrderRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(
        self,
        customer_email: str,
        postcode: str,
        lines: list[OrderLine],
        shipping_cents: int,
        carrier_service: str,
        created_at: float,
    ) -> Order:
        subtotal = sum(line.quantity * line.unit_price_cents for line in lines)
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT INTO orders (customer_email, postcode, subtotal_cents, shipping_cents,
                                    carrier_service, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (customer_email, postcode, subtotal, shipping_cents, carrier_service, created_at),
            )
            order_id = cur.lastrowid
            self.conn.executemany(
                """
                INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents)
                VALUES (?, ?, ?, ?)
                """,
                [(order_id, l.product_id, l.quantity, l.unit_price_cents) for l in lines],
            )
            self.conn.executemany(
                """
                INSERT INTO stock_movements (product_id, delta, reason, order_id, created_at)
                VALUES (?, ?, 'sale', ?, ?)
                """,
                [(l.product_id, -l.quantity, order_id, created_at) for l in lines],
            )
        return Order(
            order_id, customer_email, postcode, subtotal, shipping_cents,
            carrier_service, created_at, lines,
        )

    def get(self, order_id: int) -> Order | None:
        row = self.conn.execute(
            """
            SELECT id, customer_email, postcode, subtotal_cents, shipping_cents,
                   carrier_service, created_at
            FROM orders WHERE id = ?
            """,
            (order_id,),
        ).fetchone()
        if row is None:
            return None
        items = self.conn.execute(
            """
            SELECT oi.product_id, p.sku, oi.quantity, oi.unit_price_cents
            FROM order_items oi JOIN products p ON p.id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY oi.id
            """,
            (order_id,),
        ).fetchall()
        lines = [OrderLine(i["product_id"], i["sku"], i["quantity"], i["unit_price_cents"]) for i in items]
        return Order(**{key: row[key] for key in row.keys()}, lines=lines)
