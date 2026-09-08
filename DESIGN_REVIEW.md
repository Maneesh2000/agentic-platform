# Design review — voice-agent (voice worker + agent platform)

Reviewed 2026-08-27. Scope: `platform/` (agent_platform), the voice worker
(`platform/src/agent_platform/agents/voice/`), `web/`, and `deploy/`.
Verdict up front: the *architecture* is largely right — router-owned decisions,
deferred specialists, plan-validate-execute, a single tool gateway, seams for
optional infra. The flaws are almost all in **enforcement**: several invariants
CLAUDE.md declares are not actually held by the code, and the system's control
state is in-process memory that breaks at >1 replica.

---

## A. Critical (fix before anything ships)

### A1. The token endpoint is unauthenticated compute
`web/app/api/token/route.ts:10-42` mints a publish-capable LiveKit JWT **and
triggers agent dispatch** for anyone who can reach it — no auth, no rate limit,
no origin check, no identity, no cap on rooms or call duration. Every anonymous
GET burns worker CPU plus Deepgram/Gemini/Tavily credits. Also: identity/room
share 32 bits of entropy (`route.ts:19`), and no `metadata`/`attributes` are
set, so the agent has no idea who it's talking to — the anonymous voice channel
can never connect to the platform's authenticated ACL model.
**Fix:** require a session (or signed nonce) before minting; rate-limit per
IP/user; put user identity into token attributes; add max-duration and
concurrent-room caps.

### A2. The platform's only write bypasses the ToolGateway
`agents/document_summary/agent.py:58` calls `self._store.index_document(...)`
directly — an INSERT plus a paid embeddings call that skips policy, audit,
timeout, retry rules, budget, and the idempotency-key requirement the gateway
exists to impose (CLAUDE.md: "ALL tool calls go through the ToolGateway").
Resubmitting a task duplicates rows. **Fix:** register `retrieval.index` as a
write tool in `tools.yaml` and route it through `toolbox.call` with an
idempotency key derived from the task id.

### A3. No error handling anywhere on the voice speaking path
There are exactly two `try/except` in the whole worker (both in
`vectordb.ping`). Any mid-turn exception — `GraphRecursionError`, a Tavily
failure, a provider 400 — propagates to LiveKit's `LLMStream`, which emits a
non-recoverable error and goes **silent**; non-`APIError` exceptions are never
retried, `main.py` registers no `session.on("error")` handler, and the client
just shows a toast. **Fix:** wrap the graph call, speak a fallback line on
failure, register an error handler, and add error-path tests (there are none).

### A4. Gateway idempotency can return `None` as a "successful" replay
`gateway/gateway.py:90` records `self._write_results[key] = None` *before* the
call; on failure the key stays poisoned, so every retry with the same key hits
line 85-87 and returns `None` labeled "replayed" — the write never happened and
never will. There's also a check-then-act race across the `await audit()` at
line 86 (same key can execute twice), and the map is per-process and never
evicted. **Fix:** store a tri-state (pending/succeeded/failed) record, clear or
mark on failure, guard with a lock, and persist it (it must be shared across
replicas to mean anything).

### A5. All task-control state is per-process → broken at >1 replica
`runner.py:30-32`: `_running`, `_budgets`, `_events` are instance dicts.
Consequences: cancel on the wrong pod silently no-ops (`runner.py:43`); SSE on
the wrong pod degrades to a status poll; a restart orphans `running` rows
forever (no startup sweep, no lease); `_events` is never popped in the
`finally` (`runner.py:95-100`) so it leaks a queue per task **and** makes SSE
on finished tasks hang forever; two SSE subscribers *split* one queue's events.
**Fix:** persist cancel intent (a `cancel_requested` column checked by
`Budget`), move events to Postgres LISTEN/NOTIFY or Redis pub/sub, add a
startup reaper for orphaned `running` rows, and pop `_events` in `finally`.

### A6. Blocking parsing inside the event loop defeats the gateway timeout
`tools/document.py:25-43` does synchronous `read_text` / `PdfReader` /
`BeautifulSoup` inside `async def`. A large or adversarial PDF freezes the
whole process — and `asyncio.wait_for` at `gateway.py:101` **cannot interrupt
it** (the coroutine never yields), so the tool's `timeout_s: 60` is decorative.
**Fix:** `asyncio.to_thread(...)` (or a process pool for PDFs) + a file-size
cap before parsing.

