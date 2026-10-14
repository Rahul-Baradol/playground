# The Stockroom performance challenge

Stockroom works. All 29 tests pass. It also has **three performance bugs** that
get worse as the shop grows. Your job is to find them, fix them, and prove your
fixes worked.

## Ground rules

1. **Measure first.** Run the baseline before you change anything:
   ```bash
   python -m scripts.benchmark --save before.json
   ```
2. **Keep behavior identical.** `pytest -q` must stay green. Don't change the
   API contract.
3. **Prove it.** When you're done:
   ```bash
   python -m scripts.benchmark --compare before.json
   ```
   Compare each row's `growth` with how much more work that request really
   has to do at the LARGE scale. Work that doesn't depend on table size or on
   other requests should stay close to **1×**.
4. **Lock it in.** For each bug, write a test that would have failed before your
   fix. Some of these are harder to test than a wrong return value. Finding a
   way to test them is part of the exercise.
5. **Write it up.** For each bug, give the symptom, the root cause, the fix, and
   the before/after numbers, in a few sentences.

Only open [SOLUTIONS.md](SOLUTIONS.md) once you've finished, or you're truly stuck
after reading every hint.

---

## Incident reports

These are the reports the team received. They describe symptoms only, the way
real bug reports do.

### 🎫 STK-201: "Whole API froze during the flash sale"
> During Friday's flash sale, checkout (`POST /api/orders`) went from ~150 ms to
> several seconds. It wasn't just checkout: product pages, the facets sidebar,
> and even `/healthz` timed out too, and the load balancer started marking pods
> unhealthy. The carrier's status page says their rate API held steady at
> ~120 ms the whole time. CPU on our pods stayed low.

### 🎫 STK-214: "Facets endpoint tracks traffic, not catalog changes"
> The storefront calls `GET /api/catalog/facets` on every page view. The facets
> only change when someone edits the catalog or stock moves, and nobody touched
> the catalog all afternoon. Even so, the database does the same reads on every
> single storefront hit, and the endpoint keeps getting slower as we add products.

### 🎫 STK-227: "Reorder report is fine for the small warehouse, unusable for the big one"
> Ops runs `GET /api/reports/reorder` every morning. For the small warehouse
> it's instant. The big warehouse has about 4× the products and 8× the order
> history, but the report takes more than 20× as long, and it gets worse every
> month. The DB team says the SQL behind it finishes in a few milliseconds.

---

## Hints

Open these one at a time, only as far as you need.

<details>
<summary>General: tools worth knowing</summary>

- **Profile Python.** `python -m cProfile -s cumtime -m scripts.benchmark --quick`.
  Sort by `cumtime` and look for your own code, not the framework's.
- **Count your queries.** `sqlite3.Connection.set_trace_callback(print)` logs
  every statement that runs on a connection. Try wrapping `app.db.connect`.
- **Reproduce under load.** Some bugs only show up when requests overlap. The
  benchmark's burst scenario uses `httpx.AsyncClient` with `ASGITransport` to
  send many requests at once without starting a server. Read how it works.
- **Run a linter with more rules on.** Some performance traps are well known
  enough that linters have a rule for them.
- Each incident maps to exactly one bug, and each bug lives in a different file.

</details>

<details>
<summary>STK-201: hint 1</summary>

`/healthz` doesn't touch the database or the carrier, yet it timed out too. What
does every request handled by one uvicorn worker share? Try timing `/healthz`
while a burst of checkouts is in flight.

</details>

<details>
<summary>STK-201: hint 2</summary>

Look at how the checkout handler is declared, then follow the call down to
`MockCarrierClient.quote`. What happens to all the other requests while a plain
function waits on the network *inside* an `async def`?

</details>

<details>
<summary>STK-201: hint 3</summary>

FastAPI runs `async def` handlers directly on the event loop, and plain `def`
handlers in a threadpool. A blocking call inside `async def` stalls the loop
for everyone. You can let FastAPI run the handler in a thread, or push just the
blocking call to one yourself (`starlette.concurrency.run_in_threadpool`,
`asyncio.to_thread`). Think about which one fits this codebase, where the
repositories are synchronous too.

</details>

<details>
<summary>STK-214: hint 1</summary>

Put a counter or a `print` inside the code that builds the facets, then load the
endpoint five times in a row without changing anything. How many times does
it run? How many times should it?

</details>

<details>
<summary>STK-214: hint 2</summary>

There *is* a cache. `functools.lru_cache` builds its key from every argument of
the call. For a method, what is the first argument? Now look at
`app/dependencies.py`. How long does that object live?

</details>

<details>
<summary>STK-214: hint 3</summary>

This trap is common enough that linters flag it (ruff / flake8-bugbear rule
`B019`). The cache has to live as long as the app, like the other app-wide
objects set up in `create_app`, and every write must still invalidate it. Bonus:
what happens if a write lands *while* the facets are being computed?

</details>

<details>
<summary>STK-227: hint 1</summary>

The DB team is right. Profile one report, or time the sections of
`ReorderService.report`. Is the time spent in SQL or in Python?

</details>

<details>
<summary>STK-227: hint 2</summary>

Count how many times, in total, one report walks through the `sales` list. How
does that number change when products go up 4× and sales go up 8×?

</details>

<details>
<summary>STK-227: hint 3</summary>

Group once, then look up many times. One pass over the sales can build a `dict`
from product id to that product's sales. Or let SQLite do the grouping with
`GROUP BY product_id`. Either way, the cost becomes products + sales instead of
products × sales.

</details>

---

## Stretch goals (optional)

- Two checkouts for the last unit of a product can both pass the stock check
  before either one writes. How would you prevent overselling? Compare
  `BEGIN IMMEDIATE`, a conditional write, and a reservations table.
- The carrier quote happens inside the checkout request. What should checkout
  do when the carrier is slow or down? Think about timeouts, retries, a circuit
  breaker, and a flat-rate fallback.
- Every order invalidates the facets. During a flash sale, what hit rate would
  you expect? Would a few seconds of staleness be acceptable for the sidebar?
  What changes once you run 4 workers?
- Stock on hand is recomputed from the movement ledger on every read. When would
  you keep a `stock_levels` table up to date instead, and what would you be
  trading away?
