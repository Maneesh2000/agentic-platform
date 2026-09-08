"""Research Agent — a tool-looping specialist behind the router.

Shape (voice latency and UX drive every choice):

  chat (tool-bound LLM) --research tool call--> research node
    1. speak filler IMMEDIATELY via get_stream_writer() so the user hears
       something while the loop runs (stream_mode "custom" is enabled)
    2. run a bounded ReAct loop (create_agent) with the research tools:
       web_search / open_webpage / search_official, under prompts/research.md
       (search -> open pages -> prefer official sources -> cross-check ->
       cited findings)
    3. wrap the findings as a ToolMessage and synthesize the spoken reply
       with the outer UNBOUND llm — one hop, no re-research loop

The `research` @tool below is schema-only: it is what the main agent's LLM
sees and calls; execution happens here. Decoupling the two keeps the tool
name stable for the router and lets tests inject fakes.

GOTCHA (load-bearing): stream_mode "messages" surfaces tokens from EVERY
chat-model call in the run, so the research loop's internal reasoning would
be read aloud. The loop therefore runs on a model copy with
disable_streaming=True — no token callbacks, nothing spoken — and only the
outer synthesis streams to TTS.
"""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, tool

from ...config import settings
from ...prompts import load_prompt
from ..state import AgentState
from . import emit_filler

FILLER = "Let me look into that for you."


class _InvocableGraph(Protocol):
    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]: ...


@tool
def research(query: str) -> str:
    """Delegate to the research agent: web search, opening pages, official
    sources, cross-checked and cited findings. Use for questions that need
    fresh, niche, or verifiable information you do not reliably know —
    news, releases, prices, weather, specific technical or factual claims.
    Never use it for conversation, opinions, or things you already know."""
    raise NotImplementedError("schema only — executed by the research node")


def build_research_tools() -> list[BaseTool]:
    """The Research Agent's real tools, over langchain-tavily."""
    from langchain_tavily import TavilyExtract, TavilySearch

    searcher = TavilySearch(tavily_api_key=settings.tavily_api_key, max_results=5)
    extractor = TavilyExtract(tavily_api_key=settings.tavily_api_key)

    @tool
    async def web_search(query: str) -> str:
        """Search the public web. Returns titles, URLs, and snippets."""
        return str(await searcher.ainvoke({"query": query}))

    @tool
    async def open_webpage(url: str) -> str:
        """Open one webpage and return its extracted content. Only cite
        pages you have opened."""
        return str(await extractor.ainvoke({"urls": [url]}))

    @tool
    async def search_official(query: str, domains: list[str]) -> str:
        """Search restricted to official/primary domains (e.g.
        ["docs.livekit.io", "github.com"]) for authoritative answers."""
        return str(await searcher.ainvoke({"query": query, "include_domains": domains}))

    return [web_search, open_webpage, search_official]


def _build_agent_graph(llm: BaseChatModel, tools: Sequence[BaseTool]) -> Any:
    from langchain.agents import create_agent

    # disable_streaming: internal reasoning must never reach TTS (see module
    # docstring). BaseChatModel is pydantic, so model_copy is available.
    quiet_llm = llm.model_copy(update={"disable_streaming": True})
    return create_agent(quiet_llm, list(tools), system_prompt=load_prompt("research"))


# How the outer model is told to present findings. Voice must stay speakable
# and never recite URLs; text chat wants the links kept so they're clickable.
_STEER = {
    "voice": (
        "Answer using the research findings in the tool result. Be concise "
        "and speakable; mention source names, never URLs."
    ),
    "text": (
        "Answer using the research findings in the tool result. Use markdown, "
        "and cite each source by name with its link."
    ),
}


def build_research(
    llm: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    agent_graph: _InvocableGraph | None = None,
    surface: str = "voice",
) -> Callable[[AgentState], Awaitable[dict[str, Any]]]:
    """Node factory. `tools` / `agent_graph` are injectable so tests run
    offline; production builds the ReAct loop over the Tavily tools.
    `surface` selects how findings are presented (see _STEER)."""
    graph = agent_graph or _build_agent_graph(llm, tools or build_research_tools())
    steer_text = _STEER[surface]

    async def research_node(state: AgentState) -> dict[str, Any]:
        emit_filler(FILLER)

        last = state["messages"][-1]
        tool_messages: list[ToolMessage] = []
        for call in getattr(last, "tool_calls", []) or []:
            # Guard on the tool name: with more than one specialist bound a
            # turn can carry calls meant for another node, and without this
            # they would run a search on an empty query.
            if call["name"] != "research":
                continue
            query = str(call["args"].get("query", ""))
            result = await graph.ainvoke(
                {"messages": [HumanMessage(query)]},
                {"recursion_limit": settings.research_recursion_limit},
            )
            findings = str(result["messages"][-1].content)
            tool_messages.append(ToolMessage(content=findings, tool_call_id=call["id"]))

        # Unbound llm + a hard steer shaped to the surface: the findings are
        # written notes with URLs, and how they may be presented differs
        # between speech and text (see _STEER).
        reply = await llm.ainvoke([*state["messages"], *tool_messages, SystemMessage(steer_text)])

        # ONLY the reply goes back into state — never the raw ToolMessage.
        # Anything a node returns is emitted on stream_mode="messages", and
        # both surfaces treat every streamed message as assistant output
        # (LiveKit's _to_chat_chunk falls through to any object with a
        # `.content`). Returning the findings would therefore read the
        # internal notes, URLs and all, straight after the summary.
        # The findings still reach the answer — they are in the synthesis
        # call above — and neither surface replays raw graph state (voice
        # rebuilds from LiveKit's ChatContext, text from stored turns), so
        # dropping them here costs nothing.
        return {"messages": [reply]}

    return research_node
