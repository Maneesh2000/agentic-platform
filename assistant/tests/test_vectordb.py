"""Vector store seam — offline-safe: no Postgres server required."""

import pytest

from chat_assistant import vectordb
from chat_assistant.config import settings


@pytest.fixture(autouse=True)
async def _fresh_pool(monkeypatch: pytest.MonkeyPatch):
    # A port nothing listens on: every test starts unreachable-by-default.
    monkeypatch.setattr(
        settings, "database_url", "postgresql://voice:voice@127.0.0.1:59999/voiceagent"
    )
    await vectordb.aclose()
    yield
    await vectordb.aclose()


async def test_pool_is_lazy_singleton() -> None:
    # min_size=0: pool creation opens no connection, so this works offline.
    a = await vectordb.get_pool()
    b = await vectordb.get_pool()
    assert a is b


async def test_ping_false_when_unreachable() -> None:
    assert await vectordb.ping() is False  # and it must not raise


async def test_aclose_resets_singleton() -> None:
    first = await vectordb.get_pool()
    await vectordb.aclose()
    assert (await vectordb.get_pool()) is not first
