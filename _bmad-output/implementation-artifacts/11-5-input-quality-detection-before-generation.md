---
baseline_commit: 9d878c5
---

# Story 11.5: Input Quality Detection Before Generation

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want vague or incomplete source requirements flagged before downstream generation,
so that I can decide whether to improve documentation before generating test cases and scripts.

## Acceptance Criteria

### AC1 — Quality detection flags input issues on parsed Confluence/Jira content

**Given** Bob has parsed Confluence/Jira source content
**When** quality detection runs
**Then** it flags issues such as vague steps, missing expected results, missing preconditions, ambiguous UI references, or unsupported content warnings.

### AC2 — Specific warnings, tied to the source item, with downstream impact

**Given** quality issues are detected
**When** Bob presents extraction results
**Then** the user sees specific warnings tied to source sections or test cases
**And** the warning explains the likely impact on downstream test case/script generation.

### AC3 — User can still approve, and approval records the acknowledgement

**Given** quality issues exist
**When** the user reviews output
**Then** the user can still approve and proceed
**And** the approval records that warnings were acknowledged.

---

## ⚠️ CRITICAL: This is a DETECT-AND-RECORD story bolted onto the END of the existing extraction flow — it never blocks

By the time control reaches this story's logic, `self.pages` is **already fully assembled** by the earlier Epic 11 stories. Story 11.5 does exactly three things and **nothing else**:

1. **Detect (AC1):** run a deterministic, rule-based quality scan over each assembled page (Confluence + Jira) and attach a structured list of `quality_issues` to each page dict.
2. **Surface (AC2):** emit one user-safe `send_message(..., "warning")` summary that names each flagged page/section and explains the **downstream impact**, and set a `has_quality_warnings` flag on the review payload. The per-page issues ride along inside the existing `pages` payload.
3. **Record (AC3):** when the user approves a page, enrich the requirement metadata that is already saved so it durably records that the page's quality warnings were acknowledged. **Approval is never blocked** — the user can always proceed.

This story sits at the **tail of `_extract_descendants`** (after Confluence parsing from 11.3 and the Jira supplement from 11.4 have built `self.pages`) and inside the **approved branch of `handle_approve`** (the metadata save). It does **not** touch the intake gate (11.2), retrieval (11.1/11.3/11.4), or the MCP/LLM layers.

### Hard vs. soft dependencies — read this carefully

- **No import-level dependency on 11.1/11.4.** Detection operates on the **assembled page dicts** (`self.pages`), not on `JiraReader`/`JiraIssue`/`ContentParser`. It reads optional keys defensively (`page.get("warnings") or []`, `page.get("source_type")`), so it runs correctly whether or not 11.3/11.4 are merged.
- **Build-order reality (soft):** the natural order is 11.1 → 11.2 → 11.3 → 11.4 → 11.5, so by the time you implement this, `self.pages` items will already carry `parsed_markdown` + `warnings` (11.3) and a Jira item with `source_type="jira"` (11.4). If they are **not** merged yet, detection still works — it just sees the baseline page shape (`page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md`) and an empty parse-warning list. **Do not hard-depend on the extra keys; default them.**
- **Insertion point depends on 11.4:** place the detection call **after `self.pages` is fully built** and **before** the success `return` of `_extract_descendants`. On the current baseline (no Jira), that is right after the `if not self.pages: return …` guard. If 11.4 merged, place it **after** the `jira_warnings = await self._retrieve_jira_requirements(...)` line so Jira items are included in the scan. Either way: last thing before the `Requirements extraction complete.` message. (See **The exact edit site**.)

**Do NOT:**

