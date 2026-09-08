"""Per-session metrics: log each pipeline event, summarize usage at shutdown.

Prometheus is separate: AgentServer(prometheus_port=...) serves /metrics,
and prometheus_multiproc_dir is REQUIRED for that because each session runs
in a child process (gotcha: without it the endpoint answers but per-session
series are silently missing).
"""

import logging

from livekit.agents import AgentSession, JobContext, metrics
from livekit.agents.voice.events import MetricsCollectedEvent

logger = logging.getLogger("chat-assistant.metrics")


def attach_metrics(session: AgentSession, ctx: JobContext) -> None:
    collector = metrics.ModelUsageCollector()

    @session.on("metrics_collected")
    def _on_metrics(ev: MetricsCollectedEvent) -> None:
        metrics.log_metrics(ev.metrics)
        collector.collect(ev.metrics)

    async def _log_session_usage() -> None:
        for usage in collector.flatten():
            logger.info("session usage: %s", usage)

    ctx.add_shutdown_callback(_log_session_usage)
