"""The text surface — offline, no keys, no LiveKit, no database."""

import json
import re

import httpx
import pytest
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from chat_assistant.graph.build import build_graph
from chat_assistant.graph.specialists.research import FILLER, build_research
from chat_assistant.http.app import Message as ChatMessage
from chat_assistant.http.app import _to_langchain, create_app


class StreamingFake(GenericFakeChatModel):
    """A fake that actually streams, because `stream_mode="messages"` drives
    the async path a real provider uses.

    Two gaps in the built-in fake are filled here: it implements only the
    sync `_stream`, and that `_stream` yields nothing at all for a tool-call
    message with empty content (it only walks `content` and
    `additional_kwargs`), which real providers do emit.
    """

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        message = self._generate(messages, stop=stop, **kwargs).generations[0].message
        if message.tool_calls:
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=message.content,
                    tool_call_chunks=[
                        {
                            "name": tc["name"],
                            "args": json.dumps(tc["args"]),
                            "id": tc["id"],
                            "index": i,
                        }
                        for i, tc in enumerate(message.tool_calls)
                    ],
                    id=message.id,
                )
            )
            return
        for token in re.split(r"(\s)", str(message.content)):
            if token:
                yield ChatGenerationChunk(message=AIMessageChunk(content=token, id=message.id))

    def bind_tools(self, tools, **kwargs):
        return self


class FakeResearchGraph:
    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {"messages": [AIMessage("- v1.7 shipped [LiveKit blog — https://blog.livekit.io]")]}


async def _client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _events(body: str) -> list[tuple[str, str]]:
    """Parse an SSE body into (event, text) pairs.

    Payloads are JSON on purpose — a token may be a single space or contain
    newlines, neither of which survives raw SSE text intact.
    """
    out, event = [], None
    for line in body.splitlines():
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:") and event:
            out.append((event, json.loads(line[5:])["text"]))
    return out


async def test_chat_streams_tokens() -> None:
    app = create_app(graph=build_graph(model=StreamingFake(messages=iter([AIMessage("Hi there")]))))
    async with await _client(app) as client:
        r = await client.post("/chat", json={"messages": [{"role": "user", "content": "hello"}]})
        assert r.status_code == 200
        events = _events(r.text)

    assert "".join(d for e, d in events if e == "token") == "Hi there"
    assert events[-1][0] == "done"


async def test_history_is_replayed_into_the_graph() -> None:
    """The service is stateless: prior turns arrive in the request and must
    reach the model, or a follow-up question loses its context."""
    messages = [
        ChatMessage(role="user", content="my name is Tejesh"),
        ChatMessage(role="assistant", content="Nice to meet you."),
        ChatMessage(role="user", content="what is my name?"),
    ]
    lc = _to_langchain(messages)
    assert [type(m).__name__ for m in lc] == [
        "SystemMessage",
        "HumanMessage",
        "AIMessage",
        "HumanMessage",
    ]
    assert lc[-1].content == "what is my name?"


async def test_text_surface_uses_the_text_persona() -> None:
    """The personas must not cross: assistant.md is TTS-shaped (no markdown,
    1-3 sentences) and would make text chat useless."""
    system = _to_langchain([ChatMessage(role="user", content="hi")])[0].content
    assert "markdown" in system.lower()
    assert "text-to-speech" not in system.lower()


async def test_research_filler_becomes_a_status_event() -> None:
    """What is spoken on the voice path is a status row here."""
    fake = StreamingFake(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[{"name": "research", "args": {"query": "livekit"}, "id": "c1"}],
                ),
                AIMessage("v1.7 shipped."),
            ]
        )
    )
    graph = build_graph(
        model=fake,
        specialists={"research": lambda llm: build_research(llm, agent_graph=FakeResearchGraph())},
    )
    app = create_app(graph=graph)
    async with await _client(app) as client:
        r = await client.post("/chat", json={"messages": [{"role": "user", "content": "news?"}]})
        events = _events(r.text)

    assert (("status", FILLER)) in events

    spoken = "".join(d for e, d in events if e == "token")
    assert spoken == "v1.7 shipped."
    # Regression: the research node's raw findings are internal notes. They
    # must never reach the user — on voice they would be read aloud, URL and
    # all, immediately after the summary.
    assert "blog.livekit.io" not in spoken
    assert "FINDINGS" not in spoken.upper()


async def test_failure_streams_an_error_not_a_stack_trace() -> None:
    class Exploding:
        def astream(self, *a, **kw):
            raise RuntimeError("boom: sk-secret-leaked")

    app = create_app(graph=Exploding())
    async with await _client(app) as client:
        r = await client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        events = _events(r.text)

    errors = [d for e, d in events if e == "error"]
    assert errors and "secret" not in errors[0]
    assert events[-1][0] == "done"


async def test_empty_message_list_is_rejected() -> None:
    app = create_app(graph=build_graph(model=StreamingFake(messages=iter([]))))
    async with await _client(app) as client:
        assert (await client.post("/chat", json={"messages": []})).status_code == 422


@pytest.mark.parametrize("path", ["/health"])
async def test_health(path: str) -> None:
    app = create_app(graph=build_graph(model=StreamingFake(messages=iter([]))))
    async with await _client(app) as client:
        body = (await client.get(path)).json()
    assert body["status"] == "ok" and body["surface"] == "text"


async def test_boots_without_a_provider_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing key must fail the TURN, not the process: /health answers and
    /chat returns a clean error. Building the graph at import would crashloop
    a deployment whose key is not configured yet.

    Pinned to a provider whose key is scrubbed — a developer's .env.local may
    hold real keys, and this test must stay offline regardless."""
    from chat_assistant.config import settings

    monkeypatch.setattr(settings, "llm_model", "openai:gpt-4.1-mini")
    monkeypatch.setattr(settings, "tavily_api_key", "")
    monkeypatch.setattr(settings, "enable_document_summary", False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    app = create_app()  # no graph injected => real build_graph on first use
    async with await _client(app) as client:
        assert (await client.get("/health")).json()["status"] == "ok"
        r = await client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        events = _events(r.text)
    assert [e for e, _ in events if e == "error"]
    assert events[-1][0] == "done"


async def test_block_list_content_streams_tokens() -> None:
    """Gemini 3.x streams `content` as a list of blocks, not a string — and
    signature/thought blocks carry empty text. Handling only the string
    shape silently dropped every token: the stream ended with just `done`
    and no error anywhere. Found live, kept as a regression."""
    from chat_assistant.http.app import _chunk_text

    class BlockFake(GenericFakeChatModel):
        async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
            for blocks in (
                [{"type": "text", "text": "setup ", "index": 0}],
                [{"type": "text", "text": "works", "index": 0}],
                [{"type": "text", "text": "", "extras": {"signature": "abc"}}],
                [],
            ):
                yield ChatGenerationChunk(message=AIMessageChunk(content=blocks))

        def bind_tools(self, tools, **kwargs):
            return self

    assert _chunk_text(AIMessageChunk(content=[{"type": "text", "text": "x"}])) == "x"
    app = create_app(graph=build_graph(model=BlockFake(messages=iter([AIMessage("u")])), specialists={}))
    async with await _client(app) as client:
        r = await client.post("/chat", json={"messages": [{"role": "user", "content": "hi"}]})
        events = _events(r.text)
    assert "".join(d for e, d in events if e == "token") == "setup works"
