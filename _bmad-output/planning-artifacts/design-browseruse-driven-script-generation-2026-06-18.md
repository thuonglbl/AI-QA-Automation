# Design — browser-use-driven test-script generation (Sarah)

- **Date:** 2026-06-18
- **Author:** Thuong (with Claude Code)
- **Status:** IMPLEMENTED (2026-06-18) — Slices 1–6 done; unit-tested + suite green (backend 1459 passed, frontend 273 passed). Slice 5 added the Sarah UI inputs (target_url + chrome_path); Slice 6 added **Chrome SSO reuse via CDP connect** (`cdp_url` → connect to a running Chrome and reuse its live authenticated session). Live exploration remains integration-only (manual run with a reachable app + provider key + either a CDP URL to a logged-in Chrome or a Chrome executable).
- **Scope:** Major (new live-exploration → trace → deterministic-Playwright subsystem in Sarah)
- **Affects:** Epic 13 (Sarah / script generation)

---

## 1. Problem

Sarah currently generates Playwright pytest scripts with a **pure LLM text→text call** ([script_generator.py](../../src/ai_qa/pipelines/script_generator.py)). `browser-use` (v0.13.1, MIT, installed) is only used as an **optional vision *hint*** path ([browser/agent.py](../../src/ai_qa/browser/agent.py) `BrowserAgent`, `task="navigation only"`): it screenshots the page and a vision model *suggests* selectors that are injected into the prompt. The script itself is still **LLM-invented** — selectors can be hallucinated and the flow is **never executed/verified against the real app** during generation. Quality is capped by what the LLM can guess from text.

**Goal:** use browser-use to **actually drive the app** through each test case, capture a **real, verified action trace with real DOM selectors**, and synthesize a **deterministic Playwright script** grounded in that trace — eliminating invented selectors and producing flows proven to run.

## 2. Goals / Non-goals

**Goals**
- Drive a real browser via `browser_use.Agent` at generation time, per test case.
- Final artifact stays a **deterministic Playwright pytest script** (stable regression; NOT a live-AI-agent script).
- Work with **every provider option** the thread can select (On-Premises, Claude, Claude SSO, Gemini, OpenAI, Browser Use Cloud) by driving browser-use with the **same LLM the thread configured**.
- **Respect the model's vision capability** (do not hard-disable; browser-use auto-handles the DeepSeek exception).
- Graceful **fallback to the current LLM-only generation** when the browser/app/agent is unavailable.

