# agentic-platform

A production-shaped, fully self-hosted agentic platform. One assistant, two
surfaces — **text chat and live voice** — and every capability is reached the
same way: the chat model delegates to a specialist by tool call.

- **Media plane** — our own LiveKit SFU on Kubernetes ([deploy/livekit/](deploy/livekit/))
- **Agent workers** — Python 3.13, `livekit-agents` v1.7, autoscaled ([assistant/](assistant/), [deploy/k8s/](deploy/k8s/))
- **Brain** — a LangGraph behind the voice pipeline, built as a seam so
  specialists (web search, document extraction, tool orchestration) land
  later as graph nodes, not a rewrite ([assistant/src/chat_assistant/graph/](assistant/src/chat_assistant/graph/))
- **Client** — a ChatGPT-shaped Next.js 15 app ([web/](web/)): text chat by
  default over plain HTTP, voice as a mode you enter (see "Two surfaces,
  one brain" below)
- **Vector store** — Postgres + pgvector, a seam nothing on the speaking path
  depends on ([assistant/src/chat_assistant/vectordb.py](assistant/src/chat_assistant/vectordb.py))
- **Capabilities** — a policy-gated tool gateway with audit, retries and
  budgets, plus pgvector retrieval
  ([assistant/src/chat_assistant/capabilities/](assistant/src/chat_assistant/capabilities/))

The full design with diagrams: [architecture.html](architecture.html).

## Quickstart (all local, no cloud account)

Two API keys are enough: `GOOGLE_API_KEY` (Gemini) and `DEEPGRAM_API_KEY`
(covers both STT and TTS). Everything else is self-hosted.

```bash
# 1. Infrastructure — SFU, Redis, Postgres.
#    NOT plain `up -d`: that would also start the containerized chat
#    service, which then holds :8124 and the local one below can't bind.
docker compose up -d livekit redis postgres

# 2. The assistant (one uv project, two processes)
cd assistant
cp .env.example .env.local          # put your two keys in
uv sync
uv run assistant-chat               # text surface on :8124  (terminal 1)
uv run assistant-voice dev          # voice worker joins the SFU (terminal 2)

# 3. Web client (terminal 3)
cd ../web
cp .env.local.example .env.local    # set a real AUTH_SECRET
npm install
npm run dev                         # http://localhost:3000 (3001 if 3000 is taken)
```

First run: **sign up** at `/signup` — accounts live in your own Postgres.
Then type in the chat, attach a file with the `+` button, or hit the blue
orb for voice mode.

`uv run assistant-voice console` is the fastest voice pipeline check — talk
through the terminal mic, no SFU or browser involved.

### Local-dev gotchas (each one earned)

- **macOS/Windows + Docker**: the SFU must advertise `127.0.0.1`
  (`--node-ip` in docker-compose.yaml, already set). Without it, signalling
  works but every call dies with "could not establish pc connection" —
  Docker's bridge IP is unreachable from the host browser.
- **A Gemini 404 "model no longer available"** means Google retired the
  model name for new keys. Fix is one line in `.env.local` (`LLM_MODEL`).
- **Turn detection on dev credentials**: LiveKit's hosted interruption
  model rejects devkey/secret (401) and the SDK falls back to VAD-based
  interruption on its own. The warning in the worker log is expected.
- **Ports**: :8124 chat service (8080 is commonly taken), :8123 free,
  :8081/:9091 are owned by the LiveKit SDK inside the voice worker.
- The keyless invariant holds locally too: with no provider keys the chat
  service still boots and `/health` answers; only turns fail.
- **`uv run pytest` with real keys in `.env.local` runs the two behavioral
  evals against the live model** — they consume quota and can 429 on the
  free tier. That's the evals working, not the suite breaking; without
  keys they skip and everything else is offline.

### Containerized alternative

`docker compose up -d` (no service list) also builds and starts the chat
service in a container, reading `GOOGLE_API_KEY` etc. from your shell env —
use that instead of terminal 1 above, never both.

## Two surfaces, one brain

The client is ChatGPT-shaped: **text chat by default, voice as a mode you
enter**. Both run the same compiled LangGraph, so the Research Agent and the
provider config apply identically to either.

| | Text | Voice |
|---|---|---|
| Transport | HTTP + SSE via `/api/chat` | WebRTC through the SFU |
| Persona | [assistant_text.md](assistant/src/chat_assistant/prompts/assistant_text.md) — markdown, code, full length | [assistant.md](assistant/src/chat_assistant/prompts/assistant.md) — TTS-safe, 1–3 sentences |
| History | persisted in Postgres (`app_conversations` / `app_messages`) | ephemeral, per room |
| Specialist filler | rendered as a status line | spoken aloud |
| Needs the SFU | no | yes |

The Python service (`assistant-chat`) is **stateless** — it takes a full
message list and streams tokens back. The web app owns identity and
conversation history and proxies through `/api/chat`, so the browser never
addresses it directly. That split is why `build_graph()` needs no
checkpointer: passing the whole history each turn is exactly what LiveKit's
`LLMAdapter` already does on the voice path.

## Pipeline & provider swap

Providers are factories in [assistant/src/chat_assistant/models.py](assistant/src/chat_assistant/models.py);
swapping is a config change:

| Stage | Default                            | Env key |
|-------|------------------------------------|---------|
| STT   | Deepgram `nova-3`                  | `DEEPGRAM_API_KEY` |
| LLM   | `LLM_MODEL=google:gemini-3.6-flash`| `GOOGLE_API_KEY` |
| TTS   | `TTS_MODEL=deepgram:aura-2-andromeda-en` | `DEEPGRAM_API_KEY` (shared with STT) |
| Turn  | `inference.TurnDetector()`         | `LIVEKIT_*` only |

TTS is provider-mapped like the LLM: `TTS_MODEL="provider:model"` with
`deepgram` or `cartesia` (`TTS_MODEL=cartesia:sonic-2` + `CARTESIA_API_KEY`;
a bare model name means Cartesia). The Deepgram default keeps the whole
audio pipeline on one API key.

The LLM is **multi-provider by env**: `LLM_MODEL="provider:model"` with
`google`, `deepseek`, or `openai`, honored by both the graph path
(`init_chat_model`) and the direct path (LiveKit plugins; DeepSeek rides
`openai.LLM.with_deepseek` — its API is OpenAI-compatible):

```bash
LLM_MODEL=google:gemini-3.6-flash    GOOGLE_API_KEY=...    # default
LLM_MODEL=deepseek:deepseek-chat     DEEPSEEK_API_KEY=...
LLM_MODEL=openai:gpt-4.1-mini        OPENAI_API_KEY=...
```

Gemini is the default because voice lives or dies by time-to-first-token,
and DeepSeek's official API is markedly slower there — fine for later
non-realtime specialist nodes, costly on the speaking path.

## The LangGraph seam

The LLM stage runs through a compiled LangGraph (`LLMAdapter` from
`livekit-plugins-langchain`): `START → route → chat → (specialist →) END`.
Ordinary turns cost exactly one LLM call — there is no router LLM; the
chat model itself delegates by tool call, and `route_after_chat` sends the
turn to the matching specialist. A future fan-out (`langgraph.types.Send`,
one per task) attaches without restructuring.

**Research Agent** (first specialist, live): set `TAVILY_API_KEY` and the
main agent can delegate `research(query)` — a bounded ReAct loop
(`create_agent`) with `web_search`, `open_webpage`, and `search_official`
tools under [prompts/research.md](assistant/src/chat_assistant/prompts/research.md):
search, open the promising pages, prefer official sources, cross-check
claims across two independent sources, return cited findings. The findings
come back as a tool result; the main agent speaks a concise summary citing
sources by name (never URLs). Filler speech via `get_stream_writer()`
covers the loop's latency, and the loop's internal model runs with
`disable_streaming=True` so its reasoning is never read aloud. Without the
key, nothing registers and the graph keeps the plain fast-path shape.
Typed chat gets all of this too — text turns run through the same graph.

- Adding a specialist: see [assistant/src/chat_assistant/graph/specialists/registry.py](assistant/src/chat_assistant/graph/specialists/registry.py)
- Bisect switch: `USE_LANGGRAPH=false` falls back to the direct provider path
- Vector store: future specialists get a table each in Postgres+pgvector
  via `vectordb.get_pool()` (call `ensure_ready()` once — it installs the
  extension and returns its version). Local `docker compose up` serves it
  on :5432; in-cluster set `DATABASE_URL` ([deploy/k8s/postgres.yaml](deploy/k8s/postgres.yaml),
  or managed Postgres with pgvector). Deliberately not on the speaking
  path: workers run fine with it down. Embedding model and dimensions are
  deferred to the first real use case.
- Division of labour: LiveKit agents own *who is talking*; the graph owns
  *how the thinking is organized*. Specialists are graph subgraphs, never
  additional LiveKit agents.

## Ports contract (self-hosted SFU)

| Port      | Proto | Exposure | Carries |
|-----------|-------|----------|---------|
| 7880      | TCP   | via LB   | Signal (WSS) + RoomService; TLS at ingress |
| 7882–7892 | UDP   | public   | Media (UDP mux; range ≥ vCPUs) |
| 7881      | TCP   | public   | ICE/TCP fallback — never behind LB/TLS |
| 3478      | UDP   | public   | TURN/UDP |
| 443       | TCP   | public   | TURN/TLS (locked-down networks) |
| 6379      | TCP   | internal | Redis (multi-node room routing) |
| 8081/9091 | TCP   | internal | Worker health / Prometheus |

Agent workers need **no inbound ports** — they register with the SFU over
an outbound WebSocket and negotiate WebRTC as a room participant.

## Scaling math

- One agent pod (4 CPU / 8 Gi) ≈ **10–25 concurrent voice sessions**
  (LiveKit load test: 30 sessions at ~3.8 cores / ~2.8 GB).
- Worker marks itself unavailable at `load_threshold` 0.7; the HPA fires at
  **50%** CPU — the 20-point band is the new pod's runway (pull, model
  load, register).
