---
baseline_commit: 7d81929ca853824667ec3190090b728b18d545eb
---
# Story 17.4: Surface Which Attachments Were Read

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Mostly backend (+ tiny FE). Make attachment coverage **visible and trustworthy**: Bob posts a per-source chat summary (read / skipped-unsupported / skipped-oversized / failed) and persists a durable **attachment manifest** so the coverage survives a reload. The persisted attachment companions (17.1) and labeled prompt sections (17.3) already exist; this story is about *telling the user what happened* so they can verify source coverage. Keep the frozen 5-label sidebar intact ([[epic-10-artifact-ui-gotchas]]).

## Story

As a user,
I want to see which attachments Bob read (and which were skipped or unsupported),
so that I can trust and verify the source coverage of the extracted requirements.

## Acceptance Criteria

1. **Per-source chat summary.** Given Bob finishes processing a Confluence page or Jira issue that had attachments, when extraction completes, then Bob posts a concise chat message summarizing per source: which attachments were **read**, which were **skipped** (with reason: unsupported type / over size cap), and which **failed** — by filename. A source with zero attachments produces no attachment summary (no noise, AC ties to 17.3 AC7).

2. **Durable manifest.** Given attachments were discovered for a source, when the run completes, then a structured **attachment manifest** is persisted (per source) recording each attachment's filename, status (`read` / `skipped_unsupported` / `skipped_oversized` / `failed`), media type, and (for read) the stored companion's reference, so the coverage is available after the conversation reloads — not only in transient chat.

3. **Coverage reflects reality.** Given the manifest and chat summary, when compared with what 17.1 actually downloaded/persisted and 17.3 actually fed to the LLM, then the surfaced statuses match the real outcome (a "read" attachment is one whose parsed text was merged; a "failed" one was attempted but errored) — no attachment is reported read when it contributed nothing.

4. **Verifiable provenance in the requirement.** Given a requirement was generated using attachment content, when the user opens the requirement markdown, then it is possible to tell that attachments contributed (the labeled attachment sections from 17.3 carry through, and/or a short "Attachments read:" provenance line) so QA can cross-check against the source's real attachments.

5. **Sidebar stays frozen.** Given the existing requirements sidebar shows only `.md` results ([[artifact-ui-storage-overhaul]]), when this story surfaces attachment coverage, then it does **not** add a new top-level sidebar folder or unhide raw companions by default — surfacing is via the chat summary + manifest (+ optional provenance line). Any FE change is limited and English-only ([[app-ui-english-only]]).

## Tasks / Subtasks

- [ ] **Task 1 — Aggregate the per-source attachment outcome (AC: 1, 3)**
  - [ ] From the per-page/issue attachment record (17.1) plus the parse results (17.3), assemble a per-source summary object: `{source_id, source_url, read: [...], skipped_unsupported: [...], skipped_oversized: [...], failed: [...]}`. A "read" entry is one that was downloaded AND parsed to non-empty text AND merged (17.3); reconcile against 17.3's actual merge so AC3 holds.

