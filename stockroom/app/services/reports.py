import math

from app.models import ReorderReport, ReorderSuggestion, to_dt
from app.repository import ProductRepository, StockRepository

SECONDS_PER_DAY = 86_400


class ReorderService:
    """Flags products that will run out before a new delivery could arrive.

    A product needs reordering when its stock on hand covers fewer days of sales
    than its supplier lead time plus a safety margin. The suggested quantity
    restores cover for the lead time, the safety margin and one more sales window.
    """

    def __init__(
        self,
        products: ProductRepository,
        stock: StockRepository,
        window_days: int,
        safety_days: int,
    ):
        self.products = products
        self.stock = stock
        self.window_days = window_days
        self.safety_days = safety_days

    def report(self, now: float) -> ReorderReport:
        since = now - self.window_days * SECONDS_PER_DAY
        products = self.products.list_all()
        on_hand = self.stock.on_hand_all()
        sales = self.stock.sales_since(since)

        suggestions = []
        for product in products:
            product_sales = [m for m in sales if m.product_id == product.id]
            if not product_sales:
                continue

            units_sold = -sum(m.delta for m in product_sales)
            daily_rate = units_sold / self.window_days
            stock = max(on_hand.get(product.id, 0), 0)
            days_of_cover = stock / daily_rate
            horizon = product.lead_time_days + self.safety_days
            if days_of_cover >= horizon:
                continue

            target = math.ceil(daily_rate * (horizon + self.window_days))
            suggestions.append(
                ReorderSuggestion(
                    sku=product.sku,
                    name=product.name,
                    on_hand=stock,
                    units_sold=units_sold,
                    daily_rate=round(daily_rate, 3),
                    days_of_cover=round(days_of_cover, 1),
                    lead_time_days=product.lead_time_days,
                    suggested_quantity=max(target - stock, 0),
                    last_sold_at=to_dt(max(m.created_at for m in product_sales)),
                )
            )

        suggestions.sort(key=lambda s: (s.days_of_cover, s.sku))
        return ReorderReport(
            generated_at=to_dt(now), window_days=self.window_days, suggestions=suggestions
        )
