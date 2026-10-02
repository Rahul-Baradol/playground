import pytest
from fastapi.testclient import TestClient

from app.cache import TTLCache
from app.config import Settings
from app.main import create_app
from app.rate_limit import SlidingWindowRateLimiter


class FakeClock:
    def __init__(self, start: float = 1_000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- TTLCache ---------------------------------------------------------------


def test_cache_get_set():
    cache = TTLCache(max_entries=10, ttl_seconds=60)
    cache.set("a", 1)
    assert cache.get("a") == 1
    assert cache.get("missing") is None


def test_cache_entries_expire():
    clock = FakeClock()
    cache = TTLCache(max_entries=10, ttl_seconds=5, clock=clock)
    cache.set("a", 1)
    clock.advance(4.9)
    assert cache.get("a") == 1
    clock.advance(0.2)
    assert cache.get("a") is None
    assert len(cache) == 0


def test_cache_evicts_least_recently_used():
    cache = TTLCache(max_entries=2, ttl_seconds=60)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.get("a")  # 'b' is now least recently used
    cache.set("c", 3)
    assert cache.get("b") is None
    assert cache.get("a") == 1
    assert cache.get("c") == 3


def test_cache_rejects_bad_size():
    with pytest.raises(ValueError):
        TTLCache(max_entries=0, ttl_seconds=1)


# --- SlidingWindowRateLimiter ----------------------------------------------


def test_rate_limiter_blocks_after_limit():
    limiter = SlidingWindowRateLimiter(3, 10, clock=FakeClock())
    assert [limiter.allow("ip") for _ in range(4)] == [True, True, True, False]
    assert limiter.remaining("ip") == 0


def test_rate_limiter_keys_are_independent():
    limiter = SlidingWindowRateLimiter(1, 10, clock=FakeClock())
    assert limiter.allow("a")
    assert limiter.allow("b")
    assert not limiter.allow("a")


def test_rate_limiter_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowRateLimiter(2, 10, clock=clock)
    assert limiter.allow("ip")
    clock.advance(6)
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    clock.advance(4)  # first hit is now exactly 10s old -> outside window
    assert limiter.allow("ip")
    assert not limiter.allow("ip")
    assert limiter.remaining("ip") == 0
    clock.advance(10)
    assert limiter.remaining("ip") == 2


def test_api_returns_429_when_limited(tmp_path):
    settings = Settings(db_path=str(tmp_path / "rl.db"), rate_limit_requests=2)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/links").status_code == 200
        assert client.get("/api/links").status_code == 200
        resp = client.get("/api/links")
        assert resp.status_code == 429
        assert resp.headers["retry-after"] == "60"
        # Redirects are not rate limited.
        assert client.get("/healthz").status_code == 200
