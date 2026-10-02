# ⚠️ SPOILERS: Linkly solutions

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

Measured on an Apple Silicon laptop, full benchmark. "Large" has 2,000 links and 200,000 clicks.

| scenario                      | before (large) | after (large) | speedup |
|-------------------------------|---------------:|--------------:|--------:|
| `GET /api/links?limit=200`    |       ~850 ms  |       ~2.4 ms |  ~350×  |
| `GET /api/links/{code}/stats` |       ~155 ms  |       ~1.4 ms |  ~110×  |
| `DELETE /api/links/{code}`    |        ~16 ms  |       ~5.6 ms |    ~3×  |
| `rate_limiter.allow()`        |      ~650 µs   |      ~0.4 µs  | ~1600×  |

After the fixes, every row's `growth` column is about 1×.

---

## Bug 1: N+1 queries in `GET /api/links` (LNK-101)

**Where:** [app/routes/links.py](app/routes/links.py), `list_links`

```python
return [
    LinkOut.from_link(link, settings.base_url, clicks.count_for_link(link.id))
    for link in links.list_recent(limit, offset)
]
```

**Root cause:** one query fetches the page of links, then **one more query per
link** counts its clicks. With `limit=200` that's 201 round-trips. Bug 2 makes it
much worse: each of those 200 `COUNT(*)` queries does a full table scan of
`clicks`. So the endpoint reads the entire clicks table 200 times per request.
That's why it grew 9× on 4× more links. The cost is roughly links × clicks.

**Fix:** fetch all the counts in one grouped query.

```python
# repository.py: ClickRepository
def counts_for_links(self, link_ids: list[int]) -> dict[int, int]:
    if not link_ids:
        return {}
    placeholders = ",".join("?" * len(link_ids))
    rows = self.conn.execute(
        f"""
        SELECT link_id, COUNT(*) AS n
        FROM clicks
        WHERE link_id IN ({placeholders})
        GROUP BY link_id
        """,
        link_ids,
    ).fetchall()
    return {r["link_id"]: r["n"] for r in rows}
```

```python
# routes/links.py
page = links.list_recent(limit, offset)
counts = clicks.counts_for_links([link.id for link in page])
return [LinkOut.from_link(link, settings.base_url, counts.get(link.id, 0)) for link in page]
```

Building the `?` placeholders with an f-string is safe. Only the *number* of `?`
is interpolated. The values are still bound as parameters. A
`LEFT JOIN clicks ... GROUP BY links.id` in `list_recent` is an equally good
fix.

**Regression test idea:** count the statements that run.

```python
def test_list_links_is_not_n_plus_1(client, make_link, monkeypatch):
    import app.dependencies as deps
    statements = []
    real_connect = deps.connect

    def tracing_connect(path):
        conn = real_connect(path)
        conn.set_trace_callback(statements.append)
        return conn

    monkeypatch.setattr(deps, "connect", tracing_connect)
    for i in range(20):
        make_link(alias=f"n1-{i}")
    statements.clear()
    client.get("/api/links", params={"limit": 20})
    assert len([s for s in statements if s.lstrip().upper().startswith("SELECT")]) <= 3
```

**Lesson:** a loop that calls a data-access method is a red flag, whether you use an ORM or not.
Look out for it during code review.

---

## Bug 2: index on the wrong column (LNK-114)

**Where:** [app/db.py](app/db.py)

```sql
CREATE INDEX IF NOT EXISTS idx_clicks_clicked_at ON clicks(clicked_at);
```

**Root cause:** every hot query filters clicks by `link_id`:
`count_for_link`, `daily_counts`, `top_values`, and the `ON DELETE CASCADE` lookup.
There's no index that starts with `link_id`, so SQLite has two choices. It can
`SCAN clicks`, reading every row, or use the `clicked_at` index to read every
click in the date range for *all* links, then throw away the ones for other links.
Either way the cost grows with the size of the whole table, not with how many
clicks the one link has.

