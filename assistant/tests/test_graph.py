"""Graph structure, routing, and the specialist wiring.

No network, no API keys: these must stay green in any environment.
"""

import json
import re

import pytest
from langchain_core.language_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGenerationChunk
from langgraph.graph import END

from chat_assistant.config import settings
from chat_assistant.graph.build import build_graph
from chat_assistant.graph.router import CHAT, FALLBACK, route, route_after_chat
from chat_assistant.graph.specialists.fallback import MESSAGE as FALLBACK_MESSAGE
from chat_assistant.graph.specialists.registry import (
    SPECIALISTS,
    TOOL_TO_SPECIALIST,
    available,
    bindable,
)
from chat_assistant.graph.specialists.research import FILLER, build_research


class ToolFake(GenericFakeChatModel):
    """Streams like a real provider and accepts bind_tools (the built-in
    fakes do neither, and stream_mode="messages" drives the async path)."""

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


def _call(name: str, args: dict | None = None) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args or {}, "id": "c1"}])


class FakeResearchGraph:
    async def ainvoke(self, state: dict, config: dict) -> dict:
        return {"messages": [AIMessage("- v1.7 shipped [LiveKit blog — https://blog.livekit.io]")]}


# --- registry ------------------------------------------------------------


def test_registry_keeps_tool_factory_and_gate_together() -> None:
    """Drift between these three is what armed a mid-turn crash."""
    assert set(SPECIALISTS) == {"research", "document_summary"}
    assert TOOL_TO_SPECIALIST == {"research": "research", "summarize_document": "document_summary"}
    for name, spec in SPECIALISTS.items():
        assert spec.tool.name in TOOL_TO_SPECIALIST
        assert TOOL_TO_SPECIALIST[spec.tool.name] == name


def test_specialists_gate_off_independently(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "")
    monkeypatch.setattr(settings, "enable_document_summary", False)
    assert available() == {}

    monkeypatch.setattr(settings, "enable_document_summary", True)
    assert set(available()) == {"document_summary"}


# --- routing -------------------------------------------------------------


def test_route_defaults_to_chat() -> None:
    assert route({"messages": [HumanMessage("hi")]}) == CHAT


def test_plain_reply_ends_the_turn() -> None:
    assert route_after_chat({"messages": [AIMessage("plain reply")]}) == END


def test_unavailable_specialist_is_not_routed_to() -> None:
    """The bug this prevents: a tool bound but whose node was never compiled
    routes to a branch the graph does not have, and LangGraph raises."""
    state = {"messages": [_call("research")]}
    assert route_after_chat(state, {"research"}) == "research"
    assert route_after_chat(state, {"document_summary"}) == FALLBACK


def test_unknown_tool_falls_back_visibly() -> None:
    """Successor to the deleted PlanValidator: a name outside the closed map
    executes no node, and the user must SEE that rather than get silence."""
    assert route_after_chat({"messages": [_call("launch_missiles")]}, {"research"}) == FALLBACK


async def test_fallback_node_produces_a_visible_message() -> None:
    fake = ToolFake(messages=iter([_call("launch_missiles")]))
    graph = build_graph(
        model=fake,
        specialists={"research": lambda llm: build_research(llm, agent_graph=FakeResearchGraph())},
    )
    result = await graph.ainvoke({"messages": [HumanMessage("do the thing")]})
    assert result["messages"][-1].content == FALLBACK_MESSAGE


# --- graph shape ---------------------------------------------------------


def test_keyless_graph_is_the_plain_fast_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tavily_api_key", "")
    monkeypatch.setattr(settings, "enable_document_summary", False)
    nodes = build_graph(model=GenericFakeChatModel(messages=iter([]))).get_graph().nodes
    assert CHAT in nodes
    assert not ({"research", "document_summary", FALLBACK} & set(nodes))


def test_only_available_specialists_are_bound_and_compiled() -> None:
    assert [t.name for t in bindable({"research"})] == ["research"]
    graph = build_graph(
        model=ToolFake(messages=iter([])),
        specialists={"research": lambda llm: build_research(llm, agent_graph=FakeResearchGraph())},
    )
    nodes = set(graph.get_graph().nodes)
    assert "research" in nodes and FALLBACK in nodes
    assert "document_summary" not in nodes


async def test_graph_round_trip_with_fake_model() -> None:
    # specialists={} pins the plain fast path: one LLM call, no tool binding.
    graph = build_graph(
        model=GenericFakeChatModel(messages=iter([AIMessage("canned reply")])), specialists={}
    )
    result = await graph.ainvoke({"messages": [HumanMessage("hello")]})
    assert result["messages"][-1].content == "canned reply"
    assert [type(m).__name__ for m in result["messages"]] == ["HumanMessage", "AIMessage"]


async def test_research_round_trip_offline() -> None:
    fake = ToolFake(messages=iter([_call("research", {"query": "livekit"}), AIMessage("summary")]))
    research_graph = FakeResearchGraph()
    graph = build_graph(
        model=fake,
        specialists={"research": lambda llm: build_research(llm, agent_graph=research_graph)},
    )

    fillers, result = [], None
    async for mode, data in graph.astream(
        {"messages": [HumanMessage("what changed?")]}, stream_mode=["custom", "values"]
    ):
        if mode == "custom":
            fillers.append(data)
        else:
            result = data

    assert fillers == [FILLER]
    assert result is not None
    # The raw findings must NOT be in state: stream_mode="messages" emits
    # everything a node returns, and both surfaces speak/print it verbatim.
    assert [type(m).__name__ for m in result["messages"]] == [
        "HumanMessage",
        "AIMessage",
        "AIMessage",
    ]
    assert not any(isinstance(m, ToolMessage) for m in result["messages"])
    assert result["messages"][-1].content == "summary"
