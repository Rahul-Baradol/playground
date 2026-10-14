# Stockroom

Inventory and order management API for a small online electronics shop. It
keeps the product catalog, tracks stock as a ledger of movements (receipts,
sales, manual adjustments), takes orders with a live shipping quote from the
carrier, and tells the ops team what to reorder before it runs out.

Built with FastAPI and SQLite. Runs fully offline: the shipping carrier is a
mock client that simulates network latency.

## Endpoints

| Method & path | What it does |
|---|---|
| `POST /api/products` | Create a product, optionally with initial stock |
| `GET /api/products?category=&limit=&offset=` | List products with stock on hand |
| `GET /api/products/{sku}` | One product with stock on hand |
| `POST /api/products/{sku}/movements` | Record a stock receipt or manual adjustment |
| `GET /api/catalog/facets` | Category and price-range counts for the storefront sidebar |
| `POST /api/orders` | Check out: validate stock, quote shipping, record the sale |
| `GET /api/orders/{id}` | One order with its lines |
| `GET /api/reports/reorder` | Products that will run out before a new delivery could arrive |
| `GET /healthz` | Liveness check |

Stock on hand is never stored. It's the sum of a product's movements.

A product appears in the reorder report when its stock covers fewer days of
sales (over the last 30 days) than its supplier lead time plus 7 safety days.

## Setup

```bash
cd stockroom
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m scripts.seed --products 1600 --orders 16000   # optional sample data
uvicorn app.main:create_app --factory --reload
```

Open http://localhost:8000/docs for the interactive API docs.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `STOCKROOM_DB_PATH` | `stockroom.db` | SQLite file |
| `STOCKROOM_CARRIER_LATENCY_MS` | `120` | Simulated carrier API round-trip |

## Test

```bash
pytest -q
```

Tests use a temporary database, a fake clock and a zero-latency carrier.

## Benchmark

```bash
python -m scripts.benchmark                     # full run, a few minutes
python -m scripts.benchmark --quick             # smaller data
python -m scripts.benchmark --save before.json  # keep a baseline
python -m scripts.benchmark --compare before.json
```

Each scenario runs at a SMALL and a LARGE scale and prints median times plus
a `growth` column (large ÷ small).

## Layout

```
app/
  main.py            app factory: settings, carrier client, clock, routers
  config.py          settings from environment variables
  db.py              schema and connection helpers
  carrier.py         shipping-rate client (mock)
  models.py          request and response models
  repository.py      SQL for products, stock movements and orders
  dependencies.py    FastAPI dependency wiring
  routes/            HTTP layer: products, orders, reports
  services/          business logic: catalog, orders, reorder report
scripts/
  seed.py            fake data with a fixed RNG seed
  benchmark.py       scaling benchmark
tests/               pytest suite
```

## The challenge

Stockroom works, and every test passes. It also gets slower in ways that
matter as the shop grows. Start with [CHALLENGE.md](CHALLENGE.md).
