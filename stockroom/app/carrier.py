"""Shipping-rate client.

`MockCarrierClient` stands in for the carrier's HTTP rate API so the app runs
offline. It sleeps for `latency_ms` to mimic a network round-trip. A real client
only needs to provide the same `quote()` method.
"""

import time
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ShippingQuote:
    service: str
    price_cents: int
    estimated_days: int


class CarrierClient(Protocol):
    def quote(self, postcode: str, weight_grams: int) -> ShippingQuote: ...


class CarrierUnavailableError(Exception):
    pass


_ZONE_BASE_CENTS = {"A": 399, "B": 549, "C": 749, "D": 999}
_ZONE_DAYS = {"A": 1, "B": 2, "C": 3, "D": 5}


class MockCarrierClient:
    def __init__(self, latency_ms: int = 120):
        self.latency_ms = latency_ms

    def quote(self, postcode: str, weight_grams: int) -> ShippingQuote:
        if self.latency_ms:
            time.sleep(self.latency_ms / 1000)
        zone = self._zone_for(postcode)
        per_kg = 150 if zone in ("A", "B") else 250
        kilos = max(1, -(-weight_grams // 1000))
        price = _ZONE_BASE_CENTS[zone] + per_kg * (kilos - 1)
        service = "express" if zone == "A" else "standard"
        return ShippingQuote(service=service, price_cents=price, estimated_days=_ZONE_DAYS[zone])

    @staticmethod
    def _zone_for(postcode: str) -> str:
        digits = "".join(ch for ch in postcode if ch.isdigit())
        if not digits:
            return "D"
        return "ABCD"[int(digits[0]) % 4]
