"""The USE_LANGGRAPH bisect switch and the LLM/TTS provider maps."""

import pytest

from chat_assistant import models
from chat_assistant.config import settings


@pytest.fixture(autouse=True)
def _fake_provider_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    # Constructing clients must not require real keys.
    for env in (
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPGRAM_API_KEY",
        "CARTESIA_API_KEY",
    ):
        monkeypatch.setenv(env, "test-not-a-real-key")


def test_graph_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from livekit.plugins import langchain

    monkeypatch.setattr(settings, "use_langgraph", True)
    assert isinstance(models.build_llm(), langchain.LLMAdapter)


def test_direct_path_uses_configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from livekit.plugins import google

    monkeypatch.setattr(settings, "use_langgraph", False)
    monkeypatch.setattr(settings, "llm_model", "google:gemini-2.5-flash")
    assert isinstance(models.build_llm(), google.LLM)


@pytest.mark.parametrize(
    ("llm_model", "expected"),
    [
        ("openai:gpt-4.1-mini", "openai.LLM"),
        ("google:gemini-2.5-flash", "google.LLM"),
        # DeepSeek is OpenAI-compatible: with_deepseek returns openai.LLM
        # pointed at api.deepseek.com (and requires DEEPSEEK_API_KEY, so
        # success here proves that path was actually taken).
        ("deepseek:deepseek-chat", "openai.LLM"),
        # Bare model name keeps meaning OpenAI, for least surprise.
        ("gpt-4.1-mini", "openai.LLM"),
    ],
)
def test_provider_map(monkeypatch: pytest.MonkeyPatch, llm_model: str, expected: str) -> None:
    from livekit.plugins import google, openai

    classes = {"openai.LLM": openai.LLM, "google.LLM": google.LLM}
    monkeypatch.setattr(settings, "llm_model", llm_model)
    assert isinstance(models.build_direct_llm(), classes[expected])


def test_graph_model_id_maps_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "google:gemini-2.5-flash")
    assert models.graph_model_id() == "google_genai:gemini-2.5-flash"
    monkeypatch.setattr(settings, "llm_model", "deepseek:deepseek-chat")
    assert models.graph_model_id() == "deepseek:deepseek-chat"


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "llm_model", "mistral:mistral-large")
    with pytest.raises(ValueError, match="Unsupported LLM provider 'mistral'"):
        models.build_direct_llm()


@pytest.mark.parametrize(
    ("tts_model", "expected"),
    [
        # Deepgram default: one DEEPGRAM_API_KEY covers STT and TTS.
        ("deepgram:aura-2-andromeda-en", "deepgram.TTS"),
        ("cartesia:sonic-2", "cartesia.TTS"),
        # Bare model name keeps meaning Cartesia — the original provider.
        ("sonic-2", "cartesia.TTS"),
    ],
)
def test_tts_provider_map(monkeypatch: pytest.MonkeyPatch, tts_model: str, expected: str) -> None:
    from livekit.plugins import cartesia, deepgram

    classes = {"deepgram.TTS": deepgram.TTS, "cartesia.TTS": cartesia.TTS}
    monkeypatch.setattr(settings, "tts_model", tts_model)
    assert isinstance(models.build_tts(), classes[expected])


def test_unknown_tts_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "tts_model", "elevenlabs:eleven-v3")
    with pytest.raises(ValueError, match="Unsupported TTS provider 'elevenlabs'"):
        models.build_tts()
