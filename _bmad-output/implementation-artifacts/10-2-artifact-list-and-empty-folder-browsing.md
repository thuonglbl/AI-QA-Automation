---
baseline_commit: 90d3f6fbcaa0f5c86df52437f898308884cbc0e8
---

# Story 10.2: Artifact List and Empty Folder Browsing

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want to browse project artifact folders even when they are empty,
so that I understand the expected artifact structure before outputs exist.

## Acceptance Criteria

### AC1 — Required empty folders are always shown and marked empty

**Given** a PostgreSQL project exists but SeaweedFS has no objects for it
**When** an authorized project member opens the Project / Artifacts section
**Then** the UI shows the required empty folders: `requirements`, `test_cases`, and `test_scripts`
**And** each folder is clearly marked as empty.

### AC2 — Populated tree returns folders + entries with metadata, project-scoped

**Given** artifacts exist under one or more required folders
**When** the artifact tree is loaded
**Then** the API returns folders and artifact entries with names, types, updated timestamps, and creator/updater metadata
**And** entries are scoped only to the selected project.

### AC3 — Multi-project user sees only the thread's bound project artifacts

**Given** a user is assigned to multiple projects
**When** a thread has a bound project
**Then** the artifact tree shows only artifacts for the thread's selected project.

### AC4 — Chat always auto-scrolls to the newest message (added UX requirement)

**Given** the chat conversation is visible
**When** a new chat message arrives
**Then** the chat scroll container always scrolls to the bottom to reveal the newest message (even if the user had scrolled up)
**And** this auto-scroll does NOT fire on artifact-tree refresh — Story 10.7's "refresh must not reset scroll position" is preserved.

> Note: AC4 is an added chat-UX requirement bundled into this story by Thuong (2026-06-11). It is orthogonal to artifact browsing and touches `App.tsx`'s existing chat-scroll effect.

---

## ⚠️ CRITICAL: This is a RECONCILE + HARDEN story, NOT a greenfield build

The artifact-browsing UI **already physically exists and is load-bearing in production.** A 5-folder collapsible sidebar (`Conversations`, `Requirements`, `Test Cases`, `Scripts`, `Reports`) with an `Empty` marker, pagination, and artifact selection shipped with the already-`done` stories **10-7 (Realtime Artifact Refresh UX)** and **10-8 (Open Artifact Update/Delete Notice)**. Story **10-1 (Storage Foundation)** deliberately built the backend affordance this story consumes — `ArtifactService.required_folders()` ([service.py:201](src/ai_qa/artifacts/service.py:201)) — which is **currently unused.**

**Do NOT rebuild the sidebar, the flat list endpoint, `ArtifactService`, the kind→folder mapping, or the realtime wiring.** Your job is to **close two real gaps** without breaking the shipped contract:

1. The backend returns a **flat** artifact list, not the **folder-structured** response AC2 describes ("the API returns folders and artifact entries"), and it returns creator/updater only as **UUIDs** (no display names — see Q3 resolution).
2. The frontend groups artifacts by a **single raw kind per folder**, so it **silently drops sibling kinds** that belong in the same logical folder (`raw_html` → Requirements, `playwright_script` → Scripts). See the bug table below.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| ---------- | -------------------- | ------ |
| Flat list endpoint `GET /projects/{project_id}/artifacts` (members + admin, optional `kind` filter) | [artifacts.py:177-192](src/ai_qa/api/artifacts.py:177) | ✅ done (FROZEN — see below) |
| `ArtifactResponse` carrying name, kind, timestamps, `created_by_user_id`, `updated_by_user_id`, `thread_id` (all UUIDs) | [artifacts.py:61-76](src/ai_qa/api/artifacts.py:61) | ✅ done (FROZEN — additive only) |
| `ArtifactService.list_artifacts(project_id, kind)` — project-scoped, ordered by name | [service.py:155-162](src/ai_qa/artifacts/service.py:155) | ✅ done |
| `REQUIRED_ARTIFACT_FOLDERS = ("requirements", "test_cases", "test_scripts")` | [service.py:31](src/ai_qa/artifacts/service.py:31) | ✅ done |
| `required_folders(project_id)` projection (returns the 3 prefixes; **built for THIS story, currently unused**) | [service.py:201-207](src/ai_qa/artifacts/service.py:201) | ✅ done |
| Canonical kind→folder mapping (the single source of truth for STORAGE keys) | `build_artifact_key` — [storage.py:12-38](src/ai_qa/artifacts/storage.py:12) | ✅ done (FROZEN layout) |
| `User.display_name` (`String(255)`, NOT NULL) + `User.email` | [models.py:31-32](src/ai_qa/db/models.py:31) | ✅ done |
| Project-membership authz (non-member → `404`, no leak) | `ProjectAccessDependency` — [projects.py:79](src/ai_qa/api/projects.py:79) | ✅ done |
| Sidebar with 5 collapsible folders + `Empty` marker + 5-per-page pagination | `ProjectSidebar` — [ProjectSidebar.tsx:52-149,400-493](frontend/src/components/conversations/ProjectSidebar.tsx:52) | ✅ done (folder LABELS frozen) |
| Frontend `Artifact` interface (incl. the 3 optional 10-1 UUID fields) | [ProjectSidebar.tsx:22-32](frontend/src/components/conversations/ProjectSidebar.tsx:22) | ✅ done |
| Timestamp formatting convention (`Intl.DateTimeFormat`) | `ThreadRow` — [ProjectSidebar.tsx:168-171](frontend/src/components/conversations/ProjectSidebar.tsx:168) | ✅ done (reuse for "updated …") |
| Artifact selection / preview / realtime refresh / change-notice wiring | `onSelectArtifact`, `artifactRefreshTrigger`, `selectedArtifact`, `artifactNoticeTypeFor` — [App.tsx:395,404-429](frontend/src/App.tsx:395); `ArtifactPreview.tsx`, `ArtifactNotice.tsx` | ✅ done (FROZEN — 10-7/10-8 own these) |
| Generic typed API client `apiFetch<T>` | [api.ts:70-136](frontend/src/lib/api.ts:70) | ✅ done |

### The grouping bug this story must fix (AC2)

