from collections import Counter
from functools import lru_cache

from app.models import CategoryFacet, Facets, PriceBucket
from app.repository import Product, ProductRepository, StockRepository


class DuplicateSkuError(Exception):
    pass


class CatalogService:
    def __init__(
        self,
        products: ProductRepository,
        stock: StockRepository,
        price_bucket_edges_cents: tuple[int, ...],
    ):
        self.products = products
        self.stock = stock
        self.price_bucket_edges_cents = price_bucket_edges_cents

    def create_product(
        self,
        sku: str,
        name: str,
        category: str,
        price_cents: int,
        weight_grams: int,
        lead_time_days: int,
        initial_stock: int,
        now: float,
    ) -> Product:
        if self.products.sku_exists(sku):
            raise DuplicateSkuError(sku)
        product = self.products.create(
            sku, name, category, price_cents, weight_grams, lead_time_days, now
        )
        if initial_stock:
            self.stock.record(product.id, initial_stock, "receipt", now)
        self.invalidate()
        return product

    def adjust_stock(self, product: Product, delta: int, reason: str, now: float) -> int:
        self.stock.record(product.id, delta, reason, now)
        self.invalidate()
        return self.stock.on_hand(product.id)

    @lru_cache(maxsize=1)
    def facets(self) -> Facets:
        products = self.products.list_all()
        on_hand = self.stock.on_hand_all()

        categories: dict[str, list[Product]] = {}
        for product in products:
            categories.setdefault(product.category, []).append(product)

        category_facets = [
            CategoryFacet(
                category=name,
                products=len(members),
                in_stock=sum(1 for p in members if on_hand.get(p.id, 0) > 0),
            )
            for name, members in sorted(categories.items())
        ]

        bucket_counts = Counter(self._bucket_index(p.price_cents) for p in products)
        return Facets(
            total_products=len(products),
            in_stock_products=sum(1 for p in products if on_hand.get(p.id, 0) > 0),
            categories=category_facets,
            price_buckets=[
                PriceBucket(label=label, min_cents=lo, max_cents=hi, products=bucket_counts[i])
                for i, (label, lo, hi) in enumerate(self._buckets())
            ],
        )

    def invalidate(self) -> None:
        self.facets.cache_clear()

    def _buckets(self) -> list[tuple[str, int, int | None]]:
        edges = self.price_bucket_edges_cents
        bounds = [0, *edges]
        buckets = []
        for i, lo in enumerate(bounds):
            hi = edges[i] if i < len(edges) else None
            label = f"${lo // 100}+" if hi is None else f"${lo // 100}-${hi // 100}"
            buckets.append((label, lo, hi))
        return buckets

    def _bucket_index(self, price_cents: int) -> int:
        for i, edge in enumerate(self.price_bucket_edges_cents):
            if price_cents < edge:
                return i
        return len(self.price_bucket_edges_cents)
