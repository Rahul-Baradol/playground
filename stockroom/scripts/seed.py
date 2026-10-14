"""Fill a Stockroom database with realistic-looking fake data.

    python -m scripts.seed --products 1600 --orders 16000
"""

import argparse
import random
import time
from dataclasses import dataclass

from app.db import connect, init_db

CATEGORIES = ["audio", "cables", "cameras", "chargers", "gaming", "home", "kitchen",
              "lighting", "networking", "office", "outdoor", "storage", "tools", "wearables"]
ADJECTIVES = ["Compact", "Pro", "Ultra", "Classic", "Smart", "Mini", "Rugged", "Slim",
              "Wireless", "Heavy-Duty", "Travel", "Eco"]
NOUNS = {
    "audio": "Speaker", "cables": "Cable", "cameras": "Camera", "chargers": "Charger",
    "gaming": "Controller", "home": "Organizer", "kitchen": "Kettle", "lighting": "Lamp",
    "networking": "Router", "office": "Desk Mat", "outdoor": "Lantern", "storage": "Drive",
    "tools": "Drill", "wearables": "Band",
}
POSTCODES = ["10115", "20095", "30159", "40213", "50667", "60311", "70173", "80331", "90402"]
DAY = 86_400


@dataclass(frozen=True)
class SeedResult:
    skus: list[str]
    order_ids: list[int]


def seed(
    db_path: str,
    n_products: int,
    n_orders: int,
    days: int = 60,
    rng_seed: int = 42,
    now: float | None = None,
) -> SeedResult:
    """Insert products, their stock history and past orders."""
    rng = random.Random(rng_seed)
    now = now if now is not None else time.time()
    start = now - days * DAY
    init_db(db_path)
    conn = connect(db_path)

    product_rows = []
    for i in range(n_products):
        category = CATEGORIES[i % len(CATEGORIES)]
        product_rows.append((
            f"{category[:3].upper()}-{i:05d}",
            f"{rng.choice(ADJECTIVES)} {NOUNS[category]} {i}",
            category,
            rng.choice([499, 999, 1499, 1999, 2999, 4999, 7999, 12999, 24999, 39999]),
            rng.randint(80, 4_000),
            rng.choice([3, 5, 7, 10, 14, 21, 30]),
            start - DAY,
        ))
    conn.executemany(
        """
        INSERT INTO products (sku, name, category, price_cents, weight_grams,
                              lead_time_days, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        product_rows,
    )
    rows = conn.execute("SELECT id, sku, price_cents FROM products ORDER BY id").fetchall()
    ids = [r["id"] for r in rows]
    price = {r["id"]: r["price_cents"] for r in rows}

    stock = {pid: rng.randint(20, 300) for pid in ids}
    movements = [(pid, qty, "receipt", None, start - DAY) for pid, qty in stock.items()]

    # A few products sell far more than the rest.
    weights = [1 / (rank + 1) ** 0.9 for rank in range(len(ids))]
    rng.shuffle(weights)

    timestamps = sorted(start + rng.random() * days * DAY for _ in range(n_orders))
    next_order_id = (conn.execute("SELECT COALESCE(MAX(id), 0) FROM orders").fetchone()[0]) + 1
    order_rows, item_rows, order_ids = [], [], []
    for ts in timestamps:
        order_id = next_order_id
        next_order_id += 1
        picked = set(rng.choices(ids, weights=weights, k=rng.randint(1, 4)))
        subtotal = 0
        for pid in picked:
            qty = rng.randint(1, 3)
            if stock[pid] < qty:
                restock = rng.randint(50, 250)
                stock[pid] += restock
                movements.append((pid, restock, "receipt", None, ts - 3_600))
            stock[pid] -= qty
            subtotal += qty * price[pid]
            item_rows.append((order_id, pid, qty, price[pid]))
            movements.append((pid, -qty, "sale", order_id, ts))
        postcode = rng.choice(POSTCODES)
        order_rows.append((order_id, f"customer{rng.randint(1, 5_000)}@example.com",
                           postcode, subtotal, 499, "standard", ts))
        order_ids.append(order_id)

    conn.executemany(
        """
        INSERT INTO orders (id, customer_email, postcode, subtotal_cents, shipping_cents,
                            carrier_service, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        order_rows,
    )
    conn.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price_cents) "
        "VALUES (?, ?, ?, ?)",
        item_rows,
    )
    conn.executemany(
        "INSERT INTO stock_movements (product_id, delta, reason, order_id, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        movements,
    )
    conn.commit()
    conn.close()
    return SeedResult(skus=[r["sku"] for r in rows], order_ids=order_ids)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="stockroom.db")
    parser.add_argument("--products", type=int, default=1_600)
    parser.add_argument("--orders", type=int, default=16_000)
    args = parser.parse_args()

    started = time.perf_counter()
    seed(args.db, args.products, args.orders)
    print(f"Seeded {args.products:,} products and {args.orders:,} orders into {args.db} "
          f"in {time.perf_counter() - started:.1f}s")


if __name__ == "__main__":
    main()
