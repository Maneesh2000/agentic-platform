"""Bounds ONE specialist run — deterministic, enforced by code.

A prompt saying "use at most 5 tools" is not a budget.

What changed when the supervisor died: there is no plan, so `max_steps` went
with it, and cancellation is no longer cooperative — on voice, a barge-in is
LiveKit cancelling the asyncio task, which raises CancelledError on its own.
What remains is a tool-call ceiling and a wall clock, and the deadline is
surface-aware because a 2-minute silence is fine in text and unacceptable
in a live call.

Construct one PER INVOCATION, never per node factory: a node closure is built
once per worker process and shared by every session, so a factory-level
Budget would accumulate across callers and permanently exhaust.
"""

import time
from dataclasses import dataclass

from ..config import settings


class BudgetExceeded(Exception):
    pass


@dataclass
class Budget:
    max_tool_calls: int = 0
    deadline_at: float = 0.0  # monotonic
    tool_calls: int = 0

    @classmethod
    def for_turn(cls, *, max_tool_calls: int | None = None, deadline_seconds: float) -> "Budget":
        return cls(
            max_tool_calls=max_tool_calls
            if max_tool_calls is not None
            else settings.budget_max_tool_calls,
            deadline_at=time.monotonic() + deadline_seconds,
        )

    @classmethod
    def for_surface(cls, surface: str) -> "Budget":
        return cls.for_turn(
            deadline_seconds=settings.budget_deadline_seconds_voice
            if surface == "voice"
            else settings.budget_deadline_seconds_text
        )

    def check(self) -> None:
        if time.monotonic() > self.deadline_at:
            raise BudgetExceeded("deadline exceeded")
        if self.tool_calls > self.max_tool_calls:
            raise BudgetExceeded(f"max_tool_calls {self.max_tool_calls} exceeded")

    def tool_call(self) -> None:
        self.tool_calls += 1
        self.check()

    def remaining_seconds(self) -> float:
        return max(0.0, self.deadline_at - time.monotonic())
