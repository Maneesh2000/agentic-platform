"""Both branch points of the graph — one router owns the decision.

Fast-path rule: ordinary turns must never pay extra latency, so there is
deliberately NO separate router LLM call. The chat model itself decides by
tool binding: if it emits a specialist tool call, `route_after_chat` sends
the turn to that specialist; otherwise the turn ends after one LLM call.

`route_after_chat` is also the successor to the deleted PlanValidator. The
supervisor's guarantee was "nothing the planner says executes directly";
here `TOOL_TO_SPECIALIST` is a closed map, so a tool name outside it
resolves to no node at all. That must be VISIBLE rather than silent — an
unmatched call routes to `fallback`, because the chat node's tool-call
message has empty content and both surfaces drop empty content, which would
otherwise leave the user with silence and no error anywhere.
"""

from .specialists.registry import TOOL_TO_SPECIALIST
from .state import AgentState

CHAT = "chat"
FALLBACK = "fallback"


def route(state: AgentState) -> str:
    return CHAT


def route_after_chat(state: AgentState, available: set[str] | None = None) -> str:
    """chat -> specialist | fallback | END.

    `available` is the set of specialist nodes actually compiled into this
    graph. A tool whose specialist is registered but not available (its
    credentials are unset) must NOT be returned as a branch target — that
    branch does not exist in the path map and LangGraph would raise
    mid-turn.
    """
    last = state["messages"][-1]
    calls = getattr(last, "tool_calls", []) or []
    if not calls:
        return "__end__"
    for call in calls:
        target = TOOL_TO_SPECIALIST.get(call["name"])
        if target and (available is None or target in available):
            return target
    return FALLBACK