- Drain: SIGTERM stops job intake, live calls finish. `drain_timeout` 600s,
  k8s `terminationGracePeriodSeconds` 660.
- SFU: `hostNetwork` ⇒ one pod per node, scales by adding nodes; 5-hour
  termination grace so calls are never cut.

## The four gotchas (verified against v1.7 sources)

1. **Old API is gone** — `WorkerOptions`/`entrypoint_fnc` no longer exist;
   it's `AgentServer()` + `@server.rtc_session` + `cli.run_app(server)`.
2. **Explicit dispatch** — a non-empty `agent_name` means jobs arrive only
   when the token requests the agent (see
   [web/app/api/token/route.ts](web/app/api/token/route.ts)). An agent that
   never joins is almost always this.
3. **`advertise_internal_ip: true`** — keeps the SFU's internal ICE
   candidate alongside the mapped external one, so in-cluster workers and
   external browsers both connect. Verify in `chrome://webrtc-internals`
   that the selected pair is UDP, not TURN relay.
4. **`LLMAdapter` takes compiled graphs only** — LangGraph graphs,
   `create_agent`, deep agents. Plain LCEL chains (`prompt | llm | parser`)
   do not work.

## Verification

```bash
cd assistant
uv run ruff check src tests && uv run pytest -v   # 6 keyless + 2 eval tests
uv run assistant-voice console                        # pipeline, no network stack
docker build -t chat-assistant:dev .                 # production image
cd ../web && npx tsc --noEmit && npm run build
```