- **Block, gate, or fail extraction on quality.** AC3 is explicit: the user can still approve and proceed. Quality detection is advisory only — it never changes `StageResult.success`, never raises, never prevents the review from being presented. A page with quality issues is still a valid, approvable review item.
- **Use an LLM for detection in this story.** M1 detection is a deterministic, pure, synchronous rule-based scan — cheap, testable, no `await`, no model call. The LLM-based semantic scoring of generated artifacts is **Epic 12 Story 12.3** (Mary confidence scoring, which explicitly consumes "unresolved Bob warnings"). See Resolved Decisions. Do not add an LLM pass here.
- **Build the in-panel warning UI.** Rendering warnings inside the SplitPanel review (badges/sections per page) is **Story 11.6** ("extraction warnings are visible in the review content"). 11.5's AC2 "the user sees …" is satisfied by the backend `send_message` warning summary (the chat already renders `message_type="warning"`) **plus** carrying `quality_issues` on the pages so 11.6 can render them. **No frontend change is required in this story.**
- **Remove or rename the existing `warnings` key** on the page dicts (produced by 11.3). Detection **reads** it and folds it into `quality_issues` as `unsupported_content`; the original key stays for backward-compat with 11.6/12.3.
- **Re-run parsing, re-fetch pages, open an MCP client, or add a second LLM call.** Detection is pure string analysis over already-extracted text. Adding it must NOT change the single-MCP-client / disconnect invariants pinned by existing tests.
- **Add a DB migration, a new package, or a frontend change.** The acknowledgement is recorded in the **existing** requirement metadata artifact (`adapter.save_metadata(...)`); no schema or storage change.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| `BobAgent._extract_descendants` — builds `self.pages`; the tail (`if not self.pages` guard → success `return`) is the detection insertion site | [src/ai_qa/agents/bob.py:474-505](src/ai_qa/agents/bob.py) | ✅ done — **insert the detection call before the success return** |
| `self.pages[]` page dict shape (`page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md`); 11.3 adds `parsed_markdown` + `warnings`; 11.4 adds a Jira item with `source_type` | [src/ai_qa/agents/bob.py:461-469](src/ai_qa/agents/bob.py) | ✅ done — **add `quality_issues` key per page** |
| `BobAgent.handle_approve` markdown-review branch — saves `requirement.md` + `requirement.metadata.json` on approve | [src/ai_qa/agents/bob.py:561-584](src/ai_qa/agents/bob.py) | ✅ done — **enrich the saved metadata with the acknowledgement** |
| `BobAgent.handle_approve` confirm-parent branch — builds the `is_review_ready` review payload after `_extract_descendants` | [src/ai_qa/agents/bob.py:537-549](src/ai_qa/agents/bob.py) | ✅ done — **add `has_quality_warnings` to metadata** |
| `is_review_ready` review payload (`metadata={"is_review_ready": True, "pages": self.pages}`) | [src/ai_qa/agents/bob.py:123-127, 545-548](src/ai_qa/agents/bob.py) | ✅ done — `quality_issues` rides along inside `pages` |
| `PipelineArtifactAdapter.save_metadata(name, dict)` — JSON-serializes via `json.dumps(..., default=str)` | [src/ai_qa/pipelines/artifact_adapter.py:69](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — reuse for the acknowledgement record |
| `send_message(content, message_type, metadata=...)` — chat renders `message_type="warning"` already | [src/ai_qa/agents/base.py](src/ai_qa/agents/base.py) | ✅ done — AC2 surface |
| `StageResult` (`success`, `data`, `errors`, `warnings`, `confidence`) | [src/ai_qa/models.py:27](src/ai_qa/models.py) | ✅ done — `confidence` field exists for future use; quality lives on the page dicts, not here |
| Frontend `is_review_ready` handler reads `message.metadata?.pages`; SplitPanel renders per-page | [frontend/src/App.tsx:753-766](frontend/src/App.tsx), [frontend/src/components/SplitPanel.tsx:6](frontend/src/components/SplitPanel.tsx) | ✅ done — extra page keys are ignored at runtime; **no frontend change** |
| Pydantic pipeline models pattern (`ConfluencePage`, `ParsedContent`, `JiraIssue`) | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) | ✅ done — **add a `QualityIssue` model alongside** |

---

## Tasks / Subtasks

- [x] **Task 1 — Add the `QualityIssue` model (AC1/AC2)**
  - [x] 1.1 Open [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py). Extend the typing import to `from typing import Any, Literal`. After the `ParsedContent` class, add:
    - A module-level type alias: `QualityCategory = Literal["unsupported_content", "missing_expected_results", "missing_preconditions", "vague_language", "ambiguous_ui_reference", "insufficient_content"]`.
    - `class QualityIssue(BaseModel)` with **required** fields (no defaults → no Pydantic-`Literal`-default cast needed, per project-context): `category: QualityCategory`, `location: str` (the page title or section the issue is tied to — AC2 "tied to source sections"), `message: str` (specific, user-safe description), `impact: str` (AC2 "likely impact on downstream test case/script generation"). Add `model_config = ConfigDict(validate_assignment=True)` and a `to_dict(self) -> dict[str, Any]` returning `self.model_dump(mode="json")` (match the sibling models).
  - [x] 1.2 No new fields on `ConfluencePage` / `JiraIssue` / `StageResult`. The `QualityIssue` list is carried on the in-memory page dict (Task 3), serialized to JSON when it flows through the review payload and the acknowledgement metadata.

- [x] **Task 2 — Add the deterministic detector to `BobAgent` (AC1)**
  - [x] 2.1 In [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py), add `QualityIssue` to the existing models import: `from ai_qa.pipelines.models import ConfluencePage, QualityIssue` (keep `JiraIssue` if 11.4 already added it — single import line).
  - [x] 2.2 Add module-level tunables near the top of `bob.py` (after `logger = ...`), so they are easy to find and adjust without touching logic:
    - `_QUALITY_MIN_CONTENT_CHARS = 200` — below this the content is "thin".
    - `_VAGUE_TERMS: tuple[str, ...]` — lowercase vague-wording lexicon, e.g. `("etc.", "and so on", "tbd", "to be defined", "as appropriate", "as needed", "should work", "works properly", "works correctly", "somehow", "some kind of", "various", "as required")`.
    - `_AMBIGUOUS_UI_TERMS: tuple[str, ...]` — lowercase ambiguous UI references with no concrete element name, e.g. `("the button", "that button", "the link", "the field", "the relevant", "the appropriate", "the correct page", "the right page")`.
    - `_EXPECTED_RESULT_MARKERS: tuple[str, ...]` — lowercase markers proving expected results exist, e.g. `("expected", "then ", "## acceptance criteria", "acceptance criteria", "result")`.
    - `_PRECONDITION_MARKERS: tuple[str, ...]` — e.g. `("precondition", "given ", "## preconditions", "prerequisite", "setup")`.
    - `_IMPACT_BY_CATEGORY: dict[str, str]` — one fixed, user-safe impact sentence per `QualityCategory` (AC2). Suggested text:
      - `unsupported_content`: "Source content could not be fully parsed; generated tests may miss this detail."
      - `missing_expected_results`: "Without expected results, Mary cannot derive assertions and generated tests may lack verification steps."
      - `missing_preconditions`: "Without preconditions, test setup state is undefined and scripts may start from the wrong state."
      - `vague_language`: "Vague wording forces the model to guess; generated steps may be inaccurate or unstable."
      - `ambiguous_ui_reference`: "Unnamed UI elements force the model to guess selectors; Sarah's scripts may be brittle."
      - `insufficient_content`: "Too little detail to generate meaningful test cases for this item."
  - [x] 2.3 Add a **pure, synchronous** method `def _detect_quality_issues(self, page: dict[str, Any]) -> list[QualityIssue]`. It reads only the page dict (no MCP, no LLM, no `await`). Resolve, defensively:
    - `title = str(page.get("page_title") or page.get("page_id") or "this page")` — the AC2 "location".
    - `text = str(page.get("requirement_md") or page.get("parsed_markdown") or "")`; `lowered = text.lower()`.
    - **Build the issue list in this order** (each appends a `QualityIssue` with the matching `_IMPACT_BY_CATEGORY[...]`):
      1. **Unsupported content** — for each `w in (page.get("warnings") or [])`: append `category="unsupported_content", location=title, message=str(w)`. (These are 11.3's parse warnings; `[]` when 11.3 unmerged or for Jira. AC1's "unsupported content warnings" is satisfied here.)
      2. **Insufficient content** — if `len(text.strip()) < _QUALITY_MIN_CONTENT_CHARS`: append `insufficient_content` with a message like `"The extracted requirement for '{title}' is very short (fewer than {_QUALITY_MIN_CONTENT_CHARS} characters)."`.
      3. **Missing expected results** — if `not any(m in lowered for m in _EXPECTED_RESULT_MARKERS)`: append `missing_expected_results` ("No expected results or acceptance criteria were found.").
      4. **Missing preconditions** — if `not any(m in lowered for m in _PRECONDITION_MARKERS)`: append `missing_preconditions` ("No preconditions or setup steps were found.").
      5. **Vague language** — `found = sorted({t for t in _VAGUE_TERMS if t in lowered})`; if `found`: append `vague_language` (`f"Vague wording detected: {', '.join(found)}."`).
      6. **Ambiguous UI references** — `found = sorted({t for t in _AMBIGUOUS_UI_TERMS if t in lowered})`; if `found`: append `ambiguous_ui_reference` (`f"Ambiguous UI references without a specific element name: {', '.join(found)}."`).
    - Return the list (possibly empty). Guard every string with `or ""`/`str(...)` so `None` never leaks into a message (project-context rule). No exceptions raised.

