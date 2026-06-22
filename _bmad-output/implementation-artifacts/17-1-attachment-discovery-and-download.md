---
baseline_commit: 7d81929ca853824667ec3190090b728b18d545eb
---
# Story 17.1: Discover and Download Attachments via MCP

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend only. Bob discovers file attachments on a Confluence page (and best-effort on a Jira issue) via the **existing** MCP attachment tools — `confluence_list_attachments` + `confluence_download_attachment`, which Bob ALREADY calls for image captioning ([bob.py:1078-1116](src/ai_qa/agents/bob.py:1078)) — filters to supported document types within a size cap, downloads the bytes, and **persists them as a new `attachment` artifact kind** (raw companion of the requirement, hidden in the FE like `raw_html`/images). This story produces the bytes + a per-source attachment record; parsing (17.2) and merge-into-extraction (17.3) build on it.

## Story

As Bob,
I want to discover and download files attached to a Confluence page or Jira issue through the existing MCP retrieval path,
so that attachment bytes are available for parsing alongside the page/issue body.

## Acceptance Criteria

1. **Discover all Confluence attachments (one listing per page).** Given a Confluence page Bob is extracting, when Bob processes that page, then Bob lists every attachment via the MCP `confluence_list_attachments` tool and produces a structured per-page record `[{filename, attachment_id, media_type}]`. The listing call is shared (cached per page id) with the existing image-captioning path so each page is listed **at most once** — no duplicate `confluence_list_attachments` calls.

2. **Filter to supported types within the size cap.** Given the discovered attachment records, when Bob selects which to download, then only the **supported document types** — `xlsx`, `docx`, `pdf`, `csv`, `txt`, `pptx` (matched by media type and/or filename extension) — that are within the **per-file size cap (default 10 MB)** are selected for download. Every other attachment is recorded with a status of `skipped_unsupported` or `skipped_oversized` (with the reason) and is **not** downloaded. Images keep flowing through the existing captioning path and are NOT treated as document attachments here.

3. **Download bytes via MCP.** Given a supported, in-cap attachment, when Bob downloads it, then the raw bytes are retrieved via the MCP `confluence_download_attachment` tool (base64 → decoded bytes + media type), exactly as the image path does today ([bob.py:1099-1116](src/ai_qa/agents/bob.py:1099)).

4. **Persist downloaded bytes as a raw companion.** Given an attachment's downloaded bytes, when Bob persists it, then it is saved as a new artifact `kind="attachment"` under the requirement's storage area, browsing under the `requirements` folder and **hidden from the FE result tree** (it is not a `.md` file), carrying provenance: `source_type` (`confluence`/`jira`), `source_url` (page/issue url), `title` (the attachment filename), and `parent_source_id` (the page/issue id). Re-running extraction for the same page must not orphan-duplicate the companion uncontrollably (name is deterministic per `{page_id}/{filename}`).

