-- Application state lives in Postgres (the vector index is NOT the source
-- of truth). Single-tenant deployment: tenant_id kept as a column with a
-- default so the schema survives if that decision changes.

CREATE EXTENSION IF NOT EXISTS vector;

-- Carry a pre-supervisor-removal database forward. CREATE TABLE IF NOT
-- EXISTS silently keeps an existing table's old shape, so a dev database
-- created before the supervisor was deleted would keep audit_events.task_id
-- and fail every insert. Both blocks are idempotent.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'audit_events' AND column_name = 'task_id'
    ) THEN
        ALTER TABLE audit_events RENAME COLUMN task_id TO turn_id;
        ALTER TABLE audit_events ALTER COLUMN turn_id TYPE text USING turn_id::text;
    END IF;
END $$;

-- The supervisor's tables. Nothing can read them any more: the task API,
-- the runner and the approval flow were all deleted with it.
DROP TABLE IF EXISTS approvals;
DROP TABLE IF EXISTS tasks;

CREATE TABLE IF NOT EXISTS audit_events (
    id           bigserial PRIMARY KEY,
    turn_id      text,
    ts           timestamptz NOT NULL DEFAULT now(),
    actor        text NOT NULL,           -- user:<id> | agent:<name> | system
    event        text NOT NULL,           -- tool_call | policy_decision | state | ...
    agent        text,
    tool         text,
    decision     text,
    latency_ms   integer,
    payload_hash text,                    -- hash, never content
    detail       jsonb NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS audit_events_turn_idx ON audit_events (turn_id, id);

CREATE TABLE IF NOT EXISTS documents (
    id             uuid PRIMARY KEY,
    tenant_id      text NOT NULL DEFAULT 'default',
    source         text NOT NULL,          -- e.g. file:report.pdf
    title          text,
    classification text NOT NULL DEFAULT 'internal',
    allowed_roles  text[] NOT NULL DEFAULT '{reader}',
    created_at     timestamptz NOT NULL DEFAULT now()
);

-- EMBEDDING_DIM in config must match vector(1536); changing dimension is a
-- migration, enforced by a startup check.
CREATE TABLE IF NOT EXISTS chunks (
    id          bigserial PRIMARY KEY,
    document_id uuid NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
    seq         integer NOT NULL,
    text        text NOT NULL,
    embedding   vector(1536) NOT NULL
);
CREATE INDEX IF NOT EXISTS chunks_document_idx ON chunks (document_id, seq);
