"""Specialist subgraphs, keyed by routing name.

Adding a specialist:
  1. Build it in its own module (see research.py / document_summary.py): a
     schema-only @tool the chat LLM sees, plus a `build_<name>(llm, ...)`
     node factory with injectable internals for offline tests. Return ONLY
     the reply from the node — never a ToolMessage, which both surfaces
     would speak or print verbatim. Emit structured output internally where
     the input is untrusted; a validated model is not executable the way a
     free-form string is.
  2. Add one entry to SPECIALISTS below. The tool schema and the
     credential gate travel WITH it, so the three cannot drift apart —
     which is what previously armed a crash when only one of two
     specialists was available.
  3. Nothing else. `available()` and `bindable()` derive from this table.

Specialists are graph nodes, never additional LiveKit agents — one router
owns the decision (router.py).
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import Any

from ...config import settings
from .document_summary import build_document_summary, summarize_document
from .research import build_research, research


@dataclass(frozen=True)
class Specialist:
    factory: Callable[..., Any]
    tool: Any  # the schema-only @tool bound to the chat LLM
    enabled: Callable[[], bool]  # credentials/flag gate, read at build time


SPECIALISTS: dict[str, Specialist] = {
    "research": Specialist(
        factory=build_research,
        tool=research,
        enabled=lambda: bool(settings.tavily_api_key),
    ),
    "document_summary": Specialist(
        factory=build_document_summary,
        tool=summarize_document,
        enabled=lambda: settings.enable_document_summary,
    ),
}

# LLM tool name -> routing name (consumed by router.route_after_chat)
TOOL_TO_SPECIALIST: dict[str, str] = {s.tool.name: name for name, s in SPECIALISTS.items()}


def available(surface: str = "voice") -> dict[str, Callable[..., Any]]:
    """Specialists whose gate is satisfied, with `surface` bound in so each
    can shape output for how it will be delivered.

    A specialist that is registered but NOT available must not be bound to
    the chat model either — see bindable(). Binding a tool whose node was
    never compiled lets the model emit a call that routes to a branch the
    graph does not have.
    """
    return {
        name: partial(s.factory, surface=surface) for name, s in SPECIALISTS.items() if s.enabled()
    }


def bindable(names) -> list[Any]:
    """The tool schemas for exactly the specialists compiled into the graph."""
    return [SPECIALISTS[n].tool for n in names if n in SPECIALISTS]
