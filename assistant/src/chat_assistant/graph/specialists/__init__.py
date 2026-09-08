"""Specialist nodes and the helpers they share."""

import contextlib

from langgraph.config import get_stream_writer


def emit_filler(text: str) -> None:
    """Speak/print a holding line the moment a specialist is entered.

    Reaches TTS on the voice path and a status row on the text path (both
    surfaces consume stream_mode "custom"). Tolerates being called outside a
    runnable context so a node stays directly invocable in tests — a node
    that explodes when unit-tested is a node that gets tested through three
    layers of graph instead.
    """
    with contextlib.suppress(RuntimeError):
        get_stream_writer()(text)
