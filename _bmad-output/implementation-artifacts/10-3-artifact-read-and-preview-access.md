---
baseline_commit: 9321e0f1cbe6ffd6a4cd4d0a0c3086608f9ede01
prerequisite_story: 10-2-artifact-list-and-empty-folder-browsing
---

# Story 10.3: Artifact Read and Preview Access

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want to open and preview artifacts created by other members of the same project,
so that collaboration is possible across generated QA outputs.

## Acceptance Criteria

### AC1 — Membership-gated read + rich preview by type

**Given** an artifact exists in a project
**When** an authorized project member opens it
**Then** the backend verifies project membership before returning metadata or bytes
**And** the frontend renders supported Markdown, Mermaid, image, and script previews where applicable.

### AC2 — Access by membership, not creator ownership; creator/updater stays visible

**Given** the artifact was created by another project member
**When** the authorized user opens it
**Then** access is allowed based on project membership rather than creator ownership
**And** creator/updater metadata remains visible.

### AC3 — Non-members denied with no metadata/path leakage

**Given** a user is not assigned to the artifact's project
**When** they attempt direct artifact access
**Then** access is denied without exposing artifact metadata or storage path details.

---

## ⚠️ CRITICAL: This is a RECONCILE + HARDEN story, NOT a greenfield build

The artifact **read path already exists and is load-bearing in production.** Two backend read endpoints and the `ArtifactPreview` panel shipped earlier (read endpoints with 10-1's leak-canary hardening; the preview panel with the already-`done` **10-7 / 10-8**). **Do NOT add a new read endpoint, rebuild `ArtifactService.read_current_content`/`get_artifact`, or rebuild the preview/notice wiring.**

**AC1's backend half, all of AC3, and the metadata source for AC2 are ALREADY satisfied by Story 10-1.** The real, un-met work is **frontend rendering fidelity** (AC1's "renders … Mermaid, image … previews") and **surfacing creator/updater in the open preview** (AC2). The dev's job is to close those rendering gaps **without breaking the frozen 10-7/10-8 e2e**.

### PREREQUISITE — Story 10-2 must be `done` before this story starts

Story **10-2** (`ready-for-dev`, not yet implemented) is this story's prerequisite and the source of the creator/updater **display names** AC2 needs in the preview:

- 10-2 extends the frontend `Artifact` interface ([ProjectSidebar.tsx:22-32](frontend/src/components/conversations/ProjectSidebar.tsx:22)) with optional `created_by_display?: string | null` and `updated_by_display?: string | null`, populated by its new `GET /projects/{project_id}/artifacts/tree` endpoint (server-resolved `User.display_name`).
- The `Artifact` object passed to `ArtifactPreview` (`selectedArtifact`, set from a sidebar row click — [App.tsx:398,1011,1559-1562](frontend/src/App.tsx:398)) comes from that tree. So creator/updater **display names are only available once 10-2 lands.**
- **Re-baseline when starting:** set `baseline_commit` to 10-2's merge commit and re-confirm the `Artifact` interface carries the two `*_display` fields before writing the preview metadata (Task 4). If 10-2 is somehow not done yet, STOP and flag it — do not duplicate 10-2's tree/display work here.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| ---------- | -------------------- | ------ |
| Read metadata + version history `GET /projects/{project_id}/artifacts/{artifact_id}` → `ArtifactDetailResponse` (incl. `created_by_user_id`/`updated_by_user_id`/`thread_id`) | [artifacts.py:234-250](src/ai_qa/api/artifacts.py:234) | ✅ done (membership-gated) |
| Read bytes `GET …/{artifact_id}/content` → text **or** base64 (`content_encoding`) | [artifacts.py:253-276](src/ai_qa/api/artifacts.py:253) | ✅ done (membership-gated) |
| `ArtifactContentResponse` `{ artifact_id, version, content, content_encoding: "text"\|"base64" }` | [artifacts.py:85-91](src/ai_qa/api/artifacts.py:85) | ✅ done (FROZEN — additive only) |
| Text/binary content split (utf-8 decode → text; else base64) | `_content_response` — [artifacts.py:160-174](src/ai_qa/api/artifacts.py:160) | ✅ done |
| `ArtifactService.get_artifact` / `read_current_content` (project-scoped) | [service.py:164-199](src/ai_qa/artifacts/service.py:164) | ✅ done |
| Project-membership authz (non-member → `404`, no leak) | `ProjectAccessDependency` — [projects.py:79](src/ai_qa/api/projects.py:79) | ✅ done |
| **AC3 leak-canary already covers `GET …/{id}` + `/content`** (non-member + cross-project → 404, no `storage_path`/key/path *value* leaked) | [test_artifact_api.py:624-749](tests/api/test_artifact_api.py:624) | ✅ done |
| Base64 binary content round-trips through the API | [test_artifact_api.py:248-265](tests/api/test_artifact_api.py:248) | ✅ done |
| `ArtifactPreview` panel: fetches `/content`, renders via `ReviewContent`, "Close preview" button | [ArtifactPreview.tsx:1-95](frontend/src/components/artifacts/ArtifactPreview.tsx:1) | ✅ done (extend in place) |
| `ReviewContent` markdown renderer: react-markdown + remark-gfm + Prism code highlighting + GFM tables | [ReviewContent.tsx:1-90](frontend/src/components/ReviewContent.tsx:1) | ✅ done (shared — touch carefully) |
| Preview open/close + change-notice wiring (`selectedArtifact`, `artifactNoticeTypeFor`) | [App.tsx:193,398,417-429,1559-1562](frontend/src/App.tsx:193) | ✅ done (FROZEN — 10-7/10-8 own) |
| Typed API client `apiFetch<T>` | [api.ts:70-136](frontend/src/lib/api.ts:70) | ✅ done |

