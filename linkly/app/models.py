from datetime import datetime, timezone

from pydantic import BaseModel, Field, HttpUrl

from app.repository import Link


class LinkCreate(BaseModel):
    url: HttpUrl
    alias: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{3,32}$")
    expires_in_seconds: int | None = Field(default=None, gt=0)


class LinkOut(BaseModel):
    code: str
    short_url: str
    target_url: str
    created_at: datetime
    expires_at: datetime | None
    total_clicks: int

    @classmethod
    def from_link(cls, link: Link, base_url: str, total_clicks: int) -> "LinkOut":
        return cls(
            code=link.code,
            short_url=f"{base_url.rstrip('/')}/{link.code}",
            target_url=link.target_url,
            created_at=_to_dt(link.created_at),
            expires_at=_to_dt(link.expires_at) if link.expires_at is not None else None,
            total_clicks=total_clicks,
        )


class DailyCount(BaseModel):
    date: str
    clicks: int


class TopItem(BaseModel):
    value: str
    clicks: int


class LinkStats(BaseModel):
    code: str
    total_clicks: int
    window_days: int
    clicks_in_window: int
    daily: list[DailyCount]
    top_referrers: list[TopItem]
    top_countries: list[TopItem]


def _to_dt(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, tz=timezone.utc)
