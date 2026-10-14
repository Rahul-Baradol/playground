def test_create_and_get_product(client, make_product):
    created = make_product(sku="DRL-001", name="Cordless Drill", initial_stock=12)
    assert created["sku"] == "DRL-001"
    assert created["on_hand"] == 12

    resp = client.get("/api/products/DRL-001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Cordless Drill"
    assert body["on_hand"] == 12


def test_duplicate_sku_is_rejected(client, make_product):
    make_product(sku="DUP-001")
    resp = client.post(
        "/api/products",
        json={"sku": "DUP-001", "name": "x", "category": "tools", "price_cents": 100,
              "weight_grams": 10, "lead_time_days": 1},
    )
    assert resp.status_code == 409


def test_invalid_product_payload(client):
    resp = client.post(
        "/api/products",
        json={"sku": "lower-case", "name": "x", "category": "tools", "price_cents": 0,
              "weight_grams": 10, "lead_time_days": 1},
    )
    assert resp.status_code == 422


def test_unknown_product_is_404(client):
    assert client.get("/api/products/NOPE-1").status_code == 404


def test_list_products_filters_and_paginates(client, make_product):
    for _ in range(3):
        make_product(category="audio")
    for _ in range(2):
        make_product(category="tools", initial_stock=0)

    audio = client.get("/api/products", params={"category": "audio"}).json()
    assert [p["category"] for p in audio] == ["audio"] * 3

    tools = client.get("/api/products", params={"category": "tools"}).json()
    assert [p["on_hand"] for p in tools] == [0, 0]

    page = client.get("/api/products", params={"limit": 2, "offset": 1}).json()
    assert [p["sku"] for p in page] == ["SKU-0002", "SKU-0003"]


def test_stock_movements_change_on_hand(client, make_product):
    make_product(sku="MOV-001", initial_stock=5)

    resp = client.post("/api/products/MOV-001/movements", json={"delta": 20, "reason": "receipt"})
    assert resp.status_code == 200
    assert resp.json()["on_hand"] == 25

    resp = client.post("/api/products/MOV-001/movements", json={"delta": -3, "reason": "adjustment"})
    assert resp.json()["on_hand"] == 22
    assert client.get("/api/products/MOV-001").json()["on_hand"] == 22


def test_sale_is_not_an_allowed_manual_movement(client, make_product):
    make_product(sku="MOV-002")
    resp = client.post("/api/products/MOV-002/movements", json={"delta": -1, "reason": "sale"})
    assert resp.status_code == 422


def test_movement_for_unknown_product_is_404(client):
    resp = client.post("/api/products/NOPE-1/movements", json={"delta": 1, "reason": "receipt"})
    assert resp.status_code == 404