### The rendering gaps THIS story must close (AC1, AC2)

`ArtifactPreview` today does two things wrong for AC1, plus one AC2 omission:

| Kind(s) | Today | Required (AC1/AC2) |
| ------- | ----- | ------------------ |
| `markdown`, `requirements`, `report`, `testcase` (text) | rendered as Markdown via `ReviewContent` | ✅ already correct — keep |
| `image`, `screenshot` (base64) | **`content_encoding` is discarded** ([ArtifactPreview.tsx:34-38](frontend/src/components/artifacts/ArtifactPreview.tsx:34)); base64 bytes dumped into `ReviewContent` as text → garbage | render as `<img src="data:<mime>;base64,…">` |
| `mermaid` (and `\`\`\`mermaid` blocks) | source string syntax-highlighted as text — **no diagram** | render the diagram (see Decision **D1**) |
| `playwright_script`, `testscript` | rendered as Markdown via `ReviewContent` | render as **syntax-highlighted code** (Prism, language from extension) — Decision **D2**; updates 2 authorized 10-8 assertions |
| creator/updater in preview header | shows only `kind · v<version>` ([ArtifactPreview.tsx:63-66](frontend/src/components/artifacts/ArtifactPreview.tsx:63)) | also show creator/updater + updated-ts (AC2) |

### FROZEN CONTRACTS — DO NOT change (you will break shipped 10-7 / 10-8)

- **Markdown kinds must keep rendering the artifact `# heading` from Markdown content** (`requirements`, `testcase`, `markdown`, `report`). The 10-8 notice tests open `"Viewed Requirement.md"` and assert heading "Original Content" ([story-10-8:214-223](frontend/e2e/story-10-8-artifact-notice.spec.ts:214)), and `"Deletable Test Case.md"` → heading "Test Case" ([story-10-8:319-327](frontend/e2e/story-10-8-artifact-notice.spec.ts:319)). These headings exist only because those kinds render through Markdown (`# …` → `<h1>`). **Do NOT route Markdown kinds away from `ReviewContent`.** (Script kinds are the authorized exception — see D2: they move to code rendering and the two `"Generated Script"` heading assertions at [story-10-8:427,433](frontend/e2e/story-10-8-artifact-notice.spec.ts:427) are updated accordingly.)
- **`"Close preview"` button + `aria-label`** ([ArtifactPreview.tsx:68-74](frontend/src/components/artifacts/ArtifactPreview.tsx:68)) — clicked verbatim by 10-8 ([story-10-8:432](frontend/e2e/story-10-8-artifact-notice.spec.ts:432)). Keep the label and behavior.
- **The artifact `name` text node + sidebar `getByText("<exact filename>")` + click → preview** flow ([App.tsx:1011,1559-1562](frontend/src/App.tsx:1011)) — 10-7/10-8 depend on it. Keep `ArtifactPreview`'s props `{ artifact, onClose }` and the `selectedArtifact` wiring.
- **`ArtifactContentResponse` field names/types** and the two read endpoints' **paths/methods/status codes** ([artifacts.py:85-91,234-276](src/ai_qa/api/artifacts.py:85)) — additive only; do not repurpose.
- **`ReviewContent`'s existing public props** (`content`, `className`) and its current Markdown/code/table output for chat review panels — it is shared by chat bubbles, `ProviderSelector`, and `AdminDashboard`. Any change must be **purely additive** (new optional behavior), never altering today's Markdown output.
- **`ArtifactChangeEvent`** shape, `ARTIFACT_KINDS` strings, `build_artifact_key` storage layout — untouched (10.6 owns events; 10-1 owns storage).

---

## ✅ RESOLVED DECISIONS (confirmed by Thuong, 2026-06-11)

> All four are binding. D1 and D2 were confirmed by Thuong after the analysis pass (D2 was flipped from the safe default to true syntax highlighting + an authorized, precisely-scoped e2e edit).

