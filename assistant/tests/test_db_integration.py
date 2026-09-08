"""Real Postgres: migrations, pgvector search, audit rows.

Auto-skips when the database is unreachable, so the suite stays green
offline. Run `docker compose up -d postgres` to exercise these.
"""

import hashlib

import pytest
from langchain_core.embeddings import Embeddings

from chat_assistant import vectordb
from chat_assistant.capabilities.audit import PgAuditSink
from chat_assistant.retrieval.store import PgVectorStore

pytestmark = pytest.mark.asyncio


class HashEmbeddings(Embeddings):
    """Deterministic and dependency-free (langchain's fake lazily imports numpy)."""

    def __init__(self, size: int = 1536) -> None:
        self._size = size

    def _vec(self, text: str) -> list[float]:
        seed = hashlib.sha256(text.encode()).digest()
        raw = (seed * (self._size // len(seed) + 1))[: self._size]
        return [b / 255.0 for b in raw]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture()
async def pool():
    if not await vectordb.ping():
        pytest.skip("Postgres unavailable (docker compose up -d postgres)")
    await vectordb.apply_migrations()
    yield await vectordb.get_pool()
    await vectordb.aclose()


async def test_migrations_are_idempotent(pool) -> None:
    """Applied twice on purpose: a worker restarting must not fail on DDL."""
    await vectordb.apply_migrations()
    tables = {
        r["tablename"]
        for r in await pool.fetch("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
    }
    assert {"documents", "chunks", "audit_events"} <= tables
    # The supervisor's tables died with it.
    assert "tasks" not in tables and "approvals" not in tables


async def test_audit_rows_round_trip(pool) -> None:
    sink = PgAuditSink(vectordb.get_pool)
    turn = "turn-abc"
    await sink.emit(
        turn_id=turn,
        actor="user:alice/agent:document_summary",
        event="tool_call",
        agent="document_summary",
        tool="document.parse",
        decision="allowed",
        latency_ms=12,
        payload_hash="deadbeef",
        detail={"attempt": 1},
    )
    events = await sink.for_turn(turn)
    assert events and events[0]["decision"] == "allowed"
    assert events[0]["actor"].startswith("user:alice")
    # Hash, never content.
    assert events[0]["payload_hash"] == "deadbeef"


async def test_pgvector_search_returns_indexed_chunks(pool) -> None:
    import uuid

    store = PgVectorStore(pool, HashEmbeddings())
    marker = str(uuid.uuid4())[:8]
    await store.index_document(
        source=f"upload:{marker}", title="notes", chunks=[f"vendor delay {marker}"]
    )
    hits = await store.search(f"vendor delay {marker}", k=50)
    assert any(marker in h.text for h in hits)
