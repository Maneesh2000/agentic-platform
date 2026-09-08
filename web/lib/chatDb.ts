// Conversation storage for the text surface. Same pattern as lib/db.ts:
// web-owned tables (app_ prefix) in the shared pgvector database, created
// lazily and idempotently so a down database fails the request, not the boot.
//
// Text history lives here; voice sessions stay ephemeral by design (LiveKit
// holds their context for the life of the room). Unifying the two later means
// having the worker write to these same tables — nothing here prevents it.
import { pool } from "@/lib/db";

const globalForChat = globalThis as unknown as { chatReady?: Promise<unknown> };

export function ensureChatTables(): Promise<unknown> {
  globalForChat.chatReady ??= pool.query(`
    CREATE TABLE IF NOT EXISTS app_conversations (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id    text NOT NULL,
      title      text NOT NULL DEFAULT 'New chat',
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS app_conversations_user_idx
      ON app_conversations (user_id, updated_at DESC);

    CREATE TABLE IF NOT EXISTS app_messages (
      id              bigserial PRIMARY KEY,
      conversation_id uuid NOT NULL
        REFERENCES app_conversations (id) ON DELETE CASCADE,
      role            text NOT NULL CHECK (role IN ('user', 'assistant')),
      content         text NOT NULL,
      created_at      timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS app_messages_conv_idx
      ON app_messages (conversation_id, id);

    -- Attachments live in Postgres rather than on disk so the Next.js
    -- container and the Python assistant can both reach them without a
    -- shared filesystem -- which is what makes this work in Kubernetes
    -- with no ReadWriteMany volume. Fine for small documents; the upload
    -- route caps size accordingly.
    CREATE TABLE IF NOT EXISTS app_uploads (
      id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      user_id    text NOT NULL,
      filename   text NOT NULL,
      mime       text NOT NULL DEFAULT 'application/octet-stream',
      content    bytea NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS app_uploads_user_idx
      ON app_uploads (user_id, created_at DESC);
  `).catch((err) => {
    // Never memoize a FAILED promise — see lib/db.ts.
    globalForChat.chatReady = undefined;
    throw err;
  });
  return globalForChat.chatReady;
}

export interface Conversation {
  id: string;
  title: string;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export async function listConversations(userId: string): Promise<Conversation[]> {
  await ensureChatTables();
  const { rows } = await pool.query<Conversation>(
    `SELECT id, title, updated_at FROM app_conversations
     WHERE user_id = $1 ORDER BY updated_at DESC LIMIT 100`,
    [userId],
  );
  return rows;
}

export async function createConversation(userId: string): Promise<Conversation> {
  await ensureChatTables();
  const { rows } = await pool.query<Conversation>(
    `INSERT INTO app_conversations (user_id) VALUES ($1)
     RETURNING id, title, updated_at`,
    [userId],
  );
  return rows[0];
}

// Every read is scoped by user_id, so one user can never address another's
// conversation by guessing its id.
export async function getMessages(
  userId: string,
  conversationId: string,
): Promise<ChatMessage[] | null> {
  await ensureChatTables();
  const owned = await pool.query(
    "SELECT 1 FROM app_conversations WHERE id = $1 AND user_id = $2",
    [conversationId, userId],
  );
  if (owned.rowCount === 0) return null;

  const { rows } = await pool.query<ChatMessage>(
    "SELECT role, content FROM app_messages WHERE conversation_id = $1 ORDER BY id",
    [conversationId],
  );
  return rows;
}

export async function appendMessage(
  userId: string,
  conversationId: string,
  message: ChatMessage,
): Promise<boolean> {
  await ensureChatTables();
  const owned = await pool.query(
    "SELECT title FROM app_conversations WHERE id = $1 AND user_id = $2",
    [conversationId, userId],
  );
  if (owned.rowCount === 0) return false;

  await pool.query(
    "INSERT INTO app_messages (conversation_id, role, content) VALUES ($1, $2, $3)",
    [conversationId, message.role, message.content],
  );

  // The first user message names the conversation, the way ChatGPT does.
  const isUntitled = owned.rows[0].title === "New chat";
  if (isUntitled && message.role === "user") {
    const title = message.content.trim().slice(0, 60) || "New chat";
    await pool.query(
      "UPDATE app_conversations SET title = $1, updated_at = now() WHERE id = $2",
      [title, conversationId],
    );
  } else {
    await pool.query(
      "UPDATE app_conversations SET updated_at = now() WHERE id = $1",
      [conversationId],
    );
  }
  return true;
}

export async function deleteConversation(userId: string, conversationId: string): Promise<boolean> {
  await ensureChatTables();
  const { rowCount } = await pool.query(
    "DELETE FROM app_conversations WHERE id = $1 AND user_id = $2",
    [conversationId, userId],
  );
  return (rowCount ?? 0) > 0;
}

export interface Upload {
  id: string;
  filename: string;
  bytes: number;
}

export async function saveUpload(
  userId: string,
  filename: string,
  mime: string,
  content: Buffer,
): Promise<Upload> {
  await ensureChatTables();
  const { rows } = await pool.query<{ id: string }>(
    `INSERT INTO app_uploads (user_id, filename, mime, content)
     VALUES ($1, $2, $3, $4) RETURNING id`,
    [userId, filename, mime, content],
  );
  return { id: rows[0].id, filename, bytes: content.byteLength };
}

export async function deleteAllConversations(userId: string): Promise<number> {
  await ensureChatTables();
  const { rowCount } = await pool.query(
    "DELETE FROM app_conversations WHERE user_id = $1",
    [userId],
  );
  return rowCount ?? 0;
}
