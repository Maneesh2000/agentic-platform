"""The node that makes a dead-end audible.

The chat model can emit a tool call the graph cannot serve — a hallucinated
name, or a specialist whose credentials are not configured. That message has
empty content, and both surfaces drop empty content, so without this node the
user gets silence and nothing is logged.

This is the visible half of the guarantee the PlanValidator used to give.
"""

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from langchain_core.messages import AIMessage

from ..state import AgentState

logger = logging.getLogger("chat-assistant.fallback")

MESSAGE = "I can't do that right now — that capability isn't available. Can I help another way?"


def build_fallback() -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    async def fallback(state: AgentState) -> dict[str, Any]:
        last = state["messages"][-1]
        names = [c.get("name") for c in (getattr(last, "tool_calls", []) or [])]
        logger.warning("unroutable tool call(s): %s", names)
        return {"messages": [AIMessage(MESSAGE)]}

    return fallback
