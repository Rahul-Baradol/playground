# ⚠️ SPOILERS: Stockroom solutions

Stop here if you haven't finished [CHALLENGE.md](CHALLENGE.md).

.

.

.

.

.

.

.

.

.

.

---

## Reference results

Measured on an Apple Silicon laptop, full benchmark. LARGE has 1,600 products,
16,000 orders and 32 checkouts arriving within 100 ms. SMALL has 400 products,
2,000 orders and 4 checkouts.

| scenario | before (large) | before growth | after (large) | after growth | speedup |
|---|---:|---:|---:|---:|---:|
| `POST /api/orders` burst (batch) | 1,915 ms | 7.5× | 157 ms | 1.1× | ~12× |
| `GET /api/catalog/facets` | 13.6 ms | 4.5× | 0.98 ms | 1.1× | ~14× |
| `GET /api/reports/reorder` (dict fix) | 597 ms | 20.5× | 57 ms | 7.9× | ~10× |
| `GET /api/reports/reorder` (SQL fix) | 597 ms | 20.5× | 18.6 ms | 5.3× | ~32× |
| `GET /api/products/{sku}` (control) | 0.96 ms | 0.9× | 0.96 ms | 0.9× | — |
| `GET /api/orders/{id}` (control) | 0.87 ms | 0.9× | 0.90 ms | 1.0× | — |

The reorder report still grows after the fix, and that's correct. It has to
read every sale in the window, and LARGE has 8× the sales. Growth in line with
the data is the floor for a report like this. The bug was growth far *beyond*
it.

---

## Bug 1: blocking I/O on the event loop (STK-201)

**Where:** [app/routes/orders.py](app/routes/orders.py), `create_order`

```python
@router.post("", ...)
async def create_order(...):
    order = orders.place_order(...)   # -> MockCarrierClient.quote() -> time.sleep()
```

**Root cause:** FastAPI runs `async def` handlers directly on the event loop.
Everything inside `place_order` is synchronous: the SQLite queries and, more
importantly, the carrier call, which waits ~120 ms on the network (simulated
with `time.sleep`). While one checkout waits, the event loop can't do anything
else. No other request makes progress, not even `/healthz`. Checkouts don't
overlap their carrier waits. They queue up behind each other: 32 checkouts × 50
ms ≈ 1.6 s, and every other endpoint stalls behind them. CPU stays low because
the process is just sleeping. That's why the incident looked so strange.

The tests never caught it because tests send one request at a time and use a
zero-latency carrier.

**Fix:** let FastAPI run the handler in its threadpool by declaring it as a
plain `def`.

```python
@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    ...
```

The other ways to fix it:

- Keep `async def` and offload only the blocking work:
  `order = await run_in_threadpool(orders.place_order, ...)`
  (from `starlette.concurrency`).
- Use a real async HTTP client (`httpx.AsyncClient`) for the carrier. In this
  codebase that would mean making `OrderService` async all the way down, while
  the SQLite calls stay blocking. That's a lot of change for no gain over the
  threadpool.

The rule: inside `async def`, every I/O call must be awaited. If the libraries
underneath are synchronous (`sqlite3`, `requests`, most SDKs), use `def` and let
the framework handle threads.

**This compounds with Bug 2.** The other handlers are `async def` too, so the
uncached facets build (Bug 2) also ran on the event loop, on every storefront
page view. During the flash sale, both bugs were taking turns holding the loop.

**Regression test:** fire overlapping requests and check they overlap.

```python
import asyncio, time
import httpx
from app.config import Settings
from app.main import create_app

def test_checkouts_do_not_block_each_other(tmp_path):
    app = create_app(Settings(db_path=str(tmp_path / "burst.db"), carrier_latency_ms=200))

    async def burst() -> float:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/products", json={
                "sku": "BURST-1", "name": "x", "category": "tools", "price_cents": 100,
                "weight_grams": 100, "lead_time_days": 1, "initial_stock": 100,
            })
            assert resp.status_code == 201
            order = {"customer_email": "a@b.co", "postcode": "10115",
                     "items": [{"sku": "BURST-1", "quantity": 1}]}
            start = time.perf_counter()
            responses = await asyncio.gather(*(client.post("/api/orders", json=order)
                                               for _ in range(5)))
            assert all(r.status_code == 201 for r in responses)
            return time.perf_counter() - start

    # Five 200 ms carrier calls should overlap, not queue up behind each other.
    assert asyncio.run(burst()) < 0.6
```