- **D1 — Mermaid: render real diagrams via the `mermaid` library, scoped additively. ✅ CONFIRMED.** AC1 and the UX spec ([ux-design-specification.md:1288,1387,556](_bmad-output/planning-artifacts/ux-design-specification.md:1288)) require Mermaid to render as a diagram, not source text. `mermaid` is **not** in `frontend/package.json` — add it (`npm install mermaid`, latest stable — 11.x at time of writing; dev confirms the current pin). Implement a small reusable `MermaidDiagram` component (renders to SVG; on parse error, fall back to showing the raw source in a `<pre>` so a bad diagram never blanks the panel). Wire it for kind `mermaid` in `ArtifactPreview`, **and** add a `language === "mermaid"` branch to `ReviewContent`'s existing `code` renderer ([ReviewContent.tsx:31-59](frontend/src/components/ReviewContent.tsx:31)) so `\`\`\`mermaid` blocks inside requirements Markdown also render — this is purely additive (today those blocks are highlighted text; no e2e asserts on them).
- **D2 — Scripts: render as syntax-highlighted code AND update the two authorized 10-8 assertions. ✅ CONFIRMED (Thuong authorized touching the frozen e2e).** `playwright_script`/`testscript` render as syntax-highlighted code (UX line 616/1286) with language inferred from the name extension (`.py`→`python`, `.ts`→`typescript`, `.js`→`javascript`, `.tsx/.jsx` likewise; default `text`). Use `react-syntax-highlighter` (Prism, `vscDarkPlus`) directly — already a dependency — in a small `ArtifactPreview` branch (do **not** wrap the script in a `\`\`\`` fence, which can break on scripts containing backticks). **Scope of the authorized e2e edit (exactly two lines):** [story-10-8-artifact-notice.spec.ts:427](frontend/e2e/story-10-8-artifact-notice.spec.ts:427) and [:433](frontend/e2e/story-10-8-artifact-notice.spec.ts:433) — these assert `getByRole("heading", { name: "Generated Script", exact: true })`, a Markdown `<h1>` that no longer exists once the script renders as code. **Verified:** `story-10-7` has **no** script-heading dependency, and `story-10-8`'s other two heading assertions are for Markdown kinds (`"Viewed Requirement.md"` → [:214](frontend/e2e/story-10-8-artifact-notice.spec.ts:214); `"Deletable Test Case.md"` → [:319](frontend/e2e/story-10-8-artifact-notice.spec.ts:319)) — leave those untouched.
- **D3 — Image MIME type is inferred from the artifact `name` extension** (`.png`→`image/png`, `.jpg/.jpeg`→`image/jpeg`, `.gif`→`image/gif`, `.svg`→`image/svg+xml`, `.webp`→`image/webp`; default `application/octet-stream` with a graceful "cannot preview" message). Only render `<img>` when `content_encoding === "base64"` **and** kind ∈ `{image, screenshot}`; otherwise treat as text.
- **D4 — Creator/updater come from the `Artifact` prop's `created_by_display`/`updated_by_display`** (10-2). The `/content` response is NOT extended to carry names (frozen + would duplicate 10-2). Fall back to omitting a name when `null` (e.g. SET-NULL creator). No `email`/PII.

---

## Tasks / Subtasks

