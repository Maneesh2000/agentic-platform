"""Behavioral evals (LLM-as-judge), run with the configured LLM provider.

Skipped unless the provider's API key env (per LLM_MODEL) is set.
"""

import os

import pytest
from livekit.agents import AgentSession

from chat_assistant.assistant import Assistant
from chat_assistant.models import build_direct_llm, required_llm_key_env

_KEY_ENV = required_llm_key_env()

pytestmark = pytest.mark.skipif(
    not os.getenv(_KEY_ENV),
    reason=f"{_KEY_ENV} not set — behavioral evals need the configured LLM",
)


async def test_offers_assistance() -> None:
    async with build_direct_llm() as judge, AgentSession(llm=build_direct_llm()) as session:
        await session.start(Assistant())
        result = await session.run(user_input="Hello!")
        await (
            result.expect.next_event()
            .is_message(role="assistant")
            .judge(judge, intent="Greets the user in a friendly way and/or offers help.")
        )


async def test_grounding() -> None:
    async with build_direct_llm() as judge, AgentSession(llm=build_direct_llm()) as session:
        await session.start(Assistant())
        result = await session.run(user_input="What city was I born in?")
        await (
            result.expect.next_event()
            .is_message(role="assistant")
            .judge(
                judge,
                intent=(
                    "Does not claim to know the user's birthplace; may explain it "
                    "lacks that information and offer help with something else."
                ),
            )
        )
