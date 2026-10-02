"""Fill a Linkly database with realistic-looking fake data.

    python -m scripts.seed --links 2000 --clicks 100000
"""

import argparse
import random
import time

from app.db import connect, init_db
from app.services.shortener import generate_code

REFERRERS = [None, None, "t.co", "google.com", "news.ycombinator.com", "reddit.com",
             "linkedin.com", "facebook.com", "duckduckgo.com", "github.com"]
COUNTRIES = [None, "US", "US", "US", "IN", "DE", "GB", "FR", "BR", "JP", "CA", "AU"]
AGENTS = ["Mozilla/5.0 (Macintosh)", "Mozilla/5.0 (Windows NT 10.0)", "curl/8.4.0",
          "Mozilla/5.0 (iPhone)", "Mozilla/5.0 (Linux; Android 14)"]
DAY = 86_400


def seed(db_path: str, n_links: int, n_clicks: int, days: int = 60, rng_seed: int = 42) -> list[str]:
    """Insert links and clicks. Returns the codes created, oldest first."""
    rng = random.Random(rng_seed)
    init_db(db_path)
    conn = connect(db_path)
    now = time.time()

    codes, link_rows = [], []
    seen: set[str] = set()
    for i in range(n_links):
        code = generate_code(7)
        while code in seen:
            code = generate_code(7)
        seen.add(code)
        codes.append(code)
        created = now - days * DAY + (i / max(n_links, 1)) * days * DAY
        link_rows.append((code, f"https://example.com/articles/{i}", created, None))

    conn.executemany(
        "INSERT INTO links (code, target_url, created_at, expires_at) VALUES (?, ?, ?, ?)",
        link_rows,
    )
    id_by_code = dict(conn.execute("SELECT code, id FROM links").fetchall())
    link_ids = [id_by_code[c] for c in codes]

    # Popularity follows a rough power law: a few links get most clicks.
    weights = [1 / (rank + 1) ** 0.8 for rank in range(len(link_ids))]
    rng.shuffle(weights)
    chosen = rng.choices(link_ids, weights=weights, k=n_clicks)

    batch = []
    for link_id in chosen:
        batch.append((
            link_id,
            now - rng.random() * days * DAY,
            rng.choice(REFERRERS),
            rng.choice(AGENTS),
            rng.choice(COUNTRIES),
        ))
        if len(batch) >= 50_000:
            _insert_clicks(conn, batch)
            batch.clear()
    _insert_clicks(conn, batch)

    conn.commit()
    conn.close()
    return codes


def _insert_clicks(conn, rows) -> None:
    conn.executemany(
        "INSERT INTO clicks (link_id, clicked_at, referrer, user_agent, country) "
        "VALUES (?, ?, ?, ?, ?)",
        rows,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--db", default="linkly.db")
    parser.add_argument("--links", type=int, default=2_000)
    parser.add_argument("--clicks", type=int, default=100_000)
    args = parser.parse_args()

    start = time.perf_counter()
    seed(args.db, args.links, args.clicks)
    print(f"Seeded {args.links:,} links and {args.clicks:,} clicks into {args.db} "
          f"in {time.perf_counter() - start:.1f}s")


if __name__ == "__main__":
    main()
