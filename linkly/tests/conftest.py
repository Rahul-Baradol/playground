import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import connect
from app.main import create_app


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        db_path=str(tmp_path / "test.db"),
        base_url="http://lnk.test",
        rate_limit_requests=1_000,
        rate_limit_window_seconds=60,
    )


@pytest.fixture
def client(settings) -> TestClient:
    with TestClient(create_app(settings), follow_redirects=False) as c:
        yield c


@pytest.fixture
def conn(settings, client):
    # Depends on `client` so the schema exists before we connect.
    c = connect(settings.db_path)
    yield c
    c.close()


@pytest.fixture
def make_link(client):
    def _make(url: str = "https://example.com/page", **extra) -> dict:
        resp = client.post("/api/links", json={"url": url, **extra})
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make
