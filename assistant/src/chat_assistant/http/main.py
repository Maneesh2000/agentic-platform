"""Entrypoint for the text surface: `uv run assistant-chat`.

A separate process from the LiveKit worker on purpose — `cli.run_app()` is
blocking and the SDK owns ports 8081/9091, so the two cannot share one.
The worker keeps its property of starting with the database down; this
service is the only one that needs anything else running.
"""

import uvicorn

from ..config import settings
from ..observability.logging import tune_levels
from .app import create_app

app = create_app()


def main() -> None:
    tune_levels()
    uvicorn.run(app, host="0.0.0.0", port=settings.http_port)


if __name__ == "__main__":
    main()
