from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    Clock,
    get_catalog_service,
    get_clock,
    get_product_repo,
    get_stock_repo,
)
from app.models import Facets, MovementCreate, ProductCreate, ProductOut
from app.repository import ProductRepository, StockRepository
from app.services.catalog import CatalogService, DuplicateSkuError

router = APIRouter(prefix="/api", tags=["catalog"])


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    catalog: CatalogService = Depends(get_catalog_service),
    clock: Clock = Depends(get_clock),
) -> ProductOut:
    try:
        product = catalog.create_product(
            sku=payload.sku,
            name=payload.name,
            category=payload.category,
            price_cents=payload.price_cents,
            weight_grams=payload.weight_grams,
            lead_time_days=payload.lead_time_days,
            initial_stock=payload.initial_stock,
            now=clock(),
        )
    except DuplicateSkuError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="SKU already exists.")
    return ProductOut.from_product(product, on_hand=payload.initial_stock)


@router.get("/products", response_model=list[ProductOut])
async def list_products(
    category: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    products: ProductRepository = Depends(get_product_repo),
    stock: StockRepository = Depends(get_stock_repo),
) -> list[ProductOut]:
    page = products.list_page(category, limit, offset)
    levels = stock.on_hand_for([p.id for p in page])
    return [ProductOut.from_product(p, levels[p.id]) for p in page]


@router.get("/products/{sku}", response_model=ProductOut)
async def get_product(
    sku: str,
    products: ProductRepository = Depends(get_product_repo),
    stock: StockRepository = Depends(get_stock_repo),
) -> ProductOut:
    product = products.get_by_sku(sku)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Product not found.")
    return ProductOut.from_product(product, stock.on_hand(product.id))


@router.post("/products/{sku}/movements", response_model=ProductOut)
async def record_movement(
    sku: str,
    payload: MovementCreate,
    products: ProductRepository = Depends(get_product_repo),
    catalog: CatalogService = Depends(get_catalog_service),
    clock: Clock = Depends(get_clock),
) -> ProductOut:
    product = products.get_by_sku(sku)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Product not found.")
    on_hand = catalog.adjust_stock(product, payload.delta, payload.reason, clock())
    return ProductOut.from_product(product, on_hand)


@router.get("/catalog/facets", response_model=Facets)
def get_facets(catalog: CatalogService = Depends(get_catalog_service)) -> Facets:
    return catalog.facets()
