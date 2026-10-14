def facets(client) -> dict:
    resp = client.get("/api/catalog/facets")
    assert resp.status_code == 200
    return resp.json()


def test_empty_catalog(client):
    body = facets(client)
    assert body["total_products"] == 0
    assert body["categories"] == []
    assert all(b["products"] == 0 for b in body["price_buckets"])


def test_category_and_stock_counts(client, make_product):
    make_product(category="audio", initial_stock=3)
    make_product(category="audio", initial_stock=0)
    make_product(category="tools", initial_stock=1)

    body = facets(client)
    assert body["total_products"] == 3
    assert body["in_stock_products"] == 2
    assert body["categories"] == [
        {"category": "audio", "products": 2, "in_stock": 1},
        {"category": "tools", "products": 1, "in_stock": 1},
    ]


def test_price_buckets(client, make_product):
    for price in (500, 999, 1_000, 4_999, 30_000):
        make_product(price_cents=price)

    buckets = {b["label"]: b["products"] for b in facets(client)["price_buckets"]}
    assert buckets == {
        "$0-$10": 2,
        "$10-$25": 1,
        "$25-$50": 1,
        "$50-$100": 0,
        "$100-$250": 0,
        "$250+": 1,
    }


def test_facets_reflect_new_products(client, make_product):
    make_product(category="audio")
    assert facets(client)["total_products"] == 1

    make_product(category="kitchen")
    body = facets(client)
    assert body["total_products"] == 2
    assert [c["category"] for c in body["categories"]] == ["audio", "kitchen"]


def test_facets_reflect_stock_changes(client, make_product, place_order):
    make_product(sku="FAC-001", initial_stock=2)
    assert facets(client)["in_stock_products"] == 1

    place_order(("FAC-001", 2))
    assert facets(client)["in_stock_products"] == 0

    client.post("/api/products/FAC-001/movements", json={"delta": 5, "reason": "receipt"})
    assert facets(client)["in_stock_products"] == 1
