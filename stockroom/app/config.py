import os
from dataclasses import dataclass, field


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    db_path: str = field(default_factory=lambda: os.getenv("STOCKROOM_DB_PATH", "stockroom.db"))

    carrier_latency_ms: int = field(
        default_factory=lambda: _env_int("STOCKROOM_CARRIER_LATENCY_MS", 120)
    )

    sales_window_days: int = 30
    safety_stock_days: int = 7
    price_bucket_edges_cents: tuple[int, ...] = (1_000, 2_500, 5_000, 10_000, 25_000)