- [x] **Task 3 — Run detection over all pages + surface the summary (AC1/AC2)**
  - [x] 3.1 Add `async def _run_quality_detection(self) -> bool`. For each `page in self.pages`:
    - `issues = self._detect_quality_issues(page)`.
    - `page["quality_issues"] = [qi.model_dump(mode="json") for qi in issues]` — store **plain dicts** (JSON-serializable for the WebSocket payload and the metadata artifact). Always set the key (even to `[]`) so 11.6 can rely on it.
  - [x] 3.2 Collect a per-page summary for any page with issues. If **any** page has issues, build one user-safe message grouping by page title and, for each issue, showing `message — impact` (AC2: specific + tied to the page + downstream impact). Send it once: `await self.send_message(content=summary, message_type="warning", metadata={"is_quality_warning": True})`. Include a closing line previewing AC3, e.g. *"You can still approve to proceed; approving records that you acknowledged these warnings."*
  - [x] 3.3 Return `True` if any page had issues, else `False`. Never raise; never include raw HTML, tokens, or config in the message (security rule) — only the page title and the canned `message`/`impact` strings.
  - [x] 3.4 In `BobAgent.__init__` ([bob.py:28-40](src/ai_qa/agents/bob.py)), add `self._has_quality_warnings: bool = False` alongside the other instance attributes.

- [x] **Task 4 — Wire detection into `_extract_descendants` and the review payload (AC1/AC2)**
  - [x] 4.1 In `_extract_descendants`, **after `self.pages` is fully assembled** (after the `if not self.pages: return …` guard — and, if 11.4 is merged, **after** the `jira_warnings = await self._retrieve_jira_requirements(...)` line) and **before** the `Requirements extraction complete.` message + success `return`, add:

    ```python
    # --- 11.5: advisory input-quality detection over the assembled pages ---
    self._has_quality_warnings = await self._run_quality_detection()
    ```

    Do **not** change `StageResult.success`/`errors`/`confidence` based on quality — detection is advisory (AC3). Leave the existing `except … raise` / `finally: client.disconnect()` block untouched.
  - [x] 4.2 In `handle_approve`'s **confirm-parent → review** block, change the review payload metadata from `{"is_review_ready": True, "pages": self.pages}` to `{"is_review_ready": True, "pages": self.pages, "has_quality_warnings": self._has_quality_warnings}` ([bob.py:545-548](src/ai_qa/agents/bob.py)).
  - [x] 4.3 For consistency, make the same metadata addition in `handle_start`'s **review_markdown** block ([bob.py:123-127](src/ai_qa/agents/bob.py)). (In the live flow Bob reaches review via the confirm-parent path, but keep both payloads identical so any caller/test that uses the `handle_start` path also carries the flag.)
  - [x] 4.4 No new key needs to be added to the frontend payload plumbing — `quality_issues` is inside each page object already, and `has_quality_warnings` is read only when 11.6 builds the in-panel UI. The current frontend ignores both at runtime.

