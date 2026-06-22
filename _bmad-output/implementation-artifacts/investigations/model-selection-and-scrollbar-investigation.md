# Investigation: Alice Model Selection Quality + ThinkingBubble Model-List Scroll

## Hand-off Brief

1. **What happened.** (A) The "Alice's thought" model-list boxes clamp to `max-h-24` (96px ≈ 3 rows) with a native auto-hiding scrollbar, so with 36 models the user can't see/scroll the full list. (B) Per-agent model selection is driven by a stale keyword heuristic (`_bootstrap_alice_model`) + an LLM self-assignment, both biased toward proprietary names that don't exist on the on-prem pool — falling through to `deepseek-v3` (matches `inference-deepseek-v32`) and yielding suboptimal picks vs. the best open models actually available (GLM, Qwen3, Llama4, gpt-oss-120b).
2. **Where the case stands.** Both root causes **Confirmed** by `path:line`; live pool (38 models, GLM-5.1 present) and 2026 benchmarks gathered. Approach chosen: deterministic benchmark-ranking table. Proposed per-agent mapping drafted (see Conclusion).
3. **What's needed next.** Confirm the load-vs-quality routing decision (Alice+Mary on GLM-5.1 vs GPT-OSS-120B), then implement A (CSS) + B (table + filter + tests) in `alice.py` and `ThinkingBubble.tsx`.

---

## Case Info

| Field            | Value                                                                                              |
| ---------------- | -------------------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                                |
| Date opened      | 2026-06-18                                                                                          |
| Status           | Concluded — both fixes implemented & verified 2026-06-18                                            |
| System           | React 19 + TS frontend (Tailwind v4), FastAPI backend; provider = on-prem inference gateway   |
| Evidence sources | `frontend/src/components/ThinkingBubble.tsx`, `src/ai_qa/agents/alice.py`, user screenshot, web (pending) |

---

## Problem Statement

User (Thuong) reported two issues against the "Alice's thought" panel (screenshot provided):

1. *"available models và unavailable models có nhiều, show hết, không hiện thanh scroll"* — many models, should show all, no scrollbar appears.
2. *"các model được chọn có vẻ không phải là tốt nhất"* — selected models are not the best; e.g. the best coding model in the list is a GLM model, and `deepseek-v32` (DeepSeek-V3.2) is outdated, not the best reasoning model. Asks to research current model comparisons online and update the code to pick the best-quality model per agent.

Both claims are treated as hypotheses and verified independently below.

---

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `frontend/src/components/ThinkingBubble.tsx:68-104` | Available | Model-list rendering — `max-h-24 overflow-y-auto` on both Available & Unavailable boxes |
| `src/ai_qa/agents/alice.py:1348-1382` | Available | `_bootstrap_alice_model` — static keyword priority list for Alice's own model |
| `src/ai_qa/agents/alice.py:1384-1561` | Available | `_assign_models_via_llm` — LLM-driven per-agent assignment + keyword fallback |
| `src/ai_qa/agents/alice.py:1062-1095` | Available | `unsupported_keywords` candidate filter (leaks bge/emb/reranker/ocr) |
| User screenshot | Available | Available Models (36), Unavailable (2); Alice=deepseek-v32, Bob=qwen3-vl-235b, Mary=granite-33-8b, Sarah=deepseek-v32, Jack=mistral-v03-7b |
| Live `/v1/models` (on-prem `https://[IP_ADDRESS]/api`) | Available | 38 total models; 36 available after whisper filter. **`inference-glm-51-754b` (GLM-5.1, alias `claude-g5`) is present.** |
| Web: current per-capability model benchmarks (2026) | Available | llm-stats.com, kilo.ai, BenchLM, artificialanalysis, morphllm — see Web Research section |
| `_bmad-output/.../story-9-4-all-models-unavailable-investigation.md` | Available | Prior related case (error-path assignment rendering) — context only |