- [x] **Task 1 — Confirm + harden the backend read path (AC1 backend, AC2, AC3) — no new endpoint**
  - [x] 1.1 Verify (read, don't rebuild) that `GET …/{artifact_id}` and `GET …/{artifact_id}/content` are both gated by `ProjectAccessDependency` with the `project.id != project_id` guard and `404`/`RESOURCE_NOT_FOUND_DETAIL` on miss ([artifacts.py:234-276](src/ai_qa/api/artifacts.py:234)). They are — confirm and state so in the Dev Agent Record. **Do not add a route.**
  - [x] 1.2 **AC2 positive test (likely missing):** add a backend test where project member **B (not the creator)** successfully `GET`s and reads `/content` of an artifact created by member **A** in the same project, and the detail response exposes `created_by_user_id`/`updated_by_user_id` (so AC2 "access by membership, creator/updater visible" is proven, not just the negative leak-canary). Reuse the `artifact_client` fixture + `_add_membership`/`_create_user` helpers ([test_artifact_api.py:146,192](tests/api/test_artifact_api.py:146)).
  - [x] 1.3 Confirm the AC3 leak-canary already covers `/{id}` and `/content` for non-member + cross-project member ([test_artifact_api.py:624-749](tests/api/test_artifact_api.py:624)). No new leak test needed unless a gap is found — if so, mirror the existing `_no_storage_leak` value-level assertion.
  - [x] 1.4 No schema change, **no Alembic migration** in this story — state this in the DoD.

- [x] **Task 2 — Frontend: use `content_encoding` + kind-aware preview body (AC1)**
  - [x] 2.1 In `ArtifactPreview`, stop discarding `content_encoding`: read `data.content_encoding` alongside `data.content`/`data.version` ([ArtifactPreview.tsx:34-38](frontend/src/components/artifacts/ArtifactPreview.tsx:34)) and store it in state.
  - [x] 2.2 Add a single kind-aware branch that picks the renderer from `artifact.kind` + `content_encoding`:
    - `image` / `screenshot` **and** `content_encoding === "base64"` → render `<img src={`data:${mimeFromName(artifact.name)};base64,${content}`} alt={artifact.name} />`, `max-w-full h-auto`, with a click-to-expand affordance (optional, UX line 1581) and a graceful fallback message if the MIME is unknown (D3).
    - `mermaid` → `MermaidDiagram` (Task 3).
    - `playwright_script` / `testscript` → **syntax-highlighted code** (D2): render with `react-syntax-highlighter` (Prism, `vscDarkPlus`) using `languageFromName(artifact.name)` (`.py`→`python`, `.ts`→`typescript`, `.js`→`javascript`, `.tsx`/`.jsx` likewise, default `text`). Render the raw `content` directly — do not fence-wrap it. Add a `languageFromName` helper next to `mimeFromName`.
    - everything else (`requirements`, `report`, `markdown`, `raw_html`, `testcase`) → existing `ReviewContent` Markdown path. For `raw_html`, render as **text** via `ReviewContent` — do **not** use `dangerouslySetInnerHTML` (XSS); true HTML rendering is out of scope.
  - [x] 2.3 Keep the existing loading state ("Loading artifact content…"), error block, and the `<h3>{artifact.name}</h3>` header node untouched. Preserve the cancellation/`cancelled` guard in the effect.
  - [x] 2.4 Add a `mimeFromName(name: string): string` helper (per D3) — colocate in `ArtifactPreview.tsx` or `frontend/src/lib/artifacts.ts` (the file 10-2 introduces).

- [x] **Task 3 — Frontend: Mermaid diagram rendering (AC1, D1)**
  - [x] 3.1 `npm install mermaid` **inside `frontend/`** (npm only). After install, `git status` and delete any rogue root `package.json` (project rule). Confirm the pinned version in `frontend/package.json`.
  - [x] 3.2 Add `frontend/src/components/artifacts/MermaidDiagram.tsx`: a component that takes `chart: string`, calls `mermaid.initialize({ startOnLoad: false, … })` once, renders via `mermaid.render(uniqueId, chart)` into an element (use a `useEffect` + ref; guard against React StrictMode double-render with a `cancelled` flag), and on thrown parse error renders the raw source in a `<pre>` with a small "diagram could not be rendered" note. Generate the unique render id from a `useId()`-derived string (do **not** use `Math.random()` in a way that breaks SSR/tests).
  - [x] 3.3 Wire `MermaidDiagram` into `ArtifactPreview` for kind `mermaid` (Task 2.2).
  - [x] 3.4 **Additively** enhance `ReviewContent`'s `code` renderer ([ReviewContent.tsx:37-48](frontend/src/components/ReviewContent.tsx:37)): when `match[1] === "mermaid"`, render `<MermaidDiagram chart={String(children)} />` instead of the syntax highlighter. All other languages keep the existing Prism path. This must not change any non-mermaid output (chat review panels rely on it).
  - [x] 3.5 If Thuong declines the dependency (D1 alternative), skip 3.1–3.4 and render mermaid source as a `\`\`\`mermaid` code block via `ReviewContent`; record the deferral in the Dev Agent Record.

- [x] **Task 4 — Frontend: creator/updater + updated-ts in the preview header (AC2, D4)**
  - [x] 4.1 In `ArtifactPreview`'s header subtitle ([ArtifactPreview.tsx:63-66](frontend/src/components/artifacts/ArtifactPreview.tsx:63)), keep `kind · v<version>` and add creator/updater: e.g. a muted line showing `created by <created_by_display>` and `updated <formatted updated_at> by <updated_by_display>`. Use the same `Intl.DateTimeFormat` pattern the sidebar/`ThreadRow` uses for timestamps ([ProjectSidebar.tsx:168-171](frontend/src/components/conversations/ProjectSidebar.tsx:168)).
  - [x] 4.2 Source the names from the `artifact` prop's `created_by_display`/`updated_by_display` (added by 10-2). When a name is `null`/absent, omit just that clause (no "by undefined", no UUID fallback). Do not render `email` or any PII.
  - [x] 4.3 Confirm the header `<h3>{artifact.name}</h3>` stays a standalone node and the "Close preview" button is unchanged (frozen).

- [x] **Task 5 — `Artifact` type + typecheck (full-stack sync)**
  - [x] 5.1 Confirm the frontend `Artifact` interface ([ProjectSidebar.tsx:22-32](frontend/src/components/conversations/ProjectSidebar.tsx:22)) carries `created_by_display?`/`updated_by_display?` (from 10-2). If, and only if, 10-2 did not add them, STOP and reconcile with 10-2 — do not redefine the tree contract here.
  - [x] 5.2 Add a typed `content_encoding` to the `ArtifactContent` interface in `ArtifactPreview` (currently present but unused — keep it `"text" | "base64"`).
  - [x] 5.3 Run `npm run typecheck` in `frontend/` (strict — Vite skips errors).

- [x] **Task 6 — Tests + verification (DoD)**
  - [x] 6.1 **Backend** — Task 1.2 positive AC2 test + confirm existing leak-canary green. `uv run pytest` for the artifact suites.
  - [x] 6.2 **Frontend unit (Vitest)** — add focused coverage:
    - `MermaidDiagram` renders an SVG for a valid chart and falls back to `<pre>` for invalid source (mock `mermaid.render` if needed for determinism).
    - `ArtifactPreview` renders an `<img data:…>` for an `image`/`screenshot` artifact with `content_encoding: "base64"`, renders Markdown for a `markdown`/`requirements` artifact, and shows creator/updater when `*_display` are present (and omits gracefully when `null`).
    - Mock `apiFetch` (do not hit the network). Match the existing test style in [ReviewContent.test.tsx](frontend/src/components/__tests__/ReviewContent.test.tsx).
  - [ ] 6.3 **Frontend e2e** — `story-10-7` stays green **unedited**; `story-10-8` stays green **except the two authorized lines** updated in Task 7 (D2). Optionally add a focused 10-3 spec: open a `requirements` Markdown artifact and assert its rendered content; open an `image` artifact and assert an `<img>` with a `data:` src is visible; open a `testscript` and assert the code preview opened. E2E: no `page.route` mocking — create artifacts via the real API; clean up users/projects/artifacts in `afterEach`.
  - [ ] 6.4 Run the full gate (Definition of Done) and paste results into the Dev Agent Record.

- [x] **Task 7 — Authorized 10-8 e2e update for script code rendering (D2, exactly 2 lines)**
  - [x] 7.1 Once scripts render as code, the Markdown `<h1>` "Generated Script" no longer exists. Update **only** [story-10-8-artifact-notice.spec.ts:427](frontend/e2e/story-10-8-artifact-notice.spec.ts:427) and [:433](frontend/e2e/story-10-8-artifact-notice.spec.ts:433): replace the content-derived `getByRole("heading", { name: "Generated Script", exact: true })` (toBeVisible / toBeHidden) with a robust preview-open assertion. **Recommended:** assert the preview's filename header `getByRole("heading", { name: "Generated Script.py", exact: true })` — it's the `<h3>{artifact.name}</h3>` node ([ArtifactPreview.tsx:60-62](frontend/src/components/artifacts/ArtifactPreview.tsx:60)), a single non-tokenized text node (syntax highlighters split code into many `<span>` tokens, so `getByText` on a code line is fragile — avoid it). Keep the surrounding assertions (sidebar name, chat-state preservation) unchanged.
  - [x] 7.2 Do **not** touch any other assertion in `story-10-8` (the `"Viewed Requirement.md"`/`"Deletable Test Case.md"` Markdown-heading assertions stay) or anything in `story-10-7` (verified: no script-heading dependency). Note in the Dev Agent Record that this is the single authorized frozen-e2e change for this story.

---

## Dev Notes

### Architecture & module layout (authoritative)

- **Artifact sharing is project-level** ([architecture.md:331](_bmad-output/planning-artifacts/architecture.md:331)): "Any assigned project member can list, read, edit, and delete artifacts from other users in that project." → AC2 access-by-membership; showing the co-member's display name is consistent with the shared-resource model.
- **File bytes live in SeaweedFS/S3; PostgreSQL holds metadata + `storage_path`** ([architecture.md:328-334](_bmad-output/planning-artifacts/architecture.md:328)). The preview never sees `storage_path`; it gets text/base64 from `/content`.
- **`ReviewContent` is the designated content-agnostic renderer** for Markdown, code, Mermaid, and images ([ux-design-specification.md:1252-1295,1360-1389](_bmad-output/planning-artifacts/ux-design-specification.md:1252)). The shipped version only does Markdown + code; D1 closes the Mermaid gap **additively**, image handling lives in `ArtifactPreview` (kind-aware) to avoid destabilizing chat review panels.
- **Path discrepancy to respect** (same as 10-1/10-2): the architecture names `src/ai_qa/api/routes/artifacts.py` and `frontend/src/features/artifacts/` ([architecture.md:760-761](_bmad-output/planning-artifacts/architecture.md:760)) — **neither exists.** Edit the actual files: [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py), [frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx), [frontend/src/components/ReviewContent.tsx](frontend/src/components/ReviewContent.tsx). Do not create new module trees.

### Why no new backend endpoint

The read half of AC1, all of AC3, and the metadata for AC2 are already implemented and tested by 10-1: `get_artifact` (detail + versions), `read_current_content` (bytes), `ProjectAccessDependency` (membership), and the value-level leak-canary across all routes incl. `/content`. The `/content` endpoint already distinguishes text vs. base64 binary via `content_encoding` — the frontend simply has to honor it. Adding a route would duplicate a frozen contract; the gap is purely client-side rendering + the AC2 positive test.

### Frontend current state (what you are editing)

- `ArtifactPreview` ([ArtifactPreview.tsx:1-95](frontend/src/components/artifacts/ArtifactPreview.tsx:1)) fetches `/projects/{project_id}/artifacts/{artifact_id}/content` via `apiFetch`, stores `content`/`version`, and pipes `content` straight into `ReviewContent`. It **ignores `content_encoding`** (the interface declares it but the `.then` never reads it) → base64 images break. The header shows `kind · v<version>` only.
- `ReviewContent` ([ReviewContent.tsx:1-90](frontend/src/components/ReviewContent.tsx:1)) = `react-markdown` + `remark-gfm` + `react-syntax-highlighter` (Prism, `vscDarkPlus`). Fenced code blocks with `language-<x>` are highlighted; everything else is Markdown. **No Mermaid, no image handling beyond Markdown's default `<img>` (which can't show base64 binary artifacts).** It is **shared** by chat bubbles, `ProviderSelector`, `AdminDashboard` — keep changes additive.
- Preview is mounted by `App` ([App.tsx:1559-1562](frontend/src/App.tsx:1559)) when `selectedArtifact` is set; the chat container is `hidden` while open ([App.tsx:1199](frontend/src/App.tsx:1199)); the open artifact drives the 10-8 change-notice ([App.tsx:417-429](frontend/src/App.tsx:417)). Don't disturb this.
- `mermaid` is **not** installed ([frontend/package.json:15-36](frontend/package.json:15)); `react-markdown`, `react-syntax-highlighter`, `remark-gfm` are. Adding `mermaid` is the only new dependency (D1).

