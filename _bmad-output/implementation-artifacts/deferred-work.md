# Deferred Work Log

## Deferred from: code review of 1-4-shared-pydantic-models-stageresult-agentmessage (2026-04-09)

- `StageResult.data: Any|None` defeats type safety — intentional; different pipeline stages return different types. Consider TypeVar or typed subclasses when stage types are finalized.
- `success=False` but `data` populated: no validation — intentional design; partial results on failure are valid for progressive pipeline stages.
- errors/warnings as plain strings, no structured error codes — future enhancement; add structured error types (code, severity, source) when i18n or error recovery is needed.
- `ALL_AGENTS`/`ALL_STAGES` lists not enforced as validation — future stories will add validation where these constants are used in routing and dispatch logic.
- Circular import risk if `models.py` imports `exceptions.py` in future — pre-existing concern; monitor as pipeline grows; ensure models stay import-free of other ai_qa modules.

## Deferred from: code review of 1-2-configuration-system-with-pydantic-settings (2026-04-08)

- `file_secret_settings` dropped from pydantic-settings source chain — intentional per current spec; revisit if Docker/K8s secret-file injection is needed later.
- Missing negative temperature boundary test (`-0.1`) — lower-bound validation untested; expand in Story 1.5 when test infra (conftest, pytest-cov) is set up.
- URL format validation (`AnyHttpUrl`) not enforced on `on_premises_ai_server_url` — bare `str` field; add Pydantic URL type when provider validation is tightened.
- `reload(cfg)` in tests leaves module in reloaded state — proper conftest fixtures with import isolation deferred to Story 1.5.
- Malformed YAML parse error (`config.yaml` with invalid syntax) is untested — add error-handling test in Story 1.5 with full test infrastructure.

## Deferred from: code review of 1-1-project-restructure-to-src-layout (2026-04-07)

- `browser.kill()` without error handling — cleanup exception will propagate uncaught in `src/ai_qa/__main__.py`. Will be addressed in browser agent story (Epic 5).
- Non-standard env var naming with hyphens: `ON-PREMISES-AI-SERVER-URL` should use underscores per POSIX convention. Pre-existing issue from original `main.py`.
- Missing `[tool.hatch.build.targets.sdist]` config in `pyproject.toml` — sdist builds may misbehave. Not required by current story scope; address before first public release.

## Deferred from: code review of 2-3-baseagent-lifecycle-start-processing-review-done (2026-04-15)

- Missing logging level configuration [src/ai_qa/api/routes.py:30] — Logger instantiated but no configuration shown for log levels or handlers. Pre-existing issue not caused by this change.

## Deferred from: code review of 3-2-confluence-reader-pipeline-stage (2026-04-17)

- Pipeline trigger integration missing — FR10 requires stage to work as pipeline trigger. No trigger registration or pipeline integration code present. Out of scope for this story; requires separate integration work with pipeline orchestrator.

## Deferred from: code review of 3-3-content-parser-markdown-mermaid-and-images (2026-04-18)

- ReDoS risk on `.*?` with DOTALL in Confluence macro regexes [content_parser.py:127–160] — pre-existing regex pattern; mitigate when/if Confluence payloads are untrusted or from external sources.
- `warnings` local parameter shadows Python's built-in `warnings` module [content_parser.py:126] — low risk now (no `import warnings` in file); rename parameter if `warnings` module is ever imported.
- `TEST_CASE_HEADING_PATTERN` greedily captures entire document body if no subsequent `##` heading exists — complex regex edge case; defer to Epic 4 LLM-powered extraction (Story 4.2) which supersedes regex detection.
- Image format not validated — non-image file URLs in `<img src>` attributes will be downloaded; add file extension allowlist (PNG, JPG, GIF, WebP, SVG) when security posture is tightened.

## Deferred from: code review of 4-1-llm-abstraction-layer-langchain-litellm (2026-04-18)

- Timeout substring match quá rộng có thể false positive [client.py:60-61] — not required by acceptance criteria; current heuristic sufficient for internal LiteLLM proxy usage

## Deferred from: code review of 5-2-script-generator-pipeline-stage (2026-04-19)

- No parallelism for large test suites [script_generator.py:77-91] — Sequential for-loop processes test cases one-by-one. Pre-existing architecture pattern from other pipeline stages; consider asyncio.gather or ThreadPoolExecutor when performance becomes a bottleneck

