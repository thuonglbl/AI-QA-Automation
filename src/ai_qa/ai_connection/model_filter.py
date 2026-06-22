"""Shared classifier for non-generative model ids (embeddings / tts / stt / etc.).

A provider's model-listing endpoint advertises chat models alongside embeddings,
rerankers, OCR/ASR and other non-conversational families. Those cannot back a
conversational agent and must be filtered out of the discovered pool.

This logic was originally inline in :mod:`ai_qa.agents.alice`; it now lives here so
both Alice's configuration run AND the admin "Sync models and benchmarks" action
apply the *exact same* filter (single source of truth).
"""

from __future__ import annotations

# Non-generative / unsupported model families. A model id matching any of these
# (as a whole word or a hyphen-delimited segment) is excluded from the chat pool.
# Examples it must catch: text-embedding-ada-002, inference-bge-m3,
# inference-bge-reranker, inference-granite-emb-278m, inference-deepseek-ocr,
# inference-miner-u25, olmocr-2-7b, qwen3-asr-1.7b, whisper-1, tts-1, dall-e-3.
NON_GENERATIVE_KEYWORDS: list[str] = [
    "embed",
    # Full-word "embedding(s)" — the strict segment match below means bare "embed"
    # does NOT catch "text-embedding-3-small" / "text-embedding-ada-002", so list the
    # full word explicitly to satisfy "skip embedding" model discovery.
    "embedding",
    "embeddings",
    "tts",
    "stt",
    "whisper",
    "transcribe",
    "speech",
    "audio",
    "dall-e",
    "babbage",
    "davinci",
    "instruct",
    "realtime",
    "moderation",
    "text-search",
    "text-similarity",
    "code-search",
    "edit",
    "emb",
    "bge",
    "reranker",
    "ocr",
    "olmocr",
    "asr",
    "miner",
]


def is_non_generative_model(model_id: str) -> bool:
    """Return ``True`` when ``model_id`` is a non-generative / unsupported family.

    Matches a keyword only as a whole word or a hyphen-delimited segment, so
    ``text-embedding-ada-002`` matches ``embed`` but ``my-embedding-model`` does
    not falsely match (the keyword is ``embed``, not ``embedding``). Mirrors the
    rule Alice has always used for the discovered pool.
    """
    low = model_id.lower()
    return any(
        kw == low or low.startswith(kw + "-") or low.endswith("-" + kw) or f"-{kw}-" in low
        for kw in NON_GENERATIVE_KEYWORDS
    )