- [x] **Task 5 — Record the acknowledgement on approval (AC3)**
  - [x] 5.1 In `handle_approve`'s **markdown-review** branch, where the approved page's metadata is saved ([bob.py:577-583](src/ai_qa/agents/bob.py)), enrich the dict passed to `adapter.save_metadata(...)`:

    ```python
    quality_issues = page.get("quality_issues") or []
    adapter.save_metadata(
        f"{page['page_id']}/requirement.metadata.json",
        {
            "source_url": page["source_url"],
            "extracted_at": datetime.now(UTC).isoformat(),
            "source_type": page.get("source_type", "confluence"),
            "quality_warnings_acknowledged": bool(quality_issues),   # AC3
            "acknowledged_quality_issues": quality_issues,           # the issues acknowledged
            "acknowledged_at": datetime.now(UTC).isoformat(),
        },
    )
    ```

    `bool(quality_issues)` is the durable AC3 record that the user approved **despite** the flagged issues. When there are no issues, it records `False` + an empty list (a clean approval). `save_metadata` JSON-serializes with `default=str`, so dicts/bools/strings serialize cleanly.
  - [x] 5.2 Do **not** block, branch, or add a confirmation step. The user approving the page **is** the acknowledgement. The approval flow (advance page, save, transition to DONE on the last page) is unchanged.
  - [x] 5.3 Do not touch the `not_requirement`/skip path or the rejection path — skipped/rejected pages are not approved, so nothing is acknowledged.

- [x] **Task 6 — Unit tests (AC1/AC2/AC3)**
  - [x] 6.1 Extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py). Reuse the `bob_agent` + `mock_project_context` fixtures and match the house style (`@pytest.mark.asyncio` where async, `patch("ai_qa.agents.bob.<symbol>")`, `AsyncMock`/`MagicMock`). Add imports as needed: `from ai_qa.pipelines.models import QualityIssue`.
  - [x] 6.2 **AC1 — `_detect_quality_issues` (pure, sync, no event loop):**
    - **Clean page** → `[]`: a `requirement_md` longer than `_QUALITY_MIN_CONTENT_CHARS` containing `## Acceptance Criteria`, `Given`, `Then`, `Expected`, a named UI element, and **no** vague terms; `warnings=[]`. Assert empty list.
    - **Missing expected results** → contains a `missing_expected_results` issue (omit any expected/Then/AC marker).
    - **Missing preconditions** → contains a `missing_preconditions` issue.
    - **Vague language** → page text with `"etc."` and `"should work"` yields a `vague_language` issue whose `message` lists the matched terms.
    - **Ambiguous UI** → text with `"the button"` yields an `ambiguous_ui_reference` issue.
    - **Unsupported content fold** → `page = {..., "warnings": ["Gliffy diagram detected — manual review recommended"]}` yields an `unsupported_content` issue carrying that exact warning text.
    - **Insufficient content** → `requirement_md="too short"` yields an `insufficient_content` issue.
    - **Jira page** → `page = {"page_title": "[PROJ-1] X", "source_type": "jira", "requirement_md": "Short ticket"}` is scanned the same way (assert it gets flagged for missing AC etc.).
    - For every issue, assert `location`, `message`, and `impact` are non-empty and `"None"` never appears (no `None` leakage). Assert each `category` is a valid `QualityCategory`.
  - [x] 6.3 **AC2 — `_run_quality_detection` surfaces a warning summary:** set `bob_agent.pages = [<page with issues>, <clean page>]`, patch `bob_agent.send_message`. Call `await bob_agent._run_quality_detection()`. Assert: (a) returns `True`; (b) **every** page now has a `quality_issues` key (the clean one is `[]`); (c) `send_message` was called once with `message_type="warning"` and the content contains the flagged page title **and** an impact sentence. Then test the all-clean case: all pages clean → returns `False`, each page has `quality_issues == []`, and `send_message` was **not** called with a warning.
  - [x] 6.4 **AC3 — approval records acknowledgement:** set `bob_agent.phase = "review_markdown"`, `bob_agent.current_page_index = 0`, and `bob_agent.pages = [{"page_id": "p1", "page_title": "P1", "source_url": "u", "requirement_md": "x", "quality_issues": [{"category": "vague_language", "location": "P1", "message": "m", "impact": "i"}]}]`. Patch `ai_qa.agents.bob.PipelineArtifactAdapter` (the class), `transition_to`, and `send_message`. Call `await bob_agent.handle_approve({"action": "approved", "page_id": "p1", "markdown": "edited"})`. Assert the adapter instance's `save_metadata` was called with a dict where `quality_warnings_acknowledged is True` and `acknowledged_quality_issues` equals the page's issues. Then a second case with `quality_issues: []` → `quality_warnings_acknowledged is False`. In both, assert the approval **proceeded** (page advanced / not blocked).
  - [x] 6.5 **Integration — detection runs inside `_extract_descendants` (AC1 end-to-end):** copy the `test_bob_extract_descendants_disconnects_mcp_on_completion` scaffold (keeps `_page_id="12345"`, the project mock, and the `AppSettings`/`LLMClient`/`RequirementFormatter`/`get_llm_config` patches). The scaffold as-is produces **zero** pages, so make it produce one Confluence page: set `read_page_by_id` → `StageResult(success=True, data=ConfluencePage(page_id="12345", title="Parent", content="<p>short</p>", space_key="TEST", url="https://confluence.company.com/x"))`, leave `get_children_by_id` → `data=[]` (the parent is synthesized as one summary), and wire `RequirementFormatter.return_value.convert_page = AsyncMock(return_value="short")` (a thin requirement that will be flagged). After `await bob_agent._extract_descendants("Parent")`, assert: `bob_agent.pages[0]["quality_issues"]` is a non-empty list and `bob_agent._has_quality_warnings is True`. (If 11.3 is merged and Bob calls `convert_markdown`, wire that AsyncMock + patch `ai_qa.agents.bob.ContentParser` instead — match whatever the merged Phase-2 path calls.)
  - [x] 6.6 **Regression (do NOT weaken):** confirm the existing `test_bob_handle_approve_pagination` (calls `handle_approve()` with **no** data → never enters the approved branch, so the metadata change does not run), the single-MCP-client test, and the disconnect tests still pass. Detection adds **no** MCPClient and no LLM call, so `mock_mcp_client_class.call_count == 1` must still hold in the single-client test. Add `patch("ai_qa.agents.bob.PipelineArtifactAdapter")` only where a test now reaches `save_metadata`.

