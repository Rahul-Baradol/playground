from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import (
    Clock,
    get_catalog_service,
    get_clock,
    get_order_repo,
    get_order_service,
)
from app.models import OrderCreate, OrderOut
from app.repository import OrderRepository
from app.services.catalog import CatalogService
from app.services.orders import InsufficientStockError, OrderService, UnknownSkuError

router = APIRouter(prefix="/api/orders", tags=["orders"])


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    orders: OrderService = Depends(get_order_service),
    catalog: CatalogService = Depends(get_catalog_service),
    clock: Clock = Depends(get_clock),
) -> OrderOut:
    try:
        order = orders.place_order(
            customer_email=payload.customer_email,
            postcode=payload.postcode,
            items=[(item.sku, item.quantity) for item in payload.items],
            now=clock(),
        )
    except UnknownSkuError as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"error": "unknown_sku", "skus": exc.skus},
        )
    except InsufficientStockError as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={"error": "insufficient_stock", "sku": exc.sku, "available": exc.available},
        )
    catalog.invalidate()
    return OrderOut.from_order(order)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: int,
    orders: OrderRepository = Depends(get_order_repo),
) -> OrderOut:
    order = orders.get(order_id)
    if order is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Order not found.")
    return OrderOut.from_order(order)
