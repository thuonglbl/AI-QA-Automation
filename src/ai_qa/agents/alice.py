"""Alice Agent — AI Provider Selection & Configuration.

Alice is the first step in the pipeline. She guides users through selecting
an AI provider, configuring credentials, testing the connection, and setting
up model assignments for all subsequent agents.

Lifecycle:
    Start → Processing (connection test) → Review Request → Done
                ↓
         (Reject + feedback)
                ↓
         Back to Start

Usage:
    from ai_qa.agents.alice import AliceAgent
    alice = AliceAgent()
    await alice.handle_start({"provider": "claude", "credentials": {...}})
"""

# Standard library
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

# Local
from ai_qa.agents.base import AgentState, BaseAgent
from ai_qa.ai_connection.model_filter import is_non_generative_model
from ai_qa.ai_connection.providers import (
    ConnectionResult,
    get_provider_adapter,
    get_provider_benchmark,
    resolve_base_url,
)
from ai_qa.config import AppSettings
from ai_qa.exceptions import PipelineError, PipelineSilentAbortError
from ai_qa.models import (
    AgentModelConfig,
    AgentsConfig,
    AliceConfiguration,
    ProviderConfig,
    StageResult,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Provider Configuration
# =============================================================================

# Display order is authoritative: the frontend renders providers in this exact
# array order. ``quality_rank`` only drives the badge label, not the ordering.
# ``auth_method`` tells the frontend how to collect credentials:
#   - "api_key": render the credential text input(s) from ``credential_fields``
#   - "sso":     render a "Login SSO" button that runs the OAuth browser flow
PROVIDER_OPTIONS: list[dict[str, Any]] = [
    {
        "id": "on-premises",
        "name": "On-Premises",
        "description": "Internal infrastructure · Company API key",
        "quality_rank": 5,
        "security_level": "highest",
        "auth_method": "api_key",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your on-premises API key...",
            },
        ],
        "endpoint_setting": "on_premises_api_base_url",
        "env_key": "ON_PREMISES_AI_SERVER_KEY",
    },
    {
        "id": "claude-sso",
        "name": "Anthropic / Claude (SSO)",
        "description": "Cloud · Enterprise SSO login",
        "quality_rank": 2,
        "security_level": "enterprise",
        "auth_method": "sso",
        # No manual credential — the OAuth browser login flow obtains the token.
        "credential_fields": [],
        "endpoint_setting": "claude_api_base_url",
        "env_key": "",
    },
    {
        "id": "browser-use-cloud",
        "name": "Browser Use Cloud",
        "description": "Cloud · Personal API key",
        "quality_rank": 1,
        "security_level": "cloud",
        "auth_method": "api_key",
        "credential_fields": [
            {"name": "api_key", "label": "API Key", "type": "password", "required": True}
        ],
        "endpoint_setting": "browser_use_cloud_url",
        "env_key": "BROWSER_USE_API_KEY",
    },
    {
        "id": "claude",
        "name": "Anthropic / Claude",
        "description": "Cloud · Personal API key",
        "quality_rank": 2,
        "security_level": "good",
        "auth_method": "api_key",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your Claude API key...",
            }
        ],
        "endpoint_setting": "claude_api_base_url",
        "env_key": "ANTHROPIC_API_KEY",
    },
    {
        "id": "gemini",
        "name": "Google / Gemini",
        "description": "Cloud · Personal API key",
        "quality_rank": 3,
        "security_level": "good",
        "auth_method": "api_key",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your Google Gemini API key...",
            }
        ],
        "endpoint_setting": "gemini_api_base_url",
        "env_key": "GEMINI_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI / ChatGPT",
        "description": "Cloud · Personal API key",
        "quality_rank": 4,
        "security_level": "good",
        "auth_method": "api_key",
        "credential_fields": [
            {
                "name": "api_key",
                "label": "API Key",
                "type": "password",
                "required": True,
                "placeholder": "Enter your OpenAI API key...",
            }
        ],
        "endpoint_setting": "openai_api_base_url",
        "env_key": "OPENAI_API_KEY",
    },
]


# Agent purposes for display
AGENT_PURPOSES: dict[str, str] = {
    "bob": "Requirements conversion from Confluence and Jira",
    "mary": "Test case generation",
    "sarah": "Script generation — writes Playwright from the captured trace (coding)",
    "sarah_explore": "Browser exploration — drives the live app to capture real selectors (vision)",
    "jack": "Test execution and analysis",
}

# Display labels for the model-assignment UI. ``sarah_explore`` is not a pipeline step — it is
# the SECOND model Sarah uses (a vision model drives the browser-use explore; the coding model
# above writes the script). Defaults to ``capitalize()`` for anything not listed.
_AGENT_DISPLAY_NAME: dict[str, str] = {
    "sarah": "Sarah · Script gen",
    "sarah_explore": "Sarah · Browser explore",
}

# Tool assignments per agent
AGENT_TOOLS: dict[str, list[str]] = {
    "bob": ["confluence_reader", "content_parser"],
    "mary": ["test_case_extractor"],
    "sarah": ["script_generator", "browser_agent"],
    "jack": ["script_runner"],
}

# Prompt templates per agent
AGENT_PROMPT_TEMPLATES: dict[str, str] = {
    "bob": "test_extraction_v1",
    "mary": "test_case_generation_v1",
    "sarah": "script_generation_v1",
    "jack": "execution_analysis_v1",
}

# --- Benchmark-informed model ranking (2026) --------------------------------
#
# Per-capability ordered preferences of case-insensitive id SUBSTRINGS, matched
# against the *discovered* model pool (never an undiscovered name — see AC3 in
# Story 9.4). The first preference that matches a discovered id wins, so these
# lists encode "best available for this capability" rather than a fixed model.
#
# Ordering is grounded in 2026 open-model benchmarks (full sources in the
# investigation case file `model-selection-and-scrollbar-investigation.md`):
#   - GLM-5.1 (754B, MIT) is the strongest open reasoning/coding/agentic model
#     in the on-prem pool (SOTA SWE-Bench Pro; aligned with Claude Opus 4.6).
#     It is TEXT-ONLY, so it must NOT appear in the vision ranking.
#   - Qwen3-VL-235B is the best open vision-language model in the pool.
#   - DeepSeek-V3.2 is a strong runner-up; GPT-OSS-120B is now mid-pack.
#
# Forward-looking names (e.g. "glm-6", "deepseek-v4", "glm-5.2") are listed
# AHEAD of currently-available ones so a newer on-prem model is preferred the
# moment it is published, with no code change. Models update fast — update
# these lists (not call sites) when the benchmark landscape shifts.

_REASONING_RANK: list[str] = [
    "glm-6",
    "deepseek-v4",
    "glm-5.2",
    "glm-52",
    "glm-5.1",
    "glm-51",
    "glm-5",
    "qwen3.5",
    "deepseek-v3",
    "qwen3-vl-235b",
    "llama4-maverick",
    "qwq-32b",
    "glm45-air",
    "apertus-70b",
    "gemma4-31b",
    "qwen3-8b",
]

_CODING_RANK: list[str] = [
    "glm-6",
    "deepseek-v4",
    "glm-5.2",
    "glm-52",
    "qwen3-coder",
    "glm-5.1",
    "glm-51",
    "glm-5",
    "deepseek-v3",
    "qwen3.5",
    "qwen3-vl-235b",
    "glm45-air",
    "qwq-32b",
    "llama4-maverick",
]

_INSTRUCTION_RANK: list[str] = [
    "glm-6",
    "deepseek-v4",
    "glm-5.2",
    "glm-52",
    "glm-5.1",
    "glm-51",
    "glm-5",
    "qwen3.5",
    "deepseek-v3",
    "qwen3-vl-235b",
    "llama4-maverick",
    "glm45-air",
    "gemma4-31b",
    "granite-33",
]

# Vision rank: MULTIMODAL families ONLY. Never list a text-only flagship
# (GLM-5.1, DeepSeek, GPT-OSS) here — Bob must be able to read images/diagrams.
_VISION_RANK: list[str] = [
    "qwen3.5-vl",
    "qwen3-vl-235b",
    "qwen3-vl",
    "glm-5v",
    "glm-5.1v",
    "glm-4.6v",
    "llama4-maverick",
    "llama4-scout",
    "gemma4-31b",
    "gemma-12b",
    "granite-vision",
]

