"""The single chokepoint between agents and the outside world.

Every invocation: policy check → audit → timeout → (reads only) retry →
structured error. Agents never hold credentials, never call externals
directly, and never see a tool outside their registry allow-list.

Write tools additionally require a caller-supplied idempotency key which is
recorded BEFORE the outbound call; a replay returns the recorded response
instead of re-issuing the side effect. v1 ships zero write tools — the
mechanism exists now so increment 3's jira.create_issue can't ship without
it (and it is unit-tested against a fake write tool).
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from .errors import MissingIdempotencyKey, PolicyDenied, ToolFailed, ToolTimeout
from .policy import is_allowed
from .registry import Registry
from .specs import AgentSpec

logger = logging.getLogger("platform.gateway")

ToolFn = Callable[..., Awaitable[Any]]


def _args_hash(tool: str, args: dict) -> str:
    canonical = json.dumps({"tool": tool, "args": args}, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


class ToolGateway:
    def __init__(self, registry: Registry, audit, tool_impls: dict[str, ToolFn]) -> None:
        self._registry = registry
        self._audit = audit
        self._impls = tool_impls
        self._write_results: dict[str, Any] = {}  # idempotency_key -> recorded response

    async def invoke(
        self,
        agent: AgentSpec,
        tool_name: str,
        args: dict[str, Any],
        *,
        actor: str = "anonymous",
        idempotency_key: str | None = None,
    ) -> Any:
        tool = self._registry.tools.get(tool_name)
        payload_hash = _args_hash(tool_name, args)
        started = time.monotonic()

        async def audit(decision: str, detail: dict | None = None) -> None:
            await self._audit.emit(
                turn_id=None,
                actor=f"{actor}/agent:{agent.name}",
                event="tool_call",
                agent=agent.name,
                tool=tool_name,
                decision=decision,
                latency_ms=int((time.monotonic() - started) * 1000),
                payload_hash=payload_hash,
                detail=detail or {},
            )

        if tool is None:
            await audit("denied", {"reason": "unknown tool"})
            raise PolicyDenied(f"unknown tool {tool_name!r}")

        decision = is_allowed(agent, tool)
        if not decision.allowed:
            await audit("denied", {"reason": decision.reason})
            raise PolicyDenied(decision.reason)

        if tool.write:
            if not idempotency_key:
                await audit("denied", {"reason": "missing idempotency key"})
                raise MissingIdempotencyKey(tool_name)
            if idempotency_key in self._write_results:
                await audit("replayed")
                return self._write_results[idempotency_key]
            # Record intent BEFORE the outbound call, so a crash between
            # call and record can be reconciled rather than re-issued.
            self._write_results[idempotency_key] = None

        impl = self._impls.get(tool_name)
        if impl is None:
            await audit("failed", {"reason": "no implementation registered"})
            raise ToolFailed(tool_name, "no implementation registered")

        attempts = 1 if tool.write else max(1, tool.max_retries + 1)
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                result = await asyncio.wait_for(impl(**args), timeout=tool.timeout_s)
                if tool.write and idempotency_key:
                    self._write_results[idempotency_key] = result
                await audit("allowed", {"attempt": attempt + 1})
                return result
            except TimeoutError:
                last_error = ToolTimeout(tool_name, tool.timeout_s)
            except Exception as exc:  # structured error surface for agents
                last_error = ToolFailed(tool_name, str(exc))
        await audit("failed", {"attempts": attempts, "error": str(last_error)})
        raise last_error  # type: ignore[misc]
