import pytest
from fastapi.testclient import TestClient

from app.carrier import MockCarrierClient, ShippingQuote
from app.config import Settings
from app.db import connect
from app.main import create_app

DAY = 86_400
T0 = 1_760_000_000.0


class FakeClock:
    def __init__(self, start: float = T0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class RecordingCarrier(MockCarrierClient):
    def __init__(self):
        super().__init__(latency_ms=0)
        self.calls: list[tuple[str, int]] = []

    def quote(self, postcode: str, weight_grams: int) -> ShippingQuote:
        self.calls.append((postcode, weight_grams))
        return super().quote(postcode, weight_grams)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def carrier() -> RecordingCarrier:
    return RecordingCarrier()


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(db_path=str(tmp_path / "test.db"), carrier_latency_ms=0)


@pytest.fixture
def app(settings, carrier, clock):
    return create_app(settings, carrier=carrier, clock=clock)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app) as c:
        yield c


@pytest.fixture
def conn(settings, client):
    # Depends on `client` so the schema exists before we connect.
    c = connect(settings.db_path)
    yield c
    c.close()


@pytest.fixture
def make_product(client):
    counter = iter(range(1, 10_000))

    def _make(**overrides) -> dict:
        payload = {
            "sku": f"SKU-{next(counter):04d}",
            "name": "Test product",
            "category": "tools",
            "price_cents": 1_999,
            "weight_grams": 500,
            "lead_time_days": 7,
            "initial_stock": 100,
            **overrides,
        }
        resp = client.post("/api/products", json=payload)
        assert resp.status_code == 201, resp.text
        return resp.json()

    return _make


@pytest.fixture
def place_order(client):
    def _place(*items: tuple[str, int], postcode: str = "10115", expect: int = 201) -> dict:
        resp = client.post(
            "/api/orders",
            json={
                "customer_email": "buyer@example.com",
                "postcode": postcode,
                "items": [{"sku": sku, "quantity": qty} for sku, qty in items],
            },
        )
        assert resp.status_code == expect, resp.text
        return resp.json()

    return _place