`ProjectSidebar.getArtifactsByKind(kind)` ([ProjectSidebar.tsx:394-398](frontend/src/components/conversations/ProjectSidebar.tsx:394)) filters `artifacts.filter(a => a.kind === kind)` for the hardcoded list `['requirements', 'testcase', 'testscript', 'report']` ([ProjectSidebar.tsx:451](frontend/src/components/conversations/ProjectSidebar.tsx:451)). The canonical mapping ([storage.py:28-37](src/ai_qa/artifacts/storage.py:28)) routes more than one kind into the same logical folder:

| Logical folder | Kinds that belong there ([storage.py:28-37](src/ai_qa/artifacts/storage.py:28)) | Shown by current UI? |
| -------------- | ------------------------------------------------------------------------------- | -------------------- |
| `requirements` | `requirements`, **`raw_html`** | only `requirements` — **`raw_html` dropped** |
| `test_cases` | `testcase` | yes |
| `test_scripts` | `testscript`, **`playwright_script`** | only `testscript` — **`playwright_script` dropped** |

`raw_html` (Bob's saved Confluence pages) and `playwright_script` (Sarah's generated scripts) are real, agent-written kinds that **never appear in the sidebar today.** AC2 ("entries with names, types … scoped only to the selected project") requires entries to be grouped by their **canonical logical folder**, not by raw kind.

### FROZEN CONTRACTS — DO NOT change (you will break shipped 10-7 / 10-8)

- **Flat list endpoint** `GET /projects/{project_id}/artifacts` — keep path, method, and the flat `list[ArtifactResponse]` body. **Add a new endpoint; do not repurpose this one.**
- **`ArtifactResponse` field names/types** ([artifacts.py:61-76](src/ai_qa/api/artifacts.py:61)) — **do NOT add the new display fields to `ArtifactResponse`.** It is reused by the flat endpoint and by 10-7/10-8. The tree's richer entries use a **new** model (see Task 3.1).
- **The five sidebar folder labels** — `Conversations`, `Requirements`, `Test Cases`, `Scripts`, `Reports` — asserted verbatim by the shipped 10-7 e2e via `getByText` ([story-10-7-artifact-refresh.spec.ts:176-180](frontend/e2e/story-10-7-artifact-refresh.spec.ts:176)). Do not rename or remove any of them.
- **The `Empty` marker** copy/behavior, and **Reports renders even when empty** (shipped behavior — see Q1/AC1 note in Task 4.3) ([ProjectSidebar.tsx:110-111](frontend/src/components/conversations/ProjectSidebar.tsx:110)).
- **Each artifact NAME stays its own standalone text node** equal to `artifact.name` — 10-7/10-8 do `getByText("<exact filename>")` and `.click()` it ([story-10-8-artifact-notice.spec.ts:214,219,319,324,419,424](frontend/e2e/story-10-8-artifact-notice.spec.ts:214)). Do **not** concatenate metadata into the name node; render "updated …" + creator/updater in a **separate** sibling node.
- **The fetch effect's refresh trigger** — `artifactRefreshTrigger` must stay in the dependency array of the (now tree) fetch effect ([ProjectSidebar.tsx:341](frontend/src/components/conversations/ProjectSidebar.tsx:341)); dropping it silently breaks 10-7 realtime refresh.
- **Tree entries must stay assignable to the frontend `Artifact` type** so the row click still feeds `onSelectArtifact` → App's `.id`/`.name` notice/preview wiring ([App.tsx:417,423](frontend/src/App.tsx:417)). Do not pass folder-wrapped objects to `onSelectArtifact`.
- **`ArtifactChangeEvent`** shape, **`ARTIFACT_KINDS`** frozenset / kind strings, and **`build_artifact_key` storage layout** — Story 10.6 owns events; do not touch the event, rename kinds, or change storage keys.

---

## ✅ RESOLVED DECISIONS (confirmed by Thuong, 2026-06-11)

These were open questions; Thuong's answers are now binding, refined by the adversarial verification pass:

- **D1 (was Q1) — Reports = catch-all.** The `reports` browse folder holds every kind NOT in the 3 required folders: `report`, `image`, `screenshot`, `markdown`, `mermaid`, `configuration` (6 kinds). No artifact is invisible. The classifier `folder_for_kind` returns one of `requirements | test_cases | test_scripts | reports` and is **exhaustive** over all 11 `ARTIFACT_KINDS`.
- **D2 (was Q2) — Auto-open the active thread's project; still list all the others.** Default: when a thread has a bound project, **auto-open THAT project** in the sidebar so its tree is what's shown — **but keep listing every other member project** so the shipped 10-7 multi-project e2e doesn't break. AC3 is satisfied by **per-project data scoping** (each project's tree is fetched/scoped independently — no cross-project bleed). Auto-open must be **non-sticky** (only when no project is open / a one-shot on thread change) so a manual click on another project node is not reverted.
- **D3 (was Q3) — Show creator/updater + updated timestamp, names resolved server-side.** Other users' names are **not** resolvable client-side (the only multi-user lookup is admin-gated — see Dev Notes). Therefore the tree endpoint returns **resolved display names**. Use `User.display_name` **only** (it is NOT NULL, always present) — do **not** select or return `email` (PII discipline). Rows show name + "updated `<ts>`" + updater name in a separate text node.
- **D4 (was Q4) — Replace the flat fetch with the tree fetch** in `ProjectSidebar`, keeping the refresh trigger and the `onSelectArtifact` object shape intact (see Frozen Contracts).

---

## Tasks / Subtasks

- [ ] **Task 1 — Shared kind→folder browse classifier (AC2, D1)**
  - [ ] 1.1 Add a module-level `folder_for_kind(kind: str) -> str` (suggest [storage.py](src/ai_qa/artifacts/storage.py), next to `build_artifact_key`) returning exactly one of `"requirements" | "test_cases" | "test_scripts" | "reports"`. Mapping (exhaustive over the 11 `ARTIFACT_KINDS`):
    - `requirements`, `raw_html` → `"requirements"`
    - `testcase` → `"test_cases"`
    - `testscript`, `playwright_script` → `"test_scripts"`
    - `report`, `image`, `screenshot`, `markdown`, `mermaid`, `configuration` → `"reports"` (catch-all)
  - [ ] 1.2 **Do NOT refactor `build_artifact_key` to call this helper.** `folder_for_kind` is a **browse** classifier (catch-all label `reports`); `build_artifact_key` is a **storage** key builder whose catch-all is the literal `artifacts/` prefix and whose layout is FROZEN. They intentionally differ for the catch-all. To prevent drift on the *required* folders, add a unit test asserting `folder_for_kind` and `build_artifact_key` agree on the top-level folder for the 5 named kinds (`requirements`, `raw_html`, `testcase`, `testscript`, `playwright_script`).

