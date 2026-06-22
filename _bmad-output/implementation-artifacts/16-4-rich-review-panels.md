---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.4: Rich Review Panels

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Review panels are extensively built (Epics 10, 12, 13, 14). This is an **audit-and-consistency** story: verify the AC matrix against the live panels, standardise side-by-side + traceability where it is uneven, and confirm navigation is predictable and non-destructive. Do NOT rewrite working renderers.

## Story

As a QA user,
I want rich review panels for generated outputs and artifacts,
so that I can evaluate requirements, test cases, scripts, and reports efficiently.

## Acceptance Criteria

1. **All content kinds render.** Given reviewable content is available, when the user opens review mode, then the UI can render Markdown, Mermaid diagrams, code with syntax highlighting, images, and structured execution-report content.

2. **Side-by-side source vs generated + traceability.** Given source and generated content are linked, when a side-by-side review is opened, then the source content appears beside the generated output where applicable, and traceability metadata (source link) remains visible.

3. **Predictable, non-destructive navigation.** Given multiple review items exist, when the user navigates review items, then selection, review status, warnings, and scroll behavior remain predictable and non-destructive (no lost edits, no silent status changes).

## Tasks / Subtasks

- [ ] **Task 1 — Verify the content-kind render matrix (AC: 1)**
  - [ ] Confirm Markdown + GFM tables render via `ReviewContent` (react-markdown + remark-gfm) ([frontend/src/components/ReviewContent.tsx](frontend/src/components/ReviewContent.tsx)).
  - [ ] Confirm Mermaid renders with graceful fallback to a code block on error ([frontend/src/components/artifacts/MermaidDiagram.tsx](frontend/src/components/artifacts/MermaidDiagram.tsx)).
  - [ ] Confirm syntax-highlighted code (react-syntax-highlighter / Prism) for scripts and code blocks.
  - [ ] Confirm images/screenshots render via base64 `data:` URIs with a graceful "cannot preview" fallback ([frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx)).
  - [ ] Confirm structured execution-report rendering ([frontend/src/components/agents/JackExecutionReport.tsx](frontend/src/components/agents/JackExecutionReport.tsx) + [ExecutionResultDetail.tsx](frontend/src/components/agents/ExecutionResultDetail.tsx)).
  - [ ] Record any missing kind as a gap; the research found no missing kind for the project's content types (no PDF/video needed).

- [ ] **Task 2 — Verify side-by-side + traceability where applicable (AC: 2)**
  - [ ] Confirm `SarahScriptReviewPanel` left=source test case (with `source_url` ExternalLink) / right=generated script (Preview/Edit) ([frontend/src/components/agents/SarahScriptReviewPanel.tsx](frontend/src/components/agents/SarahScriptReviewPanel.tsx)).
  - [ ] Confirm `SplitPanel` left=raw HTML (sandboxed iframe) / right=markdown for Bob, with the source link visible ([frontend/src/components/SplitPanel.tsx](frontend/src/components/SplitPanel.tsx)).
  - [ ] For panels WITHOUT side-by-side (`MaryReviewPanel`, `BobRequirementReview`), confirm the source/traceability link (`source_url`) is still visible. "Where applicable" — do not force a split layout where there is no meaningful source pane; ensure traceability is present.

- [ ] **Task 3 — Verify predictable, non-destructive navigation (AC: 3)**
  - [ ] Confirm Prev/Next + per-item status (approved/skipped/pending), auto-advance to first unresolved, and that switching items does not silently discard unsaved edits (e.g. Sarah's edited-but-unsaved script — confirm the "● Unsaved changes" affordance and that navigation does not drop edits without signal).
  - [ ] Confirm warnings/validation banners persist with the item and scroll position is sane on item switch.
  - [ ] Fix only concrete non-destructive-navigation defects found here.

- [ ] **Task 4 — Tests (AC: 1, 2, 3)**
  - [ ] Extend existing panel tests (`SarahScriptReviewPanel.test.tsx`, `ReviewContent.test.tsx`, `ArtifactPreview.test.tsx`) to lock the render matrix + traceability link + non-destructive nav.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green.

## Dev Notes

### What already exists (do not rebuild)

- **`ReviewContent`** — react-markdown + remark-gfm; Mermaid via `language="mermaid"`; Prism code highlighting; styled tables. Handles null/empty gracefully.
- **`MermaidDiagram`** — lazy mermaid init, `useId()` render id, `securityLevel: "strict"`, fallback `<pre>` on error.
- **`ArtifactPreview`** — multi-kind: markdown→ReviewContent, code→Prism, mermaid→MermaidDiagram, images→base64 data URI; edit/delete for text kinds; error box.
- **`SarahScriptReviewPanel`** — side-by-side source test case (with `source_url`) / generated script (Preview/Edit tabs), per-script status strip, validation/warning banners, "● Unsaved changes", approval caption (color + text).
- **`SplitPanel`** — side-by-side sandboxed raw HTML / markdown for Bob requirement review, quality issues + warnings banners, source link.
- **`MaryReviewPanel`** — markdown test case + confidence badge + low-confidence banner.
- **`JackExecutionReport`** + **`ExecutionResultDetail`** — summary stats + per-test table + drilldown (linked artifacts, stack trace, screenshot, trace zip, log), all with "(not available)" graceful degradation.

### The work this story is

This is primarily verification + small consistency fixes. The render matrix (AC1) is complete. AC2's "where applicable" means: do not bolt a split layout onto panels that have no source pane; just ensure traceability links are present everywhere. AC3 is about confirming navigation never silently loses edits or changes status — the highest-risk spot is Sarah's edited-but-unsaved script when navigating away.

### Source tree components to touch

- All review panels above — **READ / VERIFY**; edit only on a proven AC2/AC3 defect.
- `frontend/src/components/conversations/ProjectSidebar.tsx` — **READ** (artifact selection feeds review). Note: the requirements **tree depth** is story [16-8](16-8-hierarchical-requirements-tree-mirroring-source-structure.md); do not change tree building here.
- Panel test files under `frontend/src/components/__tests__/` and `components/agents/__tests__/` — **UPDATE**.

### Current behavior to PRESERVE (regression guardrails)

- `SplitPanel` iframe `sandbox=""` (XSS-safe raw HTML) — never relax it.
- `MermaidDiagram` is the ONLY sanctioned `dangerouslySetInnerHTML` (trusted mermaid output) — do not add others.
- Skip-only failure placeholders (Sarah `error_message`) stay non-approvable ([[story-16-12-sarah-auth-bug]]).
- Frozen `getByText` artifact-label / `data-testid="thread-{id}"` contracts (10-7/10-8).
- Requirements sidebar shows only `.md` results (raw companions hidden) — do not re-list them ([[artifact-ui-storage-overhaul]]).
- App-UI-English-only ([[app-ui-english-only]]).

### Testing standards summary

- Vitest 4 + RTL; `SyntaxHighlighter` is mocked to a `<pre data-testid>` in tests — assert language + content via that. Mermaid is integration-tested (not mocked).
- Assert traceability via `getByRole('link')` to `source_url`.

### Project Structure Notes

- FE-only; no schema/migration; no new dependencies (react-markdown, remark-gfm, react-syntax-highlighter, mermaid, lucide-react already present).

### References

- Epic + ACs: [epics.md#Story-16.4](_bmad-output/planning-artifacts/epics.md:1767)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [16-8](16-8-hierarchical-requirements-tree-mirroring-source-structure.md), [[artifact-ui-storage-overhaul]], [[story-16-12-sarah-auth-bug]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
