#!/usr/bin/env python3
"""
create_tables.py — создаёт таблицы Play Analyzer в Postgres (Railway)

Запуск:
  1) railway variables pull   # чтобы получить .env с DATABASE_URL
  2) python create_tables.py

Требует:
  DATABASE_URL в env или .env
"""

import os
import sys
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL не найден.")
    print("Сделай: railway variables pull (создаст .env) или задай DATABASE_URL вручную.")
    sys.exit(1)

DDL = [
    # Для UUID (gen_random_uuid)
    """
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    """,

    # 1) app_developer
    """
    CREATE TABLE IF NOT EXISTS app_developer (
        developer_key VARCHAR(255) PRIMARY KEY,
        name TEXT,
        email TEXT,
        website TEXT,
        address TEXT,
        last_scraped TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # 2) app_meta_info
    """
    DROP TABLE app_meta_info;
    CREATE TABLE IF NOT EXISTS app_meta_info (
        app_id VARCHAR(255) PRIMARY KEY,

        developer_key VARCHAR(255) REFERENCES app_developer(developer_key),

        title TEXT,
        summary TEXT,
        description TEXT,

        installs TEXT,
        installs_min BIGINT,
        installs_real BIGINT,

        score NUMERIC(4,2),
        ratings BIGINT,
        reviews_count BIGINT,
        histogram JSONB,

        price NUMERIC(12,2),
        free BOOLEAN,
        iap BOOLEAN,

        genre TEXT,
        genre_id TEXT,
        content_rating TEXT,

        released DATE,
        updated TIMESTAMPTZ,
        version TEXT,

        url TEXT,
        icon TEXT,
        header_image TEXT,
        screenshots JSONB,
        video TEXT,

        last_scraped TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # 3) app_reviews
    """
    CREATE TABLE IF NOT EXISTS app_reviews (
        id BIGSERIAL PRIMARY KEY,
        app_id VARCHAR(255) NOT NULL REFERENCES app_meta_info(app_id) ON DELETE CASCADE,

        review_id TEXT,
        user_name TEXT,
        user_image TEXT,

        content TEXT,
        score INT,
        thumbs_up BIGINT,

        version TEXT,
        date TIMESTAMPTZ,

        replied_at TIMESTAMPTZ,
        reply_content TEXT,

        scraped_at TIMESTAMPTZ DEFAULT NOW(),

        UNIQUE (app_id, review_id)
    );
    """,

    # 4) app_permissions
    """
    CREATE TABLE IF NOT EXISTS app_permissions (
        id BIGSERIAL PRIMARY KEY,
        app_id VARCHAR(255) NOT NULL REFERENCES app_meta_info(app_id) ON DELETE CASCADE,

        category TEXT,
        permissions JSONB,

        scraped_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # 5) app_analysis
    """
    CREATE TABLE IF NOT EXISTS app_analysis (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        app_id VARCHAR(255) NOT NULL REFERENCES app_meta_info(app_id) ON DELETE CASCADE,

        client_id TEXT,
        scenario VARCHAR(50),
        user_context TEXT,

        prompt_used TEXT,

        market_fit INT,
        recommendations JSONB,
        raw_llm_response JSONB,

        analyzed_at TIMESTAMPTZ DEFAULT NOW()
    );
    """,

    # Индексы (ускоряют кэш/историю)
    """
    CREATE INDEX IF NOT EXISTS idx_app_meta_dev ON app_meta_info(developer_key);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_reviews_app_date ON app_reviews(app_id, date DESC);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_analysis_app_date ON app_analysis(app_id, analyzed_at DESC);
    """,
]

def main():
    print("🔌 Connecting to Postgres...")
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            for stmt in DDL:
                cur.execute(stmt)
        conn.commit()
    print("✅ Done: tables + indexes created.")

if __name__ == "__main__":
    main()
