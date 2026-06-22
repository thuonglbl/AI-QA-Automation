---
baseline_commit: 9d878c5
---

# Story 11.3: Confluence Content Retrieval and Parsing

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want Bob to retrieve and parse Confluence content,
so that natural-language test cases become clean, reviewable requirement artifacts.

## Acceptance Criteria

### AC1 — Full page content + metadata retrieved; descendant discovery supported where available

**Given** a valid Confluence page URL is provided
**When** Bob calls MCP Confluence tools
**Then** the full page content and relevant metadata are retrieved
**And** page retrieval supports configured descendant/page discovery where available.

### AC2 — Content parsed into clean, structure-preserving Markdown

**Given** Confluence content contains natural-language test cases
**When** the parser processes the content
**Then** it extracts readable requirements/test-case source content into clean Markdown
**And** headings, lists, and tables are preserved in a reviewable format.

### AC3 — Macros / attachments / images normalized or preserved by reference; unsupported content warned, not dropped

**Given** Confluence content includes embedded macros, attachments, images, or non-standard formatting
**When** parsing occurs
**Then** supported content is normalized or preserved by reference
**And** unsupported content is surfaced as warnings rather than silently dropped.

---

## ⚠️ CRITICAL: This is a WIRE-IN story — connect the existing `ContentParser` into Bob's live extraction path

The retrieval and parsing **building blocks already exist** from Epic 3, but they are **not wired together the way the architecture says they should be.** This is the single most important thing to understand before writing any code:

- **`ConfluenceReader`** ([src/ai_qa/pipelines/confluence_reader.py](src/ai_qa/pipelines/confluence_reader.py)) — retrieves page content + metadata and discovers descendants. ✅ Satisfies AC1 today.
- **`ContentParser`** ([src/ai_qa/pipelines/content_parser.py](src/ai_qa/pipelines/content_parser.py)) — converts raw Confluence HTML → clean structure-preserving Markdown (headings/lists/tables via `markdownify`), normalizes Confluence macros (info/note/warning/tip/panel/code/expand), extracts mermaid/drawio/plantuml diagrams, saves images **by reference**, and emits **warnings** for unsupported content (gliffy, complex drawio, image fetch failures, HTML→MD failure). ✅ This component already implements AC2 **and** AC3.
- **`RequirementFormatter`** ([src/ai_qa/pipelines/requirement_formatter.py](src/ai_qa/pipelines/requirement_formatter.py)) — an **LLM-based** transform that markdownifies raw HTML and asks the LLM to reshape it into a fixed BMAD story template ("As a / I want", "Given/When/Then", "Technical Requirements"). It captions images inline via a vision model. It emits **no warnings** and does **not** normalize macros.

**The problem:** [architecture.md:302](_bmad-output/planning-artifacts/architecture.md) states *"Bob uses `confluence_reader` + `content_parser`"*, but the live extraction flow in `BobAgent._extract_descendants` ([src/ai_qa/agents/bob.py:453-472](src/ai_qa/agents/bob.py)) calls `RequirementFormatter.convert_page(page)` on **raw HTML** and **never imports or calls `ContentParser` at all**. As a result, in the real pipeline today:

- AC2 is only partially met — the LLM reshapes content into a template and can silently drop tables/lists.
- AC3 is **violated** — macros are not normalized and **no parse warnings are surfaced**; unsupported content is silently dropped.

**Story 11.3's job:** insert `ContentParser` into Bob's extraction path so AC2/AC3 are actually true in the live flow, and **carry the parse warnings + clean Markdown forward** on each page so the review state (Story 11.6) can render them. AC1 is essentially already satisfied — verify it and add a soft tool-availability guard.

**Do NOT:**

