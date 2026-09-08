// Postgres access for auth. Reuses the docker-compose pgvector instance —
// same DATABASE_URL the platform uses, but a web-owned table (app_users)
// so the two schemas never fight.
import { Pool } from "pg";

const globalForPg = globalThis as unknown as {
  pgPool?: Pool;
  usersReady?: Promise<unknown>;
};

export const pool =
  globalForPg.pgPool ??
  new Pool({
    connectionString:
      process.env.DATABASE_URL ??
      "postgresql://voice:voice@localhost:5432/voiceagent",
  });
globalForPg.pgPool = pool;

// Lazy, idempotent, memoized: first auth request creates the table; a down
// database fails the request, never the boot.
export function ensureUsersTable(): Promise<unknown> {
  globalForPg.usersReady ??= pool.query(`
    CREATE TABLE IF NOT EXISTS app_users (
      id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      email         text NOT NULL UNIQUE,
      name          text NOT NULL,
      password_hash text NOT NULL,
      created_at    timestamptz NOT NULL DEFAULT now()
    )
  `).catch((err) => {
    // Never memoize a FAILED promise: if the database was briefly down at
    // first request, caching the rejection poisons the whole process — every
    // later request fails even after Postgres recovers.
    globalForPg.usersReady = undefined;
    throw err;
  });
  return globalForPg.usersReady;
}

export interface AppUser {
  id: string;
  email: string;
  name: string;
  password_hash: string;
}

export async function findUserByEmail(email: string): Promise<AppUser | null> {
  await ensureUsersTable();
  const { rows } = await pool.query<AppUser>(
    "SELECT id, email, name, password_hash FROM app_users WHERE email = $1",
    [email.trim().toLowerCase()],
  );
  return rows[0] ?? null;
}
