---
baseline_commit: 7d81929ca853824667ec3190090b728b18d545eb
---
# Story 17.3: Feed Parsed Attachments into Bob Extraction

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend only. Wire 17.1 (download) + 17.2 (parse) into Bob's extraction so attachment text reaches the LLM **alongside** the page/issue body, with provenance preserved (the LLM can tell body content from attachment X). The single merge seam is `RequirementFormatter.convert_markdown` → `_format_story`, where the body is injected as `Content:\n{raw_markdown}` ([requirement_formatter.py:284-285](src/ai_qa/pipelines/requirement_formatter.py:284)). The English-artifact boundary and the "lean prompt for on-prem latency" rule both still hold.

## Story

As Bob,
I want parsed attachment content merged into the requirement-extraction input,
so that generated requirements reflect attachments, not just the page/issue body.

## Acceptance Criteria

1. **Attachments parsed per page before extraction.** Given a Confluence page with downloaded supported attachments (from 17.1), when Bob converts that page, then each attachment's bytes are parsed via `parse_attachment` (17.2) into `[(filename, text)]` **before** the formatter LLM call at [bob.py:1167](src/ai_qa/agents/bob.py:1167).

2. **Attachment text reaches the LLM with provenance.** Given parsed attachment text, when the extraction prompt is built, then the attachment text is appended to the `Content:` block **after** the body markdown, under a clearly labeled, per-attachment section (e.g. `--- Attachment: <filename> ---`), so the model can attribute each requirement to the body vs a specific attachment and the existing anti-fabrication instruction still applies to the combined content.

3. **Provenance preserved end-to-end.** Given the merged content, when the requirement is generated, then body content and attachment content remain distinguishable in the prompt (labeled sections) — attachment text is not silently flattened into the body such that its origin is lost.

4. **Jira attachments merged best-effort.** Given a Jira issue with downloaded attachments (from 17.1), when Bob formats the issue, then the parsed attachment text is merged into the Jira requirement markdown produced by `_format_jira_markdown` ([bob.py:309](src/ai_qa/agents/bob.py:309)), under the same labeled-section convention; absent/failed Jira attachments simply contribute nothing (non-fatal).

5. **Prompt stays bounded (latency guard).** Given one or more large attachments, when the combined prompt is assembled, then the total attachment text is bounded (per-file budget from 17.2 plus an overall per-page cap), so the extraction call does not balloon — on-prem LLM latency scales with prompt size ([[project-context]]).

6. **Persisted artifacts stay English.** Given the conversation/UI may be non-English (16.9), when the requirement is generated from body + attachments, then the generated requirement markdown stays **English** — the `_format_story` generation prompt's output language is unchanged by this story ([[app-ui-english-only]]).

7. **No-attachment path is unchanged (regression).** Given a page/issue with no supported attachments, when Bob extracts it, then behavior is byte-for-byte identical to today — no extra MCP calls beyond the single shared listing, no prompt change, no new warnings.

## Tasks / Subtasks

- [ ] **Task 1 — Thread an `attachments` parameter through the formatter (AC: 2, 3)**
  - [ ] Extend `RequirementFormatter.convert_markdown` ([requirement_formatter.py:109](src/ai_qa/pipelines/requirement_formatter.py:109)) with a new keyword param `attachments: list[tuple[str, str]] | None = None` (`[(filename, text)]`).
  - [ ] Thread it into `_format_story` ([requirement_formatter.py:270](src/ai_qa/pipelines/requirement_formatter.py:270)). Build a merged content string: the existing `raw_markdown`, then — if attachments exist — a divider and one labeled block per attachment, and inject that combined string at the `Content:\n{raw_markdown}` position ([requirement_formatter.py:284](src/ai_qa/pipelines/requirement_formatter.py:284)). Keep the existing `CRITICAL: Base the requirement ONLY on the Content above...` instruction — it now correctly governs body + attachments.
  - [ ] Do NOT change the output template, the `**Source:**`/`**Extracted:**` lines, or the generation language (AC6). Do NOT change `caption_images_in_markdown` / `_absolutize_links`.

- [ ] **Task 2 — Parse + pass attachments in Bob's Phase-2 loop (AC: 1, 5)**
  - [ ] In the per-page loop ([bob.py:1118-1199](src/ai_qa/agents/bob.py:1118)), read the per-page attachment record produced by 17.1 (`page dict "attachments"` / downloaded bytes). For each `downloaded` attachment call `parse_attachment(bytes, filename=..., media_type=...)` (17.2) and collect `[(filename, result.text)]`, skipping entries whose parse yielded an empty/warning result.
  - [ ] Apply an overall per-page cap on combined attachment text (AC5) — if total exceeds the budget, truncate and record a warning; keep the body intact (body has primacy).
  - [ ] Pass the list into `formatter.convert_markdown(page, clean_md, image_fetcher=fetch_image_via_mcp, attachments=parsed_attachments)` at [bob.py:1167](src/ai_qa/agents/bob.py:1167).
  - [ ] The empty-content anti-hallucination guard at [bob.py:1135](src/ai_qa/agents/bob.py:1135) keys off `clean_md` (the body). Decide and document: a page with an empty body but a substantive attachment should NOT be stubbed — fold attachment length into the guard's "is there extractable content?" check so attachment-only pages still extract.

- [ ] **Task 3 — Merge Jira attachment text (AC: 4)**
  - [ ] In `_format_jira_markdown` ([bob.py:309](src/ai_qa/agents/bob.py:309)) (or at its call site in `_retrieve_jira_requirements`, [bob.py:534-544](src/ai_qa/agents/bob.py:534)), append the parsed Jira attachment text under the same labeled-section convention. Jira does not go through the LLM formatter, so this is a direct markdown append — keep it bounded (AC5) and clearly attributed.

