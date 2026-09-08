"""The closed tool set, plus which specialist may reach which tool.

Tools are declared in tools.yaml — that file is the whole universe of things
any specialist can call. Specialists register their own allow-list in code
(next to the node that uses it) rather than in a YAML of "agents", because a
specialist IS a graph node now: there is no separate registry of dispatchable
agents since the supervisor was removed and the chat model routes by tool call.

`register()` validates the allow-list against the tool set, so a typo fails at
registration instead of at the first call.
"""

from pathlib import Path

import yaml

from .specs import AgentSpec, ToolSpec

_DIR = Path(__file__).parent


class Registry:
    def __init__(self, tools: dict[str, ToolSpec]) -> None:
        self.tools = tools
        self.agents: dict[str, AgentSpec] = {}

    @classmethod
    def load(cls, tools_path: Path | None = None) -> "Registry":
        raw = yaml.safe_load((tools_path or _DIR / "tools.yaml").read_text()) or {}
        return cls({name: ToolSpec(name=name, **spec) for name, spec in raw.items()})

    def register(self, agent: AgentSpec) -> AgentSpec:
        unknown = [t for t in agent.allowed_tools if t not in self.tools]
        if unknown:
            raise ValueError(f"agent {agent.name!r} references unknown tools: {unknown}")
        self.agents[agent.name] = agent
        return agent