- Rewrite `ConfluenceReader`, `ContentParser`, or the MCP layer — they are production code. You are **wiring**, not rebuilding.
- Delete `RequirementFormatter` or rip out the LLM story step. The default design (below) **keeps** it but feeds it the *clean parsed Markdown* instead of raw HTML. (See the **Saved Questions** at the end for the one product decision that could change this — proceed with the default unless told otherwise.)
- Double-download images. `ContentParser._save_images` already fetches and saves images by reference. Do **not** then run `RequirementFormatter.convert_page` (which fetches + vision-captions them again). Feed the formatter pre-parsed Markdown via a new `convert_markdown(...)` method — see Task 3.
- Touch `handle_start`'s intake gate. That is Story 11.2's territory. 11.3 changes only the post-confirmation extraction path (`_extract_descendants`) and possibly `process` (the requirement-page search), never the gate.
- Hard-depend on Story 11.1. `MCPClient.check_required_tools()` / `ConfluenceReader.check_tool_availability()` may not be merged when you implement this. The tool-availability guard (AC1 "where available") must **degrade gracefully** if those methods don't exist yet.
- Add a DB migration or new packages. `markdownify`, `bs4`, `httpx` are already dependencies.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| `ConfluenceReader.read_page` / `read_page_by_id` — retrieve page content + metadata (title, author, version, labels, space_key) | [src/ai_qa/pipelines/confluence_reader.py:283](src/ai_qa/pipelines/confluence_reader.py) | ✅ done — satisfies AC1 retrieval |
| `ConfluenceReader.get_children_by_id` / `get_descendants_by_title` / `find_parent_pages` / `find_requirement_page_by_parent_id` — descendant/page discovery | [src/ai_qa/pipelines/confluence_reader.py:628](src/ai_qa/pipelines/confluence_reader.py) | ✅ done — satisfies AC1 discovery |
| `ContentParser.parse(page) -> StageResult(data=ParsedContent)` — HTML→clean Markdown, macro normalization, mermaid extraction, images-by-reference, warnings | [src/ai_qa/pipelines/content_parser.py:41](src/ai_qa/pipelines/content_parser.py) | ✅ done — **the AC2/AC3 engine; currently orphaned from Bob** |
| `ContentParser._handle_confluence_macros` — info/note/warning/tip/panel/code/expand → normalized; gliffy → warning | [src/ai_qa/pipelines/content_parser.py:147](src/ai_qa/pipelines/content_parser.py) | ✅ done — AC3 |
| `ContentParser._extract_mermaid` — mermaid/drawio→mermaid/plantuml, with warnings for un-convertible diagrams | [src/ai_qa/pipelines/content_parser.py:217](src/ai_qa/pipelines/content_parser.py) | ✅ done — AC3 |
| `ContentParser._save_images` — downloads + saves images by reference via `adapter.save_image`, warns on fetch failure | [src/ai_qa/pipelines/content_parser.py:273](src/ai_qa/pipelines/content_parser.py) | ✅ done — AC3 "preserved by reference" |
| `ParsedContent` model (`markdown`, `mermaid_diagrams`, `image_paths`, `test_cases_detected`, `parsed_at`) | [src/ai_qa/pipelines/models.py:57](src/ai_qa/pipelines/models.py) | ✅ done — `StageResult.warnings` carries AC3 warnings |
| `RequirementFormatter.convert_page(page)` — LLM story transform (consumes raw HTML today) | [src/ai_qa/pipelines/requirement_formatter.py:23](src/ai_qa/pipelines/requirement_formatter.py) | ✅ done — **extend with a `convert_markdown` path** |
| `PipelineArtifactAdapter` — `save_raw_html`, `save_requirement_page`, `save_image`, `save_metadata` | [src/ai_qa/pipelines/artifact_adapter.py:26](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — Bob builds one in `_extract_descendants`; reuse for `ContentParser` |
| `BobAgent._extract_descendants` — Phase 1 fetch raw HTML, Phase 2 convert to requirement, builds `self.pages[]` | [src/ai_qa/agents/bob.py:322](src/ai_qa/agents/bob.py) | ✅ done — **the method you modify** |
| `self.pages[]` dict shape: `page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md` | [src/ai_qa/agents/bob.py:461](src/ai_qa/agents/bob.py) | ✅ done — **add `warnings` + `parsed_markdown` keys** |
| `StageResult` (`success`, `data`, `errors`, `warnings`, `confidence`) | [src/ai_qa/models.py](src/ai_qa/models.py) | ✅ done |
| `MCPClient.check_required_tools` / `ConfluenceReader.check_tool_availability` | Story 11.1 ([11-1 story](_bmad-output/implementation-artifacts/11-1-mcp-client-foundation-for-confluence-and-jira.md)) | ⚠️ **may be unmerged** — soft-depend only |

---

## Tasks / Subtasks

- [x] **Task 1 — Fix the broken type-only import in `ContentParser` (pre-req for clean mypy)**
  - [x] 1.1 [src/ai_qa/pipelines/content_parser.py:7](src/ai_qa/pipelines/content_parser.py) imports `from ai_qa.pipelines.pipeline_artifact_adapter import PipelineArtifactAdapter` under `TYPE_CHECKING`. **That module does not exist** — the class lives in `ai_qa.pipelines.artifact_adapter`. Correct the path to `from ai_qa.pipelines.artifact_adapter import PipelineArtifactAdapter`. (Wiring `ContentParser` into Bob pulls this file fully into the type-check surface; leaving it broken fails `uv run mypy src`.)
  - [x] 1.2 Re-run nothing yet — this is a one-line fix verified by the Task 6 mypy gate.

- [x] **Task 2 — Wire `ContentParser` into `_extract_descendants` Phase 2 (AC2 + AC3)**
  - [x] 2.1 Open [src/ai_qa/agents/bob.py](src/ai_qa/agents/bob.py). Import `ContentParser` at the top: `from ai_qa.pipelines.content_parser import ContentParser`.
  - [x] 2.2 In `_extract_descendants`, **after** the `adapter = PipelineArtifactAdapter(self.project_context)` line (~bob.py:419) and **before** the Phase 2 loop, construct `parser = ContentParser(adapter)` (reuse the same adapter — do not build a second one).
  - [x] 2.3 In Phase 2 (the `for page in raw_pages:` loop, ~bob.py:455), for each `page`:
    - Call `parsed_result = await parser.parse(page)`. This is the AC2/AC3 engine: it returns `StageResult` whose `.data` is a `ParsedContent` (clean Markdown, mermaid, image paths) and whose `.warnings` is the AC3 unsupported-content list.
    - Extract `parsed: ParsedContent | None = parsed_result.data` and `warnings = parsed_result.warnings or []`. Guard: if `parsed` is `None` (parse failed), fall back to the raw markdownified HTML the formatter already handled, and append a warning — never silently drop the page.
  - [x] 2.4 Keep saving raw HTML as today (`adapter.save_raw_html(...)` in Phase 1). Do **not** remove that.

- [x] **Task 3 — Feed clean Markdown to the LLM formatter; stop re-fetching images (AC2)**
  - [x] 3.1 In [src/ai_qa/pipelines/requirement_formatter.py](src/ai_qa/pipelines/requirement_formatter.py), add a new method `async def convert_markdown(self, page: ConfluencePage, markdown: str) -> str` that **skips** the raw-HTML markdownify + image download/caption block (lines 25-65) and goes straight to `return await self._format_story(page, markdown)`. The existing `convert_page` stays for backward compatibility but is no longer Bob's path.
  - [x] 3.2 In `_format_story` ([requirement_formatter.py:78](src/ai_qa/pipelines/requirement_formatter.py)), strengthen the prompt's `## Technical Requirements` instruction so structure is preserved per AC2: e.g. *"Reorganize the remaining content under logical headings. **Preserve all source headings, bulleted/numbered lists, and Markdown tables verbatim — do not collapse tables into prose or drop list items.** Keep all image references."* This makes AC2's "headings, lists, and tables are preserved" hold in the final reviewable output.
  - [x] 3.3 In `_extract_descendants` Phase 2, call `requirement_md = await formatter.convert_markdown(page, parsed.markdown if parsed else <fallback_md>)` instead of `formatter.convert_page(page)`. The formatter now consumes the **already-parsed** clean Markdown — images were already saved by reference by `ContentParser`, so the formatter must NOT re-download/caption them (that is why we bypass `convert_page`).

- [x] **Task 4 — Carry warnings + clean Markdown forward on each page (AC2 + AC3)**
  - [x] 4.1 When appending to `self.pages` ([bob.py:461-469](src/ai_qa/agents/bob.py)), add two keys to the dict:
    - `"warnings": warnings` — the AC3 parse warnings (`list[str]`). Story 11.6 renders these in the review panel; this story's job is to **produce and carry** them so they are no longer silently dropped.
    - `"parsed_markdown": parsed.markdown if parsed else ""` — the clean, structure-preserving Markdown (AC2 "reviewable format"). Keep `requirement_md` (the LLM story) as the primary review content; `parsed_markdown` is the faithful source view.
  - [x] 4.2 **Out of scope (locked decision):** do NOT persist the clean parsed Markdown as a separate `source.md` artifact in this story. Carry `parsed_markdown` on the in-memory page dict only; persistence is deferred to Story 11.6/11.7. (See Resolved Decisions.)
  - [x] 4.3 When a page fails to convert (the existing `except` at [bob.py:470](src/ai_qa/agents/bob.py)), still append a minimal page entry carrying its `warnings` + a conversion-failure warning rather than dropping it entirely — AC3 is "warn, don't silently drop." (Match the existing `send_message(... "warning")` UX.)

- [x] **Task 5 — AC1 verification + soft tool-availability guard**
  - [x] 5.1 AC1 retrieval + descendant discovery is already implemented by `ConfluenceReader` (`read_page_by_id`, `get_children_by_id`, `get_descendants_by_title`). **Add no new retrieval logic.** The work here is a guard test plus an optional capability check.
  - [x] 5.2 "Descendant/page discovery where available" → add a **soft** capability guard: before the descendant search in `_extract_descendants`, if `hasattr(reader, "check_tool_availability")` (Story 11.1 merged), call it and, when required Confluence tools are missing, `send_message` an actionable capability warning and continue/abort gracefully. If the method does not exist (11.1 unmerged), **skip the guard entirely** — do not import or reference 11.1 symbols directly. Use `getattr`/`hasattr`, never a hard import.
  - [x] 5.3 Confirm metadata (`title`, `author`, `version`, `labels`, `space_key`) flows through `ConfluencePage` into the parsed result and the page dict's `source_url`/`page_title`. No new fields required; this is a verification + test, not new code.

- [x] **Task 6 — Unit tests (AC1/AC2/AC3)**
  - [x] 6.1 Extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py). Reuse the `bob_agent` + `mock_project_context` fixtures and match the existing style (`@pytest.mark.asyncio`, `patch("ai_qa.agents.bob.<symbol>")`, `AsyncMock`/`MagicMock`).
  - [x] 6.2 **AC2/AC3 wiring test:** patch `ai_qa.agents.bob.ContentParser`, `ai_qa.agents.bob.RequirementFormatter`, `ai_qa.agents.bob.ConfluenceReader`, `ai_qa.agents.bob.MCPClient`, `ai_qa.agents.bob.AppSettings`, `ai_qa.agents.bob.LLMClient`, and `get_llm_config`. Make the reader return one child + a `read_page_by_id` page with HTML content; make `ContentParser.parse` (AsyncMock) return a `StageResult(success=True, data=ParsedContent(...markdown="# Clean\n| a | b |\n..."), warnings=["Gliffy diagram detected — manual review recommended"])`. Assert: (a) `formatter.convert_markdown` was called with the parser's clean markdown (NOT `convert_page`), (b) the resulting `self.pages[0]["warnings"]` contains the Gliffy warning, (c) `self.pages[0]["parsed_markdown"]` holds the clean markdown.
  - [x] 6.3 **AC3 no-silent-drop test:** make `ContentParser.parse` return `data=None` / a failed parse for one page; assert the page is still represented in `self.pages` with a warning, and the run does not crash.
  - [x] 6.4 **AC1 discovery + single-client regression:** confirm the existing `test_bob_extract_descendants_creates_single_mcp_client` and the two `disconnect` tests still pass — they currently patch `RequirementFormatter`; add a `patch("ai_qa.agents.bob.ContentParser")` to those (or set defaults) so the new parse call doesn't hit a real parser. **Do not weaken these tests.**
  - [x] 6.5 **Direct `ContentParser` AC2/AC3 coverage** already exists in [tests/pipelines/test_content_parser.py](tests/pipelines/test_content_parser.py) (plain HTML→markdown, macro→blockquote, empty→warning). Add table-preservation + a macro-warning assertion only if not already covered — do not duplicate existing cases.
  - [x] 6.6 **`convert_markdown` unit test:** in a pipelines test, assert `RequirementFormatter.convert_markdown` calls `_format_story` with the passed markdown and does **not** open an `httpx` client / call `invoke_vision` (no image re-fetch). Mock `self._llm._chat_model.ainvoke`.

