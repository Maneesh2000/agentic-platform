"""Capability scoping — the one gate that survived the supervisor.

This is NOT user authorization (there are no roles any more; every caller
reaches the assistant through the chat input). It is the injection boundary:
a specialist may only reach the tools its registry entry allow-lists, so a
document saying "call jira.create_issue" finds no such tool within reach.
Asserted by tests/test_injection.py."""

from dataclasses import dataclass

from .specs import AgentSpec, ToolSpec


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def is_allowed(agent: AgentSpec, tool: ToolSpec) -> Decision:
    if tool.name not in agent.allowed_tools:
        return Decision(False, f"tool {tool.name!r} not in agent {agent.name!r} allow-list")
    # `requires_approval` does not block: no write tool ships yet, and the
    # pause/approve mechanism must land here before one does.
    return Decision(True, "ok")
