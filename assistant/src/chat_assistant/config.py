"""Every runtime knob, from environment.

Reads `.env.local` (never committed) and process env. The LiveKit SDK reads
LIVEKIT_URL / LIVEKIT_API_KEY / LIVEKIT_API_SECRET from os.environ directly,
so `load_dotenv` here also serves the SDK, not just this Settings object.
"""

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(".env.local")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env.local", extra="ignore")

    # --- dispatch ---------------------------------------------------------
    # Non-empty => explicit dispatch: the worker only joins rooms whose
    # token (or AgentDispatch API call) requests this name. "" => automatic.
    agent_name: str = Field(
        default="chat-assistant",
        validation_alias=AliasChoices("LIVEKIT_AGENT_NAME", "AGENT_NAME"),
    )

    # --- pipeline models (the provider swap point lives in models.py) -----
    stt_model: str = "nova-3"
    stt_language: str = "multi"
    # "provider:model". Supported providers: google, deepseek, openai.
    # Gemini is the default: for voice, time-to-first-token dominates, and
    # DeepSeek's official API is markedly slower there — switch with e.g.
    #   LLM_MODEL=deepseek:deepseek-chat
    llm_model: str = "google:gemini-3.6-flash"
    # "provider:model". Supported providers: deepgram, cartesia. Deepgram is
    # the default so one DEEPGRAM_API_KEY covers both STT and TTS; the Aura-2
    # voice is baked into the model name. Cartesia instead:
    #   TTS_MODEL=cartesia:sonic-2  (+ CARTESIA_API_KEY)
    tts_model: str = "deepgram:aura-2-andromeda-en"
    tts_voice: str = ""  # Cartesia only ("" => plugin default); Deepgram ignores it

    # --- LangGraph seam ---------------------------------------------------
    use_langgraph: bool = True

    # --- text surface (assistant-chat) ----------------------------------
    # Separate process from the LiveKit worker; the SDK owns 8081/9091.
    # 8124, not 8080: 8080 is occupied on the dev machine (as 8000 was, which
    # is why the platform sits on 8123). Neighbours keep them memorable.
    http_port: int = 8124
    http_cors_origins: str = "http://localhost:3000"

    # --- capabilities (tool gateway, retrieval, documents) ----------------
    # Uploads arrive through the web client and are read from Postgres by id.
    max_document_bytes: int = 10 * 1024 * 1024
    embedding_model: str = "google:gemini-embedding-001"
    embedding_dim: int = 1536
    # Bounds ONE specialist run: tool calls and wall clock. There is no plan
    # to bound any more, so max_steps died with the supervisor.
    budget_max_tool_calls: int = 24
    # Voice cannot tolerate a 5-minute silence; text can wait longer.
    budget_deadline_seconds_text: float = 120.0
    budget_deadline_seconds_voice: float = 35.0
    enable_document_summary: bool = True

    # --- research specialist ----------------------------------------------
    # Empty => the specialist is not registered and the graph keeps the
    # plain fast-path shape (keyless workers must boot).
    tavily_api_key: str = ""
    # Bounds the ReAct loop so a rabbit-hole search can't stall a live call.
    research_recursion_limit: int = 8

    # --- vector store (Postgres + pgvector) — seam now, use cases next ----
    database_url: str = Field(
        default="postgresql://voice:voice@localhost:5432/voiceagent",
        validation_alias=AliasChoices("DATABASE_URL", "PG_DSN"),
    )

    # --- worker ops (see deploy/k8s/ for how these pair with k8s) ---------
    health_port: int = 8081
    prometheus_port: int = 9091
    prometheus_multiproc_dir: str = "/tmp/prom"
    load_threshold: float = 0.7
    drain_timeout: int = 600  # 10 min; k8s terminationGracePeriodSeconds = this + 60
    initialize_process_timeout: float = 30.0

    @property
    def llm_provider_model(self) -> tuple[str, str]:
        """Split LLM_MODEL into (provider, model). A bare model name with no
        "provider:" prefix keeps meaning OpenAI, for least surprise."""
        provider, sep, model = self.llm_model.partition(":")
        if not sep:
            return "openai", self.llm_model
        return provider.strip().lower(), model.strip()

    @property
    def tts_provider_model(self) -> tuple[str, str]:
        """Split TTS_MODEL into (provider, model). A bare model name with no
        "provider:" prefix keeps meaning Cartesia — the original provider —
        so pre-existing TTS_MODEL=sonic-2 configs keep working."""
        provider, sep, model = self.tts_model.partition(":")
        if not sep:
            return "cartesia", self.tts_model
        return provider.strip().lower(), model.strip()


settings = Settings()