- [x] **Task 7 — Full gate + DoD**
  - [x] 7.1 `uv run ruff check .` and `uv run mypy src` — clean (the Task 1 import fix is required for mypy).
  - [x] 7.2 `uv run pytest tests/test_agents/test_bob.py tests/pipelines/test_content_parser.py -v` — all green (new + existing).
  - [x] 7.3 **No DB migration** — confirm `uv run alembic upgrade head` is a no-op.
  - [x] 7.4 **Frontend not touched** — warnings display is Story 11.6's job; this story only produces/carries the data. Skip `npm run typecheck` unless a shared type was incidentally affected.
  - [x] 7.5 Update the Dev Agent Record (file list, commands run, outputs).

---

## Dev Notes

### The exact edit site in `_extract_descendants`

The Phase 2 loop today ([bob.py:453-472](src/ai_qa/agents/bob.py)):

```python
# Setup LLM for Bob
config = self.get_llm_config()
llm_client = LLMClient(config)
formatter = RequirementFormatter(llm_client)

# Phase 2: Convert to Requirement
self.pages = []
for page in raw_pages:
    await self.send_message(f"Converting '{page.title}' to requirement...", "info")
    try:
        requirement_md = await formatter.convert_page(page)        # <-- raw HTML, no warnings
        adapter.save_requirement_page(page.page_id, requirement_md)
        await self.send_message(f"✓ Converted '{page.title}'", "info")
        self.pages.append({
            "page_id": page.page_id,
            "page_title": page.title,
            "source_url": page.url,
            "raw_html": page.content,
            "requirement_md": requirement_md,
        })
    except Exception as e:
        ...
```

