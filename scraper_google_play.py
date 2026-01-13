from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import google_play_scraper as gps


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_released(value: Any):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if not isinstance(value, str):
        return None
 
    v = value.strip()
    if not v:
        return None
 
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%d %b %Y"):
        try:
            return datetime.strptime(v, fmt).date()
        except ValueError:
            continue
    return None


def with_retries(fn, *, attempts: int = 3, base_sleep: float = 1.0, max_sleep: float = 8.0):
    last_err = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:  # noqa: BLE001
            last_err = e
            sleep = min(max_sleep, base_sleep * (2**i))
            sleep = sleep * (0.7 + random.random() * 0.6)
            time.sleep(sleep)
    raise last_err  # type: ignore[misc]


@dataclass
class ScrapedDeveloper:
    developer_key: str
    name: str | None
    email: str | None
    website: str | None
    address: str | None


@dataclass
class ScrapedMeta:
    app_id: str
    developer_key: str | None
    title: str | None
    summary: str | None
    description: str | None
    installs: str | None
    installs_min: int | None
    installs_real: int | None
    score: float | None
    ratings: int | None
    reviews: int | None
    histogram: dict[str, Any] | None
    price: float | None
    free: bool | None
    iap: bool | None
    genre: str | None
    genre_id: str | None
    content_rating: str | None
    released: Any
    updated: datetime | None
    version: str | None
    url: str | None
    icon: str | None
    header_image: str | None
    screenshots: list[str] | None
    video: str | None


def _safe_float(v: Any) -> float | None:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _safe_int(v: Any) -> int | None:
    try:
        if v is None:
            return None
        return int(v)
    except (TypeError, ValueError):
        return None


def scrape_app_meta(app_id: str, *, lang: str = "en", country: str = "us") -> tuple[ScrapedMeta, ScrapedDeveloper | None, list[dict[str, Any]]]:
    def _call():
        return gps.app(app_id, lang=lang, country=country)

    data = with_retries(_call, attempts=3)

    developer_key = data.get("developerId") or data.get("developer_id")
    dev = None
    if developer_key:
        dev = ScrapedDeveloper(
            developer_key=str(developer_key),
            name=data.get("developer") or data.get("developerName"),
            email=data.get("developerEmail"),
            website=data.get("developerWebsite"),
            address=data.get("developerAddress"),
        )

    updated = data.get("updated")
    if isinstance(updated, str):
        updated_dt = None
    elif isinstance(updated, datetime):
        updated_dt = updated if updated.tzinfo else updated.replace(tzinfo=timezone.utc)
    else:
        updated_dt = None

    meta = ScrapedMeta(
        app_id=app_id,
        developer_key=str(developer_key) if developer_key else None,
        title=data.get("title"),
        summary=data.get("summary"),
        description=data.get("description"),
        installs=data.get("installs"),
        installs_min=_safe_int(data.get("minInstalls")),
        installs_real=_safe_int(data.get("realInstalls")),
        score=_safe_float(data.get("score")),
        ratings=_safe_int(data.get("ratings")),
        reviews=_safe_int(data.get("reviews")),
        histogram=data.get("histogram"),
        price=_safe_float(data.get("price")),
        free=data.get("free"),
        iap=data.get("offersIAP") or data.get("iap"),
        genre=data.get("genre"),
        genre_id=data.get("genreId"),
        content_rating=data.get("contentRating"),
        released=_parse_released(data.get("released")),
        updated=updated_dt,
        version=data.get("version"),
        url=data.get("url"),
        icon=data.get("icon"),
        header_image=data.get("headerImage"),
        screenshots=data.get("screenshots"),
        video=data.get("video"),
    )

    permissions = data.get("permissions")
    if isinstance(permissions, list):
        perms = permissions
    else:
        perms = []

    return meta, dev, perms


def scrape_reviews(
    app_id: str,
    *,
    lang: str = "en",
    country: str = "us",
    count: int = 100,
    sort: int | None = None,
) -> list[dict[str, Any]]:
    def _call():
        kwargs: dict[str, Any] = {"app_id": app_id, "lang": lang, "country": country, "count": count}
        if sort is not None:
            kwargs["sort"] = sort
        result, _ = gps.reviews(**kwargs)
        return result

    raw_reviews = with_retries(_call, attempts=3)
    out: list[dict[str, Any]] = []
    for r in raw_reviews or []:
        date_val = r.get("at")
        if isinstance(date_val, datetime):
            date_dt = date_val if date_val.tzinfo else date_val.replace(tzinfo=timezone.utc)
        else:
            date_dt = None

        replied_at_val = r.get("repliedAt")
        if isinstance(replied_at_val, datetime):
            replied_at_dt = replied_at_val if replied_at_val.tzinfo else replied_at_val.replace(tzinfo=timezone.utc)
        else:
            replied_at_dt = None

        out.append(
            {
                "review_id": r.get("reviewId") or r.get("review_id"),
                "user_name": r.get("userName"),
                "user_image": r.get("userImage"),
                "content": r.get("content"),
                "score": _safe_int(r.get("score")),
                "thumbs_up": _safe_int(r.get("thumbsUpCount")),
                "version": r.get("reviewCreatedVersion"),
                "date": date_dt,
                "replied_at": replied_at_dt,
                "reply_content": r.get("replyContent"),
            }
        )

    return out
