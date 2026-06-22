---
baseline_commit: 90d3f6fbcaa0f5c86df52437f898308884cbc0e8
prerequisite_story: 10-3-artifact-read-and-preview-access
---

# Story 10.4: Artifact Edit, Delete, and Version Metadata

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want to edit and delete shared project artifacts,
so that the team can refine generated outputs collaboratively.

## Acceptance Criteria

### AC1 — Authorized edit appends a new version + records updater/timestamp

**Given** an authorized project member edits a supported artifact
**When** the edit is saved
**Then** artifact bytes are updated through the artifact service
**And** metadata records the updater and updated timestamp.

### AC2 — Prior version metadata is preserved on edit (rollback NOT in MVP)

**Given** version metadata is enabled for an artifact
**When** a user edits the artifact
**Then** the previous version metadata is preserved with timestamp, updater, and storage reference where supported
**And** rollback behavior is not implemented in MVP.

### AC3 — Authorized delete removes the artifact consistently in metadata + storage

**Given** an authorized project member deletes an artifact
**When** deletion is confirmed by the application action
**Then** the artifact is removed or marked deleted consistently in metadata and storage
**And** direct external SeaweedFS notifications are not required for MVP.

---

## ⚠️ CRITICAL: This is a RECONCILE + HARDEN story, NOT a greenfield build

The **entire backend for AC1, AC2, and AC3 already exists, is load-bearing, and is tested** — it shipped in **Story 10-1** (verified against HEAD `90d3f6f`):

- **Edit (AC1):** `POST /projects/{project_id}/artifacts/{artifact_id}/versions` → `ArtifactService.create_version` appends a version with a row lock, increments `current_version`, sets `updated_by_user_id` (the editor) and auto-refreshes `updated_at`, and writes new bytes through the storage backend ([artifacts.py:395-433](src/ai_qa/api/artifacts.py:395), [service.py:133-183](src/ai_qa/artifacts/service.py:133)).
- **Version metadata (AC2):** every edit **appends** an immutable `ArtifactVersion` row (`version`, `content_hash`, `storage_path`, `created_by_user_id`, `created_at`) — history is never mutated ([models.py:158-177](src/ai_qa/db/models.py:158), unit-proven by `test_artifact_service_appends_versions_without_mutating_history` — [test_artifact_service.py:128](tests/unit/test_artifact_service.py:128)). **Rollback is intentionally absent** (architecture.md:245,381,1050).
- **Delete (AC3):** `DELETE /projects/{project_id}/artifacts/{artifact_id}` (204) → `ArtifactService.delete_artifact` hard-deletes the artifact (cascade to versions) and best-effort-deletes every version's storage object ([artifacts.py:365-392](src/ai_qa/api/artifacts.py:365), [service.py:202-225](src/ai_qa/artifacts/service.py:202)).
- **Authz (AC1/AC3 "authorized"):** all routes are gated by `ProjectAccessDependency`; **any** project member or admin may edit/delete (project-shared model — architecture.md:331), not just the creator. Non-members → `404` with no leak ([test_artifact_api.py:620-718](tests/api/test_artifact_api.py:620)).
- **Change events:** edit/delete already broadcast `artifact_change` (`updated`/`deleted`) over WebSocket ([artifacts.py:382-392,421-431](src/ai_qa/api/artifacts.py:382)). **This is FROZEN — Story 10.6 owns events. Do NOT add, rename, or re-fire them.**

**Do NOT add a new edit/delete/version endpoint, rebuild `create_version`/`delete_artifact`, add a soft-delete column, or build a rollback feature.** The real, un-met work is **the frontend edit + delete UX** (no artifact edit/delete UI exists today — only "Close preview") plus a thin layer of **backend positive-path test hardening** for the cross-member edit/delete case and the delete unit gap.

### PREREQUISITE — Story 10-3 should be `done` before this story starts

The edit/delete UI lives in **`ArtifactPreview`**, which **Story 10-3** (`ready-for-dev`, not yet implemented) restructures (kind-aware rendering: `content_encoding` honored, image/Mermaid/script branches, creator/updater header). 10-4's "Edit" mode toggles that rendered view into a raw editor and back.

- **Re-baseline when starting:** set `baseline_commit` to the merge commit of the latest landed predecessor (10-2 then 10-3) and re-read [ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx) — it will look different from the snapshot below once 10-3 lands. Compose the Edit toggle with 10-3's kind-aware body; do not regress 10-3's renderers.
- **If 10-3 is not done yet:** you may still build edit/delete against the current preview, but coordinate so the Edit toggle and 10-3's kind-aware rendering merge cleanly (no double-rebuild of the body). Flag the ordering in the Dev Agent Record.
- **10-2** is also a hard prerequisite (already `review`): it supplies the `Artifact` interface fields and the `/artifacts/tree` refresh that the delete/edit flows rely on.

### What ALREADY EXISTS (reuse — do NOT recreate)