After this story:

```python
config = self.get_llm_config()
llm_client = LLMClient(config)
formatter = RequirementFormatter(llm_client)
parser = ContentParser(adapter)                # NEW — reuse the SAME adapter

self.pages = []
for page in raw_pages:
    await self.send_message(f"Parsing '{page.title}'...", "info")
    parsed_result = await parser.parse(page)    # NEW — AC2/AC3 engine
    parsed = parsed_result.data                 # ParsedContent | None
    warnings = parsed_result.warnings or []
    clean_md = parsed.markdown if parsed else markdownify(page.content, heading_style="ATX")
    try:
        requirement_md = await formatter.convert_markdown(page, clean_md)   # NEW — no image re-fetch
        adapter.save_requirement_page(page.page_id, requirement_md)
        self.pages.append({
            "page_id": page.page_id,
            "page_title": page.title,
            "source_url": page.url,
            "raw_html": page.content,
            "requirement_md": requirement_md,
            "parsed_markdown": clean_md,        # NEW — AC2 reviewable structure-faithful source
            "warnings": warnings,               # NEW — AC3 surfaced, not dropped
        })
    except Exception as e:
        logger.error(f"Failed to convert page {page.title}: {e}")
        await self.send_message(f"⚠ Failed to convert: '{page.title}'", "warning")
        self.pages.append({                     # NEW — warn, don't silently drop (AC3)
            "page_id": page.page_id,
            "page_title": page.title,
            "source_url": page.url,
            "raw_html": page.content,
            "requirement_md": "",
            "parsed_markdown": clean_md,
            "warnings": warnings + [f"Conversion to requirement failed: {type(e).__name__}"],
        })
```

