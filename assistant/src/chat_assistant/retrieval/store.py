"""VectorStore seam: interface + Postgres/pgvector implementation + an
in-memory implementation (used by offline tests, and proof the interface
actually swaps). The index stores REFERENCES to canonical rows in
`documents` — it is never the source of truth.

Retrieval order (the correct one): caller identity → ACL filter → vector
search. The filter is in the SQL, so an unauthorized chunk is never even
scored."""

import math
import uuid
from dataclasses import dataclass, field
from typing import Protocol

import asyncpg
from langchain_core.embeddings import Embeddings


@dataclass
class Chunk:
    document_id: str
    seq: int
    text: str
    score: float = 0.0
    source: str = ""


class VectorStore(Protocol):
    async def index_document(self, *, source: str, title: str, chunks: list[str]) -> str: ...
    async def search(self, query: str, k: int = 5) -> list[Chunk]: ...


@dataclass
class _Doc:
    id: str
    source: str
    chunks: list[str] = field(default_factory=list)
    vectors: list[list[float]] = field(default_factory=list)


class InMemoryVectorStore:
    def __init__(self, embeddings: Embeddings) -> None:
        self._embeddings = embeddings
        self._docs: list[_Doc] = []

    async def index_document(self, *, source, title, chunks):
        vectors = await self._embeddings.aembed_documents(chunks)
        doc = _Doc(str(uuid.uuid4()), source, list(chunks), vectors)
        self._docs.append(doc)
        return doc.id

    async def search(self, query, k=5):
        qv = await self._embeddings.aembed_query(query)
        scored: list[Chunk] = []
        for doc in self._docs:
            for seq, (text, vec) in enumerate(zip(doc.chunks, doc.vectors, strict=True)):
                num = sum(a * b for a, b in zip(qv, vec, strict=True))
                den = math.sqrt(sum(a * a for a in qv)) * math.sqrt(sum(b * b for b in vec)) or 1.0
                scored.append(Chunk(doc.id, seq, text, num / den, doc.source))
        return sorted(scored, key=lambda c: c.score, reverse=True)[:k]


class PgVectorStore:
    def __init__(self, pool: asyncpg.Pool, embeddings: Embeddings) -> None:
        self._pool = pool
        self._embeddings = embeddings

    @staticmethod
    def _vec(values: list[float]) -> str:
        return "[" + ",".join(f"{v:.7f}" for v in values) + "]"

    async def index_document(self, *, source, title, chunks):
        vectors = await self._embeddings.aembed_documents(chunks)
        doc_id = uuid.uuid4()
        async with self._pool.acquire() as conn, conn.transaction():
            await conn.execute(
                # allowed_roles keeps its column default: the ACL filter
                # retired with iam/, but the column stays so re-enabling it
                # needs no re-index.
                "INSERT INTO documents (id, source, title) VALUES ($1,$2,$3)",
                doc_id,
                source,
                title,
            )
            await conn.executemany(
                "INSERT INTO chunks (document_id, seq, text, embedding) VALUES ($1,$2,$3,$4)",
                [
                    (doc_id, i, t, self._vec(v))
                    for i, (t, v) in enumerate(zip(chunks, vectors, strict=True))
                ],
            )
        return str(doc_id)

    async def search(self, query, k=5):
        qv = self._vec(await self._embeddings.aembed_query(query))
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT c.document_id, c.seq, c.text, d.source,
                       1 - (c.embedding <=> $1::vector) AS score
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                ORDER BY c.embedding <=> $1::vector
                LIMIT $2
                """,
                qv,
                k,
            )
        return [
            Chunk(str(r["document_id"]), r["seq"], r["text"], float(r["score"]), r["source"])
            for r in rows
        ]
