from collections import deque
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
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        hits = self._hits.get(key)
        if hits is None:
            return deque()
        while len(hits) > 0 and (now - hits[0]) >= self.window_seconds:
            hits.popleft()
        if len(hits) == 0:
            del self._hits[key]
        return hits

    def allow(self, key: str) -> bool:
        now = self._clock()
        with self._lock:
            hits = self._prune(key, now)
            if len(hits) >= self.max_requests:
                return False
            if len(hits) == 0:
                self._hits[key] = hits
            hits.append(now)
            return True

    def remaining(self, key: str) -> int:
        now = self._clock()
        with self._lock:
            current = self._prune(key, now)
            return max(0, self.max_requests - len(current))