### Why feed the formatter parsed Markdown instead of raw HTML

`ContentParser._save_images` and `RequirementFormatter.convert_page` **both** download every image in the page. If you call both, you fetch every image twice (and run the vision model on each), doubling latency and cost. The fix is `convert_markdown`: `ContentParser` owns image handling (by reference, per AC3); the formatter receives clean Markdown where images are already referenced and only performs the LLM story transform. This is also why `convert_page` must NOT be Bob's path anymore.

### AC2 — what "preserved in a reviewable format" means

`ContentParser._html_to_markdown` uses `markdownify(..., heading_style="ATX")`, which already preserves headings, lists, and HTML tables as Markdown tables. The risk to AC2 is the **LLM story transform** downstream, which can collapse tables into prose. Two defenses, both required:

1. Carry `parsed_markdown` on the page dict — a faithful, non-LLM view of the source (this is the structure-guaranteed artifact).
2. Strengthen the `_format_story` prompt (Task 3.2) to instruct the LLM to preserve tables/lists/headings verbatim.

The review (Story 11.6) can then show the LLM story as the primary and fall back to `parsed_markdown` for faithful structure.

### AC3 — warnings are produced by `ContentParser`, carried by Bob, displayed by 11.6

`ContentParser` already emits warnings for: Gliffy diagrams, un-convertible Draw.io, PlantUML (preserved as `%% PlantUML original format`), image fetch failures, and HTML→Markdown conversion failure (`content_parser.py` lines 211, 255, 309-311, 77). Macros (info/note/warning/tip/panel/code/expand) are **normalized**, not warned. This story's contract: **collect `parsed_result.warnings` and attach to `self.pages[i]["warnings"]`** so they are no longer dropped. Rendering the warnings in the UI is Story 11.6 ("extraction warnings are visible in the review content") — do not build the UI here, but the data must be present and correct.

### AC1 — retrieval + discovery already work; keep the guard soft

`ConfluenceReader.read_page_by_id` returns content + metadata; `get_children_by_id` / `get_descendants_by_title` discover descendants; `find_parent_pages` / `find_requirement_page_by_parent_id` suggest requirement pages. Bob already orchestrates all of this. AC1's "where available" maps to Story 11.1's `check_tool_availability()`. Because **11.1, 11.2, and 11.3 are all un-implemented** (11.1/11.2 are `ready-for-dev`, 11.3 is `backlog`), you cannot assume 11.1 is merged. Use `hasattr(reader, "check_tool_availability")` and skip the guard when absent. Never `from ... import` an 11.1-only symbol.

