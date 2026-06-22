"""Unit tests for the shared non-generative model classifier."""

import pytest

from ai_qa.ai_connection.model_filter import is_non_generative_model


@pytest.mark.parametrize(
    "model_id",
    [
        # Embeddings (incl. OpenAI's "text-embedding-*" which bare "embed" missed).
        "text-embedding-3-small",
        "text-embedding-ada-002",
        "inference-granite-emb-278m",
        "inference-bge-m3",
        "inference-bge-reranker",
        "voyage-embeddings",
        # Speech: tts / stt / transcription / audio.
        "tts-1",
        "tts-1-hd",
        "whisper-1",
        "gpt-4o-mini-tts",
        "gpt-4o-transcribe",
        "qwen3-asr-1.7b",
        # Other non-generative families.
        "inference-deepseek-ocr",
        "olmocr-2-7b",
        "text-moderation-latest",
        "dall-e-3",
        "inference-miner-u25",
    ],
)
def test_non_generative_models_are_filtered(model_id: str) -> None:
    assert is_non_generative_model(model_id) is True


@pytest.mark.parametrize(
    "model_id",
    [
        "claude-sonnet-4-6",
        "claude-opus-4-8",
        "gpt-4o",
        "gpt-5",
        "gemini-2.5-pro",
        "glm-5.1",
        "deepseek-v3",
        "qwen3.5",
        "inference-glm-6",
        # Names that merely contain a keyword as a SUB-word (not a whole hyphen
        # segment) must NOT be filtered.
        "codestral-2",
        "command-r-plus",
    ],
)
def test_chat_models_are_kept(model_id: str) -> None:
    assert is_non_generative_model(model_id) is False


def test_match_is_case_insensitive() -> None:
    assert is_non_generative_model("TEXT-EMBEDDING-3-LARGE") is True
    assert is_non_generative_model("Whisper-Large-V3") is True