- [ ] **Task 2 — Folder-structured browse on the service layer (AC1, AC2, AC3, D3)**
  - [ ] 2.1 Add `ArtifactService.list_artifact_tree(project_id: UUID)`. Query all artifacts for the project (reuse the project-scoped filter `Artifact.project_id == project_id` from `list_artifacts` — [service.py:155-162](src/ai_qa/artifacts/service.py:155)), then bucket each into its folder via `folder_for_kind`.
  - [ ] 2.2 **Resolve creator/updater display names in ONE batch query** (sync session — no async/eager-load concern; the service uses a sync `Session` — [service.py:9,37,155-162](src/ai_qa/artifacts/service.py:9)). Add `User` to the imports ([service.py:12](src/ai_qa/artifacts/service.py:12)). Collect `user_ids = {a.created_by_user_id, a.updated_by_user_id for all artifacts} - {None}`; **if empty, skip the query** (avoid `WHERE id IN ()`). Otherwise: `select(User.id, User.display_name).where(User.id.in_(user_ids))` → build `name_map: dict[UUID, str]`. **Select only `id` + `display_name`** — never `email`/`password_hash` (PII). For each artifact, `created_by_display = name_map.get(created_by_user_id)` (→ `None` for SET-NULL/missing — must not crash), same for updater.
  - [ ] 2.3 **Always include the 4 browse folders** (`requirements`, `test_cases`, `test_scripts`, `reports`) in the result, even with zero entries — the 3 required ones per AC1, and `reports` to match shipped always-rendered behavior (see Task 4.3 / regression note). Mark the 3 required as `required: true`, `reports` as `required: false`. Each folder carries `name`, `prefix` (`str | None` — use the `required_folders()` shape `projects/{project_id}/{folder}/` for the 3 required; the generic `projects/{project_id}/artifacts/` or `None` for `reports`), `is_empty`, and `entries`.
  - [ ] 2.4 **Entry ordering: newest-first by `updated_at`** within each folder (matches the shipped sidebar sort at [ProjectSidebar.tsx:394-397](frontend/src/components/conversations/ProjectSidebar.tsx:394) and the new "updated `<ts>`" metadata). Note this diverges from `list_artifacts`'s `name` ordering — that is intentional; do not change `list_artifacts`.
  - [ ] 2.5 Projection only — **never create empty objects in SeaweedFS** (empty folders are computed, not materialized).

- [ ] **Task 3 — Additive tree endpoint with a NEW richer entry model (AC1, AC2, AC3, D3)**
  - [ ] 3.1 Add **new** Pydantic models in [artifacts.py](src/ai_qa/api/artifacts.py) (do **not** modify `ArtifactResponse`):
    - `ArtifactTreeEntry` — carries the same fields as `ArtifactResponse` (`id`, `project_id`, `agent_run_id`, `kind`, `name`, `current_version`, `created_at`, `updated_at`, `created_by_user_id`, `updated_by_user_id`, `thread_id`) **plus** `created_by_display: str | None` and `updated_by_display: str | None`. (Subclass `ArtifactResponse` or define standalone — either is fine, but keep the IDs so the frontend `Artifact` shape is satisfied.)
    - `ArtifactTreeFolder` — `{ name: str, prefix: str | None, required: bool, is_empty: bool, entries: list[ArtifactTreeEntry] }`.
    - `ArtifactTreeResponse` — `{ project_id: UUID, folders: list[ArtifactTreeFolder] }`.
  - [ ] 3.2 Add `GET /projects/{project_id}/artifacts/tree` → `ArtifactTreeResponse`. Depend on `ProjectAccessDependency`; keep the `project.id != project_id` guard and the non-member `404` / `RESOURCE_NOT_FOUND_DETAIL` behavior (copy the pattern from [artifacts.py:177-192](src/ai_qa/api/artifacts.py:177)). Map `ValueError` → `422`.
  - [ ] 3.3 **AC2/AC3 scoping:** the service query filters `Artifact.project_id == project_id`, so entries can never bleed across projects. Prove it with a test (Task 5).
  - [ ] 3.4 Add `ArtifactTreeEntry`, `ArtifactTreeFolder`, `ArtifactTreeResponse` to `__all__` ([artifacts.py:350-358](src/ai_qa/api/artifacts.py:350)).

