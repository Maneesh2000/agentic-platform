"""retrieval.search — the gateway-facing wrapper over the vector store.
Results are UNTRUSTED content (they came from documents)."""

from ...retrieval.store import VectorStore


def make_retrieval_search(store: VectorStore):
    async def retrieval_search(query: str, k: int = 5) -> dict:
        chunks = await store.search(query, k=k)
        return {
            "chunks": [
                {"document_id": c.document_id, "seq": c.seq, "text": c.text, "score": c.score}
                for c in chunks
            ]
        }

    return retrieval_search
