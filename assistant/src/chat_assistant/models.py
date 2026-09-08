"""Factory per pipeline stage — swapping a provider is a config change.

| Stage | Default                         | Env key            |
|-------|---------------------------------|--------------------|
| STT   | deepgram nova-3                 | DEEPGRAM_API_KEY   |
| LLM   | LLM_MODEL="google:gemini-3.6-flash" | see _LLM_KEY_ENV |
| TTS   | TTS_MODEL="deepgram:aura-2-andromeda-en" | see _TTS   |
| Turn  | inference.TurnDetector          | LIVEKIT_*          |

The LLM honors LLM_MODEL="provider:model" on BOTH paths:
  direct (USE_LANGGRAPH=false)  -> the LiveKit plugin in _DIRECT_LLM
  graph  (USE_LANGGRAPH=true)   -> init_chat_model via _GRAPH_PREFIX
DeepSeek's API is OpenAI-compatible, so its direct path rides
openai.LLM.with_deepseek — no separate LiveKit plugin needed.
"""

from collections.abc import Callable

from livekit.agents import TurnHandlingOptions, inference, llm
from livekit.plugins import cartesia, deepgram, google, openai

from .config import settings

_DIRECT_LLM: dict[str, Callable[[str], llm.LLM]] = {
    "openai": lambda model: openai.LLM(model=model),
    "google": lambda model: google.LLM(model=model),
    "deepseek": lambda model: openai.LLM.with_deepseek(model=model),
}

# init_chat_model provider ids differ from ours only for Gemini.
_GRAPH_PREFIX: dict[str, str] = {
    "openai": "openai",
    "google": "google_genai",
    "deepseek": "deepseek",
}

_LLM_KEY_ENV: dict[str, str] = {
    "openai": "OPENAI_API_KEY",
    "google": "GOOGLE_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
}


def _provider_model() -> tuple[str, str]:
    provider, model = settings.llm_provider_model
    if provider not in _DIRECT_LLM:
        raise ValueError(
            f"Unsupported LLM provider {provider!r} in LLM_MODEL={settings.llm_model!r}; "
            f"supported: {sorted(_DIRECT_LLM)}"
        )
    return provider, model


def required_llm_key_env() -> str:
    """Env var name the configured LLM provider needs (used by tests)."""
    provider, _ = _provider_model()
    return _LLM_KEY_ENV[provider]


def graph_model_id() -> str:
    """LLM_MODEL translated to init_chat_model's 'provider:model' form."""
    provider, model = _provider_model()
    return f"{_GRAPH_PREFIX[provider]}:{model}"


def build_stt() -> deepgram.STT:
    return deepgram.STT(model=settings.stt_model, language=settings.stt_language)


def build_direct_llm() -> llm.LLM:
    """The configured provider's LiveKit-native LLM (no graph)."""
    provider, model = _provider_model()
    return _DIRECT_LLM[provider](model)


def build_llm() -> llm.LLM:
    if settings.use_langgraph:
        from livekit.plugins import langchain

        from .graph.build import build_graph

        # "custom" is unused until a specialist emits filler speech via
        # get_stream_writer(); enabling it now keeps that a graph-only change.
        return langchain.LLMAdapter(graph=build_graph(), stream_mode=["messages", "custom"])
    # The bisect switch: USE_LANGGRAPH=false gives the direct provider path.
    return build_direct_llm()


# TTS honors TTS_MODEL="provider:model". Deepgram (default) reuses the STT
# key, so the whole audio pipeline runs on one DEEPGRAM_API_KEY; its Aura-2
# voice is part of the model name, so tts_voice applies to Cartesia only.
_TTS: dict[str, Callable[[str], cartesia.TTS | deepgram.TTS]] = {
    "deepgram": lambda model: deepgram.TTS(model=model),
    "cartesia": lambda model: cartesia.TTS(
        model=model, **({"voice": settings.tts_voice} if settings.tts_voice else {})
    ),
}


def build_tts() -> cartesia.TTS | deepgram.TTS:
    provider, model = settings.tts_provider_model
    if provider not in _TTS:
        raise ValueError(
            f"Unsupported TTS provider {provider!r} in TTS_MODEL={settings.tts_model!r}; "
            f"supported: {sorted(_TTS)}"
        )
    return _TTS[provider](model)


def build_turn_handling() -> TurnHandlingOptions:
    return TurnHandlingOptions(
        # End-of-turn model combining semantics with acoustic cues; auths
        # with LIVEKIT_* only, so BYO provider keys stay intact (gotcha 1).
        turn_detection=inference.TurnDetector(),
        # Tell a real interruption from a backchannel ("mhm", "right").
        interruption={"mode": "adaptive"},
        # Draft the LLM reply while end-of-turn is still being confirmed.
        preemptive_generation={"enabled": True},
    )
