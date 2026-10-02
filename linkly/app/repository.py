import sqlite3
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Link:
    id: int
    code: str
    target_url: str
    created_at: float
    expires_at: float | None

    def is_expired(self, now: float | None = None) -> bool:
        if self.expires_at is None:
            return False
        return self.expires_at <= (now if now is not None else time.time())


def _row_to_link(row: sqlite3.Row) -> Link:
    return Link(
        id=row["id"],
        code=row["code"],
        target_url=row["target_url"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
    )


class LinkRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, code: str, target_url: str, expires_at: float | None = None) -> Link:
        created_at = time.time()
        cur = self.conn.execute(
            "INSERT INTO links (code, target_url, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (code, target_url, created_at, expires_at),
        )
        self.conn.commit()
        return Link(cur.lastrowid, code, target_url, created_at, expires_at)

    def get_by_code(self, code: str) -> Link | None:
        row = self.conn.execute(
            "SELECT id, code, target_url, created_at, expires_at FROM links WHERE code = ?",
            (code,),
        ).fetchone()
        return _row_to_link(row) if row else None

    def code_exists(self, code: str) -> bool:
        row = self.conn.execute("SELECT 1 FROM links WHERE code = ?", (code,)).fetchone()
        return row is not None

    def list_recent(self, limit: int, offset: int) -> list[Link]:
        rows = self.conn.execute(
            """
            SELECT id, code, target_url, created_at, expires_at
            FROM links
            ORDER BY created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [_row_to_link(r) for r in rows]

    def count_for_links(self, link_ids: list[int]) -> dict[int, int]:
        placeholders = ",".join("?" for _ in link_ids)
        result = self.conn.execute(
            f"""
                select link_id, count(*) as n
                from clicks 
                where link_id in ({placeholders})
                group by link_id
            """,
            link_ids
        ).fetchall()

        mapping: dict[int, int] = {}
        for link_id, count in result:
            mapping[link_id] = count

        return mapping

    def delete(self, code: str) -> bool:
        cur = self.conn.execute("DELETE FROM links WHERE code = ?", (code,))
        self.conn.commit()
        return cur.rowcount > 0


class ClickRepository:
    _GROUPABLE_COLUMNS = {"referrer", "country"}

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(
        self,
        link_id: int,
        referrer: str | None = None,
        user_agent: str | None = None,
        country: str | None = None,
        clicked_at: float | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO clicks (link_id, clicked_at, referrer, user_agent, country)
            VALUES (?, ?, ?, ?, ?)
            """,
            (link_id, clicked_at or time.time(), referrer, user_agent, country),
        )
        self.conn.commit()

    def count_for_link(self, link_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM clicks WHERE link_id = ?", (link_id,)
        ).fetchone()
        return row["n"]

    def daily_counts(self, link_id: int, since: float) -> dict[str, int]:
        rows = self.conn.execute(
            """
            SELECT date(clicked_at, 'unixepoch') AS day, COUNT(*) AS n
            FROM clicks
            WHERE link_id = ? AND clicked_at >= ?
            GROUP BY day
            """,
            (link_id, since),
        ).fetchall()
        return {r["day"]: r["n"] for r in rows}

    def top_values(
        self, link_id: int, column: str, since: float, limit: int = 5
    ) -> list[tuple[str, int]]:
        if column not in self._GROUPABLE_COLUMNS:
            raise ValueError(f"cannot group clicks by {column!r}")
        rows = self.conn.execute(
            f"""
            SELECT {column} AS value, COUNT(*) AS n
            FROM clicks
            WHERE link_id = ? AND clicked_at >= ? AND {column} IS NOT NULL
            GROUP BY {column}
            ORDER BY n DESC, value ASC
            LIMIT ?
            """,
            (link_id, since, limit),
        ).fetchall()
        return [(r["value"], r["n"]) for r in rows]