- [x] **Task 7 — Full gate + DoD**
  - [x] 7.1 `uv run ruff check .` and `uv run mypy src` — clean. (`QualityIssue` is fully typed; `_detect_quality_issues` returns `list[QualityIssue]`; the page-dict assignment stores `model_dump()` dicts.)
  - [x] 7.2 `uv run pytest tests/test_agents/test_bob.py -v` — all green (new + existing). Run `tests/pipelines/test_*` only if you added a `QualityIssue` model test there.
  - [x] 7.3 **No DB migration** — confirm `uv run alembic upgrade head` is a no-op.
  - [x] 7.4 **Frontend not touched** — warning display is Story 11.6's job; this story only produces/carries the data and records the acknowledgement. Skip `npm run typecheck` unless a shared type was incidentally affected.
  - [x] 7.5 Update the Dev Agent Record (file list, commands run, outputs).

---

## Dev Notes

### The exact edit site in `_extract_descendants`

The success tail today ([bob.py:474-505](src/ai_qa/agents/bob.py)):

```python
            if not self.pages:
                return StageResult(success=False, data=None,
                                   errors=["All pages failed to extract or convert"], ...)

            await self.send_message(content="Requirements extraction complete.", ...)

            return StageResult(success=True, data=self.pages, errors=[], warnings=[], confidence=1.0)
        except Exception as e:
            logger.error(f"Error in Bob _extract_descendants: {e}", exc_info=True)
            raise
        finally:
            await client.disconnect()
```

After this story (the `except`/`finally` is **unchanged**; only the detection line is new — shown here on the current baseline with no Jira step):

```python
            if not self.pages:
                return StageResult(success=False, data=None,
                                   errors=["All pages failed to extract or convert"], ...)

            # --- 11.5: advisory input-quality detection over all assembled pages ---
            # (If 11.4 is merged, the jira supplement line runs ABOVE this so Jira items are scanned too.)
            self._has_quality_warnings = await self._run_quality_detection()

            await self.send_message(content="Requirements extraction complete.", ...)

            return StageResult(success=True, data=self.pages, errors=[], warnings=[], confidence=1.0)
        except Exception as e:                      # UNCHANGED
            logger.error(f"Error in Bob _extract_descendants: {e}", exc_info=True)
            raise
        finally:
            await client.disconnect()
```

> Ordering rule (authoritative): detection must run **after every page is appended** to `self.pages`. On the baseline that is after the Confluence Phase-2 loop. If 11.3 merged, the Confluence loop attaches `parsed_markdown` + `warnings` first; if 11.4 merged, the Jira supplement appends its item first. Place the `_run_quality_detection()` call last, immediately before `Requirements extraction complete.`. Never inside the per-page Phase-2 loop (that would scan pages incrementally and re-send the summary repeatedly).

### AC1 — what detection produces, and why deterministic

Each `QualityIssue` is `{category, location, message, impact}`. The six categories map 1:1 to the epic's illustrative list:

| Epic AC1 phrase | `QualityCategory` | How it is detected (deterministic) |
| --- | --- | --- |
| unsupported content warnings | `unsupported_content` | fold the existing `page["warnings"]` (11.3 `ContentParser` parse warnings) |
| missing expected results | `missing_expected_results` | no expected/Then/acceptance-criteria marker in the text |
| missing preconditions | `missing_preconditions` | no precondition/Given/setup marker in the text |
| vague steps | `vague_language` | `_VAGUE_TERMS` lexicon hit |
| ambiguous UI references | `ambiguous_ui_reference` | `_AMBIGUOUS_UI_TERMS` lexicon hit |
| (input too thin to use) | `insufficient_content` | text shorter than `_QUALITY_MIN_CONTENT_CHARS` |

The ACs say "issues **such as**" — the list is illustrative, not exhaustive, and a rule-based scan over the extracted Markdown satisfies it cheaply and **testably**. This matches Story 11.4's deliberate "deterministic over LLM" decision for Jira rendering. The richer, model-driven semantic scoring (true ambiguity detection, contradiction detection) is **Epic 12 Story 12.3** — Mary's confidence scoring explicitly consumes "source content is incomplete, vague, contradictory, **or includes unresolved Bob warnings**" ([epics.md:1200](_bmad-output/planning-artifacts/epics.md)). 11.5 is the producer of those Bob warnings; 12.3 is the model-driven consumer. **Do not pull 12.3's LLM scope into 11.5.**

### AC2 — "the user sees" without building 11.6's UI

11.3 and 11.4 both deferred all warning **rendering** to Story 11.6 ("extraction warnings are visible in the review content"). 11.5 keeps that split:

- **Data:** `quality_issues` is attached to each page dict and rides inside the existing `pages` review payload, so 11.6 can render per-page badges/sections later. `has_quality_warnings` is set on the payload metadata for a future top-level banner.
- **Immediate visibility (this story):** Bob emits **one** `send_message(message_type="warning")` summary at the end of extraction that names each flagged page and states the downstream impact. The chat already renders `warning` messages, so the user literally sees "specific warnings tied to source sections … explains the likely impact" with **zero** new frontend code. This is the same mechanism Bob already uses for per-page extraction warnings (`send_message(f"⚠ Failed to extract…", "warning")`).