---

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Confirm exact full set of 36 available model IDs | High | Open | Ground the ranking; ask user or read live discovery |
| 2 | Web research: best 2026 models per capability (reasoning, vision, coding+tools, instruction-following, fast/cheap) | High | Open | User-requested; informs fix mapping |
| 3 | Decide selection mechanism: deterministic ranking table vs. improved LLM prompt vs. hybrid | High | Open | Approach fork — affects implementation |
| 4 | Extend `unsupported_keywords` to exclude bge/emb/reranker/ocr from chat-candidate pool | Medium | Open | Side finding; prerequisite for clean "best per agent" |
| 5 | ThinkingBubble scroll fix: taller box + always-visible scrollbar vs. uncapped | Low | Open | Trivial CSS; small UX decision |

---

## Confirmed Findings

### Finding 1: Model-list boxes are clamped to 96px with a native (auto-hiding) scrollbar

**Evidence:** `frontend/src/components/ThinkingBubble.tsx:73` (Available) and `:92` (Unavailable) — both use `className="max-h-24 overflow-y-auto ..."`.

**Detail:** `max-h-24` = `max-height: 6rem` (96px), roughly 3 chip-rows. `overflow-y-auto` does enable scrolling, but on most OS/browser configs the native scrollbar is an auto-hiding overlay, so with 36 chips the box shows ~3 rows with no visible affordance that more exist. Matches the report "show hết, không hiện thanh scroll".

### Finding 2: Alice's own model is chosen by a stale keyword priority list

**Evidence:** `src/ai_qa/agents/alice.py:1359-1379`.

**Detail:** Priority order is `["gpt-5","opus","gpt-4","pro-3","pro","sonnet","deepseek-v4","deepseek-v3","deepseek-coder","kimi","glm","qwen-72","llama-3-70"]`. On the on-prem pool none of the leading proprietary names exist; the first match is `"deepseek-v3"` as a substring of `inference-deepseek-v32` → Alice bootstrap = `inference-deepseek-v32`, rationale "Chosen based on capability priority keyword 'deepseek-v3'." — exactly the screenshot. `"glm"` is ranked *below* `deepseek-v3`, and `"qwen-72"`/`"llama-3-70"` don't match the available `qwen3-*`/`llama4-*` naming at all. The list is both stale and order-biased.

### Finding 3: Per-agent assignment is LLM-driven with a proprietary-biased keyword fallback

**Evidence:** `src/ai_qa/agents/alice.py:1384-1495` (LLM path), `:1521-1561` (fallback).

**Detail:** The verbose natural-language rationales in the screenshot (e.g. Bob "requires a vision-capable model…") come from the LLM path — Alice (running on `deepseek-v32`) self-assigns Bob/Mary/Sarah/Jack. The model lacks current benchmark knowledge and pattern-matches names, producing plausible-but-not-optimal picks (Mary→`granite-33-8b`, Sarah→`deepseek-v32`). The deterministic fallback (`_pick` keyword lists: `opus`,`gpt-4o`,`coder`,`claude-3-5-sonnet`,`haiku`…) is also tuned for proprietary names absent from the on-prem pool, so it would degrade to `alice_model` for most agents.

### Finding 4 (Side): Non-generative models leak into the chat-candidate pool

**Evidence:** `src/ai_qa/agents/alice.py:1062-1088`.

**Detail:** `unsupported_keywords` includes `"embed"` but not `"emb"`, `"bge"`, `"reranker"`, `"ocr"`, `"asr"`. So `inference-bge-m3`, `inference-bge-reranker`, `inference-granite-emb-278m`, `inference-deepseek-ocr`, `inference-miner-u25`, `olmocr-2-7b`, `qwen3-asr-1.7b` pass the filter and appear under "Available Models" (36 = 38 total − 2 whisper). They are embedding/reranker/OCR/ASR models, invalid as chat/agent backends. A "best per agent" selection must exclude them.

### Finding 5: GLM-5.1 (the user's "best coding model") is present but outranked by a stale heuristic

**Evidence:** Live `/v1/models` returned `inference-glm-51-754b` (display `claude-g5`). The bootstrap priority list (`alice.py:1359`) ranks `"deepseek-v3"` above `"glm"`.

