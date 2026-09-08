"""What a specialist actually holds: not credentials, not clients — a narrow
handle that routes every call through the gateway and charges the budget."""

from typing import Any

from .budget import Budget
from .gateway import ToolGateway
from .specs import AgentSpec


class Toolbox:
    def __init__(
        self,
        gateway: ToolGateway,
        agent: AgentSpec,
        budget: Budget,
        actor: str = "anonymous",
    ) -> None:
        self._gateway = gateway
        self._agent = agent
        self._budget = budget
        self._actor = actor

    async def call(self, tool: str, **args: Any) -> Any:
        self._budget.tool_call()
        return await self._gateway.invoke(self._agent, tool, args, actor=self._actor)
