import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from app.models import DailyCount, LinkStats, TopItem
from app.repository import ClickRepository, Link

SECONDS_PER_DAY = 86_400


def normalize_referrer(referrer: str | None) -> str | None:
    """Reduce a full referrer URL to its host, e.g. 'https://t.co/abc' -> 't.co'."""
    if not referrer:
        return None
    host = urlparse(referrer).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or None


def normalize_country(country: str | None) -> str | None:
    if not country:
        return None
    country = country.strip().upper()
    return country if len(country) == 2 and country.isalpha() else None


class AnalyticsService:
    def __init__(self, clicks: ClickRepository):
        self.clicks = clicks

    def link_stats(self, link: Link, days: int, now: float | None = None) -> LinkStats:
        now = now if now is not None else time.time()
        today = datetime.fromtimestamp(now, tz=timezone.utc).date()
        first_day = today - timedelta(days=days - 1)
        since = datetime(
            first_day.year, first_day.month, first_day.day, tzinfo=timezone.utc
        ).timestamp()

        counts = self.clicks.daily_counts(link.id, since)
        daily = [
            DailyCount(date=d.isoformat(), clicks=counts.get(d.isoformat(), 0))
            for d in (first_day + timedelta(days=i) for i in range(days))
        ]

        return LinkStats(
            code=link.code,
            total_clicks=self.clicks.count_for_link(link.id),
            window_days=days,
            clicks_in_window=sum(c.clicks for c in daily),
            daily=daily,
            top_referrers=[
                TopItem(value=v, clicks=n)
                for v, n in self.clicks.top_values(link.id, "referrer", since)
            ],
            top_countries=[
                TopItem(value=v, clicks=n)
                for v, n in self.clicks.top_values(link.id, "country", since)
            ],
        )