# Fast tier: strong-but-lighter modern models for summarization/execution
# analysis. Prefers a capable mid-tier over the heaviest flagships.
_FAST_RANK: list[str] = [
    "glm45-air",
    "qwen3.5-30b",
    "gemma4-31b",
    "qwq-32b",
    "qwen3-8b",
    "gemma-12b",
    "granite-33",
    "mistral-v03",
    "apertus-70b",
]

_AGENT_CAPABILITY_RANK: dict[str, list[str]] = {
    "alice": _REASONING_RANK,
    "bob": _VISION_RANK,
    "mary": _INSTRUCTION_RANK,
    "sarah": _CODING_RANK,
    "sarah_explore": _VISION_RANK,
    "jack": _FAST_RANK,
}

# Agent -> capability name used to look up per-capability admin benchmark scores.
# "global" admin scores (the default) apply to every agent.
_AGENT_CAPABILITY_NAME: dict[str, str] = {
    "alice": "reasoning",
    "bob": "vision",
    "mary": "instruction",
    "sarah": "coding",
    "sarah_explore": "vision",
    "jack": "fast",
}


def _merge_scores(rows: list[tuple[str, str, float]], capability: str) -> dict[str, float]:
    """Flatten admin score rows for one capability into ``{model_id: score}``.

    A ``"global"`` score applies to every agent; a capability-specific score
    overrides the global one for that capability.
    """
    merged: dict[str, float] = {}
    for model_id, cap, score in rows:
        if cap == "global":
            merged[model_id] = score
    for model_id, cap, score in rows:
        if cap == capability:
            merged[model_id] = score
    return merged


# Benchmark-grounded, secret-free rationale templates ({model} is substituted
# with the chosen discovered id). Surfaced in the configuration-review UI.
_AGENT_RATIONALE: dict[str, str] = {
    "alice": (
        "'{model}' — strongest general-reasoning model in the discovered pool "
        "(2026 open-model benchmarks); drives configuration and orchestration."
    ),
    "bob": (
        "'{model}' — best vision-language model in the discovered pool; required "
        "for multimodal image/diagram extraction from Confluence & Jira."
    ),
    "mary": (
        "'{model}' — flagship instruction-following with structured-output / "
        "function-calling support; best fit for precise test-case generation."
    ),
    "sarah": (
        "'{model}' — top open coding & agentic model in the discovered pool "
        "(state-of-the-art SWE-Bench Pro, 2026); writes the Playwright script from the "
        "captured browser trace."
    ),
    "sarah_explore": (
        "'{model}' — best vision model in the discovered pool; DRIVES Sarah's browser-use "
        "exploration so it can SEE the live app and capture real selectors (the coding model "
        "above then turns that trace into the script)."
    ),
    "jack": (
        "'{model}' — strong, lower-latency model for fast summarization and execution analysis."
    ),
}


@dataclass(frozen=True)
class ParsedModel:
    """Structured view of a model id, used to heuristically rank UNLISTED ids."""

    family: str
    version: tuple[int, ...]
    total_b: int | None
    active_b: int | None
    tags: frozenset[str]


# Cross-family quality priors (2026). Used ONLY to rank ids that match no curated
# preference (Tier 2). WITHIN a family the parsed version decides; this map only
# orders ACROSS families. An unknown family sits just above the weakest known one
# so a new-vendor model is selectable but cannot leapfrog a known flagship on a
# version number alone. This small map is the only piece needing human upkeep.
_FAMILY_PRIOR: dict[str, int] = {
    "deepseek": 90,
    "glm": 90,
    "qwen": 88,
    "llama": 72,
    "mistral": 70,
    "gemma": 68,
    "granite": 52,
    "apertus": 50,
}
_FAMILY_PRIOR_UNKNOWN = 55  # just above the weakest known family

_PREFIX_STRIP = ("inference-", "on-premises-", "anthropic/")
_SIZE_RE = re.compile(r"^a?(\d+(?:\.\d+)?)b$")  # 754b, 235b, 7b, 1.7b, a22b
_ACTIVE_RE = re.compile(r"^a\d")  # a22b / a3b -> active-param count
# Vision NAME signals, used in UNION with the gateway's advertised flag (which the
# operator says is unreliable). Deliberately specific to avoid matching a text-only
# version token like "-v3" / "-v32".
_VISION_NAME_HINTS = ("vl", "vision", "multimodal", "maverick", "scout", "pixtral", "llava")
_VISION_FAMILY_HINTS = ("gemma",)
# Text-only flagships that are NEVER vision even when a provider gateway falsely advertises
# supports_vision (the on-prem gateway mis-flags e.g. deepseek-v32 / gpt-oss as vision, which
# would otherwise let a blind model win Bob's vision role + drive Sarah's explore). Checked
# AFTER the positive vision-name signals, so a genuine multimodal variant (e.g. a "deepseek-vl")
# still counts. Substring match against the lowercased id. Mirrors project-context's
# "keep GLM-5.1 / DeepSeek / GPT-OSS out of vision" rule — a capability FACT, not a score.
_TEXT_ONLY_VISION_DENY = ("deepseek", "gpt-oss")


def _version_from_token(token: str) -> tuple[int, ...] | None:
    """Parse a version token to an int tuple, or None if not version-like.

    Pinned by the golden-table test: a leading 'v' is stripped ('v32'->'32'); a
    dotted token splits on '.' as decimal components ('5.2'->(5,2), '3.10'->(3,10));
    a bare multi-digit run is read PER-DIGIT ('51'->(5,1), '45'->(4,5)) to match the
    on-prem glued convention (glm-51 == GLM 5.1); a single digit is (n,).
    """
    tok = token[1:] if token[:1] == "v" and token[1:2].isdigit() else token
    if not tok or not all(c.isdigit() or c == "." for c in tok):
        return None
    if "." in tok:
        parts = [int(p) for p in tok.split(".") if p != ""]
        return tuple(parts) if parts else None
    if len(tok) == 1:
        return (int(tok),)
    return tuple(int(c) for c in tok)


def parse_model_id(model_id: str) -> ParsedModel:
    """Parse a model id into family/version/size/tags. Fail-soft (never raises).

    On any ambiguity returns an empty family/version so the model lands in the
    neutral 'unknown' bucket rather than being mis-ranked.
    """
    s = model_id.lower().strip()
    for pre in _PREFIX_STRIP:
        if s.startswith(pre):
            s = s[len(pre) :]
            break
    try:
        family = ""
        version: tuple[int, ...] = ()
        total_b: int | None = None
        active_b: int | None = None
        tags: set[str] = set()
        for tok in s.replace("/", "-").split("-"):
            if not tok:
                continue
            size_m = _SIZE_RE.match(tok)
            if size_m:
                val = int(float(size_m.group(1)))
                if _ACTIVE_RE.match(tok):
                    active_b = val
                elif total_b is None or val >= total_b:
                    total_b = val
                else:
                    active_b = val
                continue
            if not family:
                head = "".join(c for c in tok if c.isalpha())
                tail = tok[len(head) :]
                if head:
                    family = head
                    if tail and not version:
                        glued = _version_from_token(tail)
                        if glued:
                            version = glued
                    continue
            parsed_v = _version_from_token(tok)
            if parsed_v is not None and not version:
                version = parsed_v
            elif tok.isalpha():
                tags.add(tok)
        return ParsedModel(family, version, total_b, active_b, frozenset(tags))
    except Exception:
        return ParsedModel("", (), None, None, frozenset())


def _model_score_key(parsed: ParsedModel) -> tuple[int, tuple[int, ...], int]:
    """Comparable ranking key: (family prior, padded version, size). Higher is better."""
    prior = _FAMILY_PRIOR.get(parsed.family, _FAMILY_PRIOR_UNKNOWN) if parsed.family else 0
    ver = (parsed.version + (0, 0, 0))[:3]
    size = parsed.active_b or parsed.total_b or 0
    return (prior, ver, size)


