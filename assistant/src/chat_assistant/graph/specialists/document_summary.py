"""Document summary — a tool-looping specialist behind the router.

Shape (mirrors research.py, with one addition that makes it SAFER):

  chat --summarize_document tool call--> document_summary node
    1. filler speech immediately (reading + embedding is slower than a search)
    2. gateway-mediated read -> parse
    3. STRUCTURED pass on a quiet model: untrusted text in, validated
       Pydantic out, one repair retry
    4. SYNTHESIS pass on the outer unbound llm: only VALIDATED FIELDS reach
       it, never the raw document

Step 3/4 is the point. research.py feeds its raw findings into synthesis;
here the schema is a sanitization boundary — injected prose that survives
into a field meets a model with no tools to abuse, and free-form "call this
tool" text is never executable because the intermediate contract is a
Pydantic model rather than a string.

Two things that are easy to get wrong and are load-bearing:
  * Budget is built PER INVOCATION. This closure is created once per worker
    process and shared by every session; a factory-level Budget would
    accumulate tool calls across callers and permanently exhaust.
  * The structured pass runs with disable_streaming=True, or stream_mode
    "messages" would emit raw JSON tokens — spoken aloud on voice.
"""

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from pydantic import BaseModel, ValidationError

from ...capabilities import AgentSpec, Budget, BudgetExceeded, Toolbox, build_gateway, registry
from ...capabilities.provenance import untrusted_notice, wrap_untrusted
from ...prompts import load_prompt
from ..state import AgentState
from . import emit_filler

logger = logging.getLogger("chat-assistant.document_summary")

FILLER = "Let me read through that and pull out the key points."
NAME = "document_summary"

# The allow-list IS the injection boundary: two read-only tools, so a
# document instructing the agent to act has nothing to escalate into.
#
# Indexing the document for later retrieval is deliberately NOT here. It
# would need `retrieval.index`, a WRITE tool, and wiring the store's
# index_document directly would be the one call bypassing the gateway —
# breaking the invariant this whole layer exists to keep. It lands when the
# write path gets idempotency keys, not before.
SPEC = AgentSpec(
    name=NAME,
    description="Summarizes an uploaded document into a structured result.",
    allowed_tools=["document.read", "document.parse"],
)


class ActionItem(BaseModel):
    task: str
    owner: str | None = None
    deadline: str | None = None


class DocumentSummaryResult(BaseModel):
    summary: str
    key_points: list[str] = []
    decisions: list[str] = []
    risks: list[str] = []
    action_items: list[ActionItem] = []


@tool
def summarize_document(attachment_id: str) -> str:
    """Summarize a document the user attached to this conversation. Use it
    when they ask what a file says, for its key points, decisions, risks, or
    action items. `attachment_id` is the id of an attachment on this turn —
    never invent one; if the user has not attached anything, say so."""
    raise NotImplementedError("schema only — executed by the document_summary node")


_STEER = {
    "voice": (
        "Answer from the summary fields below. Two or three sentences: lead with "
        "the overview, then at most two key points or risks. Never read lists, "
        "owners or deadlines aloud verbatim — offer to go deeper instead."
    ),
    "text": (
        "Answer from the summary fields below using markdown, with `## Summary`, "
        "`## Key points`, `## Decisions`, `## Risks` and `## Action items`. "
        "Omit any section that is empty."
    ),
}


def _render(result: DocumentSummaryResult, name: str) -> str:
    """Validated fields only — the raw document never reaches synthesis."""
    parts = [f"Document: {name}", f"Summary: {result.summary}"]
    for label, items in (
        ("Key points", result.key_points),
        ("Decisions", result.decisions),
        ("Risks", result.risks),
    ):
        if items:
            parts.append(label + ":\n" + "\n".join(f"- {i}" for i in items))
    if result.action_items:
        parts.append(
            "Action items:\n"
            + "\n".join(
                f"- {a.task}"
                + (f" (owner: {a.owner})" if a.owner else "")
                + (f" (due: {a.deadline})" if a.deadline else "")
                for a in result.action_items
            )
        )
    return "\n\n".join(parts)


def _parse(raw: str) -> DocumentSummaryResult:
    start, end = raw.index("{"), raw.rindex("}") + 1
    return DocumentSummaryResult.model_validate(json.loads(raw[start:end]))


def build_document_summary(
    llm: BaseChatModel,
    gateway=None,
    surface: str = "voice",
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    """Node factory. `gateway` is injectable so tests run with fakes."""
    steer = _STEER[surface]
    # Internal reasoning must never reach TTS (see module docstring).
    quiet = llm.model_copy(update={"disable_streaming": True})

    async def document_summary_node(state: AgentState) -> dict[str, Any]:
        emit_filler(FILLER)

        gw = gateway if gateway is not None else build_gateway()
        registry().register(SPEC)
        actor = state.get("actor", "anon")

        last = state["messages"][-1]
        tool_messages: list[ToolMessage] = []

        for call in getattr(last, "tool_calls", []) or []:
            # Guard on the tool name: with more than one specialist bound, a
            # turn can carry calls meant for a different node.
            if call["name"] != "summarize_document":
                continue

            # Per invocation, never per factory.
            budget = Budget.for_surface(surface)
            box = Toolbox(gw, SPEC, budget, actor=actor)
            attachment_id = str(call["args"].get("attachment_id", ""))

            try:
                async with asyncio.timeout(budget.remaining_seconds()):
                    meta = await box.call("document.read", attachment_id=attachment_id)
                    parsed = await box.call("document.parse", attachment_id=attachment_id)
                    text, name = parsed["text"], parsed["name"]
                    result = await _summarize(quiet, text, name)
            except TimeoutError:
                logger.warning("document summary timed out (%s)", surface)
                content = f"Reading {attachment_id!r} took too long to finish."
            except BudgetExceeded as exc:
                logger.warning("document summary budget: %s", exc)
                content = "I ran out of room reading that document."
            except Exception as exc:  # tool/parse failures are answerable, not fatal
                logger.warning("document summary failed: %s", exc, exc_info=True)
                content = f"I couldn't read that document: {exc}"
            else:
                content = _render(result, name) + f"\n\n({meta['bytes']} bytes)"

            tool_messages.append(ToolMessage(content=content, tool_call_id=call["id"]))

        reply = await llm.ainvoke([*state["messages"], *tool_messages, SystemMessage(steer)])
        # ONLY the reply enters state — a ToolMessage here would be spoken or
        # printed verbatim by both surfaces.
        return {"messages": [reply]}

    return document_summary_node


async def _summarize(quiet: BaseChatModel, text: str, name: str) -> DocumentSummaryResult:
    """Structured pass with one repair retry. Untrusted text is fenced."""
    messages = [
        SystemMessage(f"{load_prompt('document_summary')}\n\n{untrusted_notice()}"),
        HumanMessage(f"Document:\n{wrap_untrusted(text, name)}"),
    ]
    raw = str((await quiet.ainvoke(messages)).content)
    try:
        return _parse(raw)
    except (ValueError, ValidationError):
        repair = [*messages, HumanMessage("That was not valid JSON. Reply with ONLY the object.")]
        return _parse(str((await quiet.ainvoke(repair)).content))
