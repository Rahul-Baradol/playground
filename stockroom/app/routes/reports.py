from fastapi import APIRouter, Depends

from app.dependencies import Clock, get_clock, get_reorder_service
from app.models import ReorderReport
from app.services.reports import ReorderService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/reorder", response_model=ReorderReport)
async def reorder_report(
    service: ReorderService = Depends(get_reorder_service),
    clock: Clock = Depends(get_clock),
) -> ReorderReport:
    return service.report(now=clock())
