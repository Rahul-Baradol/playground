from tests.conftest import DAY


def report(client) -> dict:
    resp = client.get("/api/reports/reorder")
    assert resp.status_code == 200
    return resp.json()


def sell(place_order, clock, sku: str, qty: int, days_ago: float) -> None:
    now = clock.now
    clock.now = now - days_ago * DAY
    place_order((sku, qty))
    clock.now = now


def test_empty_report(client):
    body = report(client)
    assert body["window_days"] == 30
    assert body["suggestions"] == []


def test_fast_seller_with_low_cover_is_flagged(client, make_product, place_order, clock):
    make_product(sku="REP-001", name="Hot item", lead_time_days=10, initial_stock=40)
    sell(place_order, clock, "REP-001", 15, days_ago=20)
    sell(place_order, clock, "REP-001", 15, days_ago=2)

    [s] = report(client)["suggestions"]
    # 30 units in 30 days -> 1/day; 10 left covers 10 days < 10 lead + 7 safety.
    assert s["sku"] == "REP-001"
    assert s["name"] == "Hot item"
    assert s["on_hand"] == 10
    assert s["units_sold"] == 30
    assert s["daily_rate"] == 1.0
    assert s["days_of_cover"] == 10.0
    assert s["lead_time_days"] == 10
    assert s["suggested_quantity"] == (10 + 7 + 30) - 10
    assert s["last_sold_at"].startswith("2025-10-07")


def test_well_stocked_and_unsold_products_are_skipped(client, make_product, place_order, clock):
    make_product(sku="REP-010", lead_time_days=5, initial_stock=500)
    make_product(sku="REP-011", lead_time_days=5, initial_stock=0)
    sell(place_order, clock, "REP-010", 30, days_ago=3)

    assert report(client)["suggestions"] == []


def test_sales_outside_window_are_ignored(client, make_product, place_order, clock):
    make_product(sku="REP-020", lead_time_days=30, initial_stock=100)
    sell(place_order, clock, "REP-020", 95, days_ago=45)
    assert report(client)["suggestions"] == []

    sell(place_order, clock, "REP-020", 3, days_ago=1)
    [s] = report(client)["suggestions"]
    assert s["units_sold"] == 3
    assert s["on_hand"] == 2


def test_suggestions_sorted_by_cover(client, make_product, place_order, clock):
    for sku, stock in (("REP-A", 12), ("REP-B", 11), ("REP-C", 14)):
        make_product(sku=sku, lead_time_days=14, initial_stock=stock)
        sell(place_order, clock, sku, 10, days_ago=5)

    skus = [s["sku"] for s in report(client)["suggestions"]]
    assert skus == ["REP-B", "REP-A", "REP-C"]


def test_report_uses_each_products_own_sales(client, make_product, place_order, clock):
    make_product(sku="REP-X", lead_time_days=30, initial_stock=12)
    make_product(sku="REP-Y", lead_time_days=30, initial_stock=2)
    sell(place_order, clock, "REP-X", 10, days_ago=4)
    sell(place_order, clock, "REP-Y", 1, days_ago=8)

    by_sku = {s["sku"]: s for s in report(client)["suggestions"]}
    assert by_sku["REP-X"]["units_sold"] == 10
    assert by_sku["REP-Y"]["units_sold"] == 1
    assert by_sku["REP-Y"]["last_sold_at"].startswith("2025-10-01")
