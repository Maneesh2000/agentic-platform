# syntax=docker/dockerfile:1
# Multi-stage build on the uv Python image; final image runs non-root.
ARG PYTHON_VERSION=3.13
FROM ghcr.io/astral-sh/uv:python${PYTHON_VERSION}-bookworm-slim AS base

ENV PYTHONUNBUFFERED=1
# Compile bytecode at install time -> faster cold start for new workers.
ENV UV_COMPILE_BYTECODE=1
# Model caches shared across stages (silero VAD etc.).
ENV HF_HOME=/app/.cache/huggingface
ENV TORCH_HOME=/app/.cache/torch

# --- build stage ---------------------------------------------------------
FROM base AS build
RUN apt-get update && apt-get install -y \
    gcc g++ python3-dev \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Dependency layer first, for caching: lockfile only, empty src.
COPY pyproject.toml uv.lock ./
RUN mkdir -p src
RUN uv sync --locked --no-dev

# Pre-download plugin model files (VAD etc.) before copying code, so the
# download layer survives code-only rebuilds.
RUN uv run --module livekit.agents download-files

COPY . .

# --- production stage ----------------------------------------------------
FROM base
ARG UID=10001
RUN adduser --disabled-password --gecos "" --home "/app" \
    --shell "/sbin/nologin" --uid "${UID}" appuser
COPY --from=build --chown=appuser:appuser /app /app
WORKDIR /app
USER appuser

# Health :8081 and /metrics :9091 (documented; workers need no inbound
# traffic — they register with the SFU over an outbound WebSocket).
EXPOSE 8081 9091

CMD ["uv", "run", "--no-sync", "python", "-m", "chat_assistant.main", "start"]
