def test_create_link_generates_code(client, make_link):
    link = make_link("https://example.com/hello")
    assert len(link["code"]) == 7
    assert link["short_url"] == f"http://lnk.test/{link['code']}"
    assert link["target_url"] == "https://example.com/hello"
    assert link["total_clicks"] == 0
    assert link["expires_at"] is None


def test_create_link_with_alias(make_link):
    link = make_link(alias="launch-day")
    assert link["code"] == "launch-day"


def test_duplicate_alias_conflicts(client, make_link):
    make_link(alias="taken")
    resp = client.post("/api/links", json={"url": "https://other.com", "alias": "taken"})
    assert resp.status_code == 409


def test_reserved_alias_rejected(client):
    resp = client.post("/api/links", json={"url": "https://x.com", "alias": "healthz"})
    assert resp.status_code == 409


def test_invalid_url_rejected(client):
    resp = client.post("/api/links", json={"url": "not a url"})
    assert resp.status_code == 422


def test_invalid_alias_rejected(client):
    resp = client.post("/api/links", json={"url": "https://x.com", "alias": "has space"})
    assert resp.status_code == 422


def test_expiring_link_has_expiry(make_link):
    link = make_link(expires_in_seconds=3600)
    assert link["expires_at"] is not None


def test_get_link(client, make_link):
    created = make_link(alias="abc123")
    resp = client.get("/api/links/abc123")
    assert resp.status_code == 200
    assert resp.json()["target_url"] == created["target_url"]


def test_get_missing_link(client):
    assert client.get("/api/links/nope").status_code == 404


def test_list_links_newest_first_with_click_counts(client, make_link):
    make_link("https://a.com", alias="aaa")
    make_link("https://b.com", alias="bbb")
    make_link("https://c.com", alias="ccc")
    for _ in range(3):
        client.get("/aaa")
    client.get("/ccc")

    resp = client.get("/api/links")
    assert resp.status_code == 200
    body = resp.json()
    assert [l["code"] for l in body] == ["ccc", "bbb", "aaa"]
    assert {l["code"]: l["total_clicks"] for l in body} == {"aaa": 3, "bbb": 0, "ccc": 1}


def test_list_links_pagination(client, make_link):
    for i in range(5):
        make_link(alias=f"page{i}")
    first = client.get("/api/links", params={"limit": 2}).json()
    second = client.get("/api/links", params={"limit": 2, "offset": 2}).json()
    assert [l["code"] for l in first] == ["page4", "page3"]
    assert [l["code"] for l in second] == ["page2", "page1"]


def test_list_links_limit_validation(client):
    assert client.get("/api/links", params={"limit": 0}).status_code == 422
    assert client.get("/api/links", params={"limit": 501}).status_code == 422


def test_delete_link_removes_clicks_and_redirect(client, make_link, conn):
    make_link(alias="gone")
    client.get("/gone")  # populates the redirect cache
    assert client.delete("/api/links/gone").status_code == 204

    assert client.get("/api/links/gone").status_code == 404
    assert client.get("/gone").status_code == 404
    assert conn.execute("SELECT COUNT(*) FROM clicks").fetchone()[0] == 0


def test_delete_missing_link(client):
    assert client.delete("/api/links/missing").status_code == 404
