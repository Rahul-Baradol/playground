# Linkly

A small URL shortener with click analytics, built with FastAPI and SQLite.

```
POST   /api/links               create a short link (optional alias / expiry)
GET    /api/links               list links, newest first, with click totals
GET    /api/links/{code}        one link
DELETE /api/links/{code}        delete a link and its click history
GET    /api/links/{code}/stats  daily clicks, top referrers, top countries
GET    /{code}                  307 redirect to the target (records a click)
GET    /healthz                 liveness probe
```

`/api/*` routes are rate-limited per client IP. Redirect lookups are served from
an in-memory TTL/LRU cache.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
python -m scripts.seed --links 2000 --clicks 100000     # optional demo data
uvicorn app.main:create_app --factory --reload
open http://localhost:8000/docs
```

```bash
curl -s -XPOST localhost:8000/api/links -H 'content-type: application/json' \
     -d '{"url": "https://example.com/a/very/long/path", "alias": "demo"}'
curl -si localhost:8000/demo -H 'referer: https://t.co/x' -H 'x-geo-country: US'
curl -s localhost:8000/api/links/demo/stats | python -m json.tool
```

Configuration is read from environment variables (see `app/config.py`):
`LINKLY_DB_PATH`, `LINKLY_BASE_URL`, `LINKLY_CACHE_TTL`,
`LINKLY_CACHE_MAX_ENTRIES`, `LINKLY_RATE_LIMIT_REQUESTS`, `LINKLY_RATE_LIMIT_WINDOW`.

## Test and benchmark

```bash
pytest -q
python -m scripts.benchmark            # ~25s; add --quick for a faster run
```

## Layout

```
app/
  main.py            app factory, wiring
  config.py          settings
  db.py              schema + connections
  repository.py      all SQL lives here
  cache.py           TTL + LRU cache
  rate_limit.py      sliding-window rate limiter
  models.py          request/response schemas
  dependencies.py    FastAPI dependency providers
  services/          shortening + analytics logic
  routes/            HTTP handlers
scripts/             seed data, benchmark
tests/
```

**Working on the performance exercise? Start with [CHALLENGE.md](CHALLENGE.md).**