```
sqlite> EXPLAIN QUERY PLAN SELECT COUNT(*) FROM clicks WHERE link_id = 1;
`--SCAN clicks
```

The CASCADE is the sneaky part. Deleting one link makes SQLite find its child
rows in `clicks`. Without an index on `link_id`, that's a full scan on every
delete. Foreign-key columns almost always need an index.

**Fix:** a composite index with the equality column first and the range column second.

```sql
CREATE INDEX IF NOT EXISTS idx_clicks_link_id_clicked_at ON clicks(link_id, clicked_at);
```

```
sqlite> EXPLAIN QUERY PLAN SELECT COUNT(*) FROM clicks WHERE link_id = 1;
`--SEARCH clicks USING COVERING INDEX idx_clicks_link_id_clicked_at (link_id=?)
```

Why `(link_id, clicked_at)` and not `(clicked_at, link_id)`? An index is sorted
by its first column, then by the second. With `link_id` first, all of one link's
clicks sit together, already sorted by time, so `link_id = ? AND clicked_at >= ?`
becomes one contiguous range read. The other order would scatter them.
This index also serves queries on `link_id` alone, so you don't need a separate
`(link_id)` index. Drop the old `clicked_at` index unless something actually
queries by time across all links. Every index slows down writes.

> Since `CREATE TABLE IF NOT EXISTS` won't change an existing DB, a real
> deployment would also need a migration. For this exercise, delete `linkly.db`.

**Regression test idea:** check the plan.

```python
def test_click_queries_use_index(conn):
    plan = " ".join(r[3] for r in conn.execute(
        "EXPLAIN QUERY PLAN SELECT COUNT(*) FROM clicks WHERE link_id = 1"))
    assert "SCAN clicks" not in plan
```

**Lesson:** design indexes around your `WHERE` clauses, and verify them with
`EXPLAIN QUERY PLAN`. Don't guess.

---

## Bug 3: rate limiter grows forever (LNK-127)

**Where:** [app/rate_limit.py](app/rate_limit.py), `allow`

```python
hits = self._hits[key]
recent = [t for t in hits if now - t < self.window_seconds]   # filtered copy...
if len(recent) >= self.max_requests:
    return False
hits.append(now)                                               # ...but appends to the original
```

**Root cause:** `recent` is a new filtered list that gets thrown away. The
original `hits` list is never pruned, so every allowed request since startup
stays in memory. Each call then walks the entire history, which makes it O(total
requests ever made by that IP). It's both a memory leak and a CPU leak. That's
why it looked fine after a restart and got worse over days. There's a second,
smaller leak too: because of `defaultdict`, every IP that ever called the API keeps
a dict entry forever, and so does every IP that `remaining()` merely looked up.

**Fix:** a `deque` per key, pruned from the left, and empty keys removed.

```python
from collections import deque

class SlidingWindowRateLimiter:
    def __init__(self, max_requests, window_seconds, clock=time.monotonic):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while hits and now - hits[0] >= self.window_seconds:
            hits.popleft()
        if not hits:
            del self._hits[key]
        return hits

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self.max_requests:
                return False
            if not hits:
                self._hits[key] = hits
            hits.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            return max(0, self.max_requests - len(self._prune(key, now)))
```

Timestamps arrive in increasing order, so the oldest is always at the left and
pruning is amortized O(1). Each stored entry is now capped at `max_requests`.
IPs that only visited once are cleaned up the next time that key is checked. A
fully robust version would also sweep idle keys periodically, or store them in
the `TTLCache` you already have.

**Regression test idea:** check the internal size directly.

```python
def test_rate_limiter_memory_is_bounded():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(10, 60, clock=clock)
    for _ in range(10_000):
        clock.advance(1)
        limiter.allow("ip")
    assert len(limiter._hits["ip"]) <= 10
```

**Lesson:** any long-lived, in-process collection needs an eviction story. Each
time you write `.append` on something stored in `self` that lives for the app's
lifetime, ask "what removes items from this?"

---

## Things that were *not* bugs

- **`TTLCache`** is correct: it really is O(1) LRU with expiry.
- **Opening a SQLite connection per request** is cheap and avoids sharing a
  connection across threads. It's fine at this scale.
- **The redirect path** was already fast thanks to the cache. Its `growth` stayed at ~1× from the start.
  It would be wasted effort to optimize it first. Measuring is what tells you which code to leave alone.
