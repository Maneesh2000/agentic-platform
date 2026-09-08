"""Assemble the brain: START -> route -> chat -> (specialist |fallback) -> END.

Specialists attach only when their gate is satisfied, and the chat model is
bound to EXACTLY the tools whose nodes were compiled. Binding a tool whose
node is absent lets the model emit a call that routes to a branch the graph
does not have — a crash mid-turn, and one that only appears once a second
specialist exists.

A keyless worker compiles the plain fast-path graph: chat -> END.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..models import graph_model_id
from .router import CHAT, FALLBACK, route, route_after_chat
from .specialists.fallback import build_fallback
from .specialists.registry import available, bindable
from .state import AgentState


def build_graph(
    model: BaseChatModel | None = None,
    specialists: dict[str, Callable[..., Any]] | None = None,
    surface: str = "voice",
) -> CompiledStateGraph:
    """Compile the graph. `model` and `specialists` are injectable so tests
    run with fakes — no network, no keys."""
    llm = model or init_chat_model(graph_model_id())
    specs = available(surface) if specialists is None else specialists

    # Bind only what exists. Keeps the keyless fast path byte-identical to
    # the pre-specialist graph, and keeps tools and nodes in lockstep.
    chat_llm = llm.bind_tools(bindable(specs)) if specs else llm

    async def chat(state: AgentState) -> AgentState:
        return {"messages": [await chat_llm.ainvoke(state["messages"])]}

    builder = StateGraph(AgentState)
    builder.add_node(CHAT, chat)
    builder.add_conditional_edges(START, route, {CHAT: CHAT})

    if not specs:
        builder.add_edge(CHAT, END)
    else:
        for name, factory in specs.items():
            builder.add_node(name, factory(llm))
            builder.add_edge(name, END)
        builder.add_node(FALLBACK, build_fallback())
        builder.add_edge(FALLBACK, END)

        compiled = set(specs)
        builder.add_conditional_edges(
            CHAT,
            lambda state: route_after_chat(state, compiled),
            {END: END, FALLBACK: FALLBACK, **{n: n for n in specs}},
        )

    # No checkpointer, deliberately: both surfaces pass the full history on
    # every turn (LiveKit's ChatContext, or the web app's stored thread), so
    # graph-side thread memory would double-count.
    return builder.compile()
