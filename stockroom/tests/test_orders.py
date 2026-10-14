def test_place_order(client, make_product, place_order, carrier):
    make_product(sku="ORD-001", price_cents=1_000, weight_grams=700, initial_stock=10)
    make_product(sku="ORD-002", price_cents=2_500, weight_grams=400, initial_stock=10)

    order = place_order(("ORD-001", 2), ("ORD-002", 1), postcode="10115")

    assert order["subtotal_cents"] == 4_500
    assert order["shipping_cents"] == 549 + 150
    assert order["total_cents"] == 4_500 + 699
    assert order["carrier_service"] == "standard"
    assert [(i["sku"], i["quantity"]) for i in order["items"]] == [("ORD-001", 2), ("ORD-002", 1)]
    assert carrier.calls == [("10115", 1_800)]

    assert client.get("/api/products/ORD-001").json()["on_hand"] == 8
    assert client.get("/api/products/ORD-002").json()["on_hand"] == 9


def test_duplicate_lines_are_merged(client, make_product, place_order):
    make_product(sku="ORD-010", initial_stock=5)
    order = place_order(("ORD-010", 1), ("ORD-010", 2))
    assert [(i["sku"], i["quantity"]) for i in order["items"]] == [("ORD-010", 3)]
    assert client.get("/api/products/ORD-010").json()["on_hand"] == 2


def test_get_order(client, make_product, place_order):
    make_product(sku="ORD-020")
    order = place_order(("ORD-020", 1))

    resp = client.get(f"/api/orders/{order['id']}")
    assert resp.status_code == 200
    assert resp.json() == order


def test_unknown_order_is_404(client):
    assert client.get("/api/orders/999").status_code == 404


def test_unknown_sku_is_rejected(client, make_product, place_order, carrier):
    make_product(sku="ORD-030")
    body = place_order(("ORD-030", 1), ("GHOST-2", 1), ("GHOST-1", 1), expect=422)
    assert body["detail"] == {"error": "unknown_sku", "skus": ["GHOST-1", "GHOST-2"]}
    assert carrier.calls == []


def test_insufficient_stock_writes_nothing(client, make_product, place_order, carrier, conn):
    make_product(sku="ORD-040", initial_stock=5)
    make_product(sku="ORD-041", initial_stock=1)

    body = place_order(("ORD-040", 2), ("ORD-041", 3), expect=409)
    assert body["detail"] == {"error": "insufficient_stock", "sku": "ORD-041", "available": 1}
    assert carrier.calls == []
    assert conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0
    assert client.get("/api/products/ORD-040").json()["on_hand"] == 5


def test_order_validation(client):
    resp = client.post(
        "/api/orders",
        json={"customer_email": "not-an-email", "postcode": "10115", "items": []},
    )
    assert resp.status_code == 422


def test_order_uses_clock(client, make_product, place_order, clock):
    make_product(sku="ORD-050")
    order = place_order(("ORD-050", 1))
    assert order["created_at"].startswith("2025-10-09")