def _has_vision_signal(model: dict[str, Any]) -> bool:
    """Vision = a reliable name signal, OR the advertised flag for models not known to be
    text-only. The provider gateway's ``supports_vision`` flag is unreliable (it false-flags
    text-only on-prem models like deepseek-v32 / gpt-oss), so positive NAME signals win first
    and a known text-only family is rejected even when the flag is set; only then is the flag
    trusted (reliable for hosted providers + anything not on the text-only denylist)."""
    low = str(model.get("id", "")).lower()
    tokens = set(low.replace("/", "-").split("-"))
    # 1) Positive vision name signals win outright (incl. a genuine "-vl" multimodal variant).
    if tokens & set(_VISION_NAME_HINTS):
        return True
    # Vision variants that append "v" to a version (e.g. glm-5v / glm-5.1v / glm-4.6v —
    # all listed in _VISION_RANK). Without this, name-only detection (used when the
    # supports_vision flag is absent, e.g. resolving from a stored model id) misses them.
    if any(re.fullmatch(r"\d+(?:\.\d+)?v", t) for t in tokens):
        return True
    if any(h in low for h in _VISION_FAMILY_HINTS):
        return True
    # 2) Known text-only flagships are never vision, even if the gateway flag says so.
    if any(t in low for t in _TEXT_ONLY_VISION_DENY):
        return False
    # 3) Otherwise trust the advertised capability (reliable for hosted providers).
    return model.get("supports_vision") is True


def _breakdown(parsed: ParsedModel) -> str:
    """Human-readable score explanation for the configuration-review trace."""
    prior = _FAMILY_PRIOR.get(parsed.family, _FAMILY_PRIOR_UNKNOWN) if parsed.family else 0
    ver = ".".join(str(x) for x in parsed.version) if parsed.version else "?"
    if parsed.active_b:
        size = f"{parsed.active_b}b-active"
    elif parsed.total_b:
        size = f"{parsed.total_b}b"
    else:
        size = "?"
    return f"family={parsed.family or 'unknown'}(prior {prior}) version={ver} size={size}"


def _select_best_model(available_ids: list[str], ranking: list[str]) -> str | None:
    """Tier 1 (curated): first ranking substring that matches a discovered id.

    Among matches for a preference, prefers the highest parsed VERSION (so a newer
    sibling auto-wins) then a non-GRC base variant. Returns ``None`` when no
    preference matches the pool.
    """
    lowered = [(mid, mid.lower()) for mid in available_ids]
    for preference in ranking:
        matches = [mid for mid, low in lowered if preference in low]
        if not matches:
            continue
        non_grc = [mid for mid in matches if "grc" not in mid.lower()] or matches
        return max(non_grc, key=lambda mid: _model_score_key(parse_model_id(mid)))
    return None


def _promote_to_newest_sibling(winner_id: str, eligible_ids: list[str]) -> str:
    """Within the winner's family AND variant (tags), return the newest-version id.

    Lets a top-ranked/scored family automatically adopt a brand-new point release
    (e.g. ``glm-5.1`` -> ``glm-5.2``) with no admin score and no code change. A
    DIFFERENT variant (e.g. an ``-air`` / ``-vl`` tag) is not the same product
    line, so it is never promoted in. Only versions strictly newer than the
    winner win, so this never downgrades.
    """
    winner = parse_model_id(winner_id)
    if not winner.family:
        return winner_id
    best_id = winner_id
    best_key = _model_score_key(winner)
    for mid in eligible_ids:
        parsed = parse_model_id(mid)
        if parsed.family == winner.family and parsed.tags == winner.tags:
            key = _model_score_key(parsed)
            if key > best_key:
                best_id, best_key = mid, key
    return best_id


def _select_model_for(
    agent: str,
    models: list[dict[str, Any]],
    admin_scores: dict[str, float] | None = None,
) -> dict[str, Any] | None:
    """Pick the best discovered model for an agent (3-tier, deterministic, offline).

    Tier 0 admin score (operator override from the admin dashboard) -> Tier 1
    curated benchmark preference list -> Tier 2 parsed family/version/size
    heuristic (this is what ranks a BRAND-NEW unlisted id sensibly with zero code
    change). Bob is restricted to vision-capable models; the gate is SOFT —
    it degrades to the full pool (flagged) when nothing looks multimodal. Returns
    ``{model, source, breakdown, degraded}`` or ``None`` when the pool is empty.
    """
    admin = admin_scores or {}
    if not models:
        return None

    eligible = models
    degraded = False
    # Vision-role agents (Bob's image extraction; Sarah's browser-explore) are restricted to
    # vision-capable models. Soft gate: degrades to the full pool (flagged) if none look visual.
    if _AGENT_CAPABILITY_NAME.get(agent) == "vision":
        vision = [m for m in models if _has_vision_signal(m)]
        if vision:
            eligible = vision
        else:
            degraded = True
    eligible_ids = [str(m["id"]) for m in eligible]

    # Tier 0: operator-supplied scores (admin dashboard) win outright — but guard against
    # benchmark/seed noise. A non-positive score is treated as UNSCORED (a 0.0 row must not
    # let a model beat a curated pick), and a stale "-GRC" duplicate never wins while its
    # non-GRC sibling is also scored (mirrors the Tier-1 non_grc preference in
    # _select_best_model). Without this, a stale-seeded inference-qwen3-vl-235b-GRC row
    # (left behind by a partial benchmark migration) hijacked Tier-0 for every agent.
    scored = [(mid, admin[mid]) for mid in eligible_ids if mid in admin and admin[mid] > 0.0]
    non_grc_scored = [kv for kv in scored if "grc" not in kv[0].lower()] or scored
    if non_grc_scored:
        chosen, score = max(
            non_grc_scored, key=lambda kv: (kv[1], _model_score_key(parse_model_id(kv[0])))
        )
        source, base_breakdown = "admin", f"admin score={score}"
    else:
        # Tier 1: curated benchmark preference list (version-aware).
        curated = _select_best_model(eligible_ids, _AGENT_CAPABILITY_RANK[agent])
        if curated:
            chosen, source = curated, "curated"
            base_breakdown = _breakdown(parse_model_id(curated))
        else:
            # Tier 2: parsed heuristic for ids that match no curated preference.
            chosen = max(eligible_ids, key=lambda mid: _model_score_key(parse_model_id(mid)))
            source, base_breakdown = "parsed", _breakdown(parse_model_id(chosen))

    # Auto-upgrade within the winning family+variant to the newest version, so a
    # top-scored/curated family pulls in a brand-new point release (glm-5.1 ->
    # glm-5.2) automatically. A per-agent hard override (caller) bypasses this.
    upgraded = _promote_to_newest_sibling(chosen, eligible_ids)
    if upgraded != chosen:
        base_breakdown = f"{base_breakdown} → auto-upgraded from {chosen} to a newer version"
        chosen = upgraded

    return {"model": chosen, "source": source, "breakdown": base_breakdown, "degraded": degraded}