### Build-order / dependency reality

- **Story 11.1** (`ready-for-dev`, likely unmerged): adds `check_tool_availability`. Soft-depend via `hasattr` only.
- **Story 11.2** (`ready-for-dev`, likely unmerged): prepends an intake gate to `handle_start` and edits `tests/conftest.py` `mock_db`/`mock_project_context` to make the default thread Alice-configured + MCP-configured. **11.3 does not touch `handle_start`.** Your new logic lives in `_extract_descendants` (post-gate), reached by tests that call it directly — so it is independent of whether 11.2 is merged. If 11.2's conftest changes are present, the happy path still passes; if not, your `_extract_descendants` tests still work because they drive the method directly with mocks.
- See [agent-gate-conftest-regression](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/agent-gate-conftest-regression.md): if adding any precondition raises in a shared path, fix the shared `mock_db` centrally rather than per-test.

### Testing approach (match the house style)

- `asyncio_mode = "auto"` is set, but existing Bob tests annotate `@pytest.mark.asyncio` — match them.
- Patch at the Bob module boundary: `patch("ai_qa.agents.bob.ContentParser")`, `patch("ai_qa.agents.bob.RequirementFormatter")`, etc. `ContentParser.parse` is `async` → use `AsyncMock`.
- Build a real `ParsedContent` for the parser mock's `.data` so the dict-carry assertions are meaningful: `ParsedContent(page_id="1", page_title="t", source_url="u", markdown="# H\n| a | b |\n| - | - |\n| 1 | 2 |", mermaid_diagrams=[], image_paths=[], test_cases_detected=[], parsed_at=datetime.now(UTC))`.
- For `convert_markdown`, assert no `httpx.AsyncClient` is opened — mock `self._llm._chat_model.ainvoke` (AsyncMock returning an object with `.content`).
- The existing single-client / disconnect tests (`test_bob_extract_descendants_creates_single_mcp_client`, `..._disconnects_mcp_on_completion`, `..._on_exception`) must keep passing — add `patch("ai_qa.agents.bob.ContentParser")` to them so the new parse step is mocked. **Do not delete or weaken these AC regression tests.**

### Project-context rules that bite here

- **No bare `except Exception`** with `pytest.raises(Exception)` — the existing `..._on_exception` test uses `pytest.raises(Exception, match="Simulated error")`, which is acceptable because it has `match=`. New tests must include `match=` if they assert on exceptions.
- **JSON-column / dict access:** when reading optional fields use the `.get(...) or default` idiom; the `(thread.agent_configs or {})` pattern is project convention.
- **Type safety:** no `# type: ignore`. `ParsedContent` and `StageResult` are fully typed; `parsed_result.data` is `Any | None` → narrow with `parsed = parsed_result.data` then guard `if parsed:` before `.markdown` (per the "Narrow Optional before use" Pyrefly rule in project-context).
- **Security:** never log raw page HTML dicts, MCP tokens, or full config. Warnings are user-safe strings only.
- **`uv` only**, never `pip`; **never `python3`** — use `uv run` / `py -3`.

### Do NOT regress these existing behaviors

- The `confirm_parent` → `_extract_descendants` → paginated `review_markdown` flow must still work end-to-end. Your change is additive inside Phase 2.
- `_extract_descendants` still constructs exactly **one** `MCPClient` and `disconnect()`s it in `finally` (pinned by tests). `ContentParser` does not open MCP connections — it only does HTML→Markdown + `httpx` image fetches — so adding it does not change MCP client count.
- `process()` still resolves the MCP PAT via `_resolve_mcp_pat()` and disconnects. Leave it.
- The frontend review payload (`metadata={"is_review_ready": True, "pages": self.pages}`) is unchanged in shape — you only add keys to each page dict, which is backward-compatible.

### Project Structure Notes

**Modified files:**

- `src/ai_qa/agents/bob.py` — import `ContentParser`; in `_extract_descendants` Phase 2, parse each page, feed clean Markdown to `formatter.convert_markdown`, carry `warnings` + `parsed_markdown` on `self.pages`; add the soft tool-availability guard. No change to `handle_start`, `process` (beyond optional), `handle_approve`, `handle_reject`.
- `src/ai_qa/pipelines/requirement_formatter.py` — add `convert_markdown(page, markdown)`; strengthen `_format_story` prompt for structure preservation.
- `src/ai_qa/pipelines/content_parser.py` — fix the broken `TYPE_CHECKING` import path (`pipeline_artifact_adapter` → `artifact_adapter`). No behavior change.
- `tests/test_agents/test_bob.py` — add wiring/warning/no-drop tests; patch `ContentParser` in existing extract-descendants tests.
- `tests/pipelines/test_content_parser.py` and/or a formatter test — `convert_markdown` no-image-refetch test; table-preservation assertion if not already covered.

