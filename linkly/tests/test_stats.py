import time
from datetime import datetime, timedelta, timezone

from app.repository import ClickRepository, LinkRepository
from app.services.analytics import AnalyticsService, normalize_country, normalize_referrer

DAY = 86_400


def test_normalize_referrer():
    assert normalize_referrer("https://www.Google.com/search?q=x") == "google.com"
    assert normalize_referrer("") is None
    assert normalize_referrer(None) is None
    assert normalize_referrer("garbage") is None


def test_normalize_country():
    assert normalize_country(" us ") == "US"
    assert normalize_country("USA") is None
    assert normalize_country(None) is None


def test_link_stats_aggregates(conn):
    links, clicks = LinkRepository(conn), ClickRepository(conn)
    link = links.create("stat", "https://example.com")
    other = links.create("other", "https://example.org")

    now = datetime(2026, 3, 10, 12, 0, tzinfo=timezone.utc).timestamp()
    clicks.record(link.id, referrer="t.co", country="US", clicked_at=now)
    clicks.record(link.id, referrer="t.co", country="US", clicked_at=now - 60)
    clicks.record(link.id, referrer="google.com", country="FR", clicked_at=now - 2 * DAY)
    clicks.record(link.id, referrer=None, country=None, clicked_at=now - 40 * DAY)
    clicks.record(other.id, referrer="t.co", country="US", clicked_at=now)

    stats = AnalyticsService(clicks).link_stats(link, days=7, now=now)

    assert stats.total_clicks == 4
    assert stats.clicks_in_window == 3
    assert len(stats.daily) == 7
    assert stats.daily[-1].date == "2026-03-10"
    assert stats.daily[-1].clicks == 2
    assert stats.daily[-3].clicks == 1
    assert sum(d.clicks for d in stats.daily) == 3
    assert [(t.value, t.clicks) for t in stats.top_referrers] == [("t.co", 2), ("google.com", 1)]
    assert [(t.value, t.clicks) for t in stats.top_countries] == [("US", 2), ("FR", 1)]


def test_stats_endpoint(client, make_link):
    make_link(alias="stat-1")
    client.get("/stat-1", headers={"referer": "https://news.ycombinator.com/item?id=1"})
    client.get("/stat-1", headers={"x-geo-country": "IN"})

    resp = client.get("/api/links/stat-1/stats", params={"days": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_clicks"] == 2
    assert body["window_days"] == 3
    assert len(body["daily"]) == 3
    assert body["daily"][-1]["date"] == datetime.now(timezone.utc).date().isoformat()
    assert body["top_referrers"] == [{"value": "news.ycombinator.com", "clicks": 1}]
    assert body["top_countries"] == [{"value": "IN", "clicks": 1}]


def test_stats_missing_link(client):
    assert client.get("/api/links/nope/stats").status_code == 404


def test_stats_days_validation(client, make_link):
    make_link(alias="stat-2")
    assert client.get("/api/links/stat-2/stats", params={"days": 0}).status_code == 422
    assert client.get("/api/links/stat-2/stats", params={"days": 366}).status_code == 422