**Non-goals**
- Not building Jack (execution agent, Story 15.1).
- Not replacing the review/approve/save UX (Sarah's existing flow stays).
- Not requiring Browser Use Cloud (the paid service) — the library is free; only an LLM is needed.
- Not changing how Mary produces test cases.

## 3. Cost / credential matrix (verified)

The `browser-use` **library is free (MIT)**; it needs only an LLM. browser-use is driven by **the thread's configured provider/credential** (reuses the same secret resolution as [base.py `get_llm_config`](../../src/ai_qa/agents/base.py)):

| Provider (thread) | browser_use LLM wrapper | Credential | Cost |
| ------ | ------ | ------ | ------ |
| `on-premises` | `ChatOpenAI(base_url, api_key, model)` | `TEST_ON_PREMISES_KEY` / per-user | **Free** (company gateway) |
| `claude` | `ChatAnthropic(api_key, model)` | real `sk-ant-api…` | needs IT-provisioned key |
| `claude-sso` | `ChatAnthropic(api_key, model)` | `CLAUDE_SSO_ENTERPRISE_API_KEY` (real key behind SSO) | **needs IT-provisioned key** |
| `gemini` | `ChatGoogle(api_key, model)` | Gemini key | per token |
| `openai` | `ChatOpenAI(api_key, model)` | OpenAI key | per token |
| `browser-use-cloud` | `ChatBrowserUse(api_key, model)` | `BROWSER_USE_API_KEY` | free-tier limited / paid |

**Confirmed:** `BROWSER_USE_API_KEY` is NOT required unless using `ChatBrowserUse`/cloud browsers; telemetry/cloud-sync are disableable (`ANONYMIZED_TELEMETRY=false`, `BROWSER_USE_CLOUD_SYNC=false`). **Claude (both API-key and SSO options) requires a real Anthropic key** — the SSO login alone never yields one. **Vision** is on by default and only auto-disabled by browser-use for DeepSeek models; other models keep vision.

## 4. Design

### 4.1 New: provider → browser_use LLM factory

`src/ai_qa/browser/llm_factory.py` — `build_browser_use_llm(provider_id, *, api_key, base_url, model) -> browser_use.llm.BaseChatModel`. The browser-use analog of [client.py `_build_chat_model`](../../src/ai_qa/ai_connection/client.py): maps the canonical provider id to the matching `browser_use.llm` wrapper per the table above, reusing the thread's resolved secret/base_url/model. Self-signed SSL tolerated for on-prem (mirror existing rule). Telemetry/cloud-sync disabled.

### 4.2 New: live exploration step

`src/ai_qa/browser/explorer.py` (or extend `BrowserAgent`) — `explore(test_case, target_url, llm, chrome_path, *, use_vision=True) -> AgentHistoryList`:
- Builds a natural-language task from the test case (`objective` + ordered `steps` + `test_data` + expected results as success criteria).
- Runs `browser_use.Agent(task=…, llm=…, browser=<local Chrome at chrome_path, reuses active SSO session>).run(max_steps=N)`.
- `use_vision=True` by default (browser-use self-disables for DeepSeek; we don't override otherwise).
- Returns the `AgentHistoryList` (actions + `DOMSelectorMap`/`get_interacted_element()` with real `data-testid`/`role`/`aria`/xpath + per-step URLs/screenshots).
- Read-only intent: the agent performs the test steps; we do not ask it to mutate destructive state beyond what the test case implies (and the existing unsafe-pattern validators still gate the final script).

### 4.3 New: trace → deterministic Playwright (LLM-assisted)

New prompt `TRACE_TO_PLAYWRIGHT_PROMPT` in [prompts/script_generation.py](../../src/ai_qa/prompts/script_generation.py) + a `ScriptGenerator` path that feeds the LLM the **real executed trace** (action sequence + the real selectors browser-use actually used) and the test case, instructing it to emit a clean deterministic `def test_…(page: Page)` Playwright pytest script using **only those real selectors** (preference order data-testid > role > text > label), real navigations, and assertions mapped from `expected_results`. Because the selectors come from a verified run, hallucination is largely eliminated; the LLM's job is translation, not invention.

### 4.4 Wiring into Sarah

In [ScriptGenerator](../../src/ai_qa/pipelines/script_generator.py), the vision-locator preprocessing is replaced/augmented: when `target_url` + `chrome_path` are available, run §4.2 exploration → §4.3 translation. Otherwise (or on any browser/agent error) **fall back to the current LLM-only generation** (warning surfaced, no failure). All downstream stays unchanged: deterministic confidence/validators ([script_validator.py](../../src/ai_qa/pipelines/script_validator.py)), brittle-selector/secret/assertion-gap detectors, the side-by-side review UX, approve/reject/regenerate, artifact save.

### 4.5 LLM source for the agent

browser-use's driving LLM = the **model Alice assigned to Sarah for the thread** (same provider/credential the pipeline already resolves). One model drives the exploration; the same (or thread) LLM does the trace→Playwright translation.

## 5. Acceptance Criteria

1. With a configured provider + reachable `target_url` + valid `chrome_path` (active SSO), Sarah generates a script whose selectors come from the **real DOM trace** (verifiable: selectors match elements browser-use interacted with), not invented.
2. The generated artifact is a **deterministic Playwright pytest** script (no `browser_use` import in the output; runs the same way each time).
3. **All provider options** can drive browser-use via the factory (§4.1); Claude/Claude-SSO work **iff** a real Anthropic key is configured (documented prerequisite).
4. **Vision is not hard-disabled**; it follows the model (browser-use auto-disables only for DeepSeek).
5. When browser/app/agent is unavailable or errors, Sarah **falls back** to LLM-only generation with a surfaced warning — never hard-fails.
6. Existing validators, confidence, review/approve/reject/save behavior unchanged.
7. Backend suite + frontend suite stay green; new unit tests cover the factory + trace→Playwright translation with mocked `AgentHistoryList`.

## 6. Test plan / seams

- **Unit (deterministic, in CI):**
  - `build_browser_use_llm` returns the right wrapper + carries base_url/api_key/model for each provider id (incl. claude-sso → ChatAnthropic).
  - trace→Playwright translation: feed a mocked `AgentHistoryList` (canned actions + real-selector elements) → assert the produced script uses those selectors, is deterministic, passes existing validators.
  - fallback path: browser/agent error → LLM-only generation invoked + warning present.
- **Integration (NOT in CI — like current vision/LLM):** real `Agent.run()` against a live app needs Chrome + reachable app + SSO + a provider key; documented as a manual/`test_providers_live`-style gated test.

## 7. Risks / open questions

- **Live prerequisites at generation time:** app reachable + Chrome + active SSO. Where absent (CI/headless), only the fallback + unit-tested seams run. (Same limitation class as today's vision path.)
- **Determinism of exploration:** the *exploration* is AI-driven (may vary run-to-run), but the **output** is a fixed Playwright script — re-running generation may yield slightly different scripts; that's fine (human reviews/approves). Regression stability lives in the approved script, not the explorer.
- **On-prem model strength:** DeepSeek (vision off) drives via DOM only — solid for semantic DOM apps; weaker on canvas/visual-only UIs. Vision-capable models (Gemini/OpenAI/Claude/vision on-prem) improve grounding.
- **browser-use version:** pin current (0.13.1); 0.13.2 is a low-risk patch bump, optional.
- **Open:** `max_steps` budget per test case; whether to cache/reuse one browser session across a batch of test cases (perf) vs fresh session per case (isolation).

## 8. Implementation slices (proposed sequencing)

1. **Slice 1 — factory** (`llm_factory.py`) + unit tests. Low risk, no behavior change.
2. **Slice 2 — explorer** (`explorer.py`/BrowserAgent extension) + trace→Playwright prompt + `ScriptGenerator` path, behind the existing `vision_enabled`/`target_url` gate, with fallback. Unit tests with mocked history.
3. **Slice 3 — wiring + warnings + confidence integration** in Sarah; ensure review/approve/save unchanged; full suite green.
4. **Slice 4 — docs** (`project-context.md`, sprint-status entry) + optional 0.13.2 bump + manual integration test notes.

---

**Decision needed from Thuong before coding:** approve this design (esp. §4.1 reuse-thread-provider, §4.4 fallback, §5 AC), or adjust. Open knobs in §7 (max_steps, session reuse) can default and be tuned later.