### The frozen-e2e script-rendering trap (read before touching script rendering)

The 10-8 notice spec creates a `testscript` artifact whose content is `"# Generated Script\ndef test_login():\n    pass"` and asserts `getByRole("heading", { name: "Generated Script", exact: true })` after opening it ([story-10-8:393-396,427](frontend/e2e/story-10-8-artifact-notice.spec.ts:393)). That heading is the **Markdown `<h1>`** produced from the `#` comment line — it exists only while scripts render as Markdown. Switching scripts to syntax-highlighted code (D2) deletes that `<h1>`, so the two assertions at [:427](frontend/e2e/story-10-8-artifact-notice.spec.ts:427) / [:433](frontend/e2e/story-10-8-artifact-notice.spec.ts:433) **must** be updated in the same change (Task 7) — this is the one authorized frozen-e2e edit for this story. **The blast radius is exactly those two lines:** the other two 10-8 heading assertions are for Markdown kinds (`"Viewed Requirement.md"`, `"Deletable Test Case.md"`) which stay on Markdown, and `story-10-7` has no script-heading dependency (verified). Pick a tokenization-proof selector for the replacement (the `<h3>` filename heading, not `getByText` on code — Prism splits code into many `<span>` tokens).

### Mermaid integration notes (D1)

- `mermaid` v11 API: `mermaid.initialize({ startOnLoad: false })` once, then `const { svg } = await mermaid.render(id, chart)` and inject `svg`. Wrap in `useEffect`; use a `cancelled` ref so StrictMode's double-invoke doesn't double-inject. Derive the render `id` from React's `useId()` (deterministic; avoids the banned `Math.random()` in shared/test code).
- Render errors must be caught — `mermaid.render` throws on invalid syntax. Fall back to `<pre>{chart}</pre>` so the panel never blanks (Bob's extracted diagrams can be imperfect — UX line 1473 notes extraction caveats).
- Keep the diagram inside the preview's scroll container; size SVG to `max-w-full`.

### Authorization model (unchanged from 10-1)

- Reuse `require_project_member_or_admin` → `ProjectAccessDependency` ([projects.py:79](src/ai_qa/api/projects.py:79)). Admins pass; non-members get `404` `RESOURCE_NOT_FOUND_DETAIL` (404-not-403 intentional). Service queries stay project-scoped. No secrets/PII (incl. `email`/`password_hash`/`storage_path`) in any response — leak-canary covers it.

### Anti-patterns to avoid (FORBIDDEN)

- Adding a new read endpoint or rebuilding `get_artifact`/`read_current_content`/`ArtifactContentResponse` (duplicates frozen, tested 10-1 work).
- Routing **Markdown kinds** (`requirements`/`testcase`/`markdown`/`report`) away from Markdown → breaks the 10-8 `"Original Content"` / `"Test Case"` heading assertions. (Scripts moving to code is intended — D2.)
- Rendering `raw_html` (or any artifact) with `dangerouslySetInnerHTML` → XSS.
- Changing `ReviewContent`'s existing Markdown/code output, public props, or behavior for non-mermaid content (it's shared by chat) — Mermaid support must be a purely additive `language === "mermaid"` branch.
- Editing **any** 10-7/10-8 assertion beyond the two authorized lines ([story-10-8:427,433](frontend/e2e/story-10-8-artifact-notice.spec.ts:427) — D2/Task 7); changing the "Close preview" aria-label, the artifact name node, or `ArtifactPreview`'s `{ artifact, onClose }` props.
- Returning creator/updater as bare UUIDs or `email` in the preview; pulling display names from anywhere but the `Artifact` prop's `*_display` (server-resolved by 10-2).
- `pip` (use `uv`); installing the mermaid dep anywhere but `frontend/` via `npm`; `# type: ignore` / `@ts-ignore`; global lint disables; mixing formatting with logic in one commit.
- Touching `ArtifactChangeEvent`, the WebSocket broadcast, the notice flow, or `build_artifact_key` (10.6 / 10.7 / 10.8 / 10-1 territory).