### A7. Committed real Secret with `change-me` password
`deploy/k8s/postgres.yaml:9-15` is a live `Secret` manifest (not an example)
with `POSTGRES_PASSWORD: change-me`, and only `deploy/k8s/secret.yaml` is
gitignored — `kubectl apply -f deploy/k8s/` stands up Postgres with a public
password. **Fix:** rename to `.example`, gitignore the real one, and prefer
ExternalSecrets/CSI over raw env secrets.

---

## B. High — latent bugs armed to fire

1. **`bind_tools(BINDABLE)` isn't filtered by availability** —
   `graph/build.py:35` binds the module-global `BINDABLE` while route targets
   come from `specs = available()`. Today it works because there's exactly one
   specialist; the moment a second is registered and only one credential is
   configured, the chat model can emit a tool call whose branch isn't in the
   path map → crash mid-turn. Bind `[spec.tool for name, spec in specs]`, not
   the global.
2. **`research_node` runs *all* tool calls as research** —
   `specialists/research.py:106-107` iterates `last.tool_calls` without a
   `call["name"] == "research"` guard, and a missing `query` arg becomes an
   empty-string Tavily search.
3. **Silent turns** — when a tool call matches no specialist,
   `route_after_chat` → `END` with an empty `AIMessage`, and the adapter drops
   empty content: the user hears nothing, no error anywhere (`router.py:24-30`).
4. **No wall-clock bound on research** — `recursion_limit` bounds steps, not
   time (`research.py:108-113`); no `asyncio.timeout`, behind a single static
   filler sentence. Combined with preemptive generation
   (`models.py:118`), false end-of-turn detection triggers *real* Tavily spend
   for runs that get discarded.
5. **Cancellation/budget can't interrupt the expensive work** — the platform's
   whole agent runs inside one `execute` node between budget checks
   (`graph.py:59-78`), and no LLM call anywhere has a timeout. Cancel = run to
   completion, then relabel.
6. **Prompt-injection fence escape is non-idempotent** — `provenance.py:28`:
   payload `<<<<END-UNTRUSTED-CONTENT>>>>` reconstitutes a close marker
   separated only by a zero-width space (verified by execution). Escape `<`
   itself to a sentinel, or use a random per-wrap boundary.
7. **Fail-open registry defaults** — `required_roles: []` means every
   authenticated user can run the agent (`registry/models.py:29`,
   `context.py:19-21`); a tool that forgets `write: true` silently gets
   retries and no idempotency requirement. Make these fields required, or make
   the safe direction the default.
8. **Idempotency-key TOCTOU + global uniqueness** — `routes_tasks.py:43-47`
   read-then-insert races into an uncaught `UniqueViolationError` (500), and
   the key is unique *across users* (`0001_init.sql:11`): another user reusing
   your key gets a 404 (key squatting). Scope the unique index per user and
   catch the violation.
9. **Unbounded intake** — `runner.py:40` spawns a task per request with no
   semaphore; `TaskInput.text` has no size limit; chunking/embedding run over
   the **full** text (only the prompt is truncated, `agent.py:56-67`);
   retrieval `k` flows uncapped into `LIMIT`.
10. **No checkpointer / thread identity in the voice graph** — deliberate and
    reasonably argued (`build.py:53-57`), but note the cost: a pod crash loses
    every conversation on it (drain only covers graceful shutdown), and
    `config=None` in the adapter (`models.py:84`) means no `thread_id`, no
    tracing correlation, no per-room budgets are even *possible* without a
    signature change. The sqlite-checkpointer dependency is shipped but unused.

## C. Operations / Kubernetes

- **Liveness probe defaults on a saturated pod** (`deployment.yaml:51-57`):
  `timeoutSeconds: 1` on a pod deliberately run at 50-70 % CPU with no CPU
  limit can kill a pod holding up to 25 live calls. Add `timeoutSeconds`,
  a `startupProbe`, and reconsider probing a loaded realtime worker at all.
- **Prometheus multiproc dir is likely unwritable**: `emptyDir` mounts
  root-owned; `runAsNonRoot` uid 10001 with **no `fsGroup`**
  (`deployment.yaml:25-26,58-65`) — metrics silently break.