- [ ] **Task 4 — Frontend consumes the tree (AC1, AC2, AC3, D2, D3, D4)**
  - [ ] 4.1 Add a typed client wrapper + TS types. Suggest `frontend/src/lib/artifacts.ts`: `fetchArtifactTree(projectId): Promise<ArtifactTree>` calling `apiFetch<ArtifactTree>('/projects/${projectId}/artifacts/tree')`, plus `ArtifactTree` / `ArtifactTreeFolder` interfaces. **Extend the existing `Artifact` interface** ([ProjectSidebar.tsx:22-32](frontend/src/components/conversations/ProjectSidebar.tsx:22)) additively with optional `created_by_display?: string | null` and `updated_by_display?: string | null`, and type `ArtifactTreeFolder.entries` as `Artifact[]` so entries stay assignable to `Artifact` (keeps `onSelectArtifact` wiring valid).
  - [ ] 4.2 In `ProjectSidebar`, **replace** the flat `GET /projects/{id}/artifacts` fetch ([ProjectSidebar.tsx:316](frontend/src/components/conversations/ProjectSidebar.tsx:316)) with `fetchArtifactTree(openProjectId)`. **Keep `artifactRefreshTrigger` in the effect's dependency array** ([ProjectSidebar.tsx:341](frontend/src/components/conversations/ProjectSidebar.tsx:341)). Render the artifact folders from the tree response (fixes the sibling-kind grouping bug). `Conversations` stays driven by `/threads`.
  - [ ] 4.3 **Folder-name → frozen-label mapping (MIND THE KEY MISMATCH):** the tree returns folder names `requirements` / `test_cases` / `test_scripts` / `reports`, but the existing `SubFolderType` / `FOLDER_CONFIG` keys are `requirements` / `testcase` / `testscript` / `report` ([ProjectSidebar.tsx:42-50](frontend/src/components/conversations/ProjectSidebar.tsx:42)). Re-key `SubFolderType` / `FOLDER_CONFIG` to the backend folder names while keeping the **label strings identical and frozen** (`Requirements`, `Test Cases`, `Scripts`, `Reports`) and the same icons. Render **every folder in the tree response** (including `reports`) and show the existing `Empty` marker when `entries` is empty — this keeps the 3 required folders AND `Reports` visible when empty (AC1 + shipped behavior). Drive each folder's empty state from `is_empty`.
  - [ ] 4.4 **Per-row metadata (D3):** inside the existing clickable row ([ProjectSidebar.tsx:460-479](frontend/src/components/conversations/ProjectSidebar.tsx:460)), keep the `{artifact.name}` `<span>` as its own text node, and add a **separate** muted sibling node (reuse `text-[10px] text-[#6b7280]` from [ProjectSidebar.tsx:240](frontend/src/components/conversations/ProjectSidebar.tsx:240)) showing "updated `<ts>`" — formatted with the same `Intl.DateTimeFormat` pattern as `ThreadRow` ([ProjectSidebar.tsx:168-171](frontend/src/components/conversations/ProjectSidebar.tsx:168)) on `artifact.updated_at` — plus the updater display name (`updated_by_display`, fallback to omit if `null`). Use a `flex-col` inner block so metadata sits under the name; keep `truncate`/`overflow-hidden`. Optionally mirror the same metadata in `ArtifactPreview`'s subtitle ([ArtifactPreview.tsx:63-66](frontend/src/components/artifacts/ArtifactPreview.tsx:63)).
  - [ ] 4.5 **AC3 scoping (D2):** keep rendering the full `projects.map` ([ProjectSidebar.tsx:406](frontend/src/components/conversations/ProjectSidebar.tsx:406)) — do **not** hide non-active projects. When there is an active thread bound to a project (derive from `currentThreadId`; App already computes `activeProjectId = activeThread?.project_id`), auto-set `openProjectId` to it **non-stickily** (e.g. only when `openProjectId === null`, or a one-shot on thread change) so a manual click on another project ([story-10-7-artifact-refresh.spec.ts:365](frontend/e2e/story-10-7-artifact-refresh.spec.ts:365)) is not immediately reverted.
  - [ ] 4.6 Run `npm run typecheck` in `frontend/`.

- [ ] **Task 5 — Tests + verification (DoD)**
  - [ ] 5.1 **Backend** — extend [tests/api/test_artifact_browsing_api.py](tests/api/test_artifact_browsing_api.py) (copy its `browsing_client` fixture + `_create_user`/`_create_project`/`_add_membership`/`_auth_headers` helpers — [tests/api/test_artifact_browsing_api.py:69-108](tests/api/test_artifact_browsing_api.py:69)) for `GET …/tree`:
    - empty project → response has the 4 folders; the 3 required `is_empty: true`/`entries: []` and `required: true`; `reports` present;
    - populated → `raw_html` under `requirements`, `playwright_script` under `test_scripts`, `testcase` under `test_cases`, a generic kind (e.g. `report`/`image`) under `reports` (proves the grouping fix + catch-all);
    - entries carry `name`, `kind`, `updated_at`, and **resolved `created_by_display`/`updated_by_display` equal to the real `User.display_name`** (not UUIDs);
    - **SET-NULL creator** (artifact with `created_by_user_id = None`) → `created_by_display is None`, no crash;
    - **PII canary:** the tree response body contains **no** `email`, `password_hash`, or `storage_path`;
    - **cross-project scoping:** a project-B artifact never appears in project-A's tree (AC2/AC3);
    - **leak-canary** (mirror [tests/api/test_artifact_api.py:624-719](tests/api/test_artifact_api.py:624)): non-member and cross-project member hitting `/tree` get `404` `RESOURCE_NOT_FOUND_DETAIL`, no `projects/{id}/` key / `storage_path` leaked.
  - [ ] 5.2 **Backend** — extend [tests/unit/test_artifact_service.py](tests/unit/test_artifact_service.py): `folder_for_kind` covers every kind in `ARTIFACT_KINDS` (and agrees with `build_artifact_key` on the 5 named kinds — Task 1.2); `list_artifact_tree` returns the folders when empty, groups correctly when populated, resolves display names, and handles `None` creator.
  - [ ] 5.3 **Frontend** — keep the shipped 10-7/10-8 e2e green **without editing their assertions**. Optionally add focused coverage: a `raw_html` artifact renders under **Requirements** and a `playwright_script` under **Scripts**; an empty **Reports** folder still renders; AC3 auto-open is non-sticky (clicking project B is not reverted to project A). `npm run typecheck` clean.
  - [ ] 5.4 Run the full gate (see Definition of Done) and paste results into the Dev Agent Record.

- [ ] **Task 6 — Chat always auto-scrolls to the newest message (AC4, added UX requirement)**
  - [ ] 6.1 The chat auto-scroll already exists at [App.tsx:524-531](frontend/src/App.tsx:524) but is suppressed when the user has scrolled up (`if (chatScrollRef.current && !userScrolledUpRef.current)` — [App.tsx:527](frontend/src/App.tsx:527)). Change it so a **new message ALWAYS scrolls to the bottom**: when the `messages` array grows (a new message arrives), force-scroll regardless of `userScrolledUpRef`, and reset `userScrolledUpRef.current = false` (the user is now at the bottom). Track the previous message count (or last message id) via a ref to detect "a new message arrived" vs. an in-place update.
  - [ ] 6.2 Make the scroll robust to async content (markdown/images/`ReviewContent`/thinking panels that render AFTER the effect): scroll on the next frame (`requestAnimationFrame`) and/or add a bottom sentinel `<div>` at the end of the message list ([App.tsx:1200](frontend/src/App.tsx:1200)) and `scrollIntoView({ block: "end" })` it, so it reliably reaches the TRUE bottom rather than a stale `scrollHeight`.
  - [ ] 6.3 **Do NOT couple this to artifact refresh.** The effect must stay keyed on message changes; artifact-tree refresh (`artifactRefreshTrigger`) does not change `messages`, so it will not trigger scroll — preserving Story 10.7's "refresh must not reset scroll position". You may keep the existing `userScrolledUpRef` guard for the non-message deps (streaming `thinkingTrace`/`modelAssignments` at [App.tsx:531](frontend/src/App.tsx:531)) so a reader is not yanked mid-stream; only the **new-message** case is unconditional. Keep `handleChatScroll` ([App.tsx:533-537](frontend/src/App.tsx:533)).
  - [ ] 6.4 The chat container is `hidden` while an artifact preview is open ([App.tsx:1199](frontend/src/App.tsx:1199)); ensure the scroll lands at the bottom when the chat re-shows after the preview closes if messages changed meanwhile.
  - [ ] 6.5 Verify: shipped 10-7/10-8 e2e stay green (they assert chat TEXT/message preservation, NOT `scrollTop` — confirmed: no `scroll` assertion exists in either spec), and `npm run typecheck` clean. Optionally add a Vitest/e2e asserting the container is at the bottom after a new message.