### AC3 — acknowledgement is the act of approving, recorded in metadata

The user is **never blocked**. "The approval records that warnings were acknowledged" is satisfied by enriching the requirement metadata that `handle_approve` already writes on approve. `quality_warnings_acknowledged = bool(page["quality_issues"])` durably captures that the user approved a page that carried warnings. This needs no new UI affordance and no new approve-payload field — the backend already knows the page's issues. (A dedicated "I acknowledge" checkbox in the review panel, if ever wanted, is Story 11.6's concern.)

Note: in the live flow the frontend always sends the (possibly edited) `markdown` on approve (`onApprove(page.page_id, markdownContent)`), so `updated_markdown` is truthy and the metadata save path always runs for `action="approved"`. The acknowledgement is therefore recorded on every approval.

### Project-context rules that bite here

- **Type safety / no `# type: ignore`:** `QualityIssue` is fully typed. `category` is a required `Literal` field with **no default**, so the Pydantic-`Literal`-default cast rule does **not** apply (that rule is only for `Field(default=...)` on a `Literal`). Store `qi.model_dump(mode="json")` (a plain `dict`) on the page dict — do not store the `QualityIssue` object itself (the page dict is serialized to JSON over WebSocket and into the metadata artifact).
- **Narrow Optional before use:** read page fields with `page.get(k) or default` and `str(...)`-coerce so `None` never reaches a message string (Pyrefly "narrow Optional"/"bad-argument-type"). `_detect_quality_issues` takes a `dict[str, Any]`, so guard every access.
- **No bare `except`:** detection raises nothing and catches nothing — it is pure analysis. Do not wrap it in `try/except`. (Tests asserting exceptions must use `match=` per project rule, but this code path has no exceptions.)
- **Security:** the warning summary and metadata record contain only page titles + canned `message`/`impact` strings. **Never** include raw page HTML (`raw_html`), MCP tokens, or full config in any message or metadata field.
- **JSON columns / dict access:** `page.get("warnings") or []`, `page.get("quality_issues") or []` — the empty-fallback idiom from project-context.
- **`uv` only**, never `pip`; **never `python3`** — use `uv run` / `py -3`.

### Do NOT regress these existing behaviors

- The `confirm_parent` → `_extract_descendants` → paginated `review_markdown` flow must still work end-to-end. Detection is a single additive call at the tail; the review payload only gains keys.
- `_extract_descendants` still constructs exactly **one** `MCPClient` and `disconnect()`s it in `finally` (pinned by `test_bob_extract_descendants_creates_single_mcp_client` and the disconnect tests). Detection opens no connection and calls no LLM — the client count and the re-raise-on-exception behavior are untouched.
- `handle_approve` pagination semantics (advance index, save on approve, transition to `DONE` on the last page) are unchanged — only the metadata dict gains acknowledgement fields. `test_bob_handle_approve_pagination` (no `data` → never enters the approved branch) stays green.
- The review payload shape (`metadata={"is_review_ready": True, "pages": self.pages, ...}`) is backward-compatible: existing keys unchanged, only `has_quality_warnings` (metadata) and `quality_issues` (per page) added. The TS `ExtractedPage` interface ignores unknown keys at runtime — no frontend break.

### Testing approach (match the house style)

- `asyncio_mode = "auto"` is set, but existing Bob tests annotate `@pytest.mark.asyncio` — match them for async tests. `_detect_quality_issues` is sync — test it with a plain `def test_...` (no loop, fastest).
- Drive `_detect_quality_issues` with hand-built page dicts — it never touches MCP/LLM/DB, so no patching is needed.
- For `_run_quality_detection`, patch `bob_agent.send_message` (`AsyncMock`) and assert call args; build `self.pages` directly.
- For the AC3 approval test, patch `ai_qa.agents.bob.PipelineArtifactAdapter` at the class boundary and assert on `mock_adapter_class.return_value.save_metadata.call_args`. Set `phase="review_markdown"` and `current_page_index=0` so `handle_approve` enters the markdown branch.
- For the integration test, reuse the disconnect-on-completion scaffold and add a surviving Confluence page + a thin `convert_page`/`convert_markdown` AsyncMock so the produced requirement is flagged.
- Build real `QualityIssue` instances (or assert on the dict shape `{"category","location","message","impact"}`) so the assertions exercise the real model.

### Project Structure Notes

**Modified files:**

- `src/ai_qa/pipelines/models.py` — add `QualityCategory` Literal alias + `QualityIssue` model (extend the `typing` import to include `Literal`).
- `src/ai_qa/agents/bob.py` — import `QualityIssue`; add the `_QUALITY_*`/`_VAGUE_TERMS`/`_AMBIGUOUS_UI_TERMS`/marker/`_IMPACT_BY_CATEGORY` module constants; add `_detect_quality_issues()` (pure) and `_run_quality_detection()` (async); add `self._has_quality_warnings` to `__init__`; call detection at the tail of `_extract_descendants`; add `has_quality_warnings` to the two `is_review_ready` payloads; enrich the approved-page metadata in `handle_approve`. No change to `process()`, `handle_reject()`, `_resolve_mcp_pat()`, or the intake gate.
- `tests/test_agents/test_bob.py` — add detector / run-detection / acknowledgement / integration tests; keep existing regression tests green.

**New files:** none. **No DB migration. No new packages. No frontend changes.**

### Previous-story intelligence