- **Memory limit = request = 8Gi shared by 10-25 sessions** with no
  per-session cap: one runaway session OOM-kills every co-tenant call. No
  anti-affinity either, so `replicas: 2` can share a node.
- **HPA on CPU is the wrong signal** for long-lived sessions — workers at
  `load_threshold` *refuse jobs* (callers get agent-less rooms) before CPU
  triggers scale-out. LiveKit exports worker-load metrics on :9091; scale on
  those.
- `image: :latest`, no namespace on worker manifests, ServiceMonitor without a
  `release` label, no `preStop`/init process (PID 1 is `uv run` — SIGTERM
  forwarding unverified against the 660 s grace), no deployment story at all
  for `web/` (the only internet-facing component), single-replica Postgres
  with no backups.
- **Platform has no drain**: `main.py:55-56` closes the pool under running
  tasks on shutdown; `/health` is hardwired "ok" (`db_ok` has no writer).

## D. Tests & docs drift

- The only behavioral evals **never run in CI**: CI passes `OPENAI_API_KEY`
  but the default model is Gemini, so the eval tests always skip
  (`ci.yml:27` vs `config.py:33`, `models.py:54-57`).
- Suite is non-hermetic: `conftest.py` loads `.env.local` and one test asserts
  `tavily_api_key == ""` — a dev with a key gets a red suite, and the
  with-specialist graph shape is never tested in that config.
- Zero tests for: error paths, `USE_LANGGRAPH` parity (README claims parity;
  tools make it false — LiveKit `lookup_weather` is dead on the graph path),
  the token route, `main.py`, barge-in/cancellation.
- Doc drift: README says "6 keyless tests", there are 20; README calls the
  stack "fully self-hosted" while STT/LLM/TTS/turn-detection are all SaaS.

---

## E. Multi-agent best practices (what to keep, what to adopt)

**Already right in this design — keep:**
- One router owns each decision; specialists never self-select.
- Fast path is sacred: ordinary turns pay nothing for the exotic ones; filler
  speech via `get_stream_writer` buys perceived latency honestly.
- Specialists as registry-registered subgraphs, not extra runtime agents.
- Plan-as-data + validator before execution; pinning skips routing, never
  policy.
- Single tool gateway; lazy provider construction; vector store as a
  degradable seam; `USE_LANGGRAPH` bisect switch.

**Adopt (ranked):**
1. **Enforce invariants with machinery, not convention.** Every violated rule
   above (gateway bypass, unwrapped untrusted content, fail-open defaults) was
   a *convention*. Make the safe path the only path: agents get a `Toolbox`,
   never a store handle; `wrap_untrusted` happens inside the gateway for tools
   marked `untrusted_output: true`; registry fields that gate security are
   required, not defaulted.
2. **Externalize control state.** Cancel flags, idempotency records, event
   streams, and run leases belong in Postgres/Redis, not instance dicts. A
   multi-agent platform that can't run two replicas isn't a platform yet.
3. **Time-bound everything that can speak or spend.** Per-LLM-call timeouts,
   per-tool timeouts, a wall-clock deadline the budget actually interrupts
   (check it *inside* the agent between tool calls, not only at node entry).
4. **Give every conversation an identity.** `thread_id` = room id into the
   graph config even before you add a checkpointer — it's the correlation key
   for tracing, budgets, and memory later. Same for user identity in the
   LiveKit token.
5. **Split routing from speaking as specialists grow.** Today the fast chat
   model is also the router via bound tools; every new specialist grows every
   ordinary turn's prompt. At ~3+ specialists, add a cheap classifier tier in
   front (structured output, `Literal` destinations) and keep the chat model's
   binding minimal.
6. **Evaluate the router and the error paths in CI.** A labeled utterance set
   with a confusion matrix for routing; fault-injection tests (LLM raises,
   tool times out, barge-in mid-node) for the paths that currently have zero
   coverage. Fix the CI key mismatch so evals actually run.
7. **Typed results across every boundary** — already the platform rule; extend
   it to specialists' return to the chat node (the research synthesis is
   currently free prose).
8. **Degrade audibly, not silently.** Every failure on the speaking path needs
   a spoken fallback; every dropped tool call needs at least a log line and a
   metric. Silence is the worst failure mode a voice product has.

---

*Full evidence (file:line for every claim) was gathered from source; items A1,
A4, B1 and the fence-escape (B6) were re-verified by direct code read/execution
during the review.*
