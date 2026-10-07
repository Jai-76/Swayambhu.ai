from contextlib import contextmanager
from collections.abc import Iterator

import psycopg

from app.core.config import get_settings


def _dsn() -> str:
    s = get_settings()
    return (
        f"host={s.postgres_host} port={s.postgres_port} "
        f"dbname={s.postgres_db} user={s.postgres_user} password={s.postgres_password} "
        "connect_timeout=3"
    )


@contextmanager
def connection() -> Iterator[psycopg.Connection]:
    with psycopg.connect(_dsn()) as conn:
        yield conn


def available() -> bool:
    try:
        with connection():
            return True
    except psycopg.Error:
        return False


def initialize() -> None:
    with connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                attachments JSONB,
                model JSONB,
                duration_ms INTEGER,
                steps JSONB,
                sources JSONB,
                files JSONB,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                size BIGINT NOT NULL,
                stored_as TEXT NOT NULL,
                pages INTEGER,
                status TEXT NOT NULL,
                error TEXT,
                indexed BOOLEAN NOT NULL DEFAULT FALSE,
                uploaded_at TIMESTAMPTZ NOT NULL
            );
            CREATE TABLE IF NOT EXISTS document_pages (
                document_id TEXT PRIMARY KEY REFERENCES documents(id) ON DELETE CASCADE,
                pages JSONB NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                time TIMESTAMPTZ NOT NULL,
                query TEXT NOT NULL,
                model TEXT NOT NULL,
                tools JSONB NOT NULL,
                file TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS generated_files (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                size BIGINT NOT NULL,
                chat_id TEXT REFERENCES chats(id) ON DELETE SET NULL,
                created_at TIMESTAMPTZ NOT NULL,
                stored_as TEXT NOT NULL
            );
            """
        )
