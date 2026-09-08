"""The brain over HTTP — the text surface for the same LangGraph.

Deliberately STATELESS: no database, no auth, no thread storage. The caller
(web/app/api/chat/route.ts) owns identity and conversation history and sends
the full message list every turn — exactly what LiveKit's LLMAdapter does on
the voice path, which is why `build_graph()` needs no checkpointer and stays
byte-identical for both surfaces.

What differs between surfaces is only the output contract:
  voice -> prompts/assistant.md      (TTS-safe: no markdown, 1-3 sentences)
  text  -> prompts/assistant_text.md (markdown, code blocks, full length)
and the research specialist's presentation steer (graph/specialists/research.py).

SSE event stream. Every payload is a JSON object, NOT raw text: a token can
legitimately be a single space or contain newlines (markdown replies are full
of them), and raw SSE data lines cannot carry either unambiguously — a newline
would split into a second data line and whitespace is easily eaten by naive
parsers. `{"text": ...}` survives both.

  status  a specialist's filler line ("Let me look into that for you.") —
          spoken on the voice path, rendered as a status row here
  token   an assistant token delta
  error   the turn failed; the message is safe to display
  done    end of turn
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    HumanMessage,
    SystemMessage,
)
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from ..config import settings
from ..graph.build import build_graph
from ..prompts import load_prompt

logger = logging.getLogger("chat-assistant.http")

SURFACE = "text"


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class Attachment(BaseModel):
    id: str
    filename: str


class ChatRequest(BaseModel):
    messages: list[Message] = Field(min_length=1)
    # Audit actor only — never authorization (see capabilities/gateway.py).
    user_id: str | None = None
    # Files the user attached to THIS turn. The model cannot invent an id:
    # it only ever sees the ones named here.
    attachments: list[Attachment] = []


def _to_langchain(
    messages: list[Message], attachments: list[Attachment] | None = None
) -> list[BaseMessage]:
    system = SystemMessage(load_prompt("assistant_text"))
    turns: list[BaseMessage] = [
        HumanMessage(m.content) if m.role == "user" else AIMessage(m.content) for m in messages
    ]
    if attachments:
        # Names and ids only — never content. The specialist fetches the
        # bytes through the gateway; putting a document in the prompt here
        # would bypass both the audit trail and the size cap.
        listing = "\n".join(f"- {a.filename} (attachment_id: {a.id})" for a in attachments)
        turns.append(
            SystemMessage(
                "Files attached to this turn:\n" + listing + "\n"
                "Use summarize_document with the exact attachment_id above. "
                "Never invent an attachment_id."
            )
        )
    return [system, *turns]


def _chunk_text(chunk) -> str:
    """Extract the human-readable text from a message chunk.

    Providers disagree on the shape of `content`: OpenAI-style models send a
    plain string, while Gemini (3.x) streams a LIST of content blocks like
    [{"type": "text", "text": "..."}] — plus signature/thought blocks with
    empty text that must not become tokens. Handling only the string shape
    silently drops every token from a block-list provider.
    """
    content = chunk.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def _event(name: str, text: str = "") -> dict:
    return {"event": name, "data": json.dumps({"text": text})}


async def _stream(get_graph, body: ChatRequest) -> AsyncIterator[dict]:
    try:
        # Resolved inside the try: provider construction is lazy, so a missing
        # or invalid key surfaces here as a failed turn rather than a dead
        # process (see create_app).
        graph = get_graph()
        async for mode, data in graph.astream(
            {
                "messages": _to_langchain(body.messages, body.attachments),
                "actor": body.user_id or "anon",
            },
            stream_mode=["messages", "custom"],
        ):
            if mode == "custom":
                # Specialist filler: a plain string on the voice path becomes
                # speech; here it is a status line.
                yield _event("status", str(data))
            elif mode == "messages":
                chunk = data[0] if isinstance(data, tuple) else data
                # AI messages only. This mode emits EVERY message a node
                # returns, including tool results — which are internal notes,
                # not assistant output. Specialists are expected to keep them
                # out of state, but a leak here would be user-visible, so the
                # consumer refuses them too.
                if not isinstance(chunk, AIMessage | AIMessageChunk):
                    continue
                text = _chunk_text(chunk)
                if text:
                    yield _event("token", text)
    except Exception:
        # The stack belongs in the log, never in the response body.
        logger.exception("chat turn failed")
        yield _event("error", "The assistant hit an error. Please try again.")
    finally:
        yield _event("done")


def create_app(graph=None) -> FastAPI:
    """`graph` is injectable so tests run against a fake model."""
    app = FastAPI(title="chat-assistant chat")

    origins = [o.strip() for o in settings.http_cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["POST", "GET"],
        allow_headers=["*"],
    )

    # Compiled once, on first use — never at import. Provider clients validate
    # their API keys in their constructors, so building the graph eagerly would
    # make a missing key crash the process at boot instead of failing the one
    # request that needed it. /health must answer either way.
    compiled = graph

    def get_graph():
        nonlocal compiled
        if compiled is None:
            compiled = build_graph(surface=SURFACE)
        return compiled

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "surface": SURFACE}

    @app.post("/chat")
    async def chat(body: ChatRequest) -> EventSourceResponse:
        return EventSourceResponse(_stream(get_graph, body))

    return app
