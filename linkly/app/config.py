import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("LINKLY_DB_PATH", "linkly.db"))
    base_url: str = field(
        default_factory=lambda: os.getenv("LINKLY_BASE_URL", "http://localhost:8000")
    )
    code_length: int = 7

    cache_ttl_seconds: int = field(default_factory=lambda: _env_int("LINKLY_CACHE_TTL", 300))
    cache_max_entries: int = field(
        default_factory=lambda: _env_int("LINKLY_CACHE_MAX_ENTRIES", 10_000)
    )

    rate_limit_requests: int = field(
        default_factory=lambda: _env_int("LINKLY_RATE_LIMIT_REQUESTS", 120)
    )
    rate_limit_window_seconds: int = field(
        default_factory=lambda: _env_int("LINKLY_RATE_LIMIT_WINDOW", 60)
    )
