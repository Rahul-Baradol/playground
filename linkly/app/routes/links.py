from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.cache import TTLCache
from app.config import Settings
from app.dependencies import (
    get_cache,
    get_click_repo,
    get_link_repo,
    get_settings,
    rate_limit,
)
from app.models import LinkCreate, LinkOut
from app.repository import ClickRepository, LinkRepository
from app.services.shortener import AliasUnavailableError, ShortenerService

router = APIRouter(prefix="/api/links", tags=["links"], dependencies=[Depends(rate_limit)])


@router.post("", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
def create_link(
    payload: LinkCreate,
    links: LinkRepository = Depends(get_link_repo),
    settings: Settings = Depends(get_settings),
) -> LinkOut:
    service = ShortenerService(links, settings.code_length)
    try:
        link = service.shorten(str(payload.url), payload.alias, payload.expires_in_seconds)
    except AliasUnavailableError:
        raise HTTPException(status.HTTP_409_CONFLICT, detail="Alias is not available.")
    return LinkOut.from_link(link, settings.base_url, total_clicks=0)


@router.get("", response_model=list[LinkOut])
def list_links(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    links: LinkRepository = Depends(get_link_repo),
    clicks: ClickRepository = Depends(get_click_repo),
    settings: Settings = Depends(get_settings),
) -> list[LinkOut]:
    return [
        LinkOut.from_link(link, settings.base_url, clicks.count_for_link(link.id))
        for link in links.list_recent(limit, offset)
    ]


@router.get("/{code}", response_model=LinkOut)
def get_link(
    code: str,
    links: LinkRepository = Depends(get_link_repo),
    clicks: ClickRepository = Depends(get_click_repo),
    settings: Settings = Depends(get_settings),
) -> LinkOut:
    link = links.get_by_code(code)
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    return LinkOut.from_link(link, settings.base_url, clicks.count_for_link(link.id))


@router.delete("/{code}", status_code=status.HTTP_204_NO_CONTENT)
def delete_link(
    code: str,
    links: LinkRepository = Depends(get_link_repo),
    cache: TTLCache = Depends(get_cache),
) -> Response:
    if not links.delete(code):
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Link not found.")
    cache.delete(code)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
