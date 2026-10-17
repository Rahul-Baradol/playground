from app.services.catalog import FacetsCache
import time
from typing import Callable

from fastapi import FastAPI

from app.carrier import CarrierClient, MockCarrierClient
from app.config import Settings
from app.db import init_db
from app.routes import orders, products, reports


def create_app(
    settings: Settings | None = None,
    carrier: CarrierClient | None = None,
    clock: Callable[[], float] = time.time,
) -> FastAPI:
    settings = settings or Settings()
    init_db(settings.db_path)

    app = FastAPI(title="Stockroom", version="1.4.0")
    app.state.settings = settings
    app.state.carrier = carrier or MockCarrierClient(settings.carrier_latency_ms)
    app.state.clock = clock
    app.state.facets_cache = FacetsCache()

    @app.get("/healthz", tags=["ops"])
    async def healthz() -> dict:
        return {"status": "ok"}

    app.include_router(products.router)
    app.include_router(orders.router)
    app.include_router(reports.router)
    return app

