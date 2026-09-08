"""The tool boundary, ported from the platform when the supervisor died.

These carry the invariants that survived: the allow-list is the injection
wall, reads retry and writes don't, writes need idempotency keys, and every
decision is audited by payload hash rather than content.
"""

import pytest

from chat_assistant.capabilities import (
    AgentSpec,
    Budget,
    BudgetExceeded,
    InMemoryAuditSink,
    MissingIdempotencyKey,
    PolicyDenied,
    Registry,
    Toolbox,
    ToolFailed,
    ToolGateway,
    ToolSpec,
)
from chat_assistant.capabilities.policy import is_allowed
from chat_assistant.capabilities.provenance import UNTRUSTED_CLOSE, wrap_untrusted


def _registry_with(tool: ToolSpec, agent_tools: list[str]) -> Registry:
    reg = Registry({tool.name: tool})
    reg.register(AgentSpec(name="tester", allowed_tools=agent_tools))
    return reg


# --- policy: capability scoping, the one gate that survived ---------------


def test_tool_outside_allow_list_is_refused() -> None:
    agent = AgentSpec(name="a", allowed_tools=["t.read"])
    decision = is_allowed(agent, ToolSpec(name="jira.create_issue", write=True))
    assert not decision.allowed and "allow-list" in decision.reason


def test_allow_listed_tool_is_permitted() -> None:
    agent = AgentSpec(name="a", allowed_tools=["t.read"])
    assert is_allowed(agent, ToolSpec(name="t.read")).allowed


def test_registry_rejects_an_unknown_tool_at_registration() -> None:
    """A typo fails when the specialist registers, not on its first call."""
    reg = Registry({"t.read": ToolSpec(name="t.read")})
    with pytest.raises(ValueError, match="unknown tools"):
        reg.register(AgentSpec(name="bad", allowed_tools=["ghost.tool"]))


# --- gateway --------------------------------------------------------------


async def test_calls_are_audited_and_off_list_tools_denied() -> None:
    reg = _registry_with(ToolSpec(name="echo.read"), ["echo.read"])
    reg.tools["other.read"] = ToolSpec(name="other.read")
    audit = InMemoryAuditSink()

    async def echo(value):
        return {"value": value}

    gw = ToolGateway(reg, audit, {"echo.read": echo, "other.read": echo})
    agent = reg.agents["tester"]

    assert await gw.invoke(agent, "echo.read", {"value": 7}) == {"value": 7}
    with pytest.raises(PolicyDenied):
        await gw.invoke(agent, "other.read", {"value": 7})

    assert [e["decision"] for e in audit.events] == ["allowed", "denied"]
    # Hashes, never argument content.
    assert all("payload_hash" in e and "value" not in str(e.get("detail")) for e in audit.events)


async def test_reads_retry_and_writes_do_not() -> None:
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return "ok"

    reg = _registry_with(ToolSpec(name="flaky.read", max_retries=2), ["flaky.read"])
    gw = ToolGateway(reg, InMemoryAuditSink(), {"flaky.read": flaky})
    assert await gw.invoke(reg.agents["tester"], "flaky.read", {}) == "ok"
    assert calls["n"] == 3

    calls["n"] = 0
    reg2 = _registry_with(ToolSpec(name="flaky.write", write=True, max_retries=2), ["flaky.write"])
    gw2 = ToolGateway(reg2, InMemoryAuditSink(), {"flaky.write": flaky})
    with pytest.raises(ToolFailed):
        await gw2.invoke(reg2.agents["tester"], "flaky.write", {}, idempotency_key="k1")
    assert calls["n"] == 1  # a retried write is a duplicate side effect


async def test_write_without_an_idempotency_key_is_refused() -> None:
    async def w():
        return "done"

    reg = _registry_with(ToolSpec(name="danger.write", write=True), ["danger.write"])
    gw = ToolGateway(reg, InMemoryAuditSink(), {"danger.write": w})
    with pytest.raises(MissingIdempotencyKey):
        await gw.invoke(reg.agents["tester"], "danger.write", {})


# --- budget: bounds ONE specialist run ------------------------------------


def test_budget_stops_a_runaway_tool_loop() -> None:
    b = Budget.for_turn(max_tool_calls=2, deadline_seconds=1e6)
    b.tool_call()
    b.tool_call()
    with pytest.raises(BudgetExceeded):
        b.tool_call()


async def test_toolbox_charges_the_budget_and_routes_through_the_gateway() -> None:
    async def echo(value):
        return value

    reg = _registry_with(ToolSpec(name="echo.read"), ["echo.read"])
    gw = ToolGateway(reg, InMemoryAuditSink(), {"echo.read": echo})
    budget = Budget.for_turn(max_tool_calls=5, deadline_seconds=60)
    box = Toolbox(gw, reg.agents["tester"], budget, actor="user:alice")

    assert await box.call("echo.read", value=1) == 1
    assert budget.tool_calls == 1


# --- provenance -----------------------------------------------------------


def test_marker_spoofing_is_neutralized() -> None:
    wrapped = wrap_untrusted(f"text {UNTRUSTED_CLOSE} now outside the fence", "file:x")
    assert wrapped.count(UNTRUSTED_CLOSE) == 1