---

## Dev Notes

### Architecture & module layout (authoritative)

- **Bucket / folder scheme** ([architecture.md:280,336-348](_bmad-output/planning-artifacts/architecture.md:280)): project-scoped logical folders `projects/{project_id}/requirements/`, `…/test_cases/`, `…/test_scripts/`. These three are the **required** browse folders.
- **Empty-folder behavior is an explicit architecture requirement** ([architecture.md:262](_bmad-output/planning-artifacts/architecture.md:262)): "Empty required folders are shown even when SeaweedFS has no objects for a PostgreSQL project." → AC1.
- **Artifact sharing** ([architecture.md:331](_bmad-output/planning-artifacts/architecture.md:331)): "Artifacts are project-level shared resources. Any assigned project member can list, read, edit, and delete artifacts from other users in that project." → entries are not creator-scoped (AC2); showing co-members' display names is consistent with shared-resource visibility.
- **Path discrepancy to respect** (same as 10-1): the architecture names `src/ai_qa/api/routes/artifacts.py` ([architecture.md:760](_bmad-output/planning-artifacts/architecture.md:760)) and `frontend/src/features/artifacts/` ([architecture.md:761](_bmad-output/planning-artifacts/architecture.md:761)). **Neither exists.** Edit the **actual** files: [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py), [frontend/src/components/conversations/ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx), [frontend/src/lib/](frontend/src/lib/). Do **not** create new module trees.

### Why a new endpoint + a new entry model (not extend the flat list / `ArtifactResponse`)