- [ ] **Task 2 — Chat summary message (AC: 1)**
  - [ ] After the per-page conversions / Jira step, when a source had attachments, `send_message(...)` a concise English summary (counts + filenames per bucket). Place it with the existing post-extraction status/quality block (around [bob.py:1214-1234](src/ai_qa/agents/bob.py:1214)) so ordering reads naturally: extraction done → attachments read → quality findings. Keep it terse (don't dump full lists for huge sets — summarize counts + first N names).

- [ ] **Task 3 — Persist the manifest (AC: 2)**
  - [ ] Persist the per-source manifest as a `configuration` artifact sidecar via `adapter.save_metadata(name, dict)` ([artifact_adapter.py:303](src/ai_qa/pipelines/artifact_adapter.py:303)) — e.g. `name=f"{source_id}/attachments.manifest.json"`. (It browses under `reports` by default; if you want it to ride with the requirement, the `requirement.metadata` name convention routes `configuration` to `requirements` — decide and keep consistent with the existing metadata sidecar at [bob.py around save_metadata].) Reuse the existing metadata-sidecar mechanism — do NOT invent a new artifact kind.
  - [ ] Alternatively/additionally fold the attachment summary into the existing requirement metadata sidecar Bob already writes, so there is one provenance record per source. Pick ONE home for it and document the choice; don't write two divergent copies.

- [ ] **Task 4 — Provenance line in the requirement markdown (AC: 4) [optional-but-recommended]**
  - [ ] When attachments were read for a page, include a short, deterministic "Attachments read: a.xlsx, b.pdf" line in/near the requirement MD header (post-process after `convert_markdown`, do NOT ask the LLM to emit it — keep it deterministic and English). This must not break the `**Source:**`-link convention QA relies on.

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Summary aggregation: given a mixed attachment record (read/unsupported/oversized/failed), the per-source summary buckets correctly and a no-attachment source yields no summary (AC1/3).
  - [ ] Chat: Bob emits exactly one attachment summary message for a source with attachments, none for a source without (assert via the captured `send_message` calls / mock).
  - [ ] Manifest: the sidecar is persisted with the expected structure (assert `save_metadata` call args); survives independent of chat.
  - [ ] Provenance line (if implemented): appears only when attachments were read; absent otherwise; `**Source:**` link preserved.
  - [ ] FE (only if a UI change is made): typecheck + the relevant component test. If no FE change, note that explicitly.
  - [ ] `uv run pytest` (+ `npm run typecheck` / `npm test` only if FE touched).

## Dev Notes

### Surfacing strategy (keep it lightweight)

Attachments are already persisted (17.1) but hidden from the FE result tree (the sidebar filters to `.md` — [ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx) `isMarkdown`). The trustworthy-coverage signal therefore comes from (a) the chat summary, (b) the durable manifest sidecar, and (c) the optional provenance line in the requirement MD — NOT from unhiding raw companions or adding a sidebar folder. The frozen 5-label sidebar is a deliberate constraint ([[epic-10-artifact-ui-gotchas]]); do not expand it for this story.

If Thuong later wants downloadable attachments in the UI, that is a separate, larger FE story (new browse affordance + download endpoint) — explicitly out of scope here.

### Current behavior to PRESERVE (regression guardrails)

- **Sidebar frozen** — requirements folder shows only `.md`; raw companions stay hidden ([[artifact-ui-storage-overhaul]]).
- **Empty-content carrier gotcha** — chat bubbles with no text content can be dropped by the WS gate live but show on reload ([[message-timestamps-feature]]); make the attachment summary a real text message so it is not silently dropped.
- **English-only UI/messages** — the summary + provenance line are English ([[app-ui-english-only]]).
- **No new artifact kind** — reuse `configuration` sidecars (`save_metadata`); don't add a kind just for the manifest.
- **No-attachment sources unchanged** — no summary, no manifest, no provenance line (ties to 17.3 AC7).

### Dependencies on other stories

- **Requires 17.1** (the attachment record + statuses) and **17.3** (the actual merge outcome to reconcile "read" against). Build last in the epic.

### Source tree components to touch

- `src/ai_qa/agents/bob.py` — **UPDATE** (aggregate summary; emit chat message near the post-extraction block; persist manifest; optional provenance line on the requirement MD).
- `src/ai_qa/pipelines/artifact_adapter.py` — **REUSE** `save_metadata` ([artifact_adapter.py:303](src/ai_qa/pipelines/artifact_adapter.py:303)) (no new method needed unless you choose a dedicated manifest name).
- `frontend/` — **OPTIONAL/MINIMAL** (only if you choose to render the manifest; otherwise none).
- Tests — **ADD/UPDATE** Bob summary/manifest tests.

### Testing standards summary

- Backend pytest; capture `send_message`/`save_metadata` calls via mocks and assert content/args. No bare `pytest.raises(Exception)`. Pyrefly assert-then-access on mock `call_args` ([[project-context]]).

### Project Structure Notes

- Backend-only unless an FE manifest view is added; no migration, no new deps, no new artifact kind.

### References

- Epic + story: [epics.md#Epic-17](_bmad-output/planning-artifacts/epics.md:2022), [Story 17.4](_bmad-output/planning-artifacts/epics.md:2048)
- Post-extraction status/quality block (where the summary slots in): [bob.py:1214-1234](src/ai_qa/agents/bob.py:1214)
- Metadata sidecar mechanism: [artifact_adapter.py:303](src/ai_qa/pipelines/artifact_adapter.py:303) (`save_metadata`)
- Sidebar `.md` filter: [frontend/src/components/conversations/ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx) (`isMarkdown`, `renderRequirementsFolder`)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[artifact-ui-storage-overhaul]], [[epic-10-artifact-ui-gotchas]], [[message-timestamps-feature]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