5. **Jira best-effort discovery.** Given a referenced Jira issue, when Bob attempts attachment discovery, then it first checks whether the MCP server exposes a Jira attachment list/download tool (via the connected client's tool discovery); if the tools exist it discovers + downloads as for Confluence; if they are absent it logs and skips gracefully (a `warning` chat message, no failure), mirroring the existing `_retrieve_jira_requirements` / `JiraReader.check_tool_availability` pattern ([bob.py:497-554](src/ai_qa/agents/bob.py:497)).

6. **Failures never abort extraction.** Given any list or download MCP call fails for an attachment, when the error occurs, then it is logged and recorded with status `failed` (with the exception type), and Bob continues with the remaining attachments and pages — never aborting the page or the run. This mirrors the existing image-fetch `try/except → logger.warning → continue` behavior ([bob.py:1093-1116](src/ai_qa/agents/bob.py:1093)).

## Tasks / Subtasks

- [ ] **Task 1 — Register the new `attachment` artifact kind (AC: 4)**
  - [ ] Add `"attachment"` to `ARTIFACT_KINDS` ([src/ai_qa/artifacts/service.py:17](src/ai_qa/artifacts/service.py:17)).
  - [ ] In `build_artifact_key`, route `kind == "attachment"` under the requirement storage tree (e.g. `folder = "requirements/attachments"`) so it lives beside `raw_html` (`requirements/mcp/confluence`) ([src/ai_qa/artifacts/storage.py:28](src/ai_qa/artifacts/storage.py:28)).
  - [ ] In `folder_for_kind`, add `"attachment"` to the set that returns `"requirements"` (browse with the requirement companions) ([src/ai_qa/artifacts/storage.py:60](src/ai_qa/artifacts/storage.py:60)). Do **not** wire `folder_for_kind` into `build_artifact_key` — their catch-alls diverge by design (see the docstring there).

- [ ] **Task 2 — Adapter method to persist an attachment (AC: 4)**
  - [ ] Add `save_attachment(self, *, page_id: str, filename: str, content: bytes, source_type: str | None, source_url: str | None, parent_source_id: str | None) -> Artifact` to `PipelineArtifactAdapter`, mirroring `save_image` ([src/ai_qa/pipelines/artifact_adapter.py:365](src/ai_qa/pipelines/artifact_adapter.py:365)) but with `kind="attachment"`, deterministic `name=f"{page_id}/{filename}"`, `title=filename`, and the provenance fields threaded into `service.save_artifact` ([src/ai_qa/artifacts/service.py:79](src/ai_qa/artifacts/service.py:79)). Call `self._schedule_change_event(artifact.id, "created")` like `save_image` does.

- [ ] **Task 3 — Extract a reusable Confluence attachment lister (AC: 1) [ANTI-DUPLICATION]**
  - [ ] Today `fetch_image_via_mcp` ([bob.py:1070-1116](src/ai_qa/agents/bob.py:1070)) builds an in-page `attach_cache[page_id] -> {filename: {id, mediaType}}` from `confluence_list_attachments`. Refactor so the **listing + cache is shared** by both image captioning and attachment reading — extract a small helper (e.g. `_list_confluence_attachments(client, reader, page_id, audit) -> dict[str, dict[str, str]]`) that both call, so a page is listed once. Keep the existing image-fetch behavior byte-for-byte (it must still resolve `<img src>` → bytes).
  - [ ] The helper returns the full listing (filename → id + mediaType); the discovery step (Task 4) turns that into the structured attachment record.

- [ ] **Task 4 — Confluence discovery + download + persist, per page (AC: 1, 2, 3, 4, 6)**
  - [ ] Define the supported-type policy in one place: a module constant mapping the supported extensions/media types and the size cap. Suggested: `_SUPPORTED_ATTACHMENT_EXTS = {"xlsx", "docx", "pdf", "csv", "txt", "pptx"}` and `_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024`. (Image media types are explicitly NOT in this set — they go through captioning.)
  - [ ] In Bob's Phase-2 page loop ([bob.py:1118-1199](src/ai_qa/agents/bob.py:1118)), after the page's listing is available, build the per-page record: for each listed attachment classify as `selected` / `skipped_unsupported` / `skipped_oversized`. Note: `confluence_list_attachments` may not return a size — if size is absent, do not over-engineer; download then enforce the cap on the decoded byte length and reclassify as `skipped_oversized` if exceeded (discard the bytes).
  - [ ] For each `selected` attachment: download via `confluence_download_attachment` (reuse the exact `try/except` + base64-decode shape from [bob.py:1099-1116](src/ai_qa/agents/bob.py:1099)); on success persist via `adapter.save_attachment(...)` and record status `downloaded` + the bytes/media type for 17.2/17.3; on any exception record `failed` and continue (AC6).
  - [ ] Surface the per-page record on the page dict in `self.pages` (e.g. a new `"attachments": [...]` key) so 17.3 (merge) and 17.4 (surface) can read it without re-discovering. Do NOT yet parse or merge — that is 17.2/17.3.

- [ ] **Task 5 — Jira best-effort discovery (AC: 5, 6)**
  - [ ] In `_retrieve_jira_requirements` ([bob.py:497-554](src/ai_qa/agents/bob.py:497)), after a Jira issue is retrieved, probe the connected client for a Jira attachment list/download tool. Use the connected `MCPClient` discovery (`list_tools()` / `discover_capabilities()` / `check_required_tools`) rather than assuming a name — the MCP server may or may not expose `jira_download_attachment`-style tools (unconfirmed in this codebase).
  - [ ] If present: discover + download + persist (`source_type="jira"`, `parent_source_id=issue.issue_key`) reusing the same supported-type/size policy and `save_attachment`. If absent: emit a `warning` chat message and skip — never fail the Jira step (it is already wrapped best-effort and must stay non-fatal, AC6).
  - [ ] Attach the Jira attachment record to the Jira page dict appended at [bob.py:534-544](src/ai_qa/agents/bob.py:534).

- [ ] **Task 6 — Tests (all ACs)**
  - [ ] Storage: `build_artifact_key` + `folder_for_kind` route `"attachment"` correctly; `ARTIFACT_KINDS` accepts it (extend `tests/` for `artifacts/storage` + `service` validation).
  - [ ] Adapter: `save_attachment` persists bytes with the right kind/name/title/provenance (mock storage; assert the `save_artifact` call args).
  - [ ] Discovery/filter: given a stubbed `confluence_list_attachments` response, the record classifies xlsx/docx/pdf/csv/txt/pptx as selected, an unsupported type as `skipped_unsupported`, an oversized file as `skipped_oversized`, and a failing download as `failed` — without raising. Mock the MCP client's `call_tool` (return the known `{"attachments": [...]}` / `{"base64": ..., "mediaType": ...}` shapes).
  - [ ] Shared-listing: assert `confluence_list_attachments` is called **once** per page even when both an image and a document attachment are present (anti-duplication regression).
  - [ ] Jira: tool-absent → graceful skip warning + no failure; tool-present (stubbed) → downloads + persists.
  - [ ] `uv run pytest` (backend). No migration in this story (the new kind is a string value, not a schema change).

## Dev Notes

### The key discovery: the MCP attachment tools already work in this codebase

Bob ALREADY uses `confluence_list_attachments` and `confluence_download_attachment` — for image captioning, not document reading ([bob.py:1070-1116](src/ai_qa/agents/bob.py:1070)). The response shapes are therefore **known and proven**:

- `confluence_list_attachments` → `{"attachments": [{"title": <filename>, "id": <attachment_id>, "mediaType": <mime>}, ...]}`
- `confluence_download_attachment` → `{"base64": "<...>", "mediaType": "<mime>"}`

Reuse them. Always go through `reader._get_tool_name("...")` so the configured `mcp_tool_prefix` is applied ([config.py](src/ai_qa/config.py) `mcp_tool_prefix`; readers call `_get_tool_name`), and always include the `audit = {"userPrompt", "llmReasoning"}` fields the existing calls pass ([bob.py:1063-1068](src/ai_qa/agents/bob.py:1063)).

### Current behavior to PRESERVE (regression guardrails)

- **Image captioning must keep working unchanged.** `fetch_image_via_mcp` resolves `<img src>` → bytes via the same list/download tools. When you extract the shared lister (Task 3), the image path must behave byte-for-byte as before — it is on the critical requirement-fidelity path.
- **Each page listed once.** Don't add a second `confluence_list_attachments` call per page; share the cache (AC1, Task 3).
- **Best-effort, never fatal.** Both the image fetch and the whole Jira step already degrade gracefully (`try/except → warning → continue`). Attachment discovery/download must follow the same contract — a bad attachment never breaks a page; a missing Jira tool never breaks the run (AC6).
- **No-secret-leak convention.** The MCP credential is resolved at runtime; never log tokens, request dicts, or full headers — log `.keys()`/safe fields only ([[project-context]]). Attachment filenames/ids are safe to log.
- **Secrets stay out of artifacts.** Persisted attachment bytes are the user's source documents (not secrets) — but never write the MCP/Confluence credential into any artifact or message.

### Source tree components to touch

- `src/ai_qa/artifacts/service.py` — **UPDATE** (`ARTIFACT_KINDS` add `"attachment"`).
- `src/ai_qa/artifacts/storage.py` — **UPDATE** (`build_artifact_key` + `folder_for_kind` route `"attachment"`).
- `src/ai_qa/pipelines/artifact_adapter.py` — **UPDATE** (new `save_attachment`, mirror `save_image` at line 365).
- `src/ai_qa/agents/bob.py` — **UPDATE** (extract shared lister; Confluence discover/download/persist in the Phase-2 loop; Jira best-effort in `_retrieve_jira_requirements`; supported-type policy constants).
- Tests — **ADD/UPDATE** under `tests/` for storage classifiers, adapter, and Bob discovery (mock MCP `call_tool`).

### Decided scope (Thuong, 2026-06-22)

- **Persist bytes** as a raw companion (new `attachment` kind) — chosen over parse-in-memory-only, for audit trail + so 17.4 can reference the file.
- **Jira best-effort** — include Jira, but only if the MCP server exposes the tools; degrade gracefully otherwise.
- **Supported types** = `xlsx, docx, pdf, csv, txt, pptx`; per-file cap ~10 MB; others/oversized → skipped+logged. (csv/txt are trivial in 17.2; pptx adds `python-pptx` there.)

### Testing standards summary

- Backend pytest; mock the MCP client at `client.call_tool` (return the known dict shapes). No live MCP server.
- No bare `pytest.raises(Exception)` — specific type + `match=`.
- For Pyrefly/mypy cleanliness when mocking, follow the assert-then-access pattern for `call_args`/optional layers ([[project-context]] Pyrefly-clean patterns).

### Project Structure Notes

- Backend-only. No Alembic migration (the new artifact kind is a string in a `frozenset`, not a column). No new dependency in THIS story — parsing libs land in 17.2.

### References

- Epic + story: [epics.md#Epic-17](_bmad-output/planning-artifacts/epics.md:2022), [Story 17.1](_bmad-output/planning-artifacts/epics.md:2030)
- Existing attachment tool usage (the precedent): [bob.py:1070-1116](src/ai_qa/agents/bob.py:1070)
- MCP client: [src/ai_qa/mcp/client.py](src/ai_qa/mcp/client.py) (`call_tool`, `list_tools`, `discover_capabilities`, `check_required_tools`)
- Jira best-effort precedent: [bob.py:497-554](src/ai_qa/agents/bob.py:497), `JiraReader.check_tool_availability`
- Artifact storage: [storage.py:12](src/ai_qa/artifacts/storage.py:12) (`build_artifact_key`), [storage.py:41](src/ai_qa/artifacts/storage.py:41) (`folder_for_kind`), [service.py:17](src/ai_qa/artifacts/service.py:17) (`ARTIFACT_KINDS`), [service.py:79](src/ai_qa/artifacts/service.py:79) (`save_artifact`), [artifact_adapter.py:365](src/ai_qa/pipelines/artifact_adapter.py:365) (`save_image`)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[bob-clarify-loop]], [[artifact-ui-storage-overhaul]], [[epic-11-retro-mcp-extraction-quality]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
