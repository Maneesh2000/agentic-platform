"""EMBEDDING_MODEL="provider:model" — the same swap pattern as the LLMs.
Dimension is forced to EMBEDDING_DIM so vectors always match the chunks
table; changing dimension is a schema migration, not a config tweak.

Construction is LAZY: provider clients validate API keys in their
constructors, and a missing key must fail the task that needed embeddings
— never the platform's boot."""

from collections.abc import Callable

from langchain_core.embeddings import Embeddings

from ..config import settings


def _construct() -> Embeddings:
    provider, _, model = settings.embedding_model.partition(":")
    dim = settings.embedding_dim
    if provider == "google":
        from langchain_google_genai import GoogleGenerativeAIEmbeddings

        return GoogleGenerativeAIEmbeddings(model=model, output_dimensionality=dim)
    if provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(model=model, dimensions=dim)
    raise ValueError(f"unsupported embedding provider {provider!r} (google, openai)")


class LazyEmbeddings(Embeddings):
    def __init__(self, factory: Callable[[], Embeddings]) -> None:
        self._factory = factory
        self._inner: Embeddings | None = None

    def _get(self) -> Embeddings:
        if self._inner is None:
            self._inner = self._factory()
        return self._inner

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._get().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._get().embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._get().aembed_documents(texts)

    async def aembed_query(self, text: str) -> list[float]:
        return await self._get().aembed_query(text)


def build_embeddings() -> Embeddings:
    return LazyEmbeddings(_construct)
