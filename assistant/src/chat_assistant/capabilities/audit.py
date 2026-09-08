"""Audit sink — every gateway decision is recorded.

Payload HASHES, never argument content. The task/approval repositories
that used to live here died with the supervisor; a turn is not a stored
record any more, so the audit log is the only durable trace of what a
specialist actually did."""

import json
from datetime import UTC, datetime
from typing import Any, Protocol


class AuditSink(Protocol):
    async def emit(self, **event: Any) -> None: ...
    async def for_turn(self, turn_id: str) -> list[dict]: ...


class InMemoryAuditSink:
    def __init__(self) -> None:
        self.events: list[dict] = []

    async def emit(self, **event):
        event.setdefault("ts", datetime.now(UTC))
        self.events.append(event)

    async def for_turn(self, turn_id):
        return [e for e in self.events if e.get("turn_id") == turn_id]


class PgAuditSink:
    """Takes a pool GETTER, not a pool: constructing the sink must not open a
    connection, so a worker still boots with the database down."""

    def __init__(self, get_pool) -> None:
        self._get_pool = get_pool

    async def emit(self, **event):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO audit_events "
                "(turn_id, actor, event, agent, tool, decision, latency_ms, payload_hash, detail) "
                "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)",
                event.get("turn_id"),
                event.get("actor", "system"),
                event.get("event", "event"),
                event.get("agent"),
                event.get("tool"),
                event.get("decision"),
                event.get("latency_ms"),
                event.get("payload_hash"),
                json.dumps(event.get("detail", {})),
            )

    async def for_turn(self, turn_id):
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM audit_events WHERE turn_id = $1 ORDER BY id", turn_id
            )
        return [dict(r) for r in rows]