- [ ] **Task 4 — Tests (all ACs)**
  - [ ] Formatter: `convert_markdown(..., attachments=[("spec.xlsx", "Sheet1: ...")])` puts the attachment text into the prompt under a labeled section AFTER the body. Mock the LLM (`_chat_model.ainvoke`) and assert the prompt string contains both the body and the labeled attachment block (assert at the prompt seam, do not call a live model).
  - [ ] No-attachment regression: `attachments=None`/`[]` produces the **exact** prompt as today (AC7) — snapshot/equality test against the current prompt assembly.
  - [ ] Bob loop: a page with one downloaded xlsx → `parse_attachment` is called and its text is threaded into `convert_markdown` (mock parser + formatter; assert the call args). A page with no attachments → `convert_markdown` called with no `attachments` and no extra MCP calls.
  - [ ] Budget: combined attachment text over the per-page cap → truncated + warning recorded.
  - [ ] Attachment-only page (empty body, substantive attachment) → NOT stubbed by the anti-hallucination guard.
  - [ ] `uv run pytest`.

## Dev Notes

### The merge seam (exact)

`RequirementFormatter._format_story` builds the extraction prompt; the body lands at:

```text
Content:
{raw_markdown}
```

([requirement_formatter.py:284-285](src/ai_qa/pipelines/requirement_formatter.py:284)). This is the ONE place body content is injected. Append attachment text here, after the body, as labeled sections — e.g.:

```text
Content:
{raw_markdown}

--- Attachment: requirements.xlsx ---
{attachment_text}
```

`convert_markdown` ([requirement_formatter.py:127](src/ai_qa/pipelines/requirement_formatter.py:127)) currently calls `_format_story(page, markdown)` with no feedback — add the `attachments` kwarg there and in `_format_story`'s signature ([requirement_formatter.py:270](src/ai_qa/pipelines/requirement_formatter.py:270)). Image captioning (`caption_images_in_markdown`) runs AFTER `_format_story` on the formatted output and is unrelated to this change — leave it alone.

### Current behavior to PRESERVE (regression guardrails)

- **No-attachment path identical (AC7).** The default `attachments=None` must reproduce today's prompt exactly. This is the highest-value regression test.
- **English output (AC6).** Do not touch the generation prompt's language. Per [[message-timestamps-feature]]/16.9, conversation language is localized but persisted artifacts stay English; the `_format_story` output template is the English boundary — keep it.
- **Lean prompt (AC5).** Oversized extraction input hurts on-prem latency ([[project-context]] LLM-latency rule) — bound the attachment text.
- **Anti-hallucination guard.** The `_MIN_EXTRACTABLE_CONTENT_CHARS` stub at [bob.py:1135](src/ai_qa/agents/bob.py:1135) must account for attachment content so an attachment-only page is not wrongly stubbed (AC1/Task 2), AND a truly empty page (no body, no attachments) still stubs rather than fabricating.
- **`await ainvoke` only.** The formatter already uses the async path with a hard `asyncio.wait_for` timeout ([requirement_formatter.py:322](src/ai_qa/pipelines/requirement_formatter.py:322)) — do not introduce a sync `invoke` ([[project-context]] async-LLM rule).

### Dependencies on other stories

- **Requires 17.1** (per-page downloaded attachment record + bytes on `self.pages`) and **17.2** (`parse_attachment`). Build after both. If 17.1/17.2 land first, this story is mostly threading + one prompt edit + tests.

### Source tree components to touch

- `src/ai_qa/pipelines/requirement_formatter.py` — **UPDATE** (`convert_markdown` + `_format_story` signatures + prompt merge).
- `src/ai_qa/agents/bob.py` — **UPDATE** (Phase-2 loop: parse attachments + pass to formatter + anti-hallucination guard tweak; `_format_jira_markdown` merge).
- Tests — **ADD/UPDATE**: formatter prompt-assembly tests, Bob loop tests (mock parser + formatter).

### Testing standards summary

- Mock the LLM at `_chat_model.ainvoke`; assert on the constructed prompt string, never a live model. Mock `parse_attachment` and `convert_markdown` in the Bob-loop tests.
- No bare `pytest.raises(Exception)`. Follow Pyrefly assert-then-access for mock `call_args` ([[project-context]]).

### Project Structure Notes

- Backend-only, no migration, no new deps (deps were added in 17.2). The only LLM-prompt change is additive (appended labeled sections) and gated on attachments being present.

### References

- Epic + story: [epics.md#Epic-17](_bmad-output/planning-artifacts/epics.md:2022), [Story 17.3](_bmad-output/planning-artifacts/epics.md:2042)
- Merge seam: [requirement_formatter.py:109](src/ai_qa/pipelines/requirement_formatter.py:109) (`convert_markdown`), [requirement_formatter.py:270-326](src/ai_qa/pipelines/requirement_formatter.py:270) (`_format_story` + prompt)
- Bob convert call + guard: [bob.py:1167](src/ai_qa/agents/bob.py:1167), [bob.py:1135](src/ai_qa/agents/bob.py:1135)
- Jira format: [bob.py:309](src/ai_qa/agents/bob.py:309), [bob.py:497-554](src/ai_qa/agents/bob.py:497)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[mary-correct-course-clarify]], [[bob-clarify-loop]], [[epic-11-retro-mcp-extraction-quality]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
