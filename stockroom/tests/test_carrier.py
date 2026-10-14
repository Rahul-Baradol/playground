import time

from app.carrier import MockCarrierClient


def test_zones_and_weight_pricing():
    carrier = MockCarrierClient(latency_ms=0)
    assert carrier.quote("40213", 900).price_cents == 399
    assert carrier.quote("40213", 900).service == "express"
    assert carrier.quote("10115", 2_100).price_cents == 549 + 2 * 150
    assert carrier.quote("30159", 1_000).price_cents == 999
    assert carrier.quote("ABC", 1_000).estimated_days == 5


def test_latency_is_simulated():
    carrier = MockCarrierClient(latency_ms=30)
    start = time.perf_counter()
    carrier.quote("10115", 100)
    assert time.perf_counter() - start >= 0.03