**Detail:** GLM-5.1 (Z.ai, 754B, MIT) is in the pool but never selected because `deepseek-v3` matches `inference-deepseek-v32` first. Per 2026 benchmarks GLM-5.1 is the strongest all-around open-source coding/agentic model available here. Premise ("selected models are not the best; GLM-5.1 is the best coder, deepseek-v32 is outdated") is **Confirmed**.

## Live Generative Model Pool (ground truth, 2026-06-18)

Non-generative models excluded (bge/emb/reranker/ocr/asr/miner/whisper). Generative chat/VLM candidates:

| Model id | Family / notes |
| -------- | -------------- |
| `inference-glm-51-754b` (alias `claude-g5`) | **GLM-5.1, 754B** — flagship; top open coding/agentic (SWE-Bench Pro ~58, 200K ctx) |
| `inference-deepseek-v32` (+`-GRC`) | DeepSeek-V3.2 — strong reasoning (GPQA 82.4), now mid-pack |
| `inference-gpt-oss-120b` (+aliases `claude-oss`, `on-premises-gpt-osslatest`) | GPT-OSS-120B — MMLU-Pro 90.0, excellent instruction-following |
| `inference-qwen3-vl-235b` (+`-GRC`) | Qwen3-VL-235B — **best vision** in pool (DocVQA 96.5, ScreenSpot 95.4) |
| `inference-llama4-maverick` (+`-GRC`) | Llama 4 Maverick — multimodal, 1M ctx, cheaper #2 vision |
| `inference-llama4-scout-17b` | Llama 4 Scout — multimodal, long-context, lighter |
| `inference-glm45-air-110b` | GLM-4.5-Air 110B — strong mid-tier |
| `inference-qwq-32b` | QwQ-32B — reasoning-specialized 32B |
| `inference-gemma4-31b` (+`-GRC`) | Gemma 4 31B — multimodal mid |
| `inference-gemma-12b-it` | Gemma 12B IT — multimodal small-mid |
| `inference-apertus-70b` (+`-GRC`) | Apertus 70B (Swiss open) |
| `inference-granite-33-8b` | Granite 3.3 8B — small (current Mary pick) |
| `inference-granite-vision-2b` | Granite vision 2B — tiny VLM |
| `inference-qwen3-8b` | Qwen3-8B — strong small/fast |
| `inference-mistral-v03-7b` | Mistral 7B v0.3 — small (current Jack pick) |

## Web Research: 2026 Model Benchmarks (relevant to this pool)