- **Story 11.1** (`ready-for-dev`) — adds `JiraReader`/`JiraIssue`/`check_required_tools`. 11.5 does **not** import these; it scans assembled page dicts. No coupling.
- **Story 11.2** (`ready-for-dev`) — adds the `handle_start` intake gate + conftest fixture changes so the default mock thread is Alice-configured + MCP-ready. 11.5's logic lives **post-gate** (tail of `_extract_descendants`, the approved branch of `handle_approve`) and is reached by tests that call those methods directly, so it is independent of whether 11.2 is merged. See [agent-gate-conftest-regression](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/agent-gate-conftest-regression.md): if a happy-path Bob test now fails the gate, fix the shared `mock_db`/`mock_project_context` centrally, not per-test.
- **Story 11.3** (`ready-for-dev`) — wires `ContentParser` into Confluence Phase 2 and adds `parsed_markdown` + `warnings` per page. 11.5 **reads** `warnings` (folds it into `unsupported_content`) and prefers `requirement_md` then `parsed_markdown` as the text to scan. Defaults both to empty when 11.3 is unmerged.
- **Story 11.4** (`ready-for-dev`) — appends a Jira review item (`source_type="jira"`, `warnings: []`) at the tail of `_extract_descendants`. 11.5's detection call goes **after** 11.4's Jira line so Jira items are scanned. 11.5 carries `source_type` into the acknowledgement metadata.
- **Epic 3** (done) — built `ContentParser`/`ConfluenceReader`/Bob; production code, reuse only.
- **Epic 9** (done) — per-user MCP secret resolution; Bob resolves the PAT at extraction time. Detection adds no secret access.
- **Epic 10** (done) — `PipelineContext.artifact_service` carries the `db` + `ArtifactService` that `save_metadata` uses. See [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md): the artifact path is sync; `_schedule_change_event` no-ops outside an event loop (fine for unit tests).
- See [backend-test-suite-orphaned-legacy-tests](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md): a full `uv run pytest` is red from orphaned legacy tests — verify only the 11.5-touched files, not the whole-suite baseline.
- See [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md): the `_extract_descendants` snippet above is the **success tail only** — the surrounding `try/except/finally` is shown for placement and must be preserved verbatim; do not drop the `except … raise` / `finally: disconnect()`.

### Git intelligence (recent work patterns)

Recent commits center on Epic 10 artifact events (`9d878c5 feat(api): emit project-scoped artifact change events`, `1852886 feat(10-3): artifact read and preview access`) and the 3.12→3.14 upgrade (`39db313`). None touch Bob quality/detection — no merge-conflict risk. The established Bob pattern is: connect MCP once, build `self.pages[]`, emit a single `is_review_ready` payload, paginate review, save on approve. 11.5 slots a pure detection pass before the payload and enriches the on-approve metadata — it follows the established shape exactly (one connected client, additive page keys, no new payload type).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.5] — the three ACs (lines 1052-1072)
- [Source: _bmad-output/planning-artifacts/epics.md:50] — FR27 "Pipeline can detect insufficient input quality and warn before generation"; [epics.md:196] FR27 spans Epic 11 / Epic 12
- [Source: _bmad-output/planning-artifacts/epics.md:1195-1207] — Story 12.3 (Mary confidence scoring) consumes "unresolved Bob warnings" — the LLM-driven downstream of 11.5
- [Source: _bmad-output/planning-artifacts/architecture.md:73] — "Hallucination mitigation is architectural — human-in-the-loop review, confidence scoring, input quality detection"
- [Source: _bmad-output/planning-artifacts/architecture.md:459-469] — Pipeline Stage Interface / `StageResult` (`warnings`, `confidence`)
- [Source: src/ai_qa/agents/bob.py:322] — `_extract_descendants` (detection insertion at the tail); :461 page dict shape; :513-584 `handle_approve` (acknowledgement metadata)
- [Source: src/ai_qa/pipelines/models.py:57] — `ParsedContent` (add `QualityIssue` after it); :14 `ConfluencePage`
- [Source: src/ai_qa/pipelines/artifact_adapter.py:69] — `save_metadata(name, dict)`
- [Source: src/ai_qa/agents/base.py] — `send_message`, `AgentState`, `transition_to`
- [Source: frontend/src/App.tsx:178] — `ExtractedPage` interface (ignores extra keys); :753-766 `is_review_ready` handling
- [Source: frontend/src/components/SplitPanel.tsx:6] — review item shape (warning rendering is 11.6)
- [Source: tests/test_agents/test_bob.py] — existing Bob test patterns + the single-client / disconnect / pagination regression tests
- [Source: tests/conftest.py] — `mock_db` / `mock_project_context` fixtures (11.2 extends these)
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no `# type: ignore`; narrow Optional before use; no bare `except`; JSON-column empty-dict fallback; never `python3`; security (no secret/HTML/config logging)
- [Source: _bmad-output/implementation-artifacts/11-3-confluence-content-retrieval-and-parsing.md] — `warnings` + `parsed_markdown` page keys 11.5 reads
- [Source: _bmad-output/implementation-artifacts/11-4-jira-requirements-retrieval.md] — Jira `source_type` page key + tail insertion ordering

### Definition of Done

