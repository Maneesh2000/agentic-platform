"""Vector store seam (Postgres + pgvector). Use cases land next version.

Future graph specialists (document extraction, RAG-style retrieval) consume
this pool — a specialist gets its own table and owns its schema, calling
`ensure_ready()` once and `pgvector.asyncpg.register_vector(conn)` on the
connections it uses. Deliberately NOT on the speaking path: nothing in
main.py touches it, so workers start and serve calls with the DB down.

Local dev: `docker compose up` starts pgvector/pgvector on :5432
(user/pass/db: voice/voice/voiceagent). Cluster: deploy/k8s/postgres.yaml;
workers reach it via DATABASE_URL (e.g. postgresql://...@postgres:5432/...).

Embedding model and dimensions are part of the use-case work, not this
seam — pick them when the first specialist defines what gets embedded.
"""

import asyncpg

from .config import settings

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    """Process-wide lazy pool. min_size=0 => creating it opens no
    connection, so this succeeds with the database down."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            settings.database_url,
            min_size=0,
            max_size=4,
            timeout=5,  # acquire/connect timeout
            command_timeout=10,
        )
    return _pool


async def ping() -> bool:
    """True if Postgres answers AND the pgvector extension is available.
    Never raises — callers decide whether absence matters (today, nothing
    does)."""
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            available = await conn.fetchval(
                "SELECT count(*) FROM pg_available_extensions WHERE name = 'vector'"
            )
            return bool(available)
    except Exception:  # any transport/auth failure = "not available"
        return False


async def ensure_ready() -> str:
    """Install the pgvector extension (idempotent) and return its version.

    Setup path, not speaking path: raises on failure so a misconfigured
    database is loud exactly where a use case starts depending on it.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        version: str = await conn.fetchval(
            "SELECT extversion FROM pg_extension WHERE extname = 'vector'"
        )
        return version


async def apply_migrations() -> None:
    """Idempotent DDL for the capability tables (documents, chunks,
    audit_events). Setup path, not the speaking path: it raises loudly so a
    misconfigured database is obvious where a capability first needs it."""
    from pathlib import Path

    sql = (Path(__file__).parent / "retrieval" / "migrations" / "0001_init.sql").read_text()
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(sql)


async def aclose() -> None:
    """Close and forget the pool (tests, graceful shutdown)."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
