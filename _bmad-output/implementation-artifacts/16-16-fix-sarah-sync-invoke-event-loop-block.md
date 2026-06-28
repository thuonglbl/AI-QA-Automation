---
baseline_commit: 7641ef215742a18d6f5ca7951b6193abcf80164a
---
# Story 16.16: Fix Sarah sync-invoke event-loop block

Status: done

> **Priority: P1 (freeze, Sarah step).** UAT finding #1 — a confirmed latent
> whole-loop freeze that fires when Sarah's script-generation step runs on a slow model.

## Story

As a QA user,
I want Sarah's script generation to run its LLM calls without blocking the single event loop,
so that a slow on-prem model during script generation does not freeze the WebSocket and every HTTP route.

### Root cause (forensic, code-verified)

`ScriptGenerator._call_llm` / `_call_llm_with_trace` / `_call_llm_with_vision` are `async def` but call the **synchronous** `llm_client.invoke(...)` directly on the event loop ([script_generator.py:413/494/575](src/ai_qa/pipelines/script_generator.py:413)) — the only sync `.invoke(` on an async path in the repo. A slow on-prem call then blocks the loop for the whole duration, stalling WS heartbeats and every HTTP route (`AuthMiddleware.dispatch` `await call_next`).

## Acceptance Criteria

1. **Non-blocking LLM call.** Given Sarah generates a script, when the LLM call runs, then it does not block the event loop (the synchronous `invoke` is offloaded to a worker thread), so concurrent WS/HTTP work keeps progressing.
2. **Behavior preserved.** Given the LLM call, when it runs, then it still goes through `LLMClient.invoke` (keeping tenacity retry + typed-error mapping) and returns the same script content.
3. **No test regression.** Given the existing `test_script_generator` suite (which mocks `client.invoke`), when it runs, then it still passes unchanged.

## Tasks / Subtasks

- [x] **Task 1 — Offload the sync invoke (AC1, AC2)**
  - [x] `import asyncio`; replace the 3 `llm_client.invoke(messages, timeout=timeout)` call sites with `await asyncio.to_thread(llm_client.invoke, messages, timeout=timeout)`.
  - [x] Chose `to_thread` over `ainvoke` deliberately: it keeps the sync `invoke` interface so the ~25 existing tests that mock `client.invoke` stay valid, while still freeing the loop.
- [x] **Task 2 — Test (AC1, AC3)**
  - [x] `tests/pipelines/test_script_generator_async_offload.py`: assert `_call_llm` routes the sync invoke through `asyncio.to_thread` and still returns the script.
- [x] **Task 3 — Verification gates**
  - [x] ruff + mypy + targeted pytest green (2026-06-23): `ruff check` clean; `mypy src/ai_qa/pipelines/script_generator.py` → no issues; `pytest tests/pipelines/test_script_generator_async_offload.py tests/pipelines/test_script_generator.py` → 96 passed.

## Files changed

- `src/ai_qa/pipelines/script_generator.py` (`import asyncio` + 3 call sites → `asyncio.to_thread`)
- `tests/pipelines/test_script_generator_async_offload.py` (new)

## Notes / deferred

- An optional `asyncio.wait_for` total wall-clock guard (mirroring Bob's convert/vision guards) was left out to avoid compounding with the existing tenacity retry; the httpx read timeout (`LLMConfig.timeout`) still bounds each attempt. Can be added later if a byte-trickling provider is observed.
