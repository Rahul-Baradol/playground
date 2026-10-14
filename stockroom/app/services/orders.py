from collections import Counter

from app.carrier import CarrierClient
from app.repository import (
    Order,
    OrderLine,
    OrderRepository,
    ProductRepository,
    StockRepository,
)


class UnknownSkuError(Exception):
    def __init__(self, skus: list[str]):
        super().__init__(", ".join(skus))
        self.skus = skus


class InsufficientStockError(Exception):
    def __init__(self, sku: str, requested: int, available: int):
        super().__init__(f"{sku}: requested {requested}, available {available}")
        self.sku = sku
        self.requested = requested
        self.available = available


class OrderService:
    def __init__(
        self,
        products: ProductRepository,
        stock: StockRepository,
        orders: OrderRepository,
        carrier: CarrierClient,
    ):
        self.products = products
        self.stock = stock
        self.orders = orders
        self.carrier = carrier

    def place_order(
        self,
        customer_email: str,
        postcode: str,
        items: list[tuple[str, int]],
        now: float,
    ) -> Order:
        quantities: Counter[str] = Counter()
        for sku, quantity in items:
            quantities[sku] += quantity

        products = self.products.get_many_by_sku(list(quantities))
        missing = sorted(sku for sku in quantities if sku not in products)
        if missing:
            raise UnknownSkuError(missing)

        levels = self.stock.on_hand_for([p.id for p in products.values()])
        for sku, quantity in quantities.items():
            available = levels[products[sku].id]
            if available < quantity:
                raise InsufficientStockError(sku, quantity, available)

        weight = sum(products[sku].weight_grams * qty for sku, qty in quantities.items())
        quote = self.carrier.quote(postcode, weight)

        lines = [
            OrderLine(products[sku].id, sku, qty, products[sku].price_cents)
            for sku, qty in quantities.items()
        ]
        return self.orders.create(
            customer_email=customer_email,
            postcode=postcode,
            lines=lines,
            shipping_cents=quote.price_cents,
            carrier_service=quote.service,
            created_at=now,
        )
