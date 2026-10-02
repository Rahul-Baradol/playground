import sqlite3
from typing import Iterator

from fastapi import Depends, HTTPException, Request, status

from app.cache import TTLCache
from app.config import Settings
from app.db import connect
from app.repository import ClickRepository, LinkRepository


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_conn(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_link_repo(conn: sqlite3.Connection = Depends(get_conn)) -> LinkRepository:
    return LinkRepository(conn)


def get_click_repo(conn: sqlite3.Connection = Depends(get_conn)) -> ClickRepository:
    return ClickRepository(conn)


def get_cache(request: Request) -> TTLCache:
    return request.app.state.link_cache


def rate_limit(request: Request) -> None:
    limiter = request.app.state.rate_limiter
    client = request.client.host if request.client else "unknown"
    if not limiter.allow(client):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded, slow down.",
            headers={"Retry-After": str(int(limiter.window_seconds))},
        )
