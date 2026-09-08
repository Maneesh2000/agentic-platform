"""The tool boundary: registry → policy → gateway → impls.

Everything here is built LAZILY and memoized per process. Constructing the
gateway pulls in embeddings and a database pool, and CLAUDE.md's standing
rules are that boot never requires provider keys and that a worker starts
with the vector store down — so nothing below runs at import time.
"""

from functools import lru_cache

from .audit import AuditSink, InMemoryAuditSink
from .budget import Budget, BudgetExceeded
from .errors import MissingIdempotencyKey, PolicyDenied, ToolFailed, ToolTimeout
from .gateway import ToolGateway
from .registry import Registry
from .specs import AgentSpec, ToolSpec
from .toolbox import Toolbox

__all__ = [
    "AgentSpec",
    "AuditSink",
    "Budget",
    "BudgetExceeded",
    "InMemoryAuditSink",
    "MissingIdempotencyKey",
    "PolicyDenied",
    "Registry",
    "ToolFailed",
    "ToolGateway",
    "ToolSpec",
    "ToolTimeout",
    "Toolbox",
    "build_gateway",
    "registry",
]


@lru_cache(maxsize=1)
def registry() -> Registry:
    return Registry.load()


@lru_cache(maxsize=1)
def build_gateway() -> ToolGateway:
    """Gateway over the real impls. First call constructs the store (and so
    the embedding client); until then a keyless worker is unaffected."""
    from ..retrieval.embeddings import build_embeddings
    from ..retrieval.store import PgVectorStore
    from ..vectordb import get_pool
    from .audit import PgAuditSink
    from .tools.document import document_parse, document_read
    from .tools.retrieval import make_retrieval_search

    class _LazyStore:
        """The pool is opened on first use, not on construction."""

        def __init__(self) -> None:
            self._inner: PgVectorStore | None = None

        async def _get(self) -> PgVectorStore:
            if self._inner is None:
                self._inner = PgVectorStore(await get_pool(), build_embeddings())
            return self._inner

        async def index_document(self, **kw):
            return await (await self._get()).index_document(**kw)

        async def search(self, query, k=5):
            return await (await self._get()).search(query, k=k)

    store = _LazyStore()
    return ToolGateway(
        registry(),
        PgAuditSink(get_pool),
        {
            "document.read": document_read,
            "document.parse": document_parse,
            "retrieval.search": make_retrieval_search(store),
        },
    )