**New files:** none required. **No DB migration. No new packages. No frontend changes.**

### Previous-story intelligence

- **Story 11.1** (`ready-for-dev`): adds `JiraReader`, `check_required_tools`, `check_tool_availability`. 11.3 soft-depends on `check_tool_availability` only (via `hasattr`).
- **Story 11.2** (`ready-for-dev`): adds the `handle_start` intake gate + conftest fixture changes. 11.3 is independent of it (works on `_extract_descendants`).
- **Epic 3** (done): built `ConfluenceReader`, `ContentParser` (Story 3.3), and the original Bob agent (Story 3.5). `ContentParser` was authored *for* Bob per the architecture but was never wired into the live `_extract_descendants` path — 11.3 closes that gap. Production code; reuse, don't refactor beyond the targeted edits.
- **Epic 9** (done): per-user MCP secret resolution — Bob already resolves the PAT at extraction time. Unchanged.
- **Epic 10** (in-progress): `PipelineContext.artifact_service` carries the `db` and the `ArtifactService` Bob/`ContentParser` use for image + requirement saves. No conflict.
- See [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md): the artifact path is sync; `_schedule_change_event` no-ops outside an event loop (fine for unit tests).

### Git intelligence (recent work patterns)

Recent Bob-area commits: `625250d feat Bob agent read all confluence pages and review split panel`, `473dd50 fix requirement extraction from mcp confluence`, `2f4a6b5 fix confirm requirement url popup`. The established Bob pattern is: connect MCP once, fetch raw HTML per page, convert, build `self.pages[]`, send a single `is_review_ready` payload. Your change slots a parse step into the convert phase and enriches the page dict — it follows the established shape. None of the recent commits touched `ContentParser`, confirming it is orphaned from the live path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-11.3] — the three ACs
- [Source: _bmad-output/planning-artifacts/architecture.md:302] — "Bob uses `confluence_reader` + `content_parser`" (the intended composition this story realizes)
- [Source: _bmad-output/planning-artifacts/architecture.md:28] — "content parsing including embedded macros (M1)" (AC3 scope)
- [Source: src/ai_qa/agents/bob.py:322] — `_extract_descendants` (the method to modify)
- [Source: src/ai_qa/pipelines/content_parser.py] — `ContentParser.parse`, macro/mermaid/image handling, warnings (AC2/AC3 engine)
- [Source: src/ai_qa/pipelines/requirement_formatter.py] — `convert_page`, `_format_story` (add `convert_markdown`)
- [Source: src/ai_qa/pipelines/confluence_reader.py] — `read_page_by_id`, `get_children_by_id`, `get_descendants_by_title` (AC1 retrieval + discovery)
- [Source: src/ai_qa/pipelines/models.py:57] — `ParsedContent`; [models.py:14] — `ConfluencePage` metadata fields
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `PipelineArtifactAdapter` (`save_image`, `save_requirement_page`)
- [Source: tests/test_agents/test_bob.py] — existing Bob test patterns + the single-client / disconnect regression tests
- [Source: tests/pipelines/test_content_parser.py] — existing `ContentParser` coverage
- [Source: tests/conftest.py] — `mock_db` / `mock_project_context` fixtures (note 11.2 will extend these)
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; no `# type: ignore`; narrow Optional before use; no bare `except`; never `python3`; security (no secret/HTML/config logging)

### Definition of Done

- [ ] `ContentParser` is wired into `_extract_descendants`; each page is parsed and its clean Markdown feeds the LLM formatter via `convert_markdown` (no image double-fetch) (AC2).
- [ ] Parse warnings are collected and carried on `self.pages[i]["warnings"]`; unsupported content is never silently dropped, and conversion-failed pages still appear with a warning (AC3).
- [ ] `self.pages[i]["parsed_markdown"]` carries the clean, structure-preserving Markdown; the `_format_story` prompt instructs table/list/heading preservation (AC2).
- [ ] AC1 retrieval + descendant discovery verified intact; the tool-availability guard is soft (`hasattr`) and degrades gracefully when Story 11.1 is unmerged.
- [ ] Broken `TYPE_CHECKING` import in `content_parser.py` fixed (`pipeline_artifact_adapter` → `artifact_adapter`).
- [ ] Existing Bob regression tests (single-MCP-client, disconnect on completion/exception, pagination) still pass.
- [ ] New tests cover: parser wiring, warning carry, no-silent-drop, `convert_markdown` no-image-refetch.
- [ ] `uv run ruff check .` and `uv run mypy src` — clean.
- [ ] `uv run pytest tests/test_agents/test_bob.py tests/pipelines/test_content_parser.py -v` — all green.
- [ ] `uv run alembic upgrade head` is a no-op (no schema change).