AC2 says "the API returns **folders and** artifact entries." The shipped flat list ([artifacts.py:177](src/ai_qa/api/artifacts.py:177)) returns only entries and is a frozen contract (the sidebar + 10-7/10-8 e2e depend on its exact flat shape). Adding `GET …/artifacts/tree` is the additive way to satisfy AC2 while leaving the flat endpoint untouched, and makes the empty-folder guarantee (AC1) server-authoritative (what 10-1's unused `required_folders()` was built for).

**`ArtifactResponse` exposes creator/updater as bare UUIDs only** ([artifacts.py:74-75](src/ai_qa/api/artifacts.py:74)) and is built via `ArtifactResponse.model_validate(artifact)` ([artifacts.py:138-139](src/ai_qa/api/artifacts.py:138)) — it **cannot** derive a display name from a UUID column. To satisfy D3 (show creator/updater) you MUST return resolved display strings on a **new** entry model; do not add display fields to the frozen `ArtifactResponse`.

### Name resolution: why server-side, and how (D3)

Other users' names are **not** available client-side for the standard-user audience that sees this sidebar:

- The artifact API returns only UUIDs ([artifacts.py:74-75](src/ai_qa/api/artifacts.py:74); mirrored in TS at [ProjectSidebar.tsx:29-30](frontend/src/components/conversations/ProjectSidebar.tsx:29)).
- Only the **current** user's identity is known client-side via `useAuth()` ([auth.ts:3-12](frontend/src/lib/auth.ts:3)); other UUIDs cannot be resolved.
- The only multi-user lookup, `listAdminUsers()` → `GET /admin/users`, is **admin-gated** ([admin.py:209-210](src/ai_qa/api/admin.py:209)); standard users get 403.
- Project membership data carries **no** display name ([types/project.ts:1-7](frontend/src/types/project.ts:1); `projects.py` has no name/email serializer).

So the **backend** resolves names. The `User` model has `display_name` (`String(255)`, **NOT NULL** — always present) and `email` ([models.py:31-32](src/ai_qa/db/models.py:31)). **Use `display_name` only**; do not select or return `email` (PII discipline — project rule: never leak unexpected user fields). Resolution is one extra batch query keyed on distinct user IDs (sync session, O(1) queries, no N+1, no `MissingGreenlet`). `Artifact` has **no** ORM relationship to `User` for creator/updater ([models.py:151-155](src/ai_qa/db/models.py:151)) — 10-1's "columns only" note is accurate — so use the explicit batch query, not a relationship/eager-load.

### Frontend current state (what you are editing)

- `ProjectSidebar` fetches `/threads` + `/projects/{openProjectId}/artifacts` in parallel ([ProjectSidebar.tsx:314-317](frontend/src/components/conversations/ProjectSidebar.tsx:314)) and re-fetches whenever `artifactRefreshTrigger` changes ([ProjectSidebar.tsx:341](frontend/src/components/conversations/ProjectSidebar.tsx:341)). Replace the artifact fetch with the tree fetch; keep the trigger in deps.
- `SubFolder` already renders the `Empty` state, count badge, and pagination ([ProjectSidebar.tsx:108-145](frontend/src/components/conversations/ProjectSidebar.tsx:108)) — reuse it; feed it each tree folder's `entries`.
- The artifact row is an inline `<div>` (not a component) at [ProjectSidebar.tsx:460-479](frontend/src/components/conversations/ProjectSidebar.tsx:460); the click target is the outer `<div>` ([ProjectSidebar.tsx:469-472](frontend/src/components/conversations/ProjectSidebar.tsx:469)) → keep it there. `ArtifactPreview` shows only `kind · v<version>` today ([ArtifactPreview.tsx:63-66](frontend/src/components/artifacts/ArtifactPreview.tsx:63)).
- `openProjectId` ([ProjectSidebar.tsx:276](frontend/src/components/conversations/ProjectSidebar.tsx:276)) is currently independent of the active thread; D2 auto-opens the active thread's project (non-sticky).
- UI conventions: custom Tailwind (hex classes), `lucide-react` icons, no shadcn. Match the existing styling.

### Regression discipline (verified safe-with-mitigations against 10-7/10-8)

The swap to `/artifacts/tree` is safe because every shipped e2e locates artifacts by **name** (`getByText`), never by the flat endpoint's wire shape; the Reports catch-all is a strict superset of today's `report`-only Reports; and keeping all projects matches the shipped `projects.map`. Load-bearing invariants (do not violate):

- Keep `artifactRefreshTrigger` in the fetch-effect deps (else 10-7 refresh assertions at [story-10-7…:193,265,366](frontend/e2e/story-10-7-artifact-refresh.spec.ts:193) break).
- Keep tree entries assignable to `Artifact` with real `.id`/`.name` so the row click feeds App's notice/preview ([App.tsx:417,423](frontend/src/App.tsx:417)).
- Keep the five frozen labels; render Reports even when empty.
- AC3 auto-open must be non-sticky (else the 10-7 multi-project click at [story-10-7…:330-366](frontend/e2e/story-10-7-artifact-refresh.spec.ts:330) gets reverted).
- Keep the `{artifact.name}` text node standalone (no concatenated metadata).

### Authorization model (unchanged from 10-1)

- Reuse `require_project_member_or_admin` → `ProjectAccessDependency` ([projects.py:79](src/ai_qa/api/projects.py:79)). Admins pass; non-members get `404` `RESOURCE_NOT_FOUND_DETAIL` (404-not-403 is intentional). Service queries stay project-scoped. No secrets/PII (incl. `email`/`password_hash`) in the response — leak-canary covers it.

### Anti-patterns to avoid (FORBIDDEN)

- Repurposing the flat `GET …/artifacts` endpoint or adding display fields to `ArtifactResponse` → breaks the sidebar + 10-7/10-8.
- Returning bare UUIDs (or `email`) for creator/updater → defeats D3 / leaks PII.
- Renaming/removing any of the five frozen sidebar labels; concatenating metadata into the artifact-name text node → breaks 10-7/10-8 `getByText`.
- Refactoring `build_artifact_key` to emit `reports` / changing storage keys → breaks the frozen layout + 10-1 key-builder test.
- Materializing empty folders as real SeaweedFS objects; N+1 per-artifact user queries.
- `# type: ignore` / `@ts-ignore`; global lint disables; mixing formatting with logic in one commit (project rules).
- Touching `ArtifactChangeEvent`, the WebSocket broadcast, or the notice flow — 10.6/10.7/10.8 territory.

### Previous-story / brownfield intelligence

- **10-1** delivered the seams this story consumes: `REQUIRED_ARTIFACT_FOLDERS`, `required_folders()`, the artifact `created_by_user_id`/`updated_by_user_id`/`thread_id` columns, the additive `ArtifactResponse` fields, and the unified `build_artifact_key`. Read [10-1's story file](_bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md).
- The 10-1 review **deferred** "`thread_id` is foundation-only — no production caller passes it." AC3 here is satisfied by **project** scoping (`Artifact.project_id`), not by `thread_id`. Do not add thread-level artifact filtering — out of scope.
- **10-7 / 10-8** shipped the sidebar/preview/notice/refresh ahead of this story; they are why the labels, row name node, refresh trigger, and `onSelectArtifact` shape are frozen.
- Git: HEAD `90d3f6f` (story 10-1, working tree clean). No artifact work in flight.

### Latest tech / dependencies

No new dependencies. FastAPI 0.115, SQLAlchemy 2.0 (sync `Session` in the artifacts path), Pydantic v2 (backend); React 18.3, TypeScript 5.6, Vite, Tailwind, lucide-react (frontend). `uv` only for backend; `npm` only inside `frontend/`.

### Testing requirements

- **Backend (pytest):** in-memory SQLite via the `browsing_client` fixture ([tests/api/test_artifact_browsing_api.py:69-108](tests/api/test_artifact_browsing_api.py:69)) — copy it; override `get_artifact_storage` with the in-file `ArtifactStorageFake`. Use the file's helpers. No bare `pytest.raises(Exception)`; `cast(FastAPI, client.app)` for overrides; `engine.dispose()` in teardown.
- **No migration in this story** — no schema change (10-1 already added the columns). State this in the DoD.
- **Frontend:** `npm run typecheck` after the TS sync; keep 10-7/10-8 e2e green. E2E must not use `page.route` mocking — prepare state via real API; clean up in `afterEach`.

### Project Structure Notes

Touch points (extend existing files; new files are the optional `frontend/src/lib/artifacts.ts` and new test cases):

- [src/ai_qa/artifacts/storage.py](src/ai_qa/artifacts/storage.py) — add `folder_for_kind` (do NOT change `build_artifact_key`).
- [src/ai_qa/artifacts/service.py](src/ai_qa/artifacts/service.py) — add `list_artifact_tree` + `User` import + name resolution.
- [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py) — add `ArtifactTreeEntry`/`ArtifactTreeFolder`/`ArtifactTreeResponse` + `GET …/tree` (do NOT touch `ArtifactResponse` or the flat list route).
- [frontend/src/lib/artifacts.ts](frontend/src/lib/artifacts.ts) (new) — `fetchArtifactTree` + tree types.
- [frontend/src/components/conversations/ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx) — tree fetch, folder-name→label re-key, per-row metadata, AC3 auto-open, extended `Artifact` interface.
- [frontend/src/App.tsx](frontend/src/App.tsx) — AC4 chat always-scroll-on-new-message (modify the existing effect at lines 524-531; optional bottom sentinel near line 1200). Also the existing source of `activeProjectId` for AC3 auto-open.
- [tests/api/test_artifact_browsing_api.py](tests/api/test_artifact_browsing_api.py), [tests/unit/test_artifact_service.py](tests/unit/test_artifact_service.py) — new coverage.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-10.2] (lines 802-822) — the three ACs.
- [Source: _bmad-output/planning-artifacts/prd.md] — FR35 (line 409, project-level visibility), FR42 (line 419, project-level tree), **FR43 (line 420, the 3 required folders)**, **FR44 (line 421, show empty folders)**, FR45 (line 422, metadata: creator/updater/thread/agent-run), FR46 (line 423, member list/read/edit/delete), FR52 (line 432, browse regardless of creator). FR61-FR66 (realtime, lines 447-452) are 10.6/10.7/10.8 — **out of scope.** FR67 (line 453) — rollback/external notifications out of MVP.
- [Source: _bmad-output/planning-artifacts/architecture.md] — lines 261 (post-bind workspace), 262 (empty folders shown), 280 + 336-348 (folder scheme/bucket), 331 (project-shared artifacts), 760-761 (architecture-vs-actual paths).
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — **does NOT specify the Project/Artifacts tree UI** (no wireframe/columns/empty-state copy). The shipped 10-7/10-8 sidebar IS the de-facto UX; preserve it.
- [Source: src/ai_qa/artifacts/storage.py:12-38] — `build_artifact_key` (canonical kind→folder for STORAGE; the 5 named branches `folder_for_kind` must agree with).
- [Source: src/ai_qa/artifacts/service.py:9,12,31,155-162,201-207] — sync `Session`; imports; `REQUIRED_ARTIFACT_FOLDERS`; `list_artifacts`; `required_folders` (unused; consume it).
- [Source: src/ai_qa/api/artifacts.py:61-76,138-139,177-192] — frozen `ArtifactResponse` (UUID-only creator/updater) + `model_validate`; flat list endpoint (pattern to copy for `/tree`).
- [Source: src/ai_qa/db/models.py:31-32,125-155] — `User.display_name`/`email`; `Artifact` creator/updater columns + relationships (no creator/updater rel).
- [Source: src/ai_qa/api/admin.py:209-210] — `GET /admin/users` is admin-gated (why name resolution is server-side).
- [Source: frontend/src/components/conversations/ProjectSidebar.tsx:22-50,108-149,168-171,240,314-341,394-398,406,451,460-479] — `Artifact` type, `FOLDER_CONFIG`/`SubFolderType` keys, `SubFolder`/`Empty`, timestamp format, fetch effect, `getArtifactsByKind` (the bug), `projects.map`, row render.
- [Source: frontend/src/lib/auth.ts:3-12], [frontend/src/types/project.ts:1-22] — client-side user-display unavailability.
- [Source: frontend/src/App.tsx:395,404-429,417,423,1010-1011] — refresh trigger, notice wiring on `selectedArtifact.id/.name`, props to `ProjectSidebar`.
- [Source: frontend/src/App.tsx:483,524-537,1199-1200] — existing chat auto-scroll effect + `userScrolledUpRef` guard + `handleChatScroll` + the scrollable chat container (AC4 touch points).
- [Source: frontend/src/components/artifacts/ArtifactPreview.tsx:31-37,63-66] — preview metadata subtitle (optional mirror location).
- [Source: frontend/e2e/story-10-7-artifact-refresh.spec.ts:176-180,193,265,330-366] — frozen folder labels + multi-project sidebar. [story-10-8-artifact-notice.spec.ts:214-223,319-324,419-477] — name-node + click + chat-state assertions.
- [Source: tests/api/test_artifact_browsing_api.py:69-108] — canonical fixture to copy. [tests/api/test_artifact_api.py:624-719] — leak-canary pattern.
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; sync vs async session; no secrets/PII in responses/logs; full-stack TS sync; E2E no `page.route`, cleanup in `afterEach`.

### Definition of Done

- [ ] AC1-AC4 satisfied; all six tasks complete; the 4 resolved decisions (D1-D4) honored.
- [ ] AC4: a new chat message always scrolls the chat to the bottom (even after the user scrolled up); artifact-tree refresh still does NOT move scroll.
- [ ] New `GET /projects/{project_id}/artifacts/tree` returns the 4 browse folders (3 required always present + marked `is_empty`/`required`, plus `reports`); `raw_html`→requirements, `playwright_script`→test_scripts, generic kinds→reports verified.
- [ ] Tree entries carry **resolved `created_by_display`/`updated_by_display`** (from `User.display_name`), `None` for SET-NULL creators; **no `email`/`password_hash`/`storage_path`** in the response (canary asserts).
- [ ] `ArtifactResponse` and the flat list endpoint **unchanged**; the five sidebar labels unchanged; Reports renders when empty.
- [ ] **No schema change / no Alembic migration** in this story.
- [ ] `uv run ruff check .` clean; `uv run mypy` clean (strict).
- [ ] `uv run pytest` green, incl. tree-browsing + display-name + SET-NULL + PII/leak canary + service tests.
- [ ] `npm run typecheck` clean in `frontend/`; shipped 10-7/10-8 e2e still green (assertions unedited).
- [ ] No frozen contract changed (flat list endpoint, `ArtifactResponse`, the five labels, name text node, refresh trigger, `onSelectArtifact` shape, `ArtifactChangeEvent`, kind strings, `build_artifact_key` layout).
- [ ] Dev Agent Record updated with file list, commands run, and outputs.

---

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created (4 decisions resolved + adversarial verification pass applied).

### Commands Run

### File List

### Change Log

- 2026-06-11: Story 10-2 drafted — reconcile + harden. Backend: `folder_for_kind` browse classifier + `list_artifact_tree` (server-resolved creator/updater display names) + additive `GET …/artifacts/tree` with a new `ArtifactTreeEntry`/`ArtifactTreeFolder`/`ArtifactTreeResponse`. Frontend: `ProjectSidebar` replaces the flat fetch with the tree fetch (fixes `raw_html`/`playwright_script` grouping drop), shows per-row updated-ts + updater name, keeps all member projects (AC3 via scoping + non-sticky auto-open). Decisions D1-D4 confirmed by Thuong; 9 adversarial-review findings folded in (new entry model not frozen `ArtifactResponse`; `display_name` only / no email PII; entries stay `Artifact`-assignable; Reports renders when empty; `folder_for_kind` not wired into `build_artifact_key`; folder-name↔label re-key; empty-`IN` guard; updated test matrix; entry ordering). No schema change. Frozen: flat list endpoint, `ArtifactResponse`, five sidebar labels, refresh trigger, name text node.
- 2026-06-11 (update): Thuong refinements — D2 re-framed to lead with auto-open the active thread's project (others still listed, non-sticky, so 10-7 stays green); added **AC4 + Task 6** = chat always auto-scrolls to the newest message (drop the `userScrolledUpRef` suppression for new messages only; keep it for streaming thinking-trace updates; do not couple to artifact refresh so 10-7 scroll-preservation holds — verified no e2e asserts `scrollTop`). New touch point: `frontend/src/App.tsx` (chat-scroll effect).

---

### Review Findings

Code review 2026-06-11 (adversarial: Blind Hunter + Edge Case Hunter + Acceptance Auditor; all 3 layers ran). Outcome: 0 decision-needed, 6 patch, 2 deferred, 5 dismissed as noise. ACs AC1-AC4 and frozen contracts FC1-FC8 verified compliant; route ordering (`/tree` before `/{artifact_id}`) verified correct.

**Resolution (2026-06-11):** all 6 patches applied and verified — `npm run typecheck` clean, `uv run ruff check` clean, `uv run mypy src/ai_qa/artifacts/service.py` clean, affected tests green (`tests/api/test_artifact_browsing_api.py` + `tests/unit/test_artifact_service.py` = 55 passed; also part of the 1041 that pass in the full run). NOTE: the full `uv run pytest` suite is currently RED (17 failed, 32 errors) for reasons UNRELATED to this story (forensics done 2026-06-11). Two independent layers: (1) HEAD `90d3f6f` pinned `.python-version=3.14`, and on 3.14 `ai_qa.threads.service`'s direct `from ai_qa.api.auth.session import UserSession` triggered a runtime circular import — BOTH are fixed in the (uncommitted) working tree: `.python-version` is 3.14 (matches `requires-python>=3.14` + project-context + memory) and the import moved under `TYPE_CHECKING`. (2) Pre-existing **orphaned legacy test files** that reference fixtures (`client`, `admin_token`, `db_session`, `db_user`) NOT defined in the single `tests/conftest.py` (the canonical pattern is per-file inline fixtures à la `browsing_client`): `tests/unit/test_threads_service.py` (stale duplicate of `tests/threads/test_service.py`), `tests/api/test_admin_projects_api.py`, `test_admin_users_api.py`, `test_membership_api.py`, `test_agent_base.py`, `secrets/test_types.py`; plus `tests/unit/test_secret_service.py` (staged for deletion) importing the removed `SecretsService`. These fixture errors were masked at HEAD by the 3.14 circular import (collection aborted first) and surface once the import is fixed. None touch the artifact files changed here; all are unchanged vs HEAD, so they fail identically at HEAD.

#### Patch

- [x] `[Review][Patch]` Multi-project cold-load auto-open never fires (D2) [frontend/src/components/conversations/ProjectSidebar.tsx:350] — On page reload `threadId` is restored from localStorage so `currentThreadId` is set, but the auto-open effect burns its one-shot ref (`autoOpenedForThreadRef.current = currentThreadId`, line 354) before `threads` is populated. `threads` only loads after `openProjectId` is set (the fetch effect early-returns when null, line 366), so a multi-project user with nothing open gets `boundThread === undefined` and the thread's project never auto-opens; the guard then blocks the retry once `threads` arrives. Confirmed by all 3 layers. Fix: derive the bound project from App's `activeProjectId` (App already computes `activeThread?.project_id`) passed as a prop, or fetch `/threads` independently of `openProjectId`; only consume the one-shot ref once the open actually happens.
- [x] `[Review][Patch]` `prevMessageCountRef` not reset on thread switch — AC4 violated in edge case [frontend/src/App.tsx:562] — The `[threadId]` effect resets `userScrolledUpRef` but not `prevMessageCountRef`. Switch from a longer thread (e.g. 20 msgs) to a shorter one (12), then a real new message arrives (12 to 13): `13 > 20` is false so the unconditional new-message scroll is skipped; if the user had scrolled up, the streaming branch's guard also blocks it, so the newest message is not shown — violating AC4 ("always scroll to newest"). Fix: reset `prevMessageCountRef.current = 0` in the `[threadId]` effect.
- [x] `[Review][Patch]` New message during artifact preview not scrolled after preview closes [frontend/src/App.tsx:536] — The chat container is `display:none` (`hidden`) while `selectedArtifact` is open (App.tsx:1223) and the `chatBottomRef` sentinel lives inside it, so `scrollIntoView` is a no-op for messages arriving during a preview. On preview close `threadId` is unchanged and the scroll effect is keyed on `[messages,...]` only, so it never re-scrolls and the view stays mid-history. Fix: re-scroll to bottom when `selectedArtifact` transitions to null if messages changed meanwhile.
- [x] `[Review][Patch]` `list_artifact_tree` ordering lacks a tiebreaker — unstable pagination order [src/ai_qa/artifacts/service.py:253] — `order_by(Artifact.updated_at.desc())` has no secondary key, so artifacts sharing an `updated_at` (batch agent output) return in arbitrary order; with 5-per-page pagination this shuffles rows between pages across refreshes. Fix: add a deterministic tiebreaker, e.g. `.order_by(Artifact.updated_at.desc(), Artifact.id.desc())`.
- [x] `[Review][Patch]` Tautological test assertion in `test_tree_entries_carry_resolved_display_names` [tests/api/test_artifact_browsing_api.py] — `assert "-" not in (created_display or "").replace(member.display_name, "")` reduces to `"-" not in ""` (always true) because the previous line already asserts equality with `display_name`. It proves nothing. Fix: remove it (the equality assert suffices) or assert the value is not a UUID string.
- [x] `[Review][Patch]` Missing leak-canary body assertions on the `/tree` 404 test [tests/api/test_artifact_browsing_api.py] — Task 5.1's leak-canary asks the non-member 404 path to also assert no `projects/{id}/` key / `storage_path` in the 404 body; `test_tree_non_member_gets_404` only checks status + `detail`. Fix: add the body-absence assertions to that test.

#### Defer

- [x] `[Review][Defer]` Pagination page not reset on equal-length item swap [frontend/src/components/conversations/ProjectSidebar.tsx:95] — deferred, pre-existing. `SubFolder`'s `useEffect(() => setPage(1), [items.length])` misses content swaps where length is unchanged (e.g. realtime add+delete in one window); not introduced by this story.
- [x] `[Review][Defer]` Frontend silently drops backend folder names absent from `FOLDER_CONFIG` [frontend/src/components/conversations/ProjectSidebar.tsx:455] — deferred, latent. `renderArtifactFolder` returns `null` for unknown folder names; dormant today (keys match) but would reintroduce the "silent drop" class if the backend adds a 5th browse folder without a matching frontend entry.
