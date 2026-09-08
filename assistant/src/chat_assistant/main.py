"""Worker entrypoint.

Run modes (uv run assistant-voice <mode>, or python -m chat_assistant.main <mode>):
  console  talk through the terminal mic — no SFU, fastest pipeline check
  dev      connect to LIVEKIT_URL with pretty logs and hot reload
  start    production: JSON logs, health on :8081, /metrics on :9091
"""

import logging

from livekit.agents import AgentServer, AgentSession, JobContext, JobProcess, cli
from livekit.plugins import silero

from .assistant import Assistant
from .config import settings
from .models import build_llm, build_stt, build_tts, build_turn_handling
from .observability.logging import tune_levels
from .observability.metrics import attach_metrics

tune_levels()
logger = logging.getLogger("chat-assistant")

server = AgentServer(
    # Above this load the worker marks itself unavailable. The k8s HPA fires
    # at 50% CPU — deliberately below — so new pods have runway to schedule,
    # pull, and register before existing workers stop accepting jobs.
    load_threshold=settings.load_threshold,
    # SIGTERM => stop accepting jobs, let live calls finish. 600s here, not
    # the SDK's 3600s default; k8s terminationGracePeriodSeconds is 660.
    drain_timeout=settings.drain_timeout,
    port=settings.health_port,
    prometheus_port=settings.prometheus_port,
    # Required: sessions run in child processes; without multiproc mode
    # /metrics answers but per-session series are silently missing.
    prometheus_multiproc_dir=settings.prometheus_multiproc_dir,
    # The 10s SDK default is too tight once VAD/model prewarm is real work.
    initialize_process_timeout=settings.initialize_process_timeout,
)


def prewarm(proc: JobProcess) -> None:
    # Load Silero VAD once per process; every session on this process
    # reuses it instead of paying the load at call start.
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm


# Non-empty agent_name => explicit dispatch (gotcha 2): jobs arrive only
# when a token (web/app/api/token/route.ts) or the AgentDispatch API asks
# for this name. Set LIVEKIT_AGENT_NAME="" for automatic dispatch.
@server.rtc_session(agent_name=settings.agent_name)
async def entrypoint(ctx: JobContext) -> None:
    ctx.log_context_fields = {"room": ctx.room.name}

    session = AgentSession(
        stt=build_stt(),
        llm=build_llm(),
        tts=build_tts(),
        vad=ctx.proc.userdata["vad"],
        turn_handling=build_turn_handling(),
    )

    attach_metrics(session, ctx)

    await session.start(agent=Assistant(), room=ctx.room)
    await ctx.connect()


def main() -> None:
    cli.run_app(server)


if __name__ == "__main__":
    main()