On the buggy code this takes ~1.05 s and fails. On the fix the whole test takes
~0.27 s.

**Lesson:** `async def` is a promise that you never block. If anything inside
it does blocking I/O, every request on that worker pays for it.

---

## Bug 2: `lru_cache` on a per-request object (STK-214)

**Where:** [app/services/catalog.py](app/services/catalog.py), `CatalogService.facets`

```python
@lru_cache(maxsize=1)
def facets(self) -> Facets:
    ...
```

**Root cause:** `lru_cache` builds its key from *all* arguments, and for a method
the first argument is `self`. `get_catalog_service` in
[app/dependencies.py](app/dependencies.py) creates a **new `CatalogService` on
every request**, so every call has a new key. The cache never hits. Each page
view rebuilds the facets from scratch, which means loading every product and
summing the whole stock ledger. The cost grows with the catalog and with stock
history.

It passed code review because it *looks* right. There's even a correct-looking
`invalidate()` that calls `cache_clear()`. It also passed every test, because a
cache that never hits can never serve stale data. The freshness tests
(`test_facets_reflect_*`) were green *because of* the bug.

Two more problems hide in it:

- The cache holds a strong reference to `self`, and through it to that
  request's repositories and closed DB connection. With `maxsize=1` that's just
  one object. With the default `maxsize=128` it would pin 128 dead service
  objects for the life of the process.
- ruff and flake8-bugbear flag this exact pattern as `B019`.

**Fix:** put the cache on something that lives as long as the app, and keep the
invalidation on writes.

```python
# services/catalog.py
class FacetsCache:
    """Holds the latest facets for the lifetime of the app."""

    def __init__(self):
        self._value: Facets | None = None
        self._generation = 0
        self._lock = threading.Lock()

    def get_or_compute(self, compute: Callable[[], Facets]) -> Facets:
        with self._lock:
            if self._value is not None:
                return self._value
            generation = self._generation
        value = compute()
        with self._lock:
            if generation == self._generation:
                self._value = value
        return value

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            self._value = None


class CatalogService:
    def __init__(self, products, stock, price_bucket_edges_cents, facets_cache: FacetsCache):
        ...
        self.facets_cache = facets_cache

    def facets(self) -> Facets:
        return self.facets_cache.get_or_compute(self._compute_facets)

    def _compute_facets(self) -> Facets:
        ...  # the old body of facets()

    def invalidate(self) -> None:
        self.facets_cache.invalidate()
```

```python
# main.py
app.state.facets_cache = FacetsCache()

# dependencies.py
def get_facets_cache(request: Request) -> FacetsCache:
    return request.app.state.facets_cache

def get_catalog_service(..., facets_cache: FacetsCache = Depends(get_facets_cache)):
    return CatalogService(products, stock, settings.price_bucket_edges_cents, facets_cache)
```

**Why the generation counter?** Without it, this sequence serves stale data
until the next write:

1. Request A misses the cache and starts computing facets from the old data.
2. Request B creates a product and invalidates the cache.
3. Request A finishes and stores its old result.

With the counter, A notices that an invalidation happened during its compute
and doesn't store the result. The lock isn't held during the compute, so a slow
rebuild doesn't block readers. Two concurrent misses may both compute, but they
store the same value. That's fine here.

A module-level `@lru_cache` on a plain function, or a short TTL, would also work.
Each choice trades freshness against simplicity. With more than one worker
process, each one has its own cache, and an invalidation in one worker doesn't
reach the others. That's one of the stretch questions.

**Regression test:** count how often the expensive part runs.

```python
from app.repository import ProductRepository

def test_facets_are_computed_once_between_writes(client, make_product, monkeypatch):
    make_product(category="audio")
    calls = []
    real_list_all = ProductRepository.list_all

    def counting_list_all(self):
        calls.append(1)
        return real_list_all(self)

    monkeypatch.setattr(ProductRepository, "list_all", counting_list_all)
    for _ in range(3):
        assert client.get("/api/catalog/facets").json()["total_products"] == 1
    assert len(calls) == 1

    make_product(category="tools")
    assert client.get("/api/catalog/facets").json()["total_products"] == 2
    assert len(calls) == 2
```

It checks both halves of caching: it hits when nothing changed, and it's
invalidated when something did. Tests that check only freshness can't tell
"cached correctly" apart from "not cached at all".

**Lesson:** a cache is only as long-lived as the object that owns it. Always
test the hit path, not just freshness.

---

## Bug 3: nested loop over sales (STK-227)

**Where:** [app/services/reports.py](app/services/reports.py), `ReorderService.report`

