import threading
import time
from collections import defaultdict
from typing import Callable


class SlidingWindowRateLimiter:
    """Allows at most `max_requests` per `window_seconds` for each key."""

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            recent = [t for t in hits if now - t < self.window_seconds]
            if len(recent) >= self.max_requests:
                return False
            hits.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            recent = [t for t in self._hits.get(key, []) if now - t < self.window_seconds]
            return max(0, self.max_requests - len(recent))
