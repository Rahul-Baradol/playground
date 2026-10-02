from app.repository import Link
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_click_repo, get_link_repo, rate_limit
from app.models import LinkStats
from app.repository import ClickRepository, LinkRepository
from app.services.analytics import AnalyticsService

router = APIRouter(prefix="/api/links", tags=["stats"], dependencies=[Depends(rate_limit)])


@router.get("/{code}/stats", response_model=LinkStats)
def link_stats(
    code: str,
    days: int = Query(30, ge=1, le=365),
    links: LinkRepository = Depends(get_link_repo),
    clicks: ClickRepository = Depends(get_click_repo),
) -> LinkStats:
    link: Link | None = links.get_by_code(code)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    return AnalyticsService(clicks).link_stats(link, days)
