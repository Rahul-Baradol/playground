from app.services.catalog import FacetsCache
import sqlite3
from typing import Callable, Iterator

from fastapi import Depends, Request

from app.carrier import CarrierClient
from app.config import Settings
from app.db import connect
from app.repository import OrderRepository, ProductRepository, StockRepository
from app.services.catalog import CatalogService
from app.services.orders import OrderService
from app.services.reports import ReorderService

Clock = Callable[[], float]


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_clock(request: Request) -> Clock:
    return request.app.state.clock


def get_carrier(request: Request) -> CarrierClient:
    return request.app.state.carrier


def get_conn(settings: Settings = Depends(get_settings)) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.db_path)
    try:
        yield conn
    finally:
        conn.close()


def get_product_repo(conn: sqlite3.Connection = Depends(get_conn)) -> ProductRepository:
    return ProductRepository(conn)


def get_stock_repo(conn: sqlite3.Connection = Depends(get_conn)) -> StockRepository:
    return StockRepository(conn)


def get_order_repo(conn: sqlite3.Connection = Depends(get_conn)) -> OrderRepository:
    return OrderRepository(conn)

def get_facets_cache(request: Request) -> FacetsCache:
    return request.app.state.facets_cache

def get_catalog_service(
    products: ProductRepository = Depends(get_product_repo),
    stock: StockRepository = Depends(get_stock_repo),
    settings: Settings = Depends(get_settings),
    facets_cache: FacetsCache = Depends(get_facets_cache),
) -> CatalogService:
    return CatalogService(products, stock, settings.price_bucket_edges_cents, facets_cache)


def get_order_service(
    products: ProductRepository = Depends(get_product_repo),
    stock: StockRepository = Depends(get_stock_repo),
    orders: OrderRepository = Depends(get_order_repo),
    carrier: CarrierClient = Depends(get_carrier),
) -> OrderService:
    return OrderService(products, stock, orders, carrier)


def get_reorder_service(
    products: ProductRepository = Depends(get_product_repo),
    stock: StockRepository = Depends(get_stock_repo),
    settings: Settings = Depends(get_settings),
) -> ReorderService:
    return ReorderService(products, stock, settings.sales_window_days, settings.safety_stock_days)