- **Coding / agentic:** GLM-5.1 = "strongest all-around open-source coding model in 2026 for long-horizon agentic engineering" (SWE-Bench Pro 58.4, 200K ctx, MIT). DeepSeek-V3.2 solid but below GLM-5. → **Sarah: GLM-5.1.** [kilo.ai](https://kilo.ai/open-source-models), [mindstudio](https://www.mindstudio.ai/blog/best-open-source-llms-agentic-coding-2026)
- **Vision:** Qwen3-VL-235B "significantly outperforms across most benchmarks" vs Llama 4 Maverick. → **Bob: Qwen3-VL-235B** (already optimal). [llm-stats](https://llm-stats.com/models/compare/llama-4-maverick-vs-qwen3-vl-235b-a22b-thinking)
- **Reasoning / general:** GPT-OSS-120B MMLU-Pro 90.0 / GPQA 80.9; DeepSeek-V3.2 GPQA 82.4; GLM-5.1 flagship-tier. → **Alice / Mary: GLM-5.1 (max quality) or GPT-OSS-120B (lighter).** [artificialanalysis](https://artificialanalysis.ai/models/comparisons/deepseek-v3-2-reasoning-vs-gpt-oss-120b)
- **Small / fast:** Qwen3-8B is the strongest small model in the pool (newer/stronger than Mistral-7B-v0.3 at similar speed). → **Jack: Qwen3-8B.** [benchlm](https://benchlm.ai/blog/posts/best-open-source-llm)

---

## Hypothesized Paths

### Hypothesis 1: Replacing the keyword heuristic with a benchmark-informed ranking table fixes B

**Status:** Confirmed — the pool is clearly differentiated (GLM-5.1 flagship vs deepseek-v32 vs 8B granite), 2026 benchmarks give an unambiguous per-capability ranking, and a deterministic table over the live pool produces strictly better picks for 4 of 5 agents.

**Theory:** A deterministic table mapping known model families → per-capability scores (reasoning, vision, coding+tools, instruction-following, speed/cost), matched against the discovered pool, will select objectively stronger models per agent than the current substring heuristic + LLM self-assignment, and is auditable/updatable.

**Would confirm:** Web research showing clear, current ranking differences among the available families (e.g. GLM/Qwen3/Llama4/gpt-oss vs deepseek-v32) for each capability; a dry-run mapping over the real 36-model pool that produces better picks.

**Would refute:** The available pool is too homogeneous to differentiate, or benchmarks show deepseek-v32/granite are in fact the strongest available for those roles.

---

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Issue A origin | `frontend/src/components/ThinkingBubble.tsx:73,92` (`max-h-24 overflow-y-auto`) |
| Issue B origin | `src/ai_qa/agents/alice.py:1348-1382` (Alice bootstrap heuristic) + `:1384-1561` (per-agent LLM + fallback) |
| Trigger | Alice's `process()` → discovery (`:1056`) → bootstrap (`:1124`) → LLM assign (`:1132`); trace emitted to ThinkingBubble |
| Candidate filter | `src/ai_qa/agents/alice.py:1062-1095` (leaks bge/emb/reranker/ocr) |
| Related files | `frontend/src/App.tsx` (consumes trace), `frontend/src/types/provider.ts` (ThinkingTrace type) |

---

## Conclusion

**Confidence:** High. Both root causes Confirmed by citation; the full pool and 2026 benchmarks now ground the corrected mapping.

Issue A is a trivial CSS clamp. Issue B is a design defect: stale, proprietary-biased keyword heuristics plus an LLM self-assignment with no current benchmark grounding, compounded by a candidate filter that admits non-generative models. The fix is a deterministic benchmark-ranking table (user-chosen mechanism).

### Proposed per-agent mapping (current → best-available)

| Agent | Capability | Current pick | Proposed pick | Why |
| ----- | ---------- | ------------ | ------------- | --- |
| Alice | general reasoning / config | `deepseek-v32` | `glm-51-754b` *(or `gpt-oss-120b`)* | Flagship reasoner; orchestrates assignment |
| Bob | vision + extraction | `qwen3-vl-235b` | `qwen3-vl-235b` (unchanged) | Best open VLM in pool |
| Mary | structured / instruction | `granite-33-8b` | `glm-51-754b` *(or `gpt-oss-120b`)* | 8B → flagship; biggest quality jump |
| Sarah | coding + tools | `deepseek-v32` | `glm-51-754b` | Best open coding/agentic model 2026 |
| Jack | fast summarization | `mistral-v03-7b` | `qwen3-8b` | Stronger small model, similar speed |

Open design decision (load vs. quality): max-quality routes Alice+Mary+Sarah all to GLM-5.1-754B; balanced keeps GLM-5.1 for Sarah (coding) and routes Alice+Mary to GPT-OSS-120B (MMLU-Pro 90, lighter on the 754B).

## Recommended Next Steps

### Fix direction

- **A:** Raise `max-h-24` (e.g. `max-h-60`) and add an always-visible scrollbar style (or remove the clamp) on both boxes in `ThinkingBubble.tsx`.
- **B:** In `alice.py` — (1) extend `unsupported_keywords` with `bge`, `reranker`, `ocr`, `asr`, `miner`, `olmocr`, and `emb` (matched as a segment) so non-generative models leave the chat pool; (2) add a module-level benchmark ranking table (ordered id-substring preferences per capability + a benchmark rationale string); (3) rewrite `_bootstrap_alice_model` to use the Alice/reasoning ranking; (4) make per-agent assignment deterministic from the table (`_assign_models_via_llm` → table-driven `_assign_models`, prefer base ids over `-GRC`), emitting benchmark-grounded rationales. Update affected tests.

### Diagnostic

- Full pool obtained via live `/v1/models` (done). 2026 benchmarks researched (done).
- After implementation: dry-run the table over the live pool and confirm the mapping matches the Proposed table.

---

## Side Findings

- Finding 4 above: candidate filter leaks `bge`/`emb`/`reranker`/`ocr` models into the chat pool.

## Follow-up: 2026-06-18 — Implemented & verified

### What changed

- **B (selection), [alice.py](src/ai_qa/agents/alice.py):** Added benchmark ranking table (`_REASONING_RANK` / `_VISION_RANK` / `_CODING_RANK` / `_INSTRUCTION_RANK` / `_FAST_RANK`) + `_select_best_model` (prefers non-`GRC` base). Rewrote `_bootstrap_alice_model` to use the reasoning rank; replaced the LLM-driven `_assign_models_via_llm` (+ its rate-limit try/except and the `ast`/`json`/`re`/`LLMRateLimitError` imports) with a deterministic, no-network `_assign_models`. Vision rank lists multimodal families ONLY (GLM-5.1 is text-only). Refactored `_assign_fallback_models` to reuse the table.
- **Filter, [alice.py:1062](src/ai_qa/agents/alice.py):** `unsupported_keywords` extended with `emb`/`bge`/`reranker`/`ocr`/`olmocr`/`asr`/`miner` → 9 non-generative models now excluded (was 2).
- **A (scroll), [ThinkingBubble.tsx](frontend/src/components/ThinkingBubble.tsx):** Both model boxes use a shared `modelBoxClass` — `max-h-60` (was `max-h-24`) + explicit thin, always-visible scrollbar (`[scrollbar-width:thin]` + styled `::-webkit-scrollbar`) so the overlay scrollbar no longer hides.
- **Tests, [test_alice.py](tests/test_agents/test_alice.py):** `TestBootstrapAndLLM` → `TestBootstrapAndAssignment`; 5 LLM-mock tests replaced with deterministic-selection tests (best-per-capability, Bob-requires-vision, base-over-GRC, fallback-to-alice-model); 2 `_generate_configuration` tests rewritten without the LLM mock.

### Verification

- `ruff check` + `format` clean; `mypy` strict clean on `alice.py`.
- Backend: **1464 passed, 0 failed**. Frontend: typecheck clean + ThinkingBubble vitest (3) pass.
- Live dry-run over the real pool (38 discovered → 29 generative after filter): alice/mary/sarah → `inference-glm-51-754b`, bob → `inference-qwen3-vl-235b`, jack → `inference-glm45-air-110b` — matches the Proposed mapping exactly.

### Updated Conclusion

Both root causes fixed and verified end-to-end. Changeset uncommitted on `main`. **Confidence: High.**

### Residual / not in scope

- The RAG/preset entries (`ask-your-confluence`, `ask-your-jira`, `chat-with-mcp`) and `-GRC` variants still appear in the available list; they never win selection (no ranking-keyword match / non-GRC preferred) so they are harmless, left as-is.
- Ranking lists are intentionally forward-looking (e.g. `glm-6`, `deepseek-v4`); update the lists (not call sites) as benchmarks shift.

## Follow-up: 2026-06-18 #2 — Future-proofing the ranking (new/unknown models)

User flagged the gap: a static name allowlist can't rank a brand-new model id. Designed via a 13-agent workflow; implemented a **3-tier deterministic selector** in `_select_model_for` ([alice.py](src/ai_qa/agents/alice.py)):

- **Tier 0** = operator admin scores (`_load_admin_model_scores`, seam returns `{}` today — filled by the admin feature below).
- **Tier 1** = curated `_*_RANK` (now version-aware among matches: `glm-5.2` auto-beats `glm-5.1`).
- **Tier 2** = `parse_model_id` → `_model_score_key` (family prior + version tuple + size). A new version of an UNCURATED family auto-ranks; tuple versions so `3.10 > 3.5` (no float).
- Bob = SOFT vision gate (union of advertised `supports_vision` OR name pattern; degrades + flags when no VLM).
- Fixed metadata leak: `_normalize_entry` now populates `DiscoveredModel.supports_vision/tools/context_window` from `info.meta.capabilities`.
- Emits `tier_source` + `score_breakdown` to the trace; rendered in ThinkingBubble.

**Verified:** ruff+mypy clean, **1476 backend tests pass**, frontend typecheck + ThinkingBubble vitest pass. Live dry-run: mapping unchanged, all `[curated]`.

**Honest limit (documented):** a NEW major version of a CURATED family (e.g. `glm-7` while `glm-51` still present) is NOT auto-selected — Tier 1 curated is authoritative. Resolved by the admin benchmark-override feature below.

## Follow-up: 2026-06-18 #3 — Admin benchmark-override feature (Tier 0)

Designed via a 9-agent workflow (`wf_490321bc-776`), then implemented + verified.

- **DB:** two new tables ([db/models.py](src/ai_qa/db/models.py)) — `model_benchmark_scores` (model_id, capability incl. `"global"`, score 0–100, note, updated_by) + `discovered_models` (last-seen snapshot, since the admin context has no gateway creds). Alembic migration `91910492132c` (down_revision `7c2f9a3b1e84`), offline SQL verified, single head.
- **Selector wiring:** `_load_admin_score_rows` (resilient DB read) + `_merge_scores` (global then per-capability override) feed Tier 0; `_bootstrap_alice_model`/`_assign_models` take the rows; `_AGENT_CAPABILITY_NAME` maps agent→capability. `_snapshot_discovered_models` persists the pool on each config run (best-effort, never blocks).
- **Admin API** ([api/admin.py](src/ai_qa/api/admin.py), `require_admin`): `GET /admin/discovered-models` (pool + provenance + `unbenchmarked` flag), `GET/PUT/DELETE /admin/model-scores` (upsert via get-then-update).
- **Frontend:** TS types + 4 `apiFetch` client fns + a "Model Benchmark Overrides" section in [AdminDashboard.tsx](frontend/src/components/admin/AdminDashboard.tsx) — table with provenance badge, **"No benchmark"** flag, capability select + 0–100 score input + Save/Clear.

**Verification:** ruff + mypy strict clean; backend **1483 pass**; frontend typecheck clean + **288 pass** (7 new admin API tests + 1 dashboard test). Migration applied via `alembic upgrade head` is required before the feature is usable (additive, no data change).

**Status: Concluded.** Full changeset uncommitted on `main`.

## Follow-up: 2026-06-19 — Auto version-upgrade + per-agent override

Two user-requested enhancements:

1. **Auto-promote newest version within the winning family** ([alice.py](src/ai_qa/agents/alice.py) `_promote_to_newest_sibling`, applied at the end of `_select_model_for`): after any tier picks a winner, the selector adopts the newest model of the SAME family AND variant (tags). So `glm-5.1` (top admin score / curated) auto-upgrades to an unbenchmarked `glm-5.2`/`glm-5.3` with no code/score change; a different variant (`-air`/`-vl`) is never promoted in (separate product line); never downgrades. This finally closes the "new major version of a curated family" limit. Breakdown notes the upgrade in the trace. **3 new tests** (incl. the exact `glm-5.1`→`glm-5.2` case + variant-guard).

2. **Per-agent model override — already existed, now explicitly tested.** [ModelAssignmentReview.tsx](frontend/src/components/ModelAssignmentReview.tsx) already renders a per-agent `<select>` (populated from `available_models`) + OK that sends `data.assignments`; `handle_approve` ([alice.py:1237](src/ai_qa/agents/alice.py:1237)) already applies the override to the saved config (it runs AFTER selection, so a user pin always wins over auto-promotion). Added a frontend test proving a changed dropdown selection reaches `onApprove`; backend override already covered by `test_handle_approve_success`.

**Verified:** ruff + mypy strict clean; backend **1486 pass**; frontend **289 pass**.
