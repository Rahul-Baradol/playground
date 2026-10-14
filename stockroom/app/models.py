from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.repository import Order, Product


class ProductCreate(BaseModel):
    sku: str = Field(pattern=r"^[A-Z0-9-]{3,32}$")
    name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=64)
    price_cents: int = Field(gt=0)
    weight_grams: int = Field(gt=0)
    lead_time_days: int = Field(ge=0, le=180)
    initial_stock: int = Field(default=0, ge=0)


class ProductOut(BaseModel):
    sku: str
    name: str
    category: str
    price_cents: int
    weight_grams: int
    lead_time_days: int
    on_hand: int
    created_at: datetime

    @classmethod
    def from_product(cls, product: Product, on_hand: int) -> "ProductOut":
        return cls(
            sku=product.sku,
            name=product.name,
            category=product.category,
            price_cents=product.price_cents,
            weight_grams=product.weight_grams,
            lead_time_days=product.lead_time_days,
            on_hand=on_hand,
            created_at=to_dt(product.created_at),
        )


class MovementCreate(BaseModel):
    delta: int = Field(description="Positive to add stock, negative to remove it.")
    reason: Literal["receipt", "adjustment"]


class OrderLineIn(BaseModel):
    sku: str
    quantity: int = Field(gt=0, le=1_000)


class OrderCreate(BaseModel):
    customer_email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    postcode: str = Field(min_length=3, max_length=12)
    items: list[OrderLineIn] = Field(min_length=1, max_length=50)


class OrderLineOut(BaseModel):
    sku: str
    quantity: int
    unit_price_cents: int


class OrderOut(BaseModel):
    id: int
    customer_email: str
    postcode: str
    items: list[OrderLineOut]
    subtotal_cents: int
    shipping_cents: int
    total_cents: int
    carrier_service: str
    created_at: datetime

    @classmethod
    def from_order(cls, order: Order) -> "OrderOut":
        return cls(
            id=order.id,
            customer_email=order.customer_email,
            postcode=order.postcode,
            items=[
                OrderLineOut(sku=l.sku, quantity=l.quantity, unit_price_cents=l.unit_price_cents)
                for l in order.lines
            ],
            subtotal_cents=order.subtotal_cents,
            shipping_cents=order.shipping_cents,
            total_cents=order.subtotal_cents + order.shipping_cents,
            carrier_service=order.carrier_service,
            created_at=to_dt(order.created_at),
        )


class CategoryFacet(BaseModel):
    category: str
    products: int
    in_stock: int


class PriceBucket(BaseModel):
    label: str
    min_cents: int
    max_cents: int | None
    products: int


class Facets(BaseModel):
    total_products: int
    in_stock_products: int
    categories: list[CategoryFacet]
    price_buckets: list[PriceBucket]


class ReorderSuggestion(BaseModel):
    sku: str
    name: str
    on_hand: int
    units_sold: int
    daily_rate: float
    days_of_cover: float
    lead_time_days: int
    suggested_quantity: int
    last_sold_at: datetime


class ReorderReport(BaseModel):
    generated_at: datetime
    window_days: int
    suggestions: list[ReorderSuggestion]


def to_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)
