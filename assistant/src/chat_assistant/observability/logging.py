"""Log tuning.

The LiveKit CLI already emits structured JSON in `start` (production) mode
and pretty logs in `dev`/`console`, and per-job context arrives via
`ctx.log_context_fields` in main.py — so no formatter is installed here.
This module only quiets noisy dependencies.
"""

import logging

_NOISY = ("httpx", "httpcore", "openai", "websockets", "urllib3")


def tune_levels() -> None:
    for name in _NOISY:
        logging.getLogger(name).setLevel(logging.WARNING)