---

## Resolved Decisions (confirmed by Thuong — do NOT revisit)

Both design forks below were raised during story creation and **confirmed by the user to use the default**. These are locked; implement exactly as stated and do not re-open them.

1. **LLM story transform is KEPT.** `RequirementFormatter`'s LLM "BMAD story" transform stays. Feed it the clean parsed Markdown (via `convert_markdown`) and carry `parsed_markdown` separately so AC2's structure is guaranteed. `requirement_md` (the LLM story) remains the primary review content Mary consumes; `parsed_markdown` is the faithful source view. Do **not** drop the LLM step in favor of pure rule-based Markdown.

2. **Clean parsed Markdown is carried in-memory only.** Attach `parsed_markdown` to the page dict (Task 4.1). Do **not** persist a separate `source.md` artifact now — persistence is deferred to Story 11.6/11.7. Task 4.2's optional artifact save is therefore **out of scope** for this story.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- mypy error `"list[str]" has no attribute "success"` at bob.py:535 — `check_tool_availability` (Story 11.1) returns `list[str]` (missing tool names), not `StageResult`. Fixed guard to check truthiness of the list.
- Two new tests initially returned 2 pages instead of 1 because `_extract_descendants` adds the parent page to summaries when `_page_id` is set AND children are returned. Fixed tests to use `_page_id = "page-1"` with `data=[]` (no children) so summaries has exactly one entry.

### Completion Notes List

- **Task 1**: Fixed broken TYPE_CHECKING import in `content_parser.py` (`pipeline_artifact_adapter` → `artifact_adapter`). Required for `uv run mypy src` to pass once ContentParser is imported by bob.py.
- **Task 2**: Wired `ContentParser(adapter)` into `_extract_descendants` Phase 2. `parser.parse(page)` is called before the LLM formatter for each page; `parsed.markdown` feeds `formatter.convert_markdown`; fallback to `markdownify(page.content)` when parse returns `data=None`.
- **Task 3**: Added `convert_markdown(page, markdown)` to `RequirementFormatter` — goes directly to `_format_story`, skipping HTML markdownify and image download/caption that `convert_page` performs. Strengthened `_format_story` prompt to preserve tables/lists/headings verbatim.
- **Task 4**: Each page dict now carries `"parsed_markdown"` (clean AC2 source view) and `"warnings"` (AC3 parse warnings). Exception path also appends the page with a conversion-failure warning — no silent drops.
- **Task 5**: Soft tool-availability guard added using `hasattr(reader, "check_tool_availability")` — calls it when Story 11.1 is merged, sends actionable warning if tools are missing, skips entirely when 11.1 is absent. `check_tool_availability` confirmed to return `list[str]` (missing tool names).
- **Task 6**: Added 2 new Bob tests (`test_bob_extract_descendants_wires_content_parser`, `test_bob_extract_descendants_no_silent_drop_on_parse_failure`); added `ContentParser` patch to 3 existing extract_descendants tests; added `test_convert_markdown_calls_format_story_without_image_refetch` in `test_content_parser.py`.
- **Task 7**: `ruff` clean, `mypy src` clean (80 files), 55/55 target tests green, full suite 1144 passed / 2 pre-existing failures (OutputWriter deletion — Story 11.8 scope), alembic no-op, frontend untouched.

### File List

- `src/ai_qa/agents/bob.py`
- `src/ai_qa/pipelines/content_parser.py`
- `src/ai_qa/pipelines/requirement_formatter.py`
- `tests/test_agents/test_bob.py`
- `tests/pipelines/test_content_parser.py`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/11-3-confluence-content-retrieval-and-parsing.md`

### Change Log

- 2026-06-12: Story 11.3 implemented — wired ContentParser into Bob's _extract_descendants Phase 2; added convert_markdown to RequirementFormatter; fixed content_parser.py TYPE_CHECKING import; added warnings + parsed_markdown to page dicts; soft tool-availability guard; 4 new tests added (claude-sonnet-4-6)