| Capability | Where it lives today | Status |
| ---------- | -------------------- | ------ |
| Edit endpoint `POST …/{artifact_id}/versions` → `ArtifactResponse` (`current_version` bumped, `updated_by_user_id` set) | [artifacts.py:395-433](src/ai_qa/api/artifacts.py:395) | ✅ done (membership-gated, broadcasts `updated`) |
| `ArtifactVersionCreateRequest` `{ content, content_encoding: "text"\|"base64" }` (max 1,000,000 chars) | [artifacts.py:153-157](src/ai_qa/api/artifacts.py:153) | ✅ done (FROZEN — additive only) |
| `ArtifactService.create_version` (row lock, version++, hash, updater, append `ArtifactVersion`, storage write, rollback-on-failure) | [service.py:133-183](src/ai_qa/artifacts/service.py:133) | ✅ done |
| Delete endpoint `DELETE …/{artifact_id}` → `204` | [artifacts.py:365-392](src/ai_qa/api/artifacts.py:365) | ✅ done (membership-gated, broadcasts `deleted`) |
| `ArtifactService.delete_artifact` (DB cascade delete + best-effort storage cleanup of all version paths) | [service.py:202-225](src/ai_qa/artifacts/service.py:202) | ✅ done |
| Immutable version history (`ArtifactVersion`: version/hash/storage_path/creator/created_at; `uq(artifact_id, version)`) | [models.py:158-177](src/ai_qa/db/models.py:158) | ✅ done — AC2 satisfied |
| Version summaries in detail response `GET …/{artifact_id}` → `ArtifactDetailResponse.versions[]` (`ArtifactVersionSummary`) | [artifacts.py:47-58,113-116,176-191](src/ai_qa/api/artifacts.py:47) | ✅ done (no `storage_path` leaked) |
| Project-membership authz (any member/admin; non-member → `404`, no leak) | `ProjectAccessDependency` — [projects.py:79](src/ai_qa/api/projects.py:79) | ✅ done |
| AC3 leak-canary: non-member canary covers all routes incl. `DELETE` + `/versions` ([:640-686](tests/api/test_artifact_api.py:640)); cross-project-member canary covers list/detail/content/**`DELETE`** but **not** `/versions` ([:689-718](tests/api/test_artifact_api.py:689)) | [test_artifact_api.py:640-718](tests/api/test_artifact_api.py:640) | ✅ mostly (add `/versions` to the cross-project loop — Task 1.4) |
| `artifact_change` broadcast on update + delete | [artifacts.py:382-392,421-431](src/ai_qa/api/artifacts.py:382) | ✅ done (FROZEN — 10.6 owns) |
| Typed API client `apiFetch<T>(path, { method, body })` (DELETE 204 → empty body OK) | [api.ts:70-136](frontend/src/lib/api.ts:70) | ✅ done |
| `ArtifactPreview` panel (`{ artifact, onClose }`, "Close preview" button) | [ArtifactPreview.tsx:1-95](frontend/src/components/artifacts/ArtifactPreview.tsx:1) | ✅ done (extend in place) |
| Artifact-tree fetch + refresh trigger (`fetchArtifactTree`, `artifactRefreshTrigger`) | [artifacts.ts:30](frontend/src/lib/artifacts.ts:30), [App.tsx:393-429](frontend/src/App.tsx:393) | ✅ done (10-7) |
| Mutation-wrapper pattern (`method: "POST"/"DELETE"` via `apiFetch`): POST-with-body = `createAdminProject` ([projects.ts:33-40](frontend/src/lib/projects.ts:33)) / `createThread` ([threads.ts:13](frontend/src/lib/threads.ts:13)); DELETE-204 = `deleteAdminProject` ([projects.ts:55-59](frontend/src/lib/projects.ts:55)) / `removeProjectMembership` ([projects.ts:74-82](frontend/src/lib/projects.ts:74)) | (note: there is **no** `createProject`/`deleteProject`/`createThread` in `projects.ts`) | ✅ reuse this shape |

### The gaps THIS story must close

| Gap | Today | Required (AC) |
| --- | ----- | ------------- |
| **No edit UI** | `ArtifactPreview` is read-only (renders content, "Close" only) | An "Edit" affordance → editable text surface → "Save"/"Cancel"; Save calls `POST …/versions`, then reloads the preview to the new version (AC1) |
| **No delete UI** | no delete control anywhere (sidebar rows = click-to-preview; preview header = title + Close) | A "Delete" affordance **with a confirm step** → `DELETE …/{id}`; on success close the preview + refresh the tree (AC3) |
| **No version-metadata display** | preview header shows `kind · v<version>` (+ creator/updater after 10-3) | Surface the version count / "v{n}" and (optionally) the version list from `ArtifactDetailResponse.versions` so AC2's preserved history is visible (AC2) |
| **No `lib/artifacts.ts` mutation wrappers** | only `fetchArtifactTree` exists | Add `updateArtifactContent(projectId, artifactId, content, encoding)` (POST /versions) and `deleteArtifact(projectId, artifactId)` (DELETE), mirroring `lib/projects.ts` |
| **Self-echo of the 10-8 notice** | the open artifact's own update/delete event triggers the 10-8 "newer version / deleted" notice | When **you** edit/delete the open artifact, do not surface the stale-content notice for your own action — reload (edit) or close (delete) optimistically; keep 10-8's EXTERNAL-change behavior intact (see **the self-echo trap**) |
| **Stale pre-impl delete STUBS tagged for this story** | `tests/api/test_artifact_api.py:412-599` has **5 `test_artifact_delete_*`** tests under `# --- [P2] Story 10.4: Artifact Delete ---` that **never call `DELETE`** (they assert pre-delete state); `test_artifact_delete_storage_cleanup` even asserts `storage.deleted == []` (the **opposite** of shipped `delete_artifact`). `tests/api/test_artifact_events.py:301` `test_artifact_change_event_emitted_on_delete` is the same — a stub that GETs an empty list, never deletes. | **Reconcile** (Task 1.2/1.6): upgrade these stubs to real `DELETE` assertions (call DELETE, assert 204 + subsequent `GET → 404` + storage actually cleaned) or remove the dead ones — do NOT leave them asserting pre-delete/opposite state |
| **Backend positive-path test gaps** | leak-canary (negative) + same-member version test exist; no **cross-member** positive edit/delete, no direct `delete_artifact` **unit** test | Add: member **B** (not creator **A**) edits + deletes A's artifact successfully (AC1/AC3 positive); `delete_artifact` unit test (removes artifact + versions + storage) |

### FROZEN CONTRACTS — DO NOT change (you will break shipped 10-1 / 10-6 / 10-7 / 10-8)

- **The two mutation endpoints' paths/methods/status/bodies:** `POST …/{artifact_id}/versions` (200 → `ArtifactResponse`) and `DELETE …/{artifact_id}` (204). `ArtifactVersionCreateRequest` field names/types. Additive only — do not repurpose, rename, or add a new mutation route.
- **`ArtifactChangeEvent`** shape and the `created`/`updated`/`deleted` (past-tense) `change_type` values, and the `broadcast_artifact_change` calls on create/update/delete ([artifacts.py:382-392,421-431](src/ai_qa/api/artifacts.py:382)). **Story 10.6 owns events.** Do not add/move/duplicate a broadcast; the existing update/delete events already fire — the frontend just consumes them.
- **`ArtifactResponse` / `ArtifactDetailResponse` / `ArtifactVersionSummary` field names + types** — additive only. `storage_path` must never appear in any response (leak-canary enforced).
- **`ArtifactPreview` props `{ artifact, onClose }`, the `<h3>{artifact.name}</h3>` header node, and the `"Close preview"` button + `aria-label`** — clicked verbatim by 10-8 ([story-10-8:432](frontend/e2e/story-10-8-artifact-notice.spec.ts:432)). Keep them. Add edit/delete controls **alongside** Close — do not replace or rename it.
- **`artifactNoticeTypeFor` + the 10-8 notice wiring** ([App.tsx:189-199,404-429](frontend/src/App.tsx:189)) — 10-8 e2e asserts the notice on an **external** update/delete. Self-echo suppression must NOT change the external-change behavior those tests cover.
- **The sidebar artifact-row name text node + `getByText("<filename>")` → preview flow** ([ProjectSidebar.tsx:499-503](frontend/src/components/conversations/ProjectSidebar.tsx:499)) — frozen for 10-7/10-8. If you add a per-row delete affordance, keep the name its own standalone text node (mirror `ThreadRow`'s archive button pattern — [ProjectSidebar.tsx:272-283](frontend/src/components/conversations/ProjectSidebar.tsx:272)).
- **`ARTIFACT_KINDS`, `build_artifact_key` storage layout, the `Artifact`/`ArtifactVersion` schema** — untouched. **No new column, no soft-delete flag, no schema change, no Alembic migration** in this story.

---

## ✅ RESOLVED DECISIONS (D1, D2 confirmed by Thuong 2026-06-11; D3-D5 accepted defaults)

These are baked into the tasks. D1 + D2 were explicitly confirmed by Thuong; D3-D5 stand as the accepted defaults (mechanical — re-decide only if needed during dev).

- **D1 — Editable kinds = text-based only. ✅ CONFIRMED.** Inline edit (a `<textarea>`/code surface seeded with the current `/content` text) is offered for text kinds: `requirements`, `testcase`, `markdown`, `report`, `raw_html`, `mermaid`, `playwright_script`, `testscript`. **`image`/`screenshot` are NOT inline-editable** (base64 binary; editing bytes in a textarea is nonsensical) — for those, offer delete only and hide/disable the Edit control. Save sends `content_encoding: "text"`.
- **D2 — Delete (and Edit) live in the `ArtifactPreview` header. ✅ CONFIRMED.** A `Trash2` icon button next to "Close preview" (`aria-label="Delete artifact"`) → opens a small **confirm** affordance (inline confirm or dialog: "Delete '{name}'? This cannot be undone.") → `DELETE`. A sidebar-row delete is **out-of-scope** for MVP. Rationale: deletion is a deliberate action taken while viewing; the preview already owns the open-artifact lifecycle (10-8).
- **D3 — Edit is a mode toggle inside the preview.** A `Pencil` "Edit" button (`aria-label="Edit artifact"`) swaps the rendered body for a textarea pre-filled with current content; "Save"/"Cancel" buttons appear. Save → `POST …/versions` → on success, exit edit mode and **reload the content** (refetch `/content` or use the returned `current_version` + re-fetch) so the preview shows the new version immediately. Cancel discards local edits.
- **D4 — Self-echo suppression.** Track the artifact id of the user's own in-flight mutation. When the resulting `artifact_change` event echoes back for that id+type, **suppress the 10-8 notice for the self-initiated change** (the edit already reloaded the view; the delete already closed it). Keep the notice firing for **external** changes (different originator) — the 10-8 e2e drives external mutations via the admin token, so they must still notify. Simplest robust approach: on successful self-delete, `setSelectedArtifact(null)` immediately (the `eventArtifactId === selectedArtifact?.id` guard then fails → no notice); on successful self-edit, reload content and set a short-lived "suppress next update notice for this id" flag. **Clear that flag deterministically** — when the matching `updated` event is consumed AND on a short fallback timeout (~2-3s) and on artifact-selection change — so a dropped/never-arriving echo can't leave it armed and swallow a *later, genuine* external-update notice. (Comparing the post-save `current_version` returned by `POST …/versions` against the event can make the match precise.)
- **D5 — Version metadata visibility (AC2).** At minimum keep `· v{current_version}` in the header (already present). **Optionally** render a compact, collapsible "Version history" list from `ArtifactDetailResponse.versions[]` (each row: `v{n}` · `created_at` only) — read-only, **no rollback control** (out of MVP). **Note:** `ArtifactVersionSummary` ([artifacts.py:47-58](src/ai_qa/api/artifacts.py:47)) exposes `created_by_user_id` but **no resolved display name** — surfacing a per-version *updater name* would require new backend resolution and is **out of scope**; do not promise an updater name per version row. Default: show the version count + the latest-updated metadata (already covered by 10-3's creator/updater header); add the collapsible list only if low-cost. No new endpoint — reuse `GET …/{artifact_id}`.

---

## Tasks / Subtasks

- [ ] **Task 1 — Confirm + harden the backend edit/delete/version path (AC1, AC2, AC3) — no new endpoint, no migration**
  - [ ] 1.1 Verify (read, don't rebuild): `POST …/{artifact_id}/versions` and `DELETE …/{artifact_id}` are both gated by `ProjectAccessDependency` with the `project.id != project_id` guard + `404`/`RESOURCE_NOT_FOUND_DETAIL` on miss; `create_version` sets `updated_by_user_id` + appends an `ArtifactVersion`; `delete_artifact` cascades versions + cleans storage ([artifacts.py:365-433](src/ai_qa/api/artifacts.py:365), [service.py:133-225](src/ai_qa/artifacts/service.py:133)). State "verified, unchanged" in the Dev Agent Record. **Do not add a route or column.**
  - [ ] 1.2 **AC1/AC3 cross-member positive test (gap):** add a backend test where member **B** (not creator **A**, same project) successfully `POST`s a new version of A's artifact (asserts `current_version == 2`, `updated_by_user_id == B.id`) **and** `DELETE`s it (204; subsequent `GET …/{id}` → 404). Proves "authorized by membership, not creator". Reuse the `artifact_client` fixture + helpers: `_create_user` ([:108](tests/api/test_artifact_api.py:108)), `_create_project` ([:128](tests/api/test_artifact_api.py:128)), `_add_membership` ([:146](tests/api/test_artifact_api.py:146)), `_auth_headers` ([:188](tests/api/test_artifact_api.py:188)).
  - [ ] 1.3 **`delete_artifact` unit test (gap):** in [test_artifact_service.py](tests/unit/test_artifact_service.py), add a test that `delete_artifact` returns `True`, removes the `Artifact` + all `ArtifactVersion` rows, calls `storage.delete` for each version path, and returns `False` for an unknown/cross-project id. Follow the existing `create_version`-test style — e.g. `test_artifact_service_create_version_is_project_scoped` ([:316](tests/unit/test_artifact_service.py:316)) — with `LocalArtifactStorage` on a tmp path or a fake storage spy.
  - [ ] 1.4 Leak-canary: the non-member canary ([:640-686](tests/api/test_artifact_api.py:640)) already covers `DELETE` + `/versions`; the **cross-project-member** canary ([:689-718](tests/api/test_artifact_api.py:689)) covers list/detail/content/`DELETE` but **omits `/versions`** — add a `("post", …/versions)` row to its method/path loop (mirroring the existing value-level `_no_storage_leak` assertion) so the cross-project edit path is also proven leak-free.
  - [ ] 1.5 **No schema change, no Alembic migration** — state this explicitly in the DoD (version metadata is already modeled by 10-1).
  - [ ] 1.6 **Reconcile the stale pre-implementation delete stubs (do not leave them asserting pre-delete/opposite state).** Five tests under `# --- [P2] Story 10.4: Artifact Delete ---` ([test_artifact_api.py:412-599](tests/api/test_artifact_api.py:412)) — `..._removes_consistently_from_metadata_and_storage` (412), `..._cascades_to_versions` (456), `..._requires_membership` (501), `..._removes_from_listing` (534), `..._storage_cleanup` (567) — were written before 10-1 shipped delete and **never call `DELETE`**; `..._storage_cleanup` asserts `storage.deleted == []` (line 599), the **opposite** of the shipped behavior. Likewise `test_artifact_change_event_emitted_on_delete` ([test_artifact_events.py:301](tests/api/test_artifact_events.py:301)) GETs an empty list and never deletes. **Upgrade each to a real assertion** (call `DELETE`, assert 204, assert subsequent `GET → 404`, assert the fake storage's `deleted`/`contents` reflect cleanup, assert versions gone, assert the `deleted` event fired) **or delete the redundant ones** — folding the AC1/AC3 positive coverage from Task 1.2 into them where sensible. Leaving them as-is = misleading "delete coverage" that proves nothing.

- [ ] **Task 2 — Frontend artifact mutation wrappers (`lib/artifacts.ts`)**
  - [ ] 2.1 Add `updateArtifactContent(projectId: string, artifactId: string, content: string, encoding: "text" | "base64" = "text"): Promise<Artifact>` → `apiFetch<Artifact>(\`/projects/${projectId}/artifacts/${artifactId}/versions\`, { method: "POST", body: JSON.stringify({ content, content_encoding: encoding }) })`. Mirror the POST-with-body shape of `createAdminProject` ([projects.ts:33-40](frontend/src/lib/projects.ts:33)) or `createThread` ([threads.ts:13](frontend/src/lib/threads.ts:13)). (There is no `createProject` in `projects.ts` — don't search for it.)
  - [ ] 2.2 Add `deleteArtifact(projectId: string, artifactId: string): Promise<void>` → `apiFetch<void>(\`/projects/${projectId}/artifacts/${artifactId}\`, { method: "DELETE" })` (204 returns empty body — `apiFetch` handles it). Mirror the DELETE-204 shape of `deleteAdminProject` ([projects.ts:55-59](frontend/src/lib/projects.ts:55)) or `removeProjectMembership` ([projects.ts:74-82](frontend/src/lib/projects.ts:74)). (There is no `deleteProject` in `projects.ts`.)
  - [ ] 2.3 Keep `apiFetch`'s `Content-Type: application/json` auto-set (it only adds the header when `body` is present — DELETE with no body is correct).

- [ ] **Task 3 — Frontend: Delete UI in `ArtifactPreview` (AC3, D2)**
  - [ ] 3.1 Add a `Trash2` icon button to the preview header **next to** (not replacing) "Close preview", `aria-label="Delete artifact"`. Clicking it opens an inline confirm (or a small dialog) with the artifact name and a destructive "Delete"/"Cancel" pair. Use `getByRole("button", { name: ... })`-friendly labels.
  - [ ] 3.2 On confirm → call `deleteArtifact(artifact.project_id, artifact.id)`. On success: call `onClose()` (clears `selectedArtifact`) **and** trigger a tree refresh. **Wiring:** add an optional `onDeleted?: () => void` (or reuse `onClose` + let the echoed `deleted` event bump `artifactRefreshTrigger`). Surface a transient error in the existing error block on failure (no crash, preview stays open).
  - [ ] 3.3 Self-echo (D4): because `onClose()` sets `selectedArtifact = null` synchronously, the echoed `deleted` event's `eventArtifactId === selectedArtifact?.id` guard fails → the 10-8 delete notice does not fire for your own delete. Confirm this holds; if there's a race, add an explicit suppress flag. **Do not** alter `artifactNoticeTypeFor` or the external-delete path (10-8).
  - [ ] 3.4 Disable/hide the Delete confirm while a delete is in flight (avoid double-submit). Keep "Close preview" working throughout.

- [ ] **Task 4 — Frontend: Edit mode in `ArtifactPreview` (AC1, D1, D3)**
  - [ ] 4.1 Add a `Pencil` "Edit" button (`aria-label="Edit artifact"`) to the header, shown **only for editable kinds** (D1: text kinds; hidden for `image`/`screenshot`). Clicking enters edit mode.
  - [ ] 4.2 In edit mode: render a `<textarea>` (or lightweight code area) seeded with the loaded `content`; replace the rendered body. Show "Save" + "Cancel". Cancel exits edit mode discarding local changes. Preserve the loading/error states.
  - [ ] 4.3 Save → `updateArtifactContent(artifact.project_id, artifact.id, editedText, "text")`. On success: exit edit mode, set the new `version` from the response (`current_version`), and reload the body (re-fetch `/content` or set `content = editedText`) so the preview shows the saved version. On failure: stay in edit mode, surface the error, keep the user's text.
  - [ ] 4.4 Self-echo (D4): your own edit broadcasts `updated`, which (since the artifact is still selected) would pop the 10-8 "newer version available" notice for your own save. Suppress it for the self-initiated update (e.g. a ref holding the last self-updated `{id}`, consumed by the next matching event), while leaving the **external**-update notice (10-8) intact. **Clear the suppress ref deterministically** — on consuming the matching event, on a ~2-3s fallback timeout, and on selection change — so a dropped echo can't later swallow a real external notice. Keep the change minimal and well-commented.
  - [ ] 4.5 Compose with 10-3's kind-aware rendering: edit mode only swaps the **body**; the header (`<h3>` name, kind·version, creator/updater, Close) is unchanged. For `mermaid`/scripts, editing the raw source text is correct (re-renders on save).

- [ ] **Task 5 — Frontend: version-metadata visibility (AC2, D5)**
  - [ ] 5.1 Keep `· v{current_version}` in the header. **Optional (low-cost):** add a collapsible read-only "Version history" from `GET …/{artifact_id}` (`ArtifactDetailResponse.versions[]`) — each row `v{n} · {created_at}` (the summary has **no per-version display name** — do not render an updater name here; see D5). **No rollback control** (out of MVP). Reuse the sidebar `Intl.DateTimeFormat` pattern ([ProjectSidebar.tsx:472-477](frontend/src/components/conversations/ProjectSidebar.tsx:472)).
  - [ ] 5.2 If 5.1 is deferred as not-low-cost, ensure the post-edit version bump is visible in the header (the `· v{n}` increments) so AC2's "previous version preserved + new one created" is observable. Record the choice.

- [ ] **Task 6 — Full-stack sync + typecheck**
  - [ ] 6.1 Reuse the existing `Artifact` interface ([ProjectSidebar.tsx:39-53](frontend/src/components/conversations/ProjectSidebar.tsx:39)) — no new fields needed for edit/delete. If exposing version rows in the UI (D5), add a minimal `ArtifactVersionSummary` TS interface in `lib/artifacts.ts` matching the backend ([artifacts.py:47-58](src/ai_qa/api/artifacts.py:47)).
  - [ ] 6.2 Run `npm run typecheck` in `frontend/` (strict — Vite skips errors).

- [ ] **Task 7 — Tests + verification (DoD)**
  - [ ] 7.1 **Backend** — Task 1.2 cross-member positive + Task 1.3 delete unit test; confirm existing leak-canary + version tests green. `uv run pytest` for the artifact suites.
  - [ ] 7.2 **Frontend unit (Vitest)** — `ArtifactPreview`:
    - Delete: clicking Delete → confirm → calls `deleteArtifact` (mock `apiFetch`) and invokes `onClose`/refresh; cancel does nothing.
    - Edit: Edit button hidden for `image`/`screenshot`, shown for text kinds; Save calls `updateArtifactContent` with the edited text and reloads; Cancel restores the rendered view.
    - Mock `apiFetch` (no network). Match the style in [ReviewContent.test.tsx](frontend/src/components/__tests__/ReviewContent.test.tsx) or [App.test.tsx](frontend/src/App.test.tsx) (note: `App.test.tsx` sits at `frontend/src/App.test.tsx`, next to `App.tsx` — not under `components/__tests__/`).
  - [ ] 7.3 **Frontend e2e** — shipped `story-10-7` + `story-10-8` stay **green and unedited** (10-4 must not regress the external-change notice/refresh). Optionally add a focused `story-10-4-artifact-edit-delete.spec.ts`: create an artifact via the real API, open it, edit + save (assert `v2` / new content), then delete (assert preview closes + the row disappears from the sidebar tree). No `page.route` mocking; real-API state; `afterEach` cleanup of users/projects/artifacts via admin token (incl. SeaweedFS bytes).
  - [ ] 7.4 Run the full gate (Definition of Done) and paste results into the Dev Agent Record.

### Review Findings
- [x] [Review][Patch] Missing implementation code for Story 10.4 — The diff contains absolutely no code implementation for Story 10.4. The backend and frontend tasks outlined in the spec (e.g., `updateArtifactContent`, `deleteArtifact`, `ArtifactPreview` modifications) are absent. Only tests for other stories and markdown specs for Epic 11 are present.

---

## Dev Notes

### Architecture & module layout (authoritative)

- **Artifacts are project-level shared resources** ([architecture.md:331](_bmad-output/planning-artifacts/architecture.md:331)): "Any assigned project member can list, read, **edit, and delete** artifacts from other users in that project, subject to role/assignment checks." → AC1/AC3 are authorized by **membership, not creator ownership**. The backend already enforces exactly this; do not add a creator-only gate.
- **Artifact UX includes an editor** ([architecture.md:262,614,760-761](_bmad-output/planning-artifacts/architecture.md:262)): "browse/open/edit/delete shared artifacts… regardless of creator"; the artifacts UI is "tree, editor, preview notices". This story delivers the edit/delete surface in `ArtifactPreview`.
- **Version rollback is OUT of MVP** ([architecture.md:245,381,1050](_bmad-output/planning-artifacts/architecture.md:245)) — AC2's "rollback behavior is not implemented in MVP". Show history read-only; never add a rollback/restore control.
- **Events are 10.6's territory** ([architecture.md:377-381](_bmad-output/planning-artifacts/architecture.md:377)): the backend already emits change events on create/update/delete; 10-4 must not add or modify them. Direct external SeaweedFS notifications are out of MVP (AC3).
- **Path discrepancy to respect** (same as 10-1/10-2/10-3): the architecture names `src/ai_qa/api/routes/artifacts.py` and `frontend/src/features/artifacts/` ([architecture.md:760-761](_bmad-output/planning-artifacts/architecture.md:760)) — **neither exists.** Edit the actual files: [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py), [frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx), [frontend/src/lib/artifacts.ts](frontend/src/lib/artifacts.ts). Do not create new module trees.

### Why no new backend endpoint or migration

AC1 (edit via versions), AC2 (immutable version history), and AC3 (delete + storage cleanup) are fully implemented and tested by **Story 10-1** (verified at HEAD `90d3f6f` — `create_version`, `delete_artifact`, the two routes, `ArtifactVersion` schema, the `updated`/`deleted` broadcasts, and the leak-canary all exist). The version-metadata model already preserves `version`/`content_hash`/`storage_path`/`created_by_user_id`/`created_at` per edit. Adding a route, a soft-delete column, or a migration would duplicate a frozen, tested contract. The gap is **client-side UX** + a couple of **positive-path tests**.

### Frontend current state (what you are editing)

> The working tree carries 10-2's uncommitted changes (tree endpoint + `lib/artifacts.ts`). 10-3 (preview rendering) is `ready-for-dev` and will reshape `ArtifactPreview` before this story. **Re-read these files at story start.**

- `ArtifactPreview` ([ArtifactPreview.tsx:1-95](frontend/src/components/artifacts/ArtifactPreview.tsx:1)) — fetches `/content`, stores `content`/`version`, renders via `ReviewContent`, header = name + `kind · v{version}` + "Close preview". **No edit/delete controls.** (After 10-3: kind-aware body + `content_encoding` + creator/updater header.)
- `lib/artifacts.ts` ([artifacts.ts:1-33](frontend/src/lib/artifacts.ts:1)) — only `fetchArtifactTree`; **no mutation wrappers** (add them — Task 2).
- `App.tsx` ([App.tsx:393-429,1585-1591](frontend/src/App.tsx:393)) — owns `selectedArtifact`, mounts `ArtifactPreview` with `onClose={() => setSelectedArtifact(null)}`, bumps `artifactRefreshTrigger` on `artifact_change`, and pops the 10-8 notice when the **open** artifact's event arrives. The delete/edit flows must integrate here (close on self-delete; suppress self-echo notice).
- `ProjectSidebar` ([ProjectSidebar.tsx:457-510](frontend/src/components/conversations/ProjectSidebar.tsx:457)) — artifact rows are click-to-preview; the name is a standalone text node (frozen for 10-7/10-8). `ThreadRow` ([:272-301](frontend/src/components/conversations/ProjectSidebar.tsx:272)) shows the hover-affordance pattern if a sidebar delete is added later.
- `apiFetch` ([api.ts:70-136](frontend/src/lib/api.ts:70)) — sets `Content-Type: application/json` only when a `body` is present; parses empty/`204` bodies safely. Use `{ method, body: JSON.stringify(...) }`.

### The self-echo trap (read before wiring edit/delete to the UI)

The backend broadcasts `artifact_change` on **every** successful update/delete, **including your own** ([artifacts.py:382-392,421-431](src/ai_qa/api/artifacts.py:382)). The 10-8 handler shows a notice whenever the **currently-open** artifact's event arrives ([App.tsx:417-425](frontend/src/App.tsx:417)) — it does **not** distinguish self vs. external. So naively wiring edit/delete will make **your own** save pop "a newer version is available" and **your own** delete pop "was deleted" on your screen — confusing.

- **Delete:** call `onClose()`/`setSelectedArtifact(null)` synchronously on success. The echoed `deleted` event's `eventArtifactId === selectedArtifact?.id` guard then fails → no self-notice. (Verify no race; add a suppress flag if needed.)
- **Edit:** after a successful save, reload the body to the new version. To avoid the self "newer version" notice, hold the just-saved `{artifactId}` in a ref and have the notice branch skip the next matching `updated` event for it. Keep this change surgical and commented.
- **Do NOT** change `artifactNoticeTypeFor` or the external-change path. **Accuracy note:** the 10-8 e2e drives a real EXTERNAL **update** via the admin token (`updateArtifact` → `POST …/versions` — [story-10-8:232-238,443-449](frontend/e2e/story-10-8-artifact-notice.spec.ts:232)) and soft-asserts the update notice; its "delete" test ([story-10-8:289-363](frontend/e2e/story-10-8-artifact-notice.spec.ts:333)) is a **simulated stub that never issues a real `DELETE`** ("Note: the current API may not have a delete endpoint… we simulate this") — so the external-**delete**-notice path is **not actually exercised by e2e today.** Scope self-echo suppression to self-initiated mutations only, and keep `artifactNoticeTypeFor` intact. **Recommended:** have the optional Task 7.3 `story-10-4` spec cover a *real* external delete (admin-token `DELETE` while a second user views) so the external-delete notice path your self-echo logic depends on is finally protected. Do **not** edit `story-10-8` (keep it green/unedited per scope).

### Authorization model (unchanged from 10-1)

Reuse `require_project_member_or_admin` → `ProjectAccessDependency` ([projects.py:79](src/ai_qa/api/projects.py:79)). Admins pass; **any** project member may edit/delete (project-shared model — not creator-restricted); non-members → `404` `RESOURCE_NOT_FOUND_DETAIL` (404-not-403 intentional). Service queries stay project-scoped. No secrets/PII (incl. `email`/`storage_path`) in any response — leak-canary covers it.

### Anti-patterns to avoid (FORBIDDEN)

- Adding a new edit/delete/version endpoint, rebuilding `create_version`/`delete_artifact`/`ArtifactVersionCreateRequest`, adding a soft-delete column or a rollback feature (duplicates frozen, tested 10-1 work; rollback is explicitly out of MVP).
- **Adding, moving, renaming, or re-firing any `artifact_change` broadcast** — Story 10.6 owns events; update/delete already broadcast. Touching the `ArtifactChangeEvent` shape or the past-tense `change_type` values breaks 10-7/10-8.
- Changing `artifactNoticeTypeFor`, the external-change notice path, the `"Close preview"` button/`aria-label`, the `ArtifactPreview` `{ artifact, onClose }` props, the `<h3>{name}</h3>` node, or the sidebar artifact-name text node (breaks shipped 10-7/10-8 e2e).
- Making `image`/`screenshot` inline-editable (binary base64 in a textarea is meaningless — D1: delete-only for those).
- Editing any artifact with `dangerouslySetInnerHTML` or rendering `raw_html` as live HTML (XSS) — edit/preview `raw_html` as **text**.
- A schema change / Alembic migration in this story; `pip` (use `uv`); installing frontend deps anywhere but `frontend/` via `npm`; `# type: ignore` / `@ts-ignore`; global lint disables; mixing formatting with logic in one commit.
- Returning creator/updater as bare UUIDs or `email`; leaking `storage_path` in any response.

### Previous-story / brownfield intelligence

- **10-1** shipped the entire edit/delete/version backend + the `updated`/`deleted` broadcasts + the AC3 leak-canary across all routes (incl. `DELETE` + `/versions`). It also corrected the `App.tsx` realtime notice handler (`artifactNoticeTypeFor`, past-tense match) — read [10-1's story](_bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md). The collision-safe nested key scheme (`…/{artifact_id}/v{version}/{name}`) means each version's bytes are retained, so delete must clean **every** version path (it already does).
- **10-2** (prerequisite, `review`) added the tree endpoint + `created_by_display`/`updated_by_display` on `Artifact` + `lib/artifacts.ts`. Reuse its `fetchArtifactTree`/refresh.
- **10-3** (prerequisite, `ready-for-dev`) reshapes `ArtifactPreview` (kind-aware rendering, `content_encoding`, creator/updater header) and adds the `mermaid` dep. 10-4's Edit toggle composes with that body. Read [10-3's story](_bmad-output/implementation-artifacts/10-3-artifact-read-and-preview-access.md) — it documents the frozen preview contracts in detail.
- **10-7 / 10-8** shipped the refresh + open-artifact notice; they are why `ArtifactPreview` props, the "Close preview" label, the name nodes, and the notice wiring are frozen. The 10-8 e2e tests **external** update/delete — keep that path working.
- **Working-tree note:** at authoring time `git status` shows uncommitted 10-2 changes to `artifacts.py`/`service.py`/`storage.py`/test files + untracked `lib/artifacts.ts`. Start from a clean, post-10-2/10-3 tree; don't fold unrelated drift into this story's commits.
- Git: HEAD `90d3f6f` (story 10-1). Re-baseline to the latest landed predecessor (10-2 → 10-3) before starting.

### Latest tech / dependencies

- **No new dependencies.** Reuse the pinned stack: FastAPI 0.115, SQLAlchemy 2.0 (sync `Session` in the artifacts path — [project-context.md] confirms sync session here), Pydantic v2 (backend); React 18.3, TypeScript 5.6, `apiFetch`, `lucide-react` icons (`Trash2`, `Pencil`, `X` already used) (frontend). `uv` only for backend; `npm` only inside `frontend/`. (10-3 adds `mermaid` — not this story's concern.)

### Testing requirements

- **Backend (pytest):** in-memory SQLite via the `artifact_client` fixture + helpers `_create_user` ([:108](tests/api/test_artifact_api.py:108)), `_add_membership` ([:146](tests/api/test_artifact_api.py:146)), `_auth_headers` ([:188](tests/api/test_artifact_api.py:188)); `cast(FastAPI, client.app)` for overrides; override `get_artifact_storage` to `LocalArtifactStorage(tmp_path)` or a fake; `engine.dispose()` in teardown; no bare `pytest.raises(Exception)` (specific type + `match=`).
- **No migration in this story** — no schema change.
- **Frontend (Vitest):** mock `apiFetch`; assert method/body of the edit (`POST …/versions`) and delete (`DELETE`) calls; follow [ReviewContent.test.tsx](frontend/src/components/__tests__/ReviewContent.test.tsx) / `App.test.tsx`. `npm run typecheck` after TS changes.
- **Frontend (Playwright):** keep 10-7/10-8 green **unedited** (no authorized e2e edits in this story); no `page.route`; real-API state; `afterEach` cleanup of users/projects/artifacts (incl. SeaweedFS bytes via admin token). Use accessible selectors (`getByRole("button", { name: "Delete artifact" | "Edit artifact" | "Save" | "Close preview" })`).

### Project Structure Notes

Touch points (extend existing files; the only new files are tests + optional e2e spec):

- [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py) — **verify only**, no change expected (edit/delete/version routes already correct).
- [src/ai_qa/artifacts/service.py](src/ai_qa/artifacts/service.py) — **verify only** (`create_version`/`delete_artifact` already correct).
- [tests/api/test_artifact_api.py](tests/api/test_artifact_api.py) — add the AC1/AC3 cross-member positive edit+delete test.
- [tests/unit/test_artifact_service.py](tests/unit/test_artifact_service.py) — add the `delete_artifact` positive/negative unit test.
- [frontend/src/lib/artifacts.ts](frontend/src/lib/artifacts.ts) — add `updateArtifactContent` + `deleteArtifact` wrappers (+ optional `ArtifactVersionSummary` type).
- [frontend/src/components/artifacts/ArtifactPreview.tsx](frontend/src/components/artifacts/ArtifactPreview.tsx) — Edit mode (text kinds), Delete + confirm, optional version-history list; compose with 10-3's body.
- [frontend/src/App.tsx](frontend/src/App.tsx) — minimal self-echo suppression for self-initiated edit/delete (do not break the external-change path).
- [frontend/src/components/artifacts/__tests__/](frontend/src/components/artifacts/) — Vitest for `ArtifactPreview` edit/delete.
- Optional new [frontend/e2e/story-10-4-artifact-edit-delete.spec.ts](frontend/e2e/story-10-4-artifact-edit-delete.spec.ts).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-10.4] (lines 846-867) — the three ACs (edit→version+updater; preserved version metadata, no rollback; delete consistent in metadata+storage, no external SeaweedFS notify).
- [Source: _bmad-output/planning-artifacts/prd.md] — FR45 (artifact ownership/metadata/version metadata), FR46 (members list/read/**edit/delete**), FR52 (browse/open/edit/delete regardless of creator). FR61-FR66 (events/notices) are 10.6/10.7/10.8 — out of scope here.
- [Source: _bmad-output/planning-artifacts/architecture.md] — lines 245/381/1050 (version rollback out of MVP), 262 (browse/open/edit/delete regardless of creator), 331 (project-shared edit/delete authz), 377-381 (change events are 10.6; reload/close notice; external SeaweedFS notify out of MVP), 614/760-761 (artifacts UI = tree/editor/preview; architecture-vs-actual paths).
- [Source: src/ai_qa/api/artifacts.py:153-157,365-433] — `ArtifactVersionCreateRequest`; `DELETE` + `POST …/versions` routes (membership-gated, broadcast); the frozen mutation surface.
- [Source: src/ai_qa/artifacts/service.py:133-225] — `create_version` (row lock, version++, updater, append version, storage write, rollback-on-failure); `delete_artifact` (cascade + storage cleanup).
- [Source: src/ai_qa/db/models.py:125-177] — `Artifact` (no soft-delete column; SET NULL creator/updater) + `ArtifactVersion` (immutable history; `uq(artifact_id, version)`).
- [Source: tests/api/test_artifact_api.py] — helpers `_create_user` ([:108](tests/api/test_artifact_api.py:108)), `_create_project` ([:128](tests/api/test_artifact_api.py:128)), `_add_membership` ([:146](tests/api/test_artifact_api.py:146)), `_auth_headers` ([:188](tests/api/test_artifact_api.py:188)); same-member version test ([:229-245](tests/api/test_artifact_api.py:229)); **stale `[P2] Story 10.4` delete STUBS that never call DELETE** ([:412-599](tests/api/test_artifact_api.py:412) — Task 1.6); AC3 leak-canary non-member all-routes ([:640-686](tests/api/test_artifact_api.py:640)) + cross-project member (list/detail/content/DELETE, no `/versions`) ([:689-718](tests/api/test_artifact_api.py:689)); ownership-field + no-storage-leak ([:721-784](tests/api/test_artifact_api.py:721)). Positive cross-member edit/delete is the gap.
- [Source: tests/unit/test_artifact_service.py] — `test_artifact_service_appends_versions_without_mutating_history` ([:128](tests/unit/test_artifact_service.py:128), AC2); `test_artifact_service_cleans_version_file_when_commit_fails` ([:283](tests/unit/test_artifact_service.py:283)); `test_artifact_service_create_version_is_project_scoped` ([:316](tests/unit/test_artifact_service.py:316)). Direct `delete_artifact` unit test is the gap.
- [Source: tests/api/test_artifact_events.py:301] — `test_artifact_change_event_emitted_on_delete` is a pre-impl STUB (GETs empty list, never deletes) — reconcile in Task 1.6.
- [Source: frontend/src/lib/artifacts.ts:1-33] — `fetchArtifactTree` (add `updateArtifactContent`/`deleteArtifact` wrappers here); [frontend/src/lib/projects.ts](frontend/src/lib/projects.ts) — `createAdminProject` ([:33-40](frontend/src/lib/projects.ts:33), POST) + `deleteAdminProject` ([:55-59](frontend/src/lib/projects.ts:55), DELETE) are the real wrapper exemplars (no `createProject`/`deleteProject` exist); `createThread` is in [threads.ts:13](frontend/src/lib/threads.ts:13).
- [Source: frontend/src/components/artifacts/ArtifactPreview.tsx:1-95] — read-only preview to extend (Edit/Delete); [frontend/src/components/artifacts/ArtifactNotice.tsx:1-88] — 10-8 notice (auto-dismiss 10s, Dismiss only — informational; not 10-4's to change).
- [Source: frontend/src/App.tsx:189-199,393-429,1585-1591] — `artifactNoticeTypeFor`; `selectedArtifact`; `artifactRefreshTrigger`; self-echo integration point; preview mount.
- [Source: frontend/src/components/conversations/ProjectSidebar.tsx:39-53,272-301,457-510] — `Artifact` interface; `ThreadRow` hover-affordance pattern; artifact rows (frozen name node).
- [Source: frontend/e2e/story-10-8-artifact-notice.spec.ts] — external **update** notice e2e is real (`updateArtifact` → `POST …/versions` via admin token — [:232-238](frontend/e2e/story-10-8-artifact-notice.spec.ts:232), [:443-449](frontend/e2e/story-10-8-artifact-notice.spec.ts:443)); the external **delete** test ([:289-363](frontend/e2e/story-10-8-artifact-notice.spec.ts:333)) is a **simulated stub that never issues a real DELETE**. Must stay green/unedited; informs self-echo scoping and the Task 7.3 recommendation to add a real external-delete e2e.
- [Source: project-context.md] — `uv`/`npm` boundaries; Ruff + Mypy strict; sync session in artifacts; no PII/secrets in responses; full-stack TS sync; E2E no `page.route`, `afterEach` cleanup; no `dangerouslySetInnerHTML`/`@ts-ignore`.

### Definition of Done

- [ ] AC1-AC3 satisfied; all seven tasks complete (incl. Task 1.6 stub reconciliation); D1-D5 honored (or explicitly re-decided by Thuong).
- [ ] Backend edit/delete/version path confirmed unchanged (no new route, no column, **no Alembic migration**); **AC1/AC3 cross-member positive test** (member B edits + deletes member A's artifact) added and green; **`delete_artifact` unit test** added and green; **the stale `[P2] Story 10.4` delete stubs reconciled** (Task 1.6 — `test_artifact_api.py:412-599` + `test_artifact_events.py:301` now call DELETE and assert real post-delete state, or are removed — none left asserting `storage.deleted == []`); AC3 leak-canary still green for `DELETE` + `/versions` (cross-project `/versions` row added).
- [ ] Frontend: editable text kinds get an Edit mode that saves a new version via `POST …/versions` and reloads to the new version; `image`/`screenshot` are not inline-editable (D1). Delete is available with a confirm step, calls `DELETE`, closes the preview, and refreshes the tree (AC3). Version bump (`· v{n}`) is visible; optional read-only version history has **no rollback control** (AC2).
- [ ] Self-echo handled: your own edit/delete does **not** pop the 10-8 stale/deleted notice; **external** update/delete still notifies (10-8 e2e green, unedited).
- [ ] Frozen contracts intact: mutation endpoints/bodies, `ArtifactChangeEvent` + broadcasts (10.6), `ArtifactResponse`/`ArtifactDetailResponse`/`ArtifactVersionSummary` fields, `ArtifactPreview` props + "Close preview" label + name node, `artifactNoticeTypeFor` + external-change path, sidebar artifact-name node, `ARTIFACT_KINDS`/`build_artifact_key`/schema.
- [ ] `uv run ruff check .` clean; `uv run mypy` clean (strict); `uv run pytest` green (artifact suites + new tests).
- [ ] `npm run typecheck` clean in `frontend/`; new Vitest (ArtifactPreview edit/delete) green; shipped 10-7/10-8 e2e still green and **unedited**.
- [ ] No new dependency; no rogue root `package.json`.
- [ ] Dev Agent Record updated with file list, commands run, and outputs.

---

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created. Key finding: the **entire backend for AC1/AC2/AC3 already shipped in Story 10-1** (verified at HEAD `90d3f6f`): `POST …/versions` (edit→new version, updater/timestamp), immutable `ArtifactVersion` history (AC2; rollback out of MVP), `DELETE …/{id}` (cascade + storage cleanup), membership authz (any member, not creator), leak-canary across both routes, and the `updated`/`deleted` WebSocket broadcasts (frozen — 10.6 owns). No new endpoint, column, or migration. The real scope is the **frontend edit + delete UX in `ArtifactPreview`** (no edit/delete UI exists today), version-metadata visibility, and **self-echo suppression** so your own edit/delete doesn't trigger the 10-8 stale/deleted notice — while keeping the 10-8 EXTERNAL-change path green. Plus two backend positive-path test gaps (cross-member edit/delete; `delete_artifact` unit test). Decisions: D1 (editable = text kinds only; image/screenshot delete-only) and D2 (Edit/Delete in the ArtifactPreview header, sidebar-row delete out of scope) confirmed by Thuong 2026-06-11; D3-D5 accepted as defaults.

### Commands Run

### File List

### Change Log

- 2026-06-11: Story 10-4 drafted — reconcile + harden. Backend: verification only (edit/delete/version routes, `create_version`/`delete_artifact`, `ArtifactVersion` history, broadcasts, leak-canary all shipped by 10-1) + two positive-path tests (cross-member edit/delete; `delete_artifact` unit). Frontend: add `updateArtifactContent`/`deleteArtifact` wrappers to `lib/artifacts.ts`; add Edit mode (text kinds) + Delete-with-confirm + optional read-only version history to `ArtifactPreview`; self-echo suppression in `App.tsx` so self-initiated edit/delete doesn't fire the 10-8 notice (external path unchanged). Prerequisites: 10-2 (`review`) + 10-3 (`ready-for-dev`) should land first; re-baseline before starting. No schema change / no migration; no new dependency.
- 2026-06-11 (decisions confirmed by Thuong): D1 = editable kinds are text-based only (image/screenshot delete-only); D2 = Edit/Delete live in the `ArtifactPreview` header (sidebar-row delete out of scope). D3-D5 accepted as defaults.
- 2026-06-11 (adversarial review pass — 6-dimension workflow, every finding verified against on-disk code): applied 14 confirmed corrections. **Critical:** added Task 1.6 to reconcile six stale pre-implementation delete STUBS explicitly tagged `[P2] Story 10.4` (`test_artifact_api.py:412-599` ×5 — one asserting `storage.deleted == []`, the opposite of shipped behavior — and `test_artifact_events.py:301`) that never call DELETE; fixed `lib/artifacts.ts` wrapper exemplars (no `createProject`/`deleteProject` exist → `createAdminProject`@33-40 / `deleteAdminProject`@55-59; `createThread` is in `threads.ts:13`). **Accuracy:** corrected the false "10-8 e2e drives external delete" claim (its delete test is a simulated stub; only the external *update* is real → recommended a real external-delete e2e in Task 7.3); dropped the per-version "updater" name from D5/Task 5.1 (`ArtifactVersionSummary` exposes no display name); fixed test-helper citations (`_create_user`@108/`_add_membership`@146/`_auth_headers`@188), service-test lines (→128/283/316), the cross-project leak-canary `/versions` gap, the self-edit suppress-flag lifecycle (deterministic clearing), and the `App.test.tsx` path.
