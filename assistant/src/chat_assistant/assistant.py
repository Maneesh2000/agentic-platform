"""The one LiveKit Agent — a single voice and persona.

Orchestration rule: LiveKit handoffs own *who is talking*; the LangGraph in
`graph/` owns *how the thinking is organized* behind this one voice. Future
specialists become graph subgraphs, not additional LiveKit agents — two
routers competing over one decision is the failure mode to avoid.
"""

from livekit.agents import Agent

from .prompts import load_prompt
from .tools import TOOLS


class Assistant(Agent):
    def __init__(self) -> None:
        super().__init__(instructions=load_prompt("assistant"), tools=TOOLS)

    async def on_enter(self) -> None:
        await self.session.generate_reply(
            instructions=(
                "Greet the user in one short sentence and offer your help. "
                "If they already said what they need, help with that directly."
            )
        )
