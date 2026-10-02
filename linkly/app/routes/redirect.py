import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from app.cache import TTLCache
from app.dependencies import get_cache, get_click_repo, get_link_repo
from app.repository import ClickRepository, LinkRepository
from app.services.analytics import normalize_country, normalize_referrer

router = APIRouter(tags=["redirect"])


@dataclass(frozen=True)
class CachedLink:
    link_id: int
    target_url: str
    expires_at: float | None


@router.get("/{code}", include_in_schema=False)
def follow_link(
    code: str,
    request: Request,
    links: LinkRepository = Depends(get_link_repo),
    clicks: ClickRepository = Depends(get_click_repo),
    cache: TTLCache = Depends(get_cache),
) -> RedirectResponse:
    entry: CachedLink | None = cache.get(code)
    if entry is None:
        link = links.get_by_code(code)
        if link is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
        entry = CachedLink(link.id, link.target_url, link.expires_at)
        cache.set(code, entry)

    if entry.expires_at is not None and entry.expires_at <= time.time():
        raise HTTPException(status.HTTP_410_GONE, detail="Link has expired.")

    clicks.record(
        entry.link_id,
        referrer=normalize_referrer(request.headers.get("referer")),
        user_agent=request.headers.get("user-agent"),
        country=normalize_country(request.headers.get("x-geo-country")),
    )
    return RedirectResponse(entry.target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