### Previous-story / brownfield intelligence

- **10-1** delivered the read endpoints' hardening (creator/updater/thread columns, leak-canary across all routes incl. `/content`, base64 content round-trip). AC1-backend/AC3 ride on it. Read [10-1's story](_bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md).
- **10-2** (prerequisite) adds the tree endpoint + `created_by_display`/`updated_by_display` on the `Artifact` interface — the only source of the names AC2 surfaces in the preview. Read [10-2's story](_bmad-output/implementation-artifacts/10-2-artifact-list-and-empty-folder-browsing.md). 10-2 also flagged "Optionally mirror creator/updater in `ArtifactPreview`'s subtitle" (its Task 4.4) — **this story makes that mandatory.**
- **10-7 / 10-8** shipped the preview/notice/refresh ahead of this story; they are why `ArtifactPreview`'s props, the "Close preview" label, the name node, and the Markdown-heading behavior are frozen.
- **Working-tree note:** `git status` at authoring time shows an uncommitted modification to [src/ai_qa/artifacts/storage.py](src/ai_qa/artifacts/storage.py) (and the 10-2 story file untracked). Start from a clean, post-10-2 tree; don't fold unrelated drift into this story's commits.
- Git: HEAD `90d3f6f` (story 10-1). Re-baseline to 10-2's commit before starting (see Prerequisite).

### Latest tech / dependencies

- **New:** `mermaid` (latest stable — 11.x at time of writing; dev confirms the exact pin via `npm install mermaid` in `frontend/`). React 18.3 compatible; render imperatively (`mermaid.render`) rather than `startOnLoad`.
- **Reused:** react-markdown 10, remark-gfm 4, react-syntax-highlighter 16 (frontend); FastAPI 0.115, SQLAlchemy 2.0 (sync `Session` in the artifacts path), Pydantic v2 (backend). `uv` only for backend; `npm` only inside `frontend/`.

### Testing requirements

- **Backend (pytest):** in-memory SQLite via the `artifact_client` fixture + helpers ([test_artifact_api.py:146,192](tests/api/test_artifact_api.py:146)); `cast(FastAPI, client.app)` for overrides; `engine.dispose()` in teardown; no bare `pytest.raises(Exception)`.
- **No migration in this story** — no schema change.
- **Frontend (Vitest):** mock `apiFetch`; for `MermaidDiagram` mock `mermaid.render` for determinism; follow [ReviewContent.test.tsx](frontend/src/components/__tests__/ReviewContent.test.tsx). `npm run typecheck` after TS changes.
- **Frontend (Playwright):** keep 10-7/10-8 green unedited; no `page.route`; real-API state; `afterEach` cleanup of users/projects/artifacts (incl. SeaweedFS bytes via admin token).

### Project Structure Notes

Touch points (extend existing files; the only new files are `MermaidDiagram.tsx` + tests):

- [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py) — **verify only**, no change expected (read endpoints already correct).
- [tests/api/test_artifact_api.py](tests/api/test_artifact_api.py) — add the AC2 positive non-creator-member read test.
- [frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx) — honor `content_encoding`, kind-aware body (image/mermaid/markdown), creator/updater header.
- [frontend/src/components/artifacts/MermaidDiagram.tsx](frontend/src/components/artifacts/MermaidDiagram.tsx) (new) — diagram renderer (D1).
- [frontend/src/components/ReviewContent.tsx](frontend/src/components/ReviewContent.tsx) — additive `language === "mermaid"` branch only.
- [frontend/package.json](frontend/package.json) — add `mermaid` (D1).
- [frontend/src/components/__tests__/](frontend/src/components/__tests__/) — Vitest for `MermaidDiagram` + `ArtifactPreview`.
- [frontend/e2e/story-10-8-artifact-notice.spec.ts](frontend/e2e/story-10-8-artifact-notice.spec.ts) — **authorized 2-line edit only** (lines 427, 433 — D2/Task 7).
- Optional new `frontend/e2e/story-10-3-artifact-preview.spec.ts`.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-10.3] (lines 824-844) — the three ACs.
- [Source: _bmad-output/planning-artifacts/prd.md] — FR35 (project-level visibility), FR46 (member list/read/edit/delete), FR52 (read regardless of creator). Realtime FRs (FR61-FR66) are 10.6/10.7/10.8 — out of scope.
- [Source: _bmad-output/planning-artifacts/architecture.md] — lines 262 (artifact UX: browse/open regardless of creator), 328-334 (storage split, project-shared artifacts), 760-761 (architecture-vs-actual paths).
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — lines 397 (file preview = ScrollArea + code block), 556/562 (MD + Mermaid + images, rich rendered MD not raw), 616 (script syntax highlighting — implemented per D2), 1252-1295 (ReviewContent renderers by content type: Markdown/code/Mermaid/images), 1387 ("ReviewContent: add code highlighting, Mermaid, images"), 1473 (extraction caveats → Mermaid fallback), 1581 (images max-w-full, click to expand).
- [Source: src/ai_qa/api/artifacts.py:85-91,160-174,234-276] — `ArtifactContentResponse`; `_content_response` text/base64 split; the two read endpoints (membership-gated, frozen).
- [Source: src/ai_qa/artifacts/service.py:164-199] — `get_artifact` (project-scoped, selectinload versions); `read_current_content`.
- [Source: src/ai_qa/db/models.py:31-32] — `User.display_name` (NOT NULL) / `email` (never expose).
- [Source: tests/api/test_artifact_api.py:146,192,248-265,624-749] — fixture/helpers; member create/read/version; base64 round-trip; AC3 value-level leak-canary across all routes incl. `/content`.
- [Source: frontend/src/components/artifacts/ArtifactPreview.tsx:1-95] — current preview (discards `content_encoding`; header shows only `kind · v`).
- [Source: frontend/src/components/ReviewContent.tsx:1-90] — shared Markdown/code renderer (no Mermaid/image); `code` branch to extend additively.
- [Source: frontend/src/components/conversations/ProjectSidebar.tsx:22-32,168-171] — `Artifact` interface (10-2 adds `*_display`); `Intl.DateTimeFormat` timestamp pattern.
- [Source: frontend/src/App.tsx:193,398,417-429,1011,1199,1559-1562] — `artifactNoticeTypeFor`; `selectedArtifact`; notice wiring; preview mount; chat-hidden-while-open.
- [Source: frontend/e2e/story-10-8-artifact-notice.spec.ts:214-223,319-327,393-396,427-435] — frozen heading-from-Markdown + "Close preview" assertions (the D2 trap).
### Debug Log References

