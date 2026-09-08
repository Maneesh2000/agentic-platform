"""Registry schemas. A tool exists only if tools.yaml declares it, and a
specialist may only reach the tools its AgentSpec allow-lists."""

from typing import Literal

from pydantic import BaseModel

RiskLevel = Literal["low", "medium", "high"]


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    # The read/write split is load-bearing: the gateway auto-retries READS
    # ONLY; a write retried after a timeout is a duplicate side effect.
    write: bool = False
    requires_approval: bool = False
    max_retries: int = 2  # applied to reads; writes never auto-retry
    timeout_s: float = 30.0
    risk_level: RiskLevel = "low"


class AgentSpec(BaseModel):
    """A specialist's capability scope. `allowed_tools` is the injection
    boundary — the closed set of tools this specialist may reach."""

    name: str
    version: str = "0.1.0"
    description: str = ""
    allowed_tools: list[str] = []
    risk_level: RiskLevel = "low"
    prompt_version: str = "v1"
