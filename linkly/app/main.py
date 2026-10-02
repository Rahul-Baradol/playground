from fastapi import FastAPI

from app.cache import TTLCache
from app.config import Settings
from app.db import init_db
from app.rate_limit import SlidingWindowRateLimiter
from app.routes import links, redirect, stats


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    init_db(settings.db_path)

    app = FastAPI(title="Linkly", version="0.3.0")
    app.state.settings = settings
    app.state.link_cache = TTLCache(settings.cache_max_entries, settings.cache_ttl_seconds)
    app.state.rate_limiter = SlidingWindowRateLimiter(
        settings.rate_limit_requests, settings.rate_limit_window_seconds
    )

    @app.get("/healthz", tags=["ops"])
    def healthz() -> dict:
        return {"status": "ok"}

    app.include_router(links.router)
    app.include_router(stats.router)
    # Must be registered last: it catches every single-segment path.
    app.include_router(redirect.router)
    return app
