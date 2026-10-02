# The Linkly performance challenge

Linkly works. All 33 tests pass. It also has **three performance bugs** that
get worse as the product grows. Your job is to find them, fix them, and prove
your fixes worked.

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
   For a healthy endpoint, the `growth` column should be close to **1×**: the
   time shouldn't depend much on how big the tables are.
4. **Lock it in.** For each bug, write a test that would have failed before your
   fix. This is the step most engineers skip, and the one that matters most.
5. **Write it up.** For each bug, give the symptom, the root cause, the fix, and
   the before/after numbers, in a few sentences. Writing a clear incident summary
   is a skill in its own right.

Only open [SOLUTIONS.md](SOLUTIONS.md) once you've finished, or you're truly stuck
after reading every hint.

---

## Incident reports

These are the reports the team received. They describe symptoms only, the way
real bug reports do.

### 🎫 LNK-101: "Dashboard got really slow"
> The links dashboard (`GET /api/links?limit=200`) used to load instantly.
> Now that we have a few thousand links, it takes close to a second. The
> database CPU spikes every time someone opens the dashboard.

### 🎫 LNK-114: "Stats page timing out for big customers"
> `GET /api/links/{code}/stats` is fine for new accounts. For accounts with lots
> of click history it's slow, even when they're only looking at one link. Deleting
> links has also gotten sluggish.

### 🎫 LNK-127: "API latency creeps up until we restart"
> After a deploy the API is snappy. Over days, p99 latency on every `/api/*`
> route slowly climbs and memory grows steadily. A restart fixes it, so on-call
> has been restarting the pods every weekend. No single slow query shows up in
> the DB logs.

---

## Hints

Open these one at a time, only as far as you need.

<details>
<summary>General: tools worth knowing</summary>

- **Count your queries.** `sqlite3.Connection.set_trace_callback(print)` logs
  every statement that runs on a connection. Try wrapping `app.db.connect`.
- **Ask the database how it runs a query.** In the `sqlite3` shell, or via
  `conn.execute(...)`, try `EXPLAIN QUERY PLAN SELECT ...`. Look for the words
  `SCAN` and `SEARCH`.
- **Profile Python.** `python -m cProfile -s cumtime -m scripts.benchmark --quick`
- **Watch memory.** `tracemalloc` (standard library) can show you what's growing.
- Each incident maps to exactly one bug, and each bug lives in a different file.

</details>

<details>
<summary>LNK-101: hint 1</summary>

Turn on query logging and load the dashboard once with `limit=200`. How many
SQL statements run? How many *should* run?

</details>

<details>
<summary>LNK-101: hint 2</summary>

The route handler looks clean and readable. Read what happens *inside* the list
comprehension. This pattern has a famous name. It's the classic ORM
performance trap, and you can fall into it just as easily with raw SQL.

</details>

<details>
<summary>LNK-101: hint 3</summary>

You can get every count you need in **one** query, using `GROUP BY` together
with either `IN (...)` or a `LEFT JOIN`. Make sure links with zero clicks still
show `total_clicks: 0`.

</details>

<details>
<summary>LNK-114: hint 1</summary>

Every slow query here filters on the same column. Look at the schema in
`app/db.py`. What does the database have to do to find one link's clicks?

</details>

<details>
<summary>LNK-114: hint 2</summary>

Run `EXPLAIN QUERY PLAN SELECT COUNT(*) FROM clicks WHERE link_id = 1;`. Then
try it for the `daily_counts` query. There *is* an index on `clicks`. Is it the
one these queries need?

</details>

<details>
<summary>LNK-114: hint 3</summary>

Think about column order in a composite index. The stats queries filter on
equality on one column and a range on another. Which one should come first?
Also, why does `DELETE` get slower? Look at `ON DELETE CASCADE`.

</details>

<details>
<summary>LNK-127: hint 1</summary>

"No slow query in the DB logs" and "a restart fixes it" mean the problem is
**in-process state** that grows over time. Which objects live for the whole
life of the app? Check `create_app`.

</details>

<details>
<summary>LNK-127: hint 2</summary>

Look at `SlidingWindowRateLimiter.allow`. Write down which variable gets
filtered and which variable gets appended to. Are they the same list?

</details>

<details>
<summary>LNK-127: hint 3</summary>

There are actually two leaks. One is per client: old timestamps are never
dropped. The other is across clients: keys for IPs that went quiet stay forever.
`collections.deque` with `popleft()` fits the first one nicely. Since timestamps
are appended in order, the oldest is always at the front.

</details>

---

## Stretch goals (optional)

- Each redirect does a synchronous `INSERT` + `COMMIT` before responding. How
  would you take click recording off the hot path? What would you be trading away?
- `GET /api/links` uses `LIMIT/OFFSET`. What happens at `offset=100000`? Look up
  keyset (cursor) pagination.
- The rate limiter is in-memory. What breaks when you run 4 uvicorn workers or
  3 pods? How would you redesign it?
- The redirect cache can serve a deleted link from another process for up to
  `cache_ttl_seconds`. Is that acceptable? How would you fix it if it weren't?