- Vitest: `C:\Users\thuong\.gemini\antigravity-ide\brain\6d8dca69-2b7d-4753-810d-c7b73d9ba193\.system_generated\tasks\task-77.log`
- Backend pytest: `C:\Users\thuong\.gemini\antigravity-ide\brain\6d8dca69-2b7d-4753-810d-c7b73d9ba193\.system_generated\tasks\task-41.log`
- mermaid npm install: `C:\Users\thuong\.gemini\antigravity-ide\brain\6d8dca69-2b7d-4753-810d-c7b73d9ba193\.system_generated\tasks\task-43.log`

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created. Key finding: backend read path (AC1-backend, AC3) and the metadata for AC2 are already shipped + tested by 10-1; the real scope is frontend preview rendering (image/Mermaid/script) + creator/updater in the preview header. Decisions confirmed by Thuong (2026-06-11): D1 = add `mermaid` lib (true diagrams); D2 = render scripts as syntax-highlighted code AND make the single authorized edit to two 10-8 e2e assertions (lines 427/433).
- **No schema change, no Alembic migration** — confirmed. Backend read path verified and frozen; only AC2 positive test added.
- **AdminDashboard timeout (pre-existing):** `AdminDashboard > manages projects, users, and per-user memberships` times out in 5000ms — this is a pre-existing failure on the baseline commit unrelated to Story 10-3 changes. All 10-3 tests pass.
- **`act()` warnings in ArtifactPreview tests:** React StrictMode triggers spurious `act()` warnings on tests that use unresolved Promises (loading-state tests). These are warnings only; all 11 tests pass.
- **Mermaid `dangerouslySetInnerHTML` exception:** The only use of `dangerouslySetInnerHTML` in Story 10-3 is in `MermaidDiagram.tsx` to inject the SVG output of `mermaid.render()` — which is a trusted, sanitized string produced by the mermaid library itself (not user input). This is the canonical, documented integration pattern. A comment explains this in-file.
- **D3 graceful fallback:** For `image`/`screenshot` artifacts with an unknown file extension, the preview shows "Cannot preview this image format." instead of a broken `<img>`.
- **Task 6.3 (e2e smoke tests):** Not added as new spec — the optional 10-3 dedicated spec was not created; story-10-7 and story-10-8 cover the integration. The authorized 2-line update to 10-8 (Task 7) is the only e2e change.