- [ ] `QualityIssue` model + `QualityCategory` Literal added to `pipelines/models.py`.
- [ ] `_detect_quality_issues()` is pure/sync and flags unsupported content (folded from `warnings`), missing expected results, missing preconditions, vague language, ambiguous UI references, and insufficient content — with `location` + downstream `impact` on every issue and no `None` leakage (AC1/AC2).
- [ ] `_run_quality_detection()` attaches `quality_issues` to every page, emits one `message_type="warning"` summary (page title + impact) when any issue exists, and returns/sets `self._has_quality_warnings` (AC2).
- [ ] Detection is called at the tail of `_extract_descendants` (after all pages, incl. Jira if merged, are assembled), is advisory only, and never changes `StageResult.success` or blocks the review (AC3).
- [ ] Both `is_review_ready` payloads carry `has_quality_warnings`; `quality_issues` rides inside `pages`.
- [ ] `handle_approve` records `quality_warnings_acknowledged` + `acknowledged_quality_issues` + `acknowledged_at` in the saved requirement metadata, and approval still proceeds without blocking (AC3).
- [ ] Existing Bob regression tests (single-MCP-client, disconnect on completion/exception, pagination) still pass unchanged; detection adds no MCP client and no LLM call.
- [ ] New tests cover: the detector across all six categories + clean case, the run-detection summary + flag, the acknowledgement metadata (issues present and absent), and the `_extract_descendants` integration.
- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
- [ ] `uv run pytest tests/test_agents/test_bob.py -v` — all green.
- [ ] `uv run alembic upgrade head` is a no-op (no schema change). No frontend change.

---

## Resolved Decisions (confirmed by Thuong — do NOT revisit)

These design forks were raised during story creation and **confirmed by Thuong to use the defaults below** (2026-06-11), consistent with the prior Epic 11 stories. They are locked; implement exactly as stated and do not re-open them.

1. **Detection is deterministic / rule-based, NOT LLM-based (M1 default).** A pure, synchronous lexicon + missing-section + thin-content scan over the extracted Markdown — cheap, fast, and trivially unit-testable. This mirrors Story 11.4's "deterministic over LLM" decision. The model-driven semantic scoring (true ambiguity/contradiction detection, confidence scores) is **Epic 12 Story 12.3**, which explicitly consumes "unresolved Bob warnings". *(Alternative considered and deferred: run an LLM quality pass per page in Bob — adds cost/latency, hard to test, and overlaps 12.3.)*

2. **Quality detection never blocks extraction or approval (AC3-aligned).** It is advisory: it attaches `quality_issues`, surfaces a warning, and records acknowledgement on approve. `StageResult.success` is unaffected; the user can always proceed. *(Alternative rejected: a hard "fix your docs first" gate — contradicts AC3.)*

3. **Warning rendering stays minimal in this story; the in-panel UI is Story 11.6.** AC2 "the user sees …" is met by the backend `send_message` warning summary (chat already renders it) plus carrying `quality_issues` on the pages for 11.6 to render. **No frontend change in 11.5.** *(Consistent with 11.3/11.4 deferring all warning UI to 11.6.)*

4. **Acknowledgement is recorded in the existing requirement metadata artifact** (`quality_warnings_acknowledged` + `acknowledged_quality_issues` + `acknowledged_at`), inferred from the page's own `quality_issues` at approve time — no new approve-payload field, no new UI affordance, no schema change. *(Alternative deferred: an explicit "I acknowledge" checkbox feeding a flag — 11.6's concern.)*

## Saved Questions (resolved to defaults by Thuong — 2026-06-11)

1. **Deterministic vs. LLM detection: DETERMINISTIC (confirmed).** M1 detection is the pure rule-based scan (Resolved Decision 1). The model-driven semantic version is deferred to Mary / Epic 12 Story 12.3 — do not add an LLM pass in Bob here.
2. **Detection thresholds/lexicon: use the first-cut defaults (confirmed).** `_QUALITY_MIN_CONTENT_CHARS = 200` and the vague/ambiguous-term lists ship as specified. Tuning is a follow-up if real content over/under-triggers.
3. **Acknowledgement storage: per-requirement `requirement.metadata.json` (confirmed).** A thread-level acknowledgement record is not added in this story.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- `QualityCategory` Literal alias and `QualityIssue` Pydantic model added to `pipelines/models.py`; `Literal` added to typing import.
- Module-level tunable constants (`_QUALITY_MIN_CONTENT_CHARS`, `_VAGUE_TERMS`, `_AMBIGUOUS_UI_TERMS`, `_EXPECTED_RESULT_MARKERS`, `_PRECONDITION_MARKERS`, `_IMPACT_BY_CATEGORY`) added to `bob.py` after `logger`.
- `_detect_quality_issues(page)` (pure, sync) and `_run_quality_detection()` (async) added to `BobAgent`; `self._has_quality_warnings: bool = False` added to `__init__`.
- Detection wired at tail of `_extract_descendants` after `_retrieve_jira_requirements` call; advisory only — `StageResult.success` never changed.
- Both `is_review_ready` payloads (`handle_start` + `handle_approve` confirm-parent path) enriched with `has_quality_warnings`.
- `handle_approve` approved-page metadata save enriched with `quality_warnings_acknowledged`, `acknowledged_quality_issues`, `acknowledged_at`, `source_type`.
- 14 new tests covering all 6 detector categories + clean page, `_run_quality_detection` summary + flag, AC3 ack (with/without issues), integration in `_extract_descendants`, no-None leakage.
- `uv run ruff check .` → clean; `uv run mypy src` → 0 issues; `uv run pytest tests/test_agents/test_bob.py` → 57 passed; `uv run pytest tests/pipelines/` → 181 passed; `uv run alembic upgrade head` → no-op. No frontend changes.

### File List

- `src/ai_qa/pipelines/models.py`
- `src/ai_qa/agents/bob.py`
- `tests/test_agents/test_bob.py`

### Change Log

- 2026-06-12: Story 11.5 implemented — added `QualityIssue` model, deterministic quality detector (`_detect_quality_issues` + `_run_quality_detection`), detection wired into `_extract_descendants`, `has_quality_warnings` added to both review payloads, quality acknowledgement recorded in approval metadata. 14 new tests; all 57 bob tests pass; no schema change; no frontend change.