```python
sales = self.stock.sales_since(since)
for product in products:
    product_sales = [m for m in sales if m.product_id == product.id]
```

**Root cause:** for every product, the code scans the *entire* sales list to find
that product's sales. That's products × sales comparisons: 1,600 × ~19,500 sales in
the window ≈ 31 million at LARGE. LARGE has 4× the products and 8× the sales, so the work grows
4 × 8 = 32×, and the benchmark showed 20.5×. The SQL really does finish in
milliseconds. All the time goes into the Python list comprehension, which is
why the DB team saw nothing.

It reads naturally, and with the 20 products in a test fixture it's instant.
Quadratic code usually looks like this.

**Fix A (one file, minimal):** group the sales once, then look each product up.

```python
from collections import defaultdict
from app.repository import StockMovement

sales_by_product: dict[int, list[StockMovement]] = defaultdict(list)
for movement in self.stock.sales_since(since):
    sales_by_product[movement.product_id].append(movement)

suggestions = []
for product in products:
    product_sales = sales_by_product.get(product.id)
    if not product_sales:
        continue
    ...
```

Now it's O(products + sales): 597 ms → 57 ms. Use `.get()`, not `[...]`, on the
`defaultdict`. Indexing would insert an empty list for every product that
never sold.

**Fix B (faster):** don't send ~19,500 rows to Python just to add them up. Let
SQLite aggregate.

```python
# repository.py
def sales_summary_since(self, since: float) -> dict[int, SalesSummary]:
    rows = self.conn.execute(
        """
        SELECT product_id, -SUM(delta) AS units_sold, MAX(created_at) AS last_sold_at
        FROM stock_movements
        WHERE reason = 'sale' AND created_at >= ?
        GROUP BY product_id
        """,
        (since,),
    ).fetchall()
    return {r["product_id"]: SalesSummary(r["units_sold"], r["last_sold_at"]) for r in rows}
```

The report only needs units sold and the last sale time per product, so this
returns one small row per product. Measured: 597 ms → 18.6 ms, with all tests
still green.

**Regression test:** timing tests are flaky, so count the work instead.

```python
from app.repository import StockRepository

def test_reorder_report_reads_sales_once(client, make_product, place_order, monkeypatch):
    for i in range(20):
        make_product(sku=f"LOOP-{i:02d}", initial_stock=2, lead_time_days=30)
        place_order((f"LOOP-{i:02d}", 1))

    class CountingList(list):
        iterations = 0

        def __iter__(self):
            CountingList.iterations += 1
            return super().__iter__()

    real_sales_since = StockRepository.sales_since
    monkeypatch.setattr(
        StockRepository, "sales_since",
        lambda self, since: CountingList(real_sales_since(self, since)),
    )
    body = client.get("/api/reports/reorder").json()
    assert len(body["suggestions"]) == 20
    assert CountingList.iterations <= 2
```

On the buggy code the list is iterated 20 times, once per product. Fix A
iterates it once. Fix B never calls `sales_since`. If you use Fix B, delete
`sales_since` and test the new query's results directly instead.

**Lesson:** a loop over A containing a filter over B is O(A × B). When you see
`[x for x in big_list if x.key == ...]` inside a loop, reach for a dict.

---

## Things that were *not* bugs

- **The controls.** `GET /api/products/{sku}` and `GET /api/orders/{id}` stayed at
  ~1× growth from the start, so there was nothing to gain there.
- **Recomputing stock on hand from the ledger.** It's a `SUM` over one
  product's movements via the `(product_id, created_at)` index. It's cheap,
  and it's always consistent. A denormalized `stock_levels` table is a
  trade-off (see the stretch goals), not a fix.
- **The other `async def` handlers.** Strictly speaking, they also block the
  loop while they call SQLite. Each call takes about a millisecond, so it
  doesn't show up here. Converting them to `def` is the consistent choice, and a
  good cleanup to do alongside Bug 1, but the carrier call was the incident.
- **SQLite's single writer.** If the 32 benchmark checkouts arrive at *exactly*
  the same instant, they all try to write at once and back off on SQLite's write
  lock: 32 simultaneous writes took ~257 ms even with zero carrier latency. That
  is why the benchmark spreads arrivals over 100 ms. It's a limit of SQLite,
  not of this code. Postgres, or batching writes, is the real answer at that
  volume.
- **Opening a connection per request.** It's cheap for SQLite and avoids
  sharing a connection across threads. That matters more once Bug 1 is fixed
  and handlers really do run in threads.