class AliceAgent(BaseAgent):
    """Alice Agent — AI Provider Selection & Configuration.

    Alice guides users through:
    1. Provider selection (Browser Use Cloud, Claude, Gemini/ChatGPT, On-Premises)
    2. Credential configuration
    3. Connection testing
    4. Model assignment review
    5. Configuration persistence

    Attributes:
        _selected_provider: Currently selected provider ID
        _provider_credentials: Stored credentials for selected provider
        _configuration: Complete AliceConfiguration after approval
    """

    def __init__(self) -> None:
        """Initialize Alice Agent."""
        super().__init__(
            name="Alice",
            color="#EC4899",  # Pink per UX-DR19
            step_number=1,
            step_title="AI Provider Configuration",
        )
        self._selected_provider: str | None = None
        self._provider_credentials: dict[str, str] = {}
        self._configuration: AliceConfiguration | None = None
        self._model_reasoning: list[dict[str, str]] = []
        self._settings = AppSettings()

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def check_existing_configuration(self) -> AliceConfiguration | None:
        """Check for existing valid configuration in DB.

        Returns:
            AliceConfiguration if valid config exists, None otherwise
        """
        if not self.project_context or not self.project_context.thread_id:
            return None

        if not self.project_context.artifact_service:
            return None

        db = self.project_context.artifact_service.db
        from ai_qa.threads.models import Thread

        thread = db.get(Thread, self.project_context.thread_id)
        if not thread or not thread.provider_name:
            return None

        try:
            # Reconstruct the expected configurations from the Thread
            provider_config = ProviderConfig(
                provider=thread.provider_name,
                provider_name=thread.provider_name.capitalize(),
                endpoint=thread.provider_base_url or "",
                credential_reference="",  # Loaded from user directly via base.py now
                tested_at="",
                test_result="success",
            )

            # Build agents config — tolerate both structured dict and legacy flat string.
            # Structured: {"model": str, "temperature": float, "rationale": str}
            # Legacy:     "model-id-string"
            agents_dict: dict[str, Any] = {}
            loaded_reasoning: list[dict[str, str]] = []
            for agent_name, agent_cfg in (thread.agent_configs or {}).items():
                if isinstance(agent_cfg, dict):
                    model_name = agent_cfg.get("model") or agent_cfg.get("model_name")
                    temperature = float(agent_cfg.get("temperature", 0.0))
                    rationale = str(agent_cfg.get("rationale", ""))
                else:
                    model_name = agent_cfg if isinstance(agent_cfg, str) else None
                    temperature = 0.0
                    rationale = ""
                agents_dict[agent_name.lower()] = {
                    "model": model_name,
                    "temperature": temperature,
                    "prompt_template": "default",
                    "tools": [],
                }
                if rationale:
                    loaded_reasoning.append(
                        {
                            "agent": agent_name.lower(),
                            "model": model_name or "",
                            "rationale": rationale,
                        }
                    )

            # Ensure Alice config exists
            if "alice" not in agents_dict:
                agents_dict["alice"] = {
                    "model": "claude-3-5-sonnet-20241022",
                    "temperature": 0.0,
                    "prompt_template": "default",
                    "tools": [],
                }

            # Restore rationale into _model_reasoning so the inspect view shows real values
            if loaded_reasoning:
                self._model_reasoning = loaded_reasoning

            agents_config = AgentsConfig.model_validate({"updated_at": "", "agents": agents_dict})

            return AliceConfiguration(provider=provider_config, agents=agents_config)
        except Exception as exc:
            logger.warning("Failed to load existing configuration from DB: %s", exc)
            return None

    def get_provider_options(self) -> list[dict[str, Any]]:
        """Get provider options for frontend display.

        Returns:
            List of provider option dictionaries
        """
        return [
            {
                "id": p["id"],
                "name": p["name"],
                "description": p.get("description", ""),
                "quality_rank": p["quality_rank"],
                "security_level": p["security_level"],
                "auth_method": p.get("auth_method", "api_key"),
                "credential_fields": p["credential_fields"],
            }
            for p in PROVIDER_OPTIONS
        ]

    def get_on_prem_defaults(self) -> dict[str, object]:
        """Return non-secret on-premises defaults (status only — never the key).

        Returns:
            Dict with ``server_url`` (str) and ``api_key_configured`` (bool).
            Never returns the decrypted API key (FR57 / FR58 / Task 10).
        """
        if self.project_context and self.project_context.artifact_service:
            db = self.project_context.artifact_service.db
            from ai_qa.secrets import SECRET_TYPE_ON_PREMISES
            from ai_qa.secrets.service import get_user_secret

            server_url = ""
            if self.project_context.thread_id:
                from ai_qa.threads.models import Thread

                thread = db.get(Thread, self.project_context.thread_id)
                if thread and thread.provider_base_url:
                    server_url = thread.provider_base_url

            stored = get_user_secret(db, self.project_context.user_id, SECRET_TYPE_ON_PREMISES)
            return {
                "server_url": server_url,
                "api_key_configured": bool(stored),
            }
        return {"server_url": "", "api_key_configured": False}

    def get_configured_providers(self) -> list[str]:
        """Provider ids that already have a stored secret for the current user.

        The frontend uses this to SKIP the credential prompt and reuse the stored
        key (auto-connect). Never returns any secret value — only which providers
        have one on file. Returns ``[]`` when there is no DB/user context.
        """
        if not (self.project_context and self.project_context.artifact_service):
            return []
        db = self.project_context.artifact_service.db
        from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
        from ai_qa.secrets.service import get_user_secret

        configured: list[str] = []
        for provider in PROVIDER_OPTIONS:
            secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider["id"])
            if secret_type and get_user_secret(db, self.project_context.user_id, secret_type):
                configured.append(provider["id"])
        return configured

    # -------------------------------------------------------------------------
    # BaseAgent Interface
    # -------------------------------------------------------------------------

    async def process(
        self,
        input_data: dict[str, Any],
        feedback: str | None = None,
    ) -> StageResult:
        """Process Alice step logic.

        Args:
            input_data: Provider selection and credentials
            feedback: User rejection feedback (for re-processing)

        Returns:
            StageResult with configuration data on success

        Raises:
            PipelineError: If connection test fails or invalid input
        """
        # Handle feedback/reject case
        if feedback:
            logger.info("Alice received feedback: %s", feedback)
            # Return to start state for re-selection
            return StageResult(
                success=True,
                data={"action": "restart_selection", "feedback": feedback},
            )

        # Extract provider selection and credentials
        provider_id = input_data.get("provider")
        credentials = input_data.get("credentials", {})

        if not provider_id:
            raise PipelineError("No provider selected")

        # Validate provider
        provider_info = self._get_provider_info(provider_id)
        if not provider_info:
            raise PipelineError(f"Unknown provider: {provider_id}")

        self._selected_provider = provider_id
        self._provider_credentials = credentials
        self._model_reasoning = []

        # Immediately update the thread with the provider info so it's not null in the DB
        # even if the connection test or LLM assignment fails later.
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.thread_id
        ):
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.threads.models import Thread

                thread = db.get(Thread, self.project_context.thread_id)
                if thread:
                    thread.provider_name = provider_id
                    thread.provider_base_url = provider_info.get("endpoint", "")
                    db.commit()
            except Exception as e:
                logger.warning("Failed to save initial provider info to DB: %s", e)

        # When the api_key is blank, resolve the user's STORED secret BEFORE the
        # connection test so the adapter receives the real key. This powers the
        # "key on file -> skip the prompt and auto-connect" UX for every provider
        # (on-premises blank-reuse, Claude SSO token from the OAuth callback, and
        # any provider whose key was entered on a previous run). ``_original_api_key``
        # stays blank for a reused key, so the persist block below never re-writes it
        # (Task 10 ordering fix preserved).
        _original_api_key = credentials.get("api_key", "").strip()
        if not _original_api_key and self.project_context and self.project_context.artifact_service:
            try:
                from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
                from ai_qa.secrets.service import get_user_secret

                _secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider_info["id"])
                if _secret_type:
                    _stored = get_user_secret(
                        self.project_context.artifact_service.db,
                        self.project_context.user_id,
                        _secret_type,
                    )
                    if _stored:
                        credentials = {**credentials, "api_key": _stored}
            except Exception as _pre_e:
                logger.warning(
                    "Failed to resolve stored key for %s: %s", provider_info["id"], _pre_e
                )

        # Test connection
        await self._send_connection_test_status(
            "testing", f"Testing connection to {provider_info['name']}..."
        )

        try:
            connection_result = await self._test_connection(provider_info, credentials)
        except Exception as exc:
            logger.error("Connection test failed: %s", exc)
            connection_result = ConnectionResult(
                success=False,
                provider=provider_info["id"],
                provider_name=provider_info["name"],
                status="failed",
                message=(
                    f"Could not validate the connection to {provider_info['name']}. "
                    "Please check your credentials and try again."
                ),
                error_category="provider_error",
            )

        if not connection_result.success:
            await self._send_connection_test_status("failed", connection_result.message)
            raise PipelineError(connection_result.message)

        # Persist credentials if user is authenticated.
        # Use _original_api_key (pre-resolution) so a reused stored key is never
        # re-written back to storage (Task 10).
        if self.project_context and self.project_context.artifact_service:
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
                from ai_qa.secrets.service import set_user_secret

                secret_type = PROVIDER_SECRET_TYPE_MAP.get(provider_info["id"])
                if secret_type and _original_api_key:
                    set_user_secret(
                        db, self.project_context.user_id, secret_type, _original_api_key
                    )
                    db.commit()
            except Exception as e:
                logger.warning("Failed to persist user credentials: %s", e)

        # Generate configuration
        self._configuration = await self._generate_configuration(provider_info, credentials)

        # Return result with model assignments for review
        return StageResult(
            success=True,
            data={
                "configuration": self._configuration.model_dump(),
                "model_assignments": self._get_model_assignments_display(),
                "provider_endpoint": self._mask_endpoint(self._configuration.provider.endpoint),
                "benchmark": get_provider_benchmark(provider_id),
            },
        )

    async def handle_start(self, input_data: dict[str, Any]) -> None:
        """Override handle_start to support existing configuration check."""
        if not self.project_context or not self.project_context.artifact_service:
            return

        db = self.project_context.artifact_service.db

        # 1. Project selection logic if thread is unbound
        if self.project_context.project_id is None:
            if input_data.get("project_id"):
                # Bind project
                from uuid import UUID

                from ai_qa.threads.service import ThreadService

                try:
                    project_id = UUID(str(input_data["project_id"]))
                except ValueError:
                    logger.error("Invalid project_id UUID format: %s", input_data.get("project_id"))
                    await self.send_message(
                        content="Invalid project selection payload format.",
                        message_type="error",
                    )
                    return

                thread_id = self.project_context.thread_id
                if not thread_id:
                    raise PipelineError("No thread_id in context")

                thread_service = ThreadService(db)
                try:
                    thread_service.bind_project(thread_id, project_id, self.project_context.user_id)
                    self.project_context.project_id = project_id
                except Exception as e:
                    logger.error("Failed to bind project to thread: %s", e)
                    await self.send_message(
                        content=f"Failed to bind project: {e}",
                        message_type="error",
                    )
                    return
            else:
                # Need to prompt for project selection
                from ai_qa.projects.service import get_user_projects

                projects = get_user_projects(db, self.project_context.user_id)
                if not projects:
                    await self.send_message(
                        content="You are not a member of any projects. Please ask an administrator to add you to a project before continuing.",
                        message_type="error",
                    )
                    return
                elif len(projects) == 1:
                    # Auto-bind if exactly 1 project
                    from ai_qa.threads.service import ThreadService

                    project_id = projects[0].id
                    thread_id = self.project_context.thread_id
                    if thread_id:
                        thread_service = ThreadService(db)
                        try:
                            thread_service.bind_project(
                                thread_id, project_id, self.project_context.user_id
                            )
                            self.project_context.project_id = project_id

                            await self.send_message(
                                content=f"Auto-bound to your only project: {projects[0].name}",
                                message_type="info",
                                metadata={
                                    "type": "project_auto_bind",
                                    "project_id": str(project_id),
                                    "project_name": projects[0].name,
                                },
                            )
                        except Exception as e:
                            logger.error("Failed to auto-bind project: %s", e)
                            await self.send_message(
                                content=f"Failed to auto-bind project: {e}",
                                message_type="error",
                            )
                            return
                    else:
                        raise PipelineError("No thread_id in context")
                else:
                    # Present options
                    project_options = [{"id": str(p.id), "name": p.name} for p in projects]
                    await self.send_message(
                        content="Please select a project for this conversation:",
                        message_type="info",
                        metadata={
                            "type": "project_selection",
                            "projects": project_options,
                        },
                    )
                    return  # Stop processing until frontend sends project_id back

        # 2. Check existing thread configuration (resume same thread)
        existing_config = await self.check_existing_configuration()

        if existing_config and not input_data.get("force_reconfigure"):
            # Use existing thread configuration — this is a RESUME, not a saved-config prompt.
            self._configuration = existing_config
            self._selected_provider = existing_config.provider.provider

            # Show review with existing config
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content=self._format_model_assignments(existing_config),
                message_type="text",
                metadata={
                    "configuration": existing_config.model_dump(),
                    "model_assignments": self._get_model_assignments_from_config(
                        existing_config, self._model_reasoning
                    ),
                    "provider_endpoint": self._mask_endpoint(existing_config.provider.endpoint),
                },
            )
            return

        # Handle explicit "use saved configuration" response from frontend
        if input_data.get("use_saved_config") and not input_data.get("force_reconfigure"):
            if (
                self.project_context
                and self.project_context.artifact_service
                and self.project_context.project_id  # F3: project must be bound
            ):
                db = self.project_context.artifact_service.db
                from ai_qa.userconfig.service import get_provider_config

                saved = get_provider_config(
                    db, self.project_context.user_id, self.project_context.project_id
                )
                if saved:
                    try:
                        prov = saved["provider"] or {}
                        saved_provider_id_s = prov.get("provider", "")
                        if not saved_provider_id_s:  # F4: reject empty provider
                            raise ValueError("Saved config has no provider id")
                        agt = saved["agents"] or {}
                        raw_agents_s = agt.get("agents") or {}
                        agents_dict_s: dict[str, Any] = {}
                        for agent_name, cfg_s in raw_agents_s.items():
                            agents_dict_s[agent_name] = {
                                "model": cfg_s.get("model"),
                                "temperature": float(cfg_s.get("temperature", 0.0)),
                                "prompt_template": cfg_s.get("prompt_template", "default"),
                                "tools": cfg_s.get("tools", []),
                            }
                        if not agents_dict_s:  # F5: reject empty agent assignments
                            raise ValueError("Saved config has no agent assignments")
                        if "alice" not in agents_dict_s:
                            agents_dict_s["alice"] = {
                                "model": "claude-3-5-sonnet-20241022",
                                "temperature": 0.0,
                                "prompt_template": "default",
                                "tools": [],
                            }
                        # F2: restore _model_reasoning so _save_configuration writes real
                        # rationale into the new thread snapshot (not empty strings).
                        self._model_reasoning = [
                            {
                                "agent": n,
                                "model": cfg_s.get("model", ""),
                                "rationale": cfg_s.get("rationale", ""),
                            }
                            for n, cfg_s in raw_agents_s.items()
                        ]
                        from ai_qa.models import AgentsConfig, AliceConfiguration, ProviderConfig

                        loaded_config = AliceConfiguration(
                            provider=ProviderConfig(
                                provider=saved_provider_id_s,
                                provider_name=prov.get("provider_name", ""),
                                endpoint=prov.get("endpoint", ""),
                                credential_reference="",
                                tested_at=prov.get("tested_at", ""),
                                test_result=prov.get("test_result", "success"),
                            ),
                            agents=AgentsConfig.model_validate(
                                {"updated_at": "", "agents": agents_dict_s}
                            ),
                        )
                        self._configuration = loaded_config
                        self._selected_provider = loaded_config.provider.provider
                        self._save_configuration(loaded_config)
                        await self.transition_to(AgentState.DONE)
                        return
                    except Exception as exc:
                        logger.warning("Failed to apply saved config: %s", exc)
            # F7+F8: show provider options directly — do NOT fall through to the
            # saved-config prompt block, which would re-offer the same config.
            await self.send_message(
                content="Saved configuration could not be applied. Please select a provider.",
                message_type="info",
            )
            await self.send_message(
                content="",
                message_type="info",
                metadata={
                    "type": "provider_options",
                    "options": self.get_provider_options(),
                    "on_prem_defaults": self.get_on_prem_defaults(),
                    "configured_providers": self.get_configured_providers(),
                },
            )
            return

        # Check if there is a valid saved (user, project) config to offer explicitly
        if (
            not input_data.get("provider")
            and not input_data.get("force_reconfigure")
            and self.project_context
            and self.project_context.artifact_service
            and self.project_context.project_id
        ):
            db = self.project_context.artifact_service.db
            from ai_qa.userconfig.service import get_provider_config

            saved_cfg = get_provider_config(
                db, self.project_context.user_id, self.project_context.project_id
            )
            if saved_cfg and saved_cfg.get("provider"):
                saved_provider_id = (saved_cfg["provider"] or {}).get("provider", "")
                # Validity check: provider in project.enabled_providers AND secret configured
                from ai_qa.db.models import Project
                from ai_qa.secrets import PROVIDER_SECRET_TYPE_MAP
                from ai_qa.secrets.service import get_user_secret

                project = db.get(Project, self.project_context.project_id)
                enabled = (project.enabled_providers if project else []) or []
                provider_allowed = not enabled or saved_provider_id in enabled
                secret_type = PROVIDER_SECRET_TYPE_MAP.get(saved_provider_id)
                secret_ok = bool(
                    secret_type and get_user_secret(db, self.project_context.user_id, secret_type)
                )
                if provider_allowed and secret_ok:
                    prov_meta = saved_cfg["provider"] or {}
                    agt_meta = (saved_cfg.get("agents") or {}).get("agents") or {}
                    agents_summary = [
                        {
                            "agent": n,
                            "model": v.get("model", ""),
                            "rationale": v.get("rationale", ""),
                        }
                        for n, v in agt_meta.items()
                    ]
                    await self.send_message(
                        content="You have a saved provider configuration for this project.",
                        message_type="info",
                        metadata={
                            "type": "saved_config_prompt",
                            "saved_config": {
                                "provider_name": prov_meta.get("provider_name", ""),
                                "endpoint": self._mask_endpoint(prov_meta.get("endpoint", "")),
                                "agents": agents_summary,
                            },
                            "options": self.get_provider_options(),
                            "enabled_providers": enabled,
                        },
                    )
                    return

        # Check if user already selected provider (frontend sent provider in input_data)
        if input_data.get("provider"):
            # User already selected provider, skip greeting and go straight to processing
            await self.transition_to(AgentState.PROCESSING)
            try:
                result = await self.process(input_data, feedback=None)
            except PipelineSilentAbortError:
                return
            except PipelineError as exc:
                logger.error("Alice process failed: %s", exc)
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message([str(exc)]),
                    message_type="error",
                )
                return

            if result.success:
                await self.transition_to(AgentState.REVIEW_REQUEST)
                await self.send_message(
                    content=self._format_review_content(result),
                    message_type="text",
                    metadata=result.data,
                )
            else:
                await self.transition_to(AgentState.ERROR)
                await self.send_message(
                    content=self._format_error_message(result.errors),
                    message_type="error",
                )
        else:
            # No provider selected yet — show the provider options. The card panel
            # carries its own heading, so no greeting/"select a provider" chat text
            # (content="" keeps the bubble empty; the panel renders from metadata).
            await self.send_message(
                content="",
                message_type="info",
                metadata={
                    "type": "provider_options",
                    "options": self.get_provider_options(),
                    "on_prem_defaults": self.get_on_prem_defaults(),
                    "configured_providers": self.get_configured_providers(),
                },
            )

    def _format_error_message(self, errors: list[str]) -> str:
        """Override base error formatting to remove generic text for Rate Limit errors."""
        error_text = errors[0] if errors else "An unexpected error occurred"
        if "Rate Limit Error:" in error_text:
            return (
                f"**What happened:** {error_text}\n\n"
                f"**What to do:** Please check your provider subscription plan and billing details, or create a new thread using a different API key."
            )
        return super()._format_error_message(errors)

    async def handle_approve(self, data: dict[str, Any] | None = None) -> None:
        """Save configuration and complete Alice step."""
        if self._configuration is None:
            logger.error("Cannot approve - no configuration generated")
            await self.send_message(
                content="Error: No configuration to approve. Please start over.",
                message_type="error",
            )
            return

        if data and "assignments" in data:
            for agent_name, new_model in data["assignments"].items():
                if agent_name in self._configuration.agents.agents:
                    self._configuration.agents.agents[agent_name].model = new_model

        # Save configuration files
        try:
            self._save_configuration(self._configuration)
        except OSError as exc:
            logger.error("Failed to save configuration: %s", exc)
            await self.send_message(
                content=f"Failed to save configuration: {exc}",
                message_type="error",
            )
            await self.transition_to(AgentState.ERROR)
            return

        # Persist non-secret config per (user, project) for future threads
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.project_id
        ):
            try:
                db = self.project_context.artifact_service.db
                from ai_qa.userconfig.service import save_provider_config

                provider_cfg = {
                    "provider": self._configuration.provider.provider,
                    "provider_name": self._configuration.provider.provider_name,
                    "endpoint": self._configuration.provider.endpoint,
                    "tested_at": self._configuration.provider.tested_at,
                    "test_result": self._configuration.provider.test_result,
                    "rationale": "",
                }
                reasoning_map = {
                    r["agent"]: r.get("rationale", "")
                    for r in self._model_reasoning
                    if isinstance(r, dict) and "agent" in r
                }
                agents_cfg: dict[str, Any] = {"version": "1", "updated_at": "", "agents": {}}
                for name, cfg in self._configuration.agents.agents.items():
                    agents_cfg["agents"][name] = {
                        "model": cfg.model,
                        "temperature": cfg.temperature,
                        "prompt_template": cfg.prompt_template,
                        "tools": list(cfg.tools),
                        "rationale": reasoning_map.get(name, ""),
                    }
                save_provider_config(
                    db,
                    self.project_context.user_id,
                    self.project_context.project_id,
                    provider_cfg,
                    agents_cfg,
                )
                db.commit()
            except Exception as exc:
                logger.warning("Failed to persist per-project provider config: %s", exc)

        await self.transition_to(AgentState.DONE)

    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Reject the model assignment review and return to provider configuration.

        Does NOT persist any approved configuration. Only creates a conversational
        acknowledgment message and resets the thread to configuration adjustment.
        """
        await self.send_message(
            content="Understood. Let's adjust your provider configuration.",
            message_type="text",
        )
        # Clear generated configuration so re-selection starts fresh
        self._configuration = None
        self._model_reasoning = []
        await self.transition_to(AgentState.START)
        # Re-show provider options so the user can reconfigure
        await self.send_message(
            content="",
            message_type="info",
            metadata={
                "type": "provider_options",
                "options": self.get_provider_options(),
                "on_prem_defaults": self.get_on_prem_defaults(),
                "configured_providers": self.get_configured_providers(),
            },
        )

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _assign_fallback_models(self, models_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Best-effort per-agent picks for the all-models-unavailable error trace.

        Reuses the benchmark ranking table so the display stays consistent with
        the normal deterministic assignment. Only reached when every discovered
        model is unsupported/unavailable (the pipeline aborts afterwards), so the
        picks are informational. Falls back to the first listed model, then to
        ``"Unavailable"`` when nothing was discovered at all.
        """
        model_ids = [str(m["id"]) for m in models_list]
        reasoning: list[dict[str, Any]] = []
        for agent in ["alice", "bob", "mary", "sarah", "jack"]:
            chosen = _select_best_model(model_ids, _AGENT_CAPABILITY_RANK[agent])
            if not chosen:
                chosen = model_ids[0] if model_ids else "Unavailable"
            reasoning.append(
                {
                    "agent": agent.capitalize(),
                    "purpose": AGENT_PURPOSES.get(agent, ""),
                    "model": chosen,
                    "reasoning": "Fallback selection due to empty or rate-limited models.",
                }
            )
        return reasoning

    def _get_provider_info(self, provider_id: str) -> dict[str, Any] | None:
        """Get provider info by ID."""
        for p in PROVIDER_OPTIONS:
            if p["id"] == provider_id:
                info = p.copy()
                setting_name = info.get("endpoint_setting")
                if setting_name:
                    # Resolve the config-owned base URL through the registry so the
                    # provider adapters and Alice share a single source of truth
                    # (avoids drift between PROVIDER_OPTIONS and the registry map).
                    info["endpoint"] = resolve_base_url(self._settings, provider_id)
                return info
        return None

    async def _test_connection(
        self, provider_info: dict[str, Any], credentials: dict[str, str]
    ) -> ConnectionResult:
        """Test connection to provider via its adapter.

        Delegates auth + reachability validation to the provider adapter, which
        owns the on-prem config guard, the api-key format floor, and all
        provider-specific header/endpoint details. Base URLs are config-owned
        (resolved via ``resolve_base_url`` in ``_get_provider_info``); credentials
        are passed in by the caller.

        Args:
            provider_info: Provider configuration (includes config-owned endpoint)
            credentials: User-provided credentials

        Returns:
            A normalized, secret-free ``ConnectionResult``.
        """
        provider_id = provider_info["id"]
        endpoint = provider_info.get("endpoint", "")
        adapter = get_provider_adapter(provider_id)
        result = await adapter.validate_connection(
            {"api_key": credentials.get("api_key", "")}, endpoint
        )
        if result.success:
            logger.info("Connection test passed for %s", provider_info["name"])
        return result

    async def _simulate_delay(self, seconds: float) -> None:
        """Simulate processing delay."""
        import asyncio

        await asyncio.sleep(seconds)

    async def _send_connection_test_status(self, status: str, message: str) -> None:
        """Send connection test status update."""
        await self.send_message(
            content=message,
            message_type="info" if status != "failed" else "error",
            metadata={
                "type": "connection_test",
                "status": status,
                "message": message,
            },
        )

    async def _generate_configuration(
        self, provider_info: dict[str, Any], credentials: dict[str, str]
    ) -> AliceConfiguration:
        """Generate complete configuration for selected provider.

        Args:
            provider_info: Selected provider info
            credentials: User credentials

        Returns:
            Complete AliceConfiguration
        """
        provider_id = provider_info["id"]
        now = datetime.now(UTC).isoformat()

        # Determine endpoint
        endpoint = provider_info.get("endpoint", "")
        api_key = credentials.get("api_key", "")

        # 1. Discover available models via the provider adapter (Story 9.4).
        #    Discovery runs only after a successful validate_connection in
        #    process(), so the AC1 precondition is satisfied. The adapter returns
        #    the raw discovered set; Alice owns ranking/assignment + the gate.
        adapter = get_provider_adapter(provider_id)
        discovered = await adapter.list_models({"api_key": api_key}, endpoint)

        # Categorize models into available and unavailable
        available_models: list[dict[str, Any]] = []
        unavailable_models: list[dict[str, Any]] = []

        for dm in discovered:
            # Skip non-generative families (embeddings / tts / stt / rerankers /
            # OCR / ASR …) via the shared classifier so Alice's pool and the admin
            # "Sync models and benchmarks" action agree on what counts as a chat model.
            if is_non_generative_model(dm.id):
                unavailable_models.append(
                    {"id": dm.id, "name": dm.display_name, "status": "not support / outdated"}
                )
            else:
                available_models.append(
                    {
                        "id": dm.id,
                        "name": dm.display_name,
                        "supports_vision": dm.supports_vision,
                    }
                )

        if not available_models:
            # Emit trace to show the models that were discovered but unavailable
            fallback_assignments = self._assign_fallback_models(unavailable_models)
            error_trace = {
                "connection_status": "success",
                "available_models": [],
                "unavailable_models": unavailable_models,
                "chain_of_thought": [
                    "[What happened] No available models were found. "
                    "The provider may have rejected model-listing requests (check that your "
                    "key has model-listing permissions) or no models match your credentials.",
                    "[What to do] Verify your API key has access to list models, "
                    "then create a new thread to try again.",
                ],
                "assignments": fallback_assignments,
            }
            await self.send_message(
                content="Finished model assignment reasoning.",
                message_type="info",
                metadata={"type": "thinking_trace", "trace": error_trace},
            )

            # Transition to ERROR and abort silently to prevent plaintext bubble
            await self.transition_to(AgentState.ERROR)
            raise PipelineSilentAbortError()

        # Persist the discovered pool so the admin dashboard can list/score models
        # without holding live gateway credentials (best-effort, never blocks).
        self._snapshot_discovered_models(available_models)

        # 2. Bootstrap Alice model (admin scores are the highest selection tier).
        admin_score_rows = self._load_admin_score_rows()
        alice_model, alice_rationale = self._bootstrap_alice_model(
            available_models, admin_score_rows
        )
        if not alice_model:
            raise PipelineError(
                "No available model to proceed. Please check your subscription then create a new thread to continue."
            )

        # 3. Assign per-agent models deterministically from the benchmark
        #    ranking table (no LLM, no network — fully reproducible).
        model_mappings, reasoning = self._assign_models(
            alice_model, available_models, admin_score_rows
        )

        # 4. Emit thinking trace
        trace_payload: dict[str, Any] = {
            "connection_status": "success",
            "available_models": available_models,
            "unavailable_models": unavailable_models,
            "bootstrap_model": alice_model,
            "bootstrap_rationale": alice_rationale,
            "agent_needs": AGENT_PURPOSES,
            "assignments": reasoning,
            "benchmark": get_provider_benchmark(provider_id),
        }
        await self.send_message(
            content="Finished model assignment reasoning.",
            message_type="info",
            metadata={"type": "thinking_trace", "trace": trace_payload},
        )

        # Create provider config
        provider_config = ProviderConfig(
            provider=provider_id,
            provider_name=provider_info["name"],
            endpoint=endpoint,
            credential_reference="",
            tested_at=now,
            test_result="success",
        )

        agents: dict[str, AgentModelConfig] = {}
        # Also assign Alice her model
        agents["alice"] = AgentModelConfig(
            model=alice_model,
            temperature=0.0,
            prompt_template="default_v1",
            tools=[],
        )
        for agent_name in ["bob", "mary", "sarah", "sarah_explore", "jack"]:
            agents[agent_name] = AgentModelConfig(
                model=model_mappings.get(agent_name, alice_model),
                temperature=0.0,
                prompt_template=AGENT_PROMPT_TEMPLATES.get(agent_name, "default_v1"),
                tools=AGENT_TOOLS.get(agent_name, []),
            )

        agents_config = AgentsConfig(
            updated_at=now,
            agents=agents,
        )

        # Store rationale for display in the review panel (threaded through
        # _get_model_assignments_display / _format_model_assignments). Alice's own
        # rationale is only carried on the bootstrap trace (bootstrap_rationale), so
        # prepend it here too — otherwise her row in the confirm/review table (and the
        # persisted agent_configs) would render with a blank rationale. Kept out of the
        # trace ``assignments`` above so the bootstrap card never lists Alice twice.
        self._model_reasoning = [
            {"agent": "alice", "model": alice_model, "rationale": alice_rationale},
            *reasoning,
        ]

        # Immediately update the thread with the provider info so it's not null in the DB
        # before the user approves the agent configurations.
        if (
            self.project_context
            and self.project_context.artifact_service
            and self.project_context.thread_id
        ):
            db = self.project_context.artifact_service.db
            from ai_qa.threads.models import Thread

            thread = db.get(Thread, self.project_context.thread_id)
            if thread:
                thread.provider_name = provider_id
                thread.provider_base_url = endpoint
                db.commit()

        return AliceConfiguration(provider=provider_config, agents=agents_config)

    def _save_configuration(self, config: AliceConfiguration) -> None:
        """Save configuration to Thread database."""
        if (
            not self.project_context
            or not self.project_context.artifact_service
            or not self.project_context.thread_id
        ):
            logger.error("No project context or thread_id available to save configuration.")
            raise OSError("No thread_id available to save configuration.")

        db = self.project_context.artifact_service.db
        from ai_qa.threads.models import Thread

        thread = db.get(Thread, self.project_context.thread_id)
        if thread:
            thread.provider_name = config.provider.provider
            thread.provider_base_url = config.provider.endpoint

            # Write structured per-agent entries (model + temperature + rationale)
            # so check_existing_configuration and _load_agent_config can round-trip.
            reasoning_map = {
                r["agent"]: r.get("rationale", "")
                for r in self._model_reasoning
                if isinstance(r, dict) and "agent" in r
            }
            new_configs = {}
            for agent_name, agent_cfg in config.agents.agents.items():
                new_configs[agent_name] = {
                    "model": agent_cfg.model,
                    "temperature": agent_cfg.temperature,
                    "rationale": reasoning_map.get(agent_name, ""),
                }

            thread.agent_configs = new_configs

            db.commit()
            logger.info("Configuration saved to database for thread %s", thread.id)
        else:
            raise OSError("Thread not found to save configuration.")

    def _is_config_valid(self, provider_data: dict[str, Any]) -> bool:
        """Check if existing configuration is still valid (not expired)."""
        try:
            tested_at = datetime.fromisoformat(provider_data.get("tested_at", "1970-01-01"))
            age_days = (datetime.now(UTC) - tested_at).days
            return age_days < 30
        except ValueError, TypeError:
            return False

    def _get_model_assignments_display(self) -> list[dict[str, str]]:
        """Get model assignments for display in review (with rationale)."""
        if not self._configuration:
            return []

        return self._get_model_assignments_from_config(self._configuration, self._model_reasoning)

    def _get_model_assignments_from_config(
        self,
        config: AliceConfiguration,
        reasoning: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        """Get model assignments from configuration."""
        reasoning_map: dict[str, str] = {}
        if reasoning:
            for r in reasoning:
                if isinstance(r, dict) and "agent" in r and "rationale" in r:
                    reasoning_map[r["agent"]] = r["rationale"]

        assignments = []
        for agent_name, agent_config in config.agents.agents.items():
            if agent_name == "alice":
                purpose = "Provider Selection & Configuration"
            else:
                purpose = AGENT_PURPOSES.get(agent_name, "Agent task")
            agent_display = _AGENT_DISPLAY_NAME.get(agent_name, agent_name.capitalize())
            # Prefer the real (possibly degraded-annotated) rationale; fall back to the
            # canonical per-agent template so resumed/legacy threads whose stored
            # rationale is blank still render a reason that matches the bootstrap card.
            rationale = reasoning_map.get(agent_name, "")
            if not rationale:
                template = _AGENT_RATIONALE.get(agent_name, "")
                rationale = template.format(model=agent_config.model) if template else ""
            assignments.append(
                {
                    # ``key`` is the stable config/override key (e.g. "sarah_explore"); ``agent``
                    # is the human label. The review UI overrides by ``key`` so two Sarah rows
                    # (script-gen + browser-explore) never collide.
                    "key": agent_name,
                    "agent": agent_display,
                    "model": agent_config.model,
                    "purpose": purpose,
                    "rationale": rationale,
                }
            )
        return assignments

    def _bootstrap_alice_model(
        self,
        available_models: list[dict[str, Any]],
        admin_score_rows: list[tuple[str, str, float]] | None = None,
    ) -> tuple[str, str]:
        """Bootstrap Alice's reasoning model from the benchmark ranking table.

        Picks the highest-ranked *discovered* model for general reasoning
        (``_REASONING_RANK``); falls back to the first discovered model when no
        ranked preference matches the pool.

        Returns:
            tuple of (model_id, rationale)
        """
        if not available_models:
            return "", ""

        admin = _merge_scores(admin_score_rows or [], _AGENT_CAPABILITY_NAME["alice"])
        pick = _select_model_for("alice", available_models, admin)
        if pick:
            return pick["model"], _AGENT_RATIONALE["alice"].format(model=pick["model"])

        # Fallback to first available
        return str(available_models[0]["id"]), "Fallback to first available model."

    def _load_admin_score_rows(self) -> list[tuple[str, str, float]]:
        """Operator-supplied benchmark scores (admin dashboard), highest selection tier.

        Reads ``model_benchmark_scores`` via the agent's DB session and returns
        ``[(model_id, capability, score)]``. Resilient: returns ``[]`` when no real
        session/context is available (e.g. unit tests with a mocked context) or on
        any query error, so selection degrades to the curated/heuristic tiers.
        """
        ctx = self.project_context
        service = ctx.artifact_service if ctx else None
        db = service.db if service else None
        if db is None:
            return []
        try:
            from sqlalchemy import select

            from ai_qa.db.models import ModelBenchmarkScore

            result = db.execute(
                select(
                    ModelBenchmarkScore.model_id,
                    ModelBenchmarkScore.capability,
                    ModelBenchmarkScore.score,
                )
            ).all()
        except Exception as exc:  # pragma: no cover - defensive, mocked DBs etc.
            logger.warning("Could not load admin model scores: %s", type(exc).__name__)
            return []
        # A real query yields a list of Row tuples; a mocked session does not.
        if not isinstance(result, list):
            return []
        return [(str(r[0]), str(r[1]), float(r[2])) for r in result]

    def _snapshot_discovered_models(self, available_models: list[dict[str, Any]]) -> None:
        """Upsert the current discovered pool into ``discovered_models`` (best-effort).

        Lets the admin dashboard list models to score without live credentials.
        Never raises — a snapshot failure must not abort a configuration run.
        """
        ctx = self.project_context
        service = ctx.artifact_service if ctx else None
        db = service.db if service else None
        if db is None:
            return
        try:
            from sqlalchemy import select

            from ai_qa.db.models import DiscoveredModelSnapshot

            now = datetime.now(UTC)
            for model in available_models:
                model_id = str(model["id"])
                row = db.execute(
                    select(DiscoveredModelSnapshot).where(
                        DiscoveredModelSnapshot.model_id == model_id
                    )
                ).scalar_one_or_none()
                if row is None:
                    db.add(
                        DiscoveredModelSnapshot(
                            model_id=model_id,
                            display_name=str(model.get("name") or model_id),
                            supports_vision=model.get("supports_vision"),
                            last_seen_at=now,
                        )
                    )
                else:
                    row.display_name = str(model.get("name") or model_id)
                    row.supports_vision = model.get("supports_vision")
                    row.last_seen_at = now
            db.commit()
        except Exception as exc:  # pragma: no cover - best-effort, never blocks config
            logger.warning("Could not snapshot discovered models: %s", type(exc).__name__)
            try:
                db.rollback()
            except Exception:
                logger.debug("Rollback after snapshot failure also failed.")

    def _assign_models(
        self,
        alice_model: str,
        available_models: list[dict[str, Any]],
        admin_score_rows: list[tuple[str, str, float]] | None = None,
    ) -> tuple[dict[str, str], list[dict[str, str]]]:
        """Deterministically assign per-agent models from the discovered pool.

        Uses the benchmark ranking table (``_AGENT_CAPABILITY_RANK``) to pick the
        best discovered model for each agent's primary capability — no LLM call,
        no network, fully reproducible. Bob is matched against a vision-only
        ranking so it can never receive a text-only flagship. Any agent with no
        ranked match falls back to ``alice_model`` (itself a discovered id), so an
        undiscovered model is never assigned (Story 9.4 AC3).

        Returns:
            tuple of (mappings, reasoning) keyed by agent (bob/mary/sarah/jack).
        """
        rows = admin_score_rows or []
        mappings: dict[str, str] = {}
        reasoning: list[dict[str, str]] = []
        for agent in ["bob", "mary", "sarah", "sarah_explore", "jack"]:
            admin = _merge_scores(rows, _AGENT_CAPABILITY_NAME[agent])
            pick = _select_model_for(agent, available_models, admin)
            chosen = pick["model"] if pick else alice_model
            mappings[agent] = chosen
            rationale = _AGENT_RATIONALE[agent].format(model=chosen)
            if pick and pick.get("degraded"):
                rationale += " (no vision-capable model in the pool — using best general model.)"
            reasoning.append(
                {
                    "agent": agent,
                    "model": chosen,
                    "rationale": rationale,
                    "tier_source": str(pick["source"]) if pick else "fallback",
                    "score_breakdown": str(pick["breakdown"]) if pick else "",
                }
            )
        return mappings, reasoning

    @staticmethod
    def _mask_endpoint(endpoint: str) -> str:
        """Mask sensitive parts of endpoint for display."""
        if not endpoint:
            return "N/A"

        # Keep domain but mask any API keys in URL
        try:
            from urllib.parse import urlparse

            parsed = urlparse(endpoint)
            return f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            return endpoint[:30] + "..." if len(endpoint) > 30 else endpoint

    def _format_review_content(self, result: StageResult) -> str:
        """Format review content with model assignments table."""
        if not result.data or "model_assignments" not in result.data:
            return "Review ready."

        assignments: list[dict[str, str]] = result.data.get("model_assignments", [])
        endpoint: str = result.data.get("provider_endpoint", "N/A")
        provider_id = self._selected_provider
        provider_info = self._get_provider_info(provider_id) if provider_id else None
        provider_name = provider_info["name"] if provider_info else "Provider"

        lines = [
            f"Connected successfully to {provider_name}.",
            "",
            "## AI Provider Configuration Review",
            "",
            f"**Provider Endpoint:** {endpoint}",
            "",
            "### Model Assignments",
            "",
            "| Agent | Model | Purpose | Rationale |",
            "|-------|-------|---------|-----------|",
        ]

        for assignment in assignments:
            rationale = assignment.get("rationale", "")
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} | {rationale} |"
            )

        lines.extend(
            [
                "",
                "Please review the configuration above. Click **Approve** to save and continue, "
                "or **Reject** to change your provider settings.",
            ]
        )

        return "\n".join(lines)

    def _format_model_assignments(self, config: AliceConfiguration) -> str:
        """Format model assignments from existing config."""
        assignments = self._get_model_assignments_from_config(config, self._model_reasoning)
        endpoint = self._mask_endpoint(config.provider.endpoint)

        lines = [
            "## AI Provider Configuration Review",
            "",
            f"**Provider:** {config.provider.provider_name}",
            f"**Endpoint:** {endpoint}",
            "",
            "### Model Assignments",
            "",
            "| Agent | Model | Purpose | Rationale |",
            "|-------|-------|---------|-----------|",
        ]

        for assignment in assignments:
            rationale = assignment.get("rationale", "")
            lines.append(
                f"| {assignment['agent']} | {assignment['model']} | {assignment['purpose']} | {rationale} |"
            )

        lines.extend(
            [
                "",
                "This is your saved configuration. Click **Approve** to continue with these settings, "
                "or **Reject** to reconfigure.",
            ]
        )

        return "\n".join(lines)
