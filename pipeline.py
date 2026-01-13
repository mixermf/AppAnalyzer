from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
from typing import Any

from config import get_env_int
from db import Database, MetaInfo, is_fresh
from llm_perplexity import analyze_app
from scraper_google_play import scrape_app_meta, scrape_reviews


ANALYSIS_MAX_AGE_DAYS = get_env_int("ANALYSIS_MAX_AGE_DAYS", 7)
META_MAX_AGE_DAYS = get_env_int("META_MAX_AGE_DAYS", 7)
REVIEWS_MAX_AGE_DAYS = get_env_int("REVIEWS_MAX_AGE_DAYS", 7)
REVIEWS_COUNT = get_env_int("REVIEWS_COUNT", 100)


def _meta_to_db(meta) -> MetaInfo:
    return MetaInfo(
        app_id=meta.app_id,
        developer_key=meta.developer_key,
        title=meta.title,
        summary=meta.summary,
        description=meta.description,
        installs=meta.installs,
        installs_min=meta.installs_min,
        installs_real=meta.installs_real,
        score=meta.score,
        ratings=meta.ratings,
        reviews_count=meta.reviews,
        histogram=meta.histogram,
        price=meta.price,
        free=meta.free,
        iap=meta.iap,
        genre=meta.genre,
        genre_id=meta.genre_id,
        content_rating=meta.content_rating,
        released=meta.released,
        updated=meta.updated,
        version=meta.version,
        url=meta.url,
        icon=meta.icon,
        header_image=meta.header_image,
        screenshots=meta.screenshots,
        video=meta.video,
        last_scraped=None,
    )


def run_user_pipeline(
    *,
    app_id: str,
    scenario: str,
    user_context: str | None,
    client_id: str | None,
    lang: str = "en",
    country: str = "us",
) -> dict[str, Any]:
    db = Database()

    analysis_max_age = timedelta(days=ANALYSIS_MAX_AGE_DAYS)
    meta_max_age = timedelta(days=META_MAX_AGE_DAYS)

    latest = db.get_latest_analysis(app_id=app_id, scenario=scenario, client_id=client_id)
    if latest and is_fresh(latest.analyzed_at, max_age=analysis_max_age):
        return {
            "source": "analysis_cache",
            "meta": asdict(db.get_meta_info(app_id=app_id)) if db.get_meta_info(app_id=app_id) else None,
            "analysis": {
                "market_fit": latest.market_fit,
                "recommendations": latest.recommendations,
                "raw": latest.raw_llm_response,
                "analyzed_at": latest.analyzed_at.isoformat(),
            },
        }

    meta_row = db.get_meta_info(app_id=app_id)
    meta_is_fresh = meta_row is not None and is_fresh(meta_row.last_scraped, max_age=meta_max_age)

    if not meta_is_fresh:
        scraped_meta, dev, permissions = scrape_app_meta(app_id, lang=lang, country=country)
        if dev is not None:
            db.upsert_developer(
                developer_key=dev.developer_key,
                name=dev.name,
                email=dev.email,
                website=dev.website,
                address=dev.address,
            )
        db.upsert_meta_info(_meta_to_db(scraped_meta))
        if permissions:
            db.replace_permissions(app_id=app_id, permissions=permissions)
        meta_row = db.get_meta_info(app_id=app_id)

        reviews = scrape_reviews(app_id, lang=lang, country=country, count=REVIEWS_COUNT)
        if reviews:
            db.insert_reviews(app_id=app_id, reviews=reviews)

    meta_payload = asdict(meta_row) if meta_row else {"app_id": app_id}

    result = analyze_app(app_id=app_id, meta=meta_payload, scenario=scenario, user_context=user_context)

    db.insert_analysis(
        app_id=app_id,
        client_id=client_id,
        scenario=scenario,
        user_context=user_context,
        prompt_used=result.prompt_used,
        market_fit=result.market_fit,
        recommendations=result.recommendations,
        raw_llm_response=result.raw,
    )

    return {
        "source": "fresh_analysis",
        "meta": meta_payload,
        "analysis": {
            "market_fit": result.market_fit,
            "recommendations": result.recommendations,
            "raw": result.raw,
        },
    }


def run_cron_refresh(*, app_id: str, lang: str = "en", country: str = "us") -> dict[str, Any]:
    db = Database()
    meta_max_age = timedelta(days=META_MAX_AGE_DAYS)

    meta_row = db.get_meta_info(app_id=app_id)
    meta_is_fresh = meta_row is not None and is_fresh(meta_row.last_scraped, max_age=meta_max_age)
    if meta_is_fresh:
        return {"app_id": app_id, "status": "skipped_fresh"}

    scraped_meta, dev, permissions = scrape_app_meta(app_id, lang=lang, country=country)
    if dev is not None:
        db.upsert_developer(
            developer_key=dev.developer_key,
            name=dev.name,
            email=dev.email,
            website=dev.website,
            address=dev.address,
        )
    db.upsert_meta_info(_meta_to_db(scraped_meta))
    if permissions:
        db.replace_permissions(app_id=app_id, permissions=permissions)

    reviews = scrape_reviews(app_id, lang=lang, country=country, count=REVIEWS_COUNT)
    inserted_reviews = 0
    if reviews:
        inserted_reviews = db.insert_reviews(app_id=app_id, reviews=reviews)

    return {"app_id": app_id, "status": "refreshed", "inserted_reviews": inserted_reviews}
