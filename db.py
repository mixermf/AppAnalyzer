import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

import psycopg


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_timestamptz(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    return None


@dataclass
class MetaInfo:
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
    reviews_count: int | None
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
    last_scraped: datetime | None


@dataclass
class AnalysisRow:
    id: str
    app_id: str
    client_id: str | None
    scenario: str | None
    user_context: str | None
    prompt_used: str | None
    market_fit: int | None
    recommendations: Any
    raw_llm_response: Any
    analyzed_at: datetime


class Database:
    def __init__(self, database_url: str | None = None) -> None:
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            raise RuntimeError("DATABASE_URL is not set")

    def connect(self) -> psycopg.Connection:
        return psycopg.connect(self.database_url)

    def get_latest_analysis(self, *, app_id: str, scenario: str | None, client_id: str | None) -> AnalysisRow | None:
        sql = """
            SELECT id, app_id, client_id, scenario, user_context, prompt_used,
                   market_fit, recommendations, raw_llm_response, analyzed_at
            FROM app_analysis
            WHERE app_id = %s
              AND (%s IS NULL OR scenario = %s)
              AND (%s IS NULL OR client_id = %s)
            ORDER BY analyzed_at DESC
            LIMIT 1
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (app_id, scenario, scenario, client_id, client_id))
                row = cur.fetchone()
                if not row:
                    return None

        analyzed_at = parse_timestamptz(row[9]) or utcnow()
        return AnalysisRow(
            id=str(row[0]),
            app_id=row[1],
            client_id=row[2],
            scenario=row[3],
            user_context=row[4],
            prompt_used=row[5],
            market_fit=row[6],
            recommendations=row[7],
            raw_llm_response=row[8],
            analyzed_at=analyzed_at,
        )

    def insert_analysis(
        self,
        *,
        app_id: str,
        client_id: str | None,
        scenario: str | None,
        user_context: str | None,
        prompt_used: str | None,
        market_fit: int | None,
        recommendations: Any,
        raw_llm_response: Any,
    ) -> None:
        sql = """
            INSERT INTO app_analysis (
                app_id, client_id, scenario, user_context, prompt_used,
                market_fit, recommendations, raw_llm_response
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        app_id,
                        client_id,
                        scenario,
                        user_context,
                        prompt_used,
                        market_fit,
                        json.dumps(recommendations) if isinstance(recommendations, (dict, list)) else recommendations,
                        json.dumps(raw_llm_response) if isinstance(raw_llm_response, (dict, list)) else raw_llm_response,
                    ),
                )
            conn.commit()

    def get_meta_info(self, *, app_id: str) -> MetaInfo | None:
        sql = """
            SELECT app_id, developer_key, title, summary, description,
                   installs, installs_min, installs_real,
                   score, ratings, reviews_count, histogram,
                   price, free, iap,
                   genre, genre_id, content_rating,
                   released, updated, version,
                   url, icon, header_image, screenshots, video,
                   last_scraped
            FROM app_meta_info
            WHERE app_id = %s
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (app_id,))
                row = cur.fetchone()
                if not row:
                    return None

        return MetaInfo(
            app_id=row[0],
            developer_key=row[1],
            title=row[2],
            summary=row[3],
            description=row[4],
            installs=row[5],
            installs_min=row[6],
            installs_real=row[7],
            score=float(row[8]) if row[8] is not None else None,
            ratings=row[9],
            reviews_count=row[10],
            histogram=row[11],
            price=float(row[12]) if row[12] is not None else None,
            free=row[13],
            iap=row[14],
            genre=row[15],
            genre_id=row[16],
            content_rating=row[17],
            released=row[18],
            updated=parse_timestamptz(row[19]),
            version=row[20],
            url=row[21],
            icon=row[22],
            header_image=row[23],
            screenshots=row[24],
            video=row[25],
            last_scraped=parse_timestamptz(row[26]),
        )

    def upsert_developer(
        self,
        *,
        developer_key: str,
        name: str | None,
        email: str | None,
        website: str | None,
        address: str | None,
        scraped_at: datetime | None = None,
    ) -> None:
        scraped_at = scraped_at or utcnow()
        sql = """
            INSERT INTO app_developer (developer_key, name, email, website, address, last_scraped)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (developer_key) DO UPDATE SET
                name = EXCLUDED.name,
                email = EXCLUDED.email,
                website = EXCLUDED.website,
                address = EXCLUDED.address,
                last_scraped = EXCLUDED.last_scraped
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (developer_key, name, email, website, address, scraped_at))
            conn.commit()

    def upsert_meta_info(self, meta: MetaInfo, *, scraped_at: datetime | None = None) -> None:
        scraped_at = scraped_at or utcnow()
        sql = """
            INSERT INTO app_meta_info (
                app_id, developer_key,
                title, summary, description,
                installs, installs_min, installs_real,
                score, ratings, reviews_count, histogram,
                price, free, iap,
                genre, genre_id, content_rating,
                released, updated, version,
                url, icon, header_image, screenshots, video,
                last_scraped
            ) VALUES (
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            ON CONFLICT (app_id) DO UPDATE SET
                developer_key = EXCLUDED.developer_key,
                title = EXCLUDED.title,
                summary = EXCLUDED.summary,
                description = EXCLUDED.description,
                installs = EXCLUDED.installs,
                installs_min = EXCLUDED.installs_min,
                installs_real = EXCLUDED.installs_real,
                score = EXCLUDED.score,
                ratings = EXCLUDED.ratings,
                reviews_count = EXCLUDED.reviews_count,
                histogram = EXCLUDED.histogram,
                price = EXCLUDED.price,
                free = EXCLUDED.free,
                iap = EXCLUDED.iap,
                genre = EXCLUDED.genre,
                genre_id = EXCLUDED.genre_id,
                content_rating = EXCLUDED.content_rating,
                released = EXCLUDED.released,
                updated = EXCLUDED.updated,
                version = EXCLUDED.version,
                url = EXCLUDED.url,
                icon = EXCLUDED.icon,
                header_image = EXCLUDED.header_image,
                screenshots = EXCLUDED.screenshots,
                video = EXCLUDED.video,
                last_scraped = EXCLUDED.last_scraped
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        meta.app_id,
                        meta.developer_key,
                        meta.title,
                        meta.summary,
                        meta.description,
                        meta.installs,
                        meta.installs_min,
                        meta.installs_real,
                        meta.score,
                        meta.ratings,
                        meta.reviews_count,
                        json.dumps(meta.histogram) if meta.histogram is not None else None,
                        meta.price,
                        meta.free,
                        meta.iap,
                        meta.genre,
                        meta.genre_id,
                        meta.content_rating,
                        meta.released,
                        meta.updated,
                        meta.version,
                        meta.url,
                        meta.icon,
                        meta.header_image,
                        json.dumps(meta.screenshots) if meta.screenshots is not None else None,
                        meta.video,
                        scraped_at,
                    ),
                )
            conn.commit()

    def insert_reviews(self, *, app_id: str, reviews: Iterable[dict[str, Any]]) -> int:
        sql = """
            INSERT INTO app_reviews (
                app_id, review_id, user_name, user_image,
                content, score, thumbs_up,
                version, date,
                replied_at, reply_content
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (app_id, review_id) DO NOTHING
        """
        inserted = 0
        with self.connect() as conn:
            with conn.cursor() as cur:
                for r in reviews:
                    cur.execute(
                        sql,
                        (
                            app_id,
                            r.get("review_id"),
                            r.get("user_name"),
                            r.get("user_image"),
                            r.get("content"),
                            r.get("score"),
                            r.get("thumbs_up"),
                            r.get("version"),
                            r.get("date"),
                            r.get("replied_at"),
                            r.get("reply_content"),
                        ),
                    )
                    inserted += cur.rowcount
            conn.commit()
        return inserted

    def replace_permissions(self, *, app_id: str, permissions: list[dict[str, Any]]) -> None:
        delete_sql = "DELETE FROM app_permissions WHERE app_id = %s"
        insert_sql = """
            INSERT INTO app_permissions (app_id, category, permissions)
            VALUES (%s, %s, %s)
        """
        with self.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(delete_sql, (app_id,))
                for p in permissions:
                    cur.execute(
                        insert_sql,
                        (
                            app_id,
                            p.get("category"),
                            json.dumps(p.get("permissions")) if isinstance(p.get("permissions"), (dict, list)) else p.get("permissions"),
                        ),
                    )
            conn.commit()


def is_fresh(ts: datetime | None, *, max_age: timedelta) -> bool:
    if ts is None:
        return False
    return utcnow() - ts <= max_age
