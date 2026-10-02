import time

from app.repository import LinkRepository


def test_redirect_follows_and_records_click(client, make_link, conn):
    make_link("https://example.com/target", alias="go-now")
    resp = client.get(
        "/go-now",
        headers={
            "referer": "https://www.twitter.com/some/post",
            "x-geo-country": "de",
            "user-agent": "pytest-agent",
        },
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/target"

    row = conn.execute("SELECT referrer, country, user_agent FROM clicks").fetchone()
    assert tuple(row) == ("twitter.com", "DE", "pytest-agent")


def test_redirect_unknown_code(client):
    assert client.get("/doesnotexist").status_code == 404


def test_redirect_expired_link(client, conn):
    LinkRepository(conn).create("old", "https://example.com", expires_at=time.time() - 10)
    assert client.get("/old").status_code == 410
    assert conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0] == 0


def test_redirect_uses_cache(client, make_link, conn):
    make_link("https://example.com/original", alias="cached")
    assert client.get("/cached").headers["location"] == "https://example.com/original"

    # Change the row behind the cache's back; cached entry should still win.
    conn.execute("UPDATE links SET target_url = 'https://changed.com' WHERE code = 'cached'")
    conn.commit()
    assert client.get("/cached").headers["location"] == "https://example.com/original"


def test_healthz_not_shadowed_by_redirect(client):
    assert client.get("/healthz").json() == {"status": "ok"}
