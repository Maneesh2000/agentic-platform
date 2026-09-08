# agentic-platform — conventions

## Non-negotiable

- **Never run `git commit` or `git push`.** The user commits and pushes
  themselves. Build, test, and leave the tree for their review.

## Layout

One Python service, one brain, two surfaces.

- `assistant/` — the whole backend (package `chat_assistant`). `main.py` is
  the LiveKit voice worker (`assistant-voice console|dev|start`); `http/` is
  the text service (`assistant-chat`, :8124). Both compile the SAME graph.
- `assistant/src/chat_assistant/graph/` — the brain. `chat` node + specialist
  nodes. **There is no router LLM and no planner**: the chat model delegates
  by tool call and `route_after_chat` maps tool name → node.
- `assistant/src/chat_assistant/graph/specialists/` — `research` (Tavily),
  `document_summary` (uploads), `fallback`. One entry in `registry.py`
  registers a specialist's factory, tool schema and gate together.
- `assistant/src/chat_assistant/capabilities/` — the tool boundary:
  registry (tools.yaml) → policy → gateway → impls, plus toolbox, budget,
  provenance and audit. Everything here is built lazily.
- `assistant/src/chat_assistant/retrieval/` — pgvector store, embeddings and
  the SQL migrations.
- `web/` — Next.js 15 client, ChatGPT-shaped: text by default, voice as a
  mode. Token route stays on the Node runtime (never `runtime = "edge"`).
  API routes are excluded from the middleware matcher on purpose and do
  their own `auth()` → JSON 401; a middleware redirect would hand an SSE
  reader HTML. Conversations, users and uploads live in web-owned `app_*`
  tables (`lib/chatDb.ts`).
- `deploy/livekit/` — SFU Helm values. `deploy/k8s/` — worker manifests.

## Commands

```bash
cd assistant && uv sync                 # install
uv run ruff check src tests             # lint
uv run pytest -v                        # offline; DB tests skip without Postgres
uv run assistant-voice console|dev|start   # voice worker
uv run assistant-chat                   # text service on :8124
cd web && npm run dev|build             # client; typecheck: npx tsc --noEmit
docker compose up -d                    # SFU + Redis + Postgres + chat
```

## Rules that encode past decisions

- **The chat graph is the only orchestrator.** The supervisor (rules →
  planner LLM → PlanValidator → execute) was deleted; access to every agent
  goes through the chat input. Do not reintroduce a second router.
- Specialists are **LangGraph nodes**, never additional LiveKit agents.
  Register them in `graph/specialists/registry.py` — factory, tool schema
  and gate in ONE entry, because drift between those three armed a crash.
- **Bind only what you compile.** `build_graph` binds the tools of exactly
  the specialists whose nodes exist. A bound tool with no node routes to a
  branch the graph does not have.
- **Guard on the tool name inside a node.** A turn can carry parallel calls;
  a node that iterates `tool_calls` blindly will run on another's arguments.
- **An unroutable tool call must be visible.** It goes to the `fallback`
  node. The chat model's tool-call message has empty content and both
  surfaces drop empty content — silence with no error is the failure mode.
  This is the successor to the deleted PlanValidator: `TOOL_TO_SPECIALIST`
  is the closed set, and the fallback test is what proves it.
- The fast path is sacred: ordinary turns must never pay for a fan-out;
  filler speech goes through `emit_filler()` (stream_mode "custom").
- **A node must never return a ToolMessage into graph state.** stream_mode
  "messages" emits everything a node returns and both surfaces treat it as
  assistant output (LiveKit's `_to_chat_chunk` falls through to any object
  with `.content`) — raw tool results get spoken/printed verbatim. Feed
  them to the synthesis call and return only the reply.
- Specialist-internal LLM calls run `disable_streaming=True`, or their
  reasoning (and raw JSON) is spoken aloud.
- **Budgets are per invocation, never per factory.** A node closure is built
  once per worker process and shared by every session.
- **Blocking work goes through `asyncio.to_thread`.** pypdf/BeautifulSoup
  inline would freeze the event loop of a worker holding ~25 live calls,
  and `wait_for` cannot interrupt a coroutine that never yields.
- ALL tool calls go through the ToolGateway: policy → audit (payload
  hashes, never content) → timeout → retry. Reads retry; writes never
  auto-retry and require an idempotency key.
- The agent tool allow-list is **capability scoping / injection defense**,
  not user permission. A specialist reading untrusted content holds
  read-only tools and produces a validated Pydantic model — the structured
  pass is a sanitization boundary, so raw document text never reaches the
  synthesis call.
- Provider changes go through `models.py` factories + config, not call
  sites. `LLM_MODEL="provider:model"` (google | deepseek | openai) must keep
  working on BOTH paths — extend `_DIRECT_LLM`/`_GRAPH_PREFIX`/`_LLM_KEY_ENV`
  together. TTS is likewise mapped: `TTS_MODEL="provider:model"`
  (deepgram | cartesia); deepgram shares `DEEPGRAM_API_KEY` with STT.
- Provider construction stays LAZY, and so does the gateway: boot never
  requires provider keys or a database. `/health` must answer regardless.
- Vector store is a seam — nothing on the speaking path may depend on it;
  `ping()` never raises and workers start with it down.
- `USE_LANGGRAPH=false` is the bisect switch; both paths must keep working.
- k8s numbers are load-bearing: HPA 50% < load_threshold 0.7;
  terminationGracePeriodSeconds 660 = drain_timeout 600 + 60.

## Consciously retired (do not "restore" without reading this)

- **Supervisor, PlanValidator, task API, agent pinning, `ROUTING_MODE`** —
  replaced by tool-call routing + the closed `TOOL_TO_SPECIALIST` map.
- **`iam/` and the retrieval ACL** — they were already no-ops under open
  access. Identity is now one `actor` string used for the audit trail only.
  The `documents.allowed_roles` column survives so re-enabling needs no
  re-index, but re-adding authorization is real work, not a flag flip.
- **Budget `max_steps` and cooperative cancellation** — there is no plan to
  bound, and voice barge-in is LiveKit cancelling the task.

## Gotchas (v1.7, verified)

1. `AgentServer`/`rtc_session` replaced `WorkerOptions`/`entrypoint_fnc`.
2. Non-empty `agent_name` = explicit dispatch; token must request the agent.
3. SFU needs `rtc.advertise_internal_ip: true` for in-cluster workers.
4. `LLMAdapter` rejects plain LCEL chains — compiled graphs only.