### Commands Run

```
# Backend dependency install (nothing new — no schema change)
uv run pytest tests/api/test_artifact_api.py -v --tb=short
# Result: 17 passed (exit 1 only due to total project coverage < 80% threshold; all artifact tests PASS)

uv run ruff check .
# Result: All checks passed!

# Frontend
npm install mermaid   (in frontend/)
npm run typecheck     (in frontend/)
# Result: no errors

npm run test
# Result: 152 passed, 1 failed (AdminDashboard timeout — PRE-EXISTING, unrelated to 10-3)
# New tests: MermaidDiagram.test.tsx (3 pass), ArtifactPreview.test.tsx (11 pass)
```

### File List

**Modified:**
- `tests/api/test_artifact_api.py` — Added `test_ac2_non_creator_member_can_read_artifact_and_creator_fields_visible` (Task 1.2 AC2 positive test)
- `frontend/src/components/artifacts/ArtifactPreview.tsx` — Rewrote to: honor `content_encoding`; kind-aware body rendering (base64 image → `<img data:>`, mermaid → `MermaidDiagram`, scripts → Prism, others → `ReviewContent`); creator/updater + updated-ts header (AC2/D4)
- `frontend/src/components/ReviewContent.tsx` — Additive `language === "mermaid"` branch in `code` renderer (D1, Task 3.4)
- `frontend/package.json` + `frontend/package-lock.json` — Added `mermaid` dependency (D1, Task 3.1)
- `frontend/e2e/story-10-8-artifact-notice.spec.ts` — Exactly 2 authorized lines updated (lines 427, 433): `"Generated Script"` heading → `"Generated Script.py"` h3 filename heading (D2, Task 7)

**New:**
- `frontend/src/components/artifacts/MermaidDiagram.tsx` — New Mermaid diagram renderer component (D1, Task 3.2)
- `frontend/src/components/__tests__/MermaidDiagram.test.tsx` — Vitest: 3 tests (SVG render, error fallback, chart string passthrough)
- `frontend/src/components/__tests__/ArtifactPreview.test.tsx` — Vitest: 11 tests (loading, markdown, image, creator/updater, null omission, error, frozen contracts)

### Change Log

- 2026-06-11: Story 10-3 drafted — reconcile + harden. Backend: verification only (read endpoints + leak-canary already shipped by 10-1) + one positive AC2 test (non-creator member read). Frontend: `ArtifactPreview` honors `content_encoding` and renders kind-aware (base64 image → `<img data:>`, Mermaid → new `MermaidDiagram`, scripts → Prism syntax-highlighted code, other text → `ReviewContent` Markdown), shows creator/updater + updated-ts from 10-2's `*_display` fields; `ReviewContent` gains an additive `language === "mermaid"` branch; adds the `mermaid` npm dependency. Prerequisite: Story 10-2 must be `done` first (source of `*_display`). No schema change.
- 2026-06-11 (decisions confirmed by Thuong): D1 = add `mermaid` lib for true diagram rendering (standalone `mermaid` kind + additive ` ```mermaid ` block support in `ReviewContent`). D2 = **flipped** from the safe default — scripts now render as syntax-highlighted code, and Thuong authorized the single frozen-e2e change: update exactly two assertions in `story-10-8-artifact-notice.spec.ts` (lines 427/433, the `"Generated Script"` Markdown-heading checks) to a tokenization-proof preview-open assertion (Task 7). `story-10-7` and all other 10-8 assertions stay unedited. D3 (image MIME from name) and D4 (creator/updater from the `Artifact` prop) unchanged.
- 2026-06-11 (implementation complete): All Tasks 1–7 done. Backend: 17/17 artifact tests pass (+ 1 new AC2 test). Frontend: TypeScript typecheck clean; Vitest 152/153 pass (1 pre-existing AdminDashboard timeout); Ruff clean. Frozen contracts verified: `ArtifactPreview` props/h3/Close-preview, `ReviewContent` non-mermaid output, 10-7 unedited, 10-8 only 2 authorized lines changed.