With keys set, run pytest again for the LLM-as-judge behavioral evals. Then
`USE_LANGGRAPH=true|false` back to back — the agent must behave identically.

## Deploy

1. SFU + Redis + TURN: [deploy/livekit/README.md](deploy/livekit/README.md)
2. Workers: `kubectl apply -f deploy/k8s/` (copy `secret.example.yaml`
   first; `LIVEKIT_URL` points at the **in-cluster** SFU service)
3. Constraints to accept: no private/serverless clusters, one SFU pod per
   node, no service mesh on SFU nodes.

## Capabilities & the tool gateway

Specialists never touch the outside world directly. They hold a `Toolbox`
bound to one `AgentSpec`, and every call goes through the gateway:

```
specialist → Toolbox (charges the budget)
           → ToolGateway → allow-list check → audit (payload HASH, never content)
                         → timeout → retry (reads only; writes need an
                           idempotency key and replay instead of re-issuing)
                         → tool impl
```

Tools are declared in
[capabilities/tools.yaml](assistant/src/chat_assistant/capabilities/tools.yaml) —
that file is the whole universe of what any specialist can call. A specialist
registers its own allow-list in code next to the node that uses it, and an
unknown tool fails at registration rather than on first call.

**The allow-list is the injection boundary, not a user permission.** The
document specialist holds `document.read` and `document.parse` and nothing
else, so a document instructing the agent to "call jira.create_issue" finds
no such tool within reach. Its structured pass is a second wall: untrusted
text goes in, a validated Pydantic model comes out, and only validated
fields reach the synthesis call — which itself holds no tools.

### Attachments

Uploads go to Postgres (`app_uploads`), not a shared filesystem, so the
Next.js container and the Python service both reach them by id — and it
works identically in Kubernetes with no ReadWriteMany volume. Parsing runs
in `asyncio.to_thread`, because pypdf inline would freeze the event loop of
a worker holding ~25 live calls.

### Adding a specialist

1. Write the module beside
   [research.py](assistant/src/chat_assistant/graph/specialists/research.py):
   a schema-only `@tool`, a `build_<name>(llm, ...)` node factory, filler
   speech on entry, and **return only the reply — never a ToolMessage**.
2. Add one entry to
   [specialists/registry.py](assistant/src/chat_assistant/graph/specialists/registry.py).
   The factory, the tool schema and the credential gate live together, so
   they cannot drift apart.
3. Declare any new tools in `capabilities/tools.yaml` and allow-list them on
   the specialist's `AgentSpec`.
