---
baseline_commit: 589e1f217f17453e3c06b2d2ffe66dea2f8f94d6
---
# Story 15.4: Sort Users Management and Show Project-Admin's Project

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want the Users Management list sorted and annotated,
so that I can scan users by role, status, timezone, and name.

## Acceptance Criteria

1. **Multi-key sort.** Given the Users Management list, when it renders, then users are sorted by role (admin → project_admin → standard → other), then status (active before inactive), then timezone (A→Z), then display name (A→Z).
2. **Show administered project(s).** Given a project_admin user, when the row renders, then the administered project name(s) appear near the role badge (multiple names, comma-joined, if the user admins multiple projects).
3. **Accessible status.** Given the active/inactive status, when it renders, then status is conveyed with text + icon, not color alone, per the design system.

## Tasks / Subtasks

- [x] **Task 1 — Derive a sorted list (AC: 1)** in `frontend/src/components/admin/AdminDashboard.tsx`:
  - [x] Add a `useMemo` over `users` that returns a **sorted copy** (never mutate state) before the `.map` at `:792`.
  - [x] Comparator, in order:
    1. Role rank: `admin → 0`, `project_admin → 1`, `standard → 2`, anything else → `3`.
    2. `is_active` descending (active first): active = 0, inactive = 1.
    3. `timezone` A→Z via `localeCompare`, guard nullish: `(a.timezone ?? "").localeCompare(b.timezone ?? "")`.
    4. `display_name` A→Z via `localeCompare`.
  - [x] Map over the sorted copy.
- [x] **Task 2 — Render administered project name(s) (AC: 2)**:
  - [x] For each user, derive `const adminProjects = u.project_memberships.filter(m => m.role === "project_admin").map(m => m.project_name)`.
  - [x] When `adminProjects.length > 0`, render the comma-joined names near the role badge (`:805-824`), e.g. a small muted span: `Admin of: {adminProjects.join(", ")}`. Only render for project_admin rows (the filter naturally yields `[]` otherwise).
- [x] **Task 3 — Status as text + icon (AC: 3)**:
  - [x] Replace the color-only active/inactive badge (`:811-815`) with text + icon: active → `CheckCircle` (emerald) + "Active"; inactive → `XCircle` (slate/red) + "Inactive". `CheckCircle`/`XCircle` are already imported (`:12-13`). Keep an accessible label.
- [x] **Task 4 — Backend N+1 guard (optional, recommended)**:
  - [x] In `list_users` (`src/ai_qa/api/admin.py:282-289`) add `.options(selectinload(User.memberships).selectinload(ProjectMembership.project))` to avoid per-row project lazy-loads when building `project_memberships`. Import `selectinload`. No response/schema change.
- [x] **Task 5 — Tests (AC: 1-3)**:
  - [x] Frontend (`AdminDashboard.test.tsx`): assert DOM order (admin → project_admin → standard) given a fixture with mixed roles/status/timezone/names; assert a project_admin row shows its project name; assert the status badge renders text ("Active"/"Inactive") not just color.
  - [x] Backend: if Task 4 is done, a light assertion that `list_users` still returns memberships with `project_name` is enough (existing tests likely cover the shape).
  - [x] Run `npm run test`, `npm run typecheck`; `uv run pytest --no-cov tests/api/test_admin_users_api.py` if Task 4 touched the backend.

## Dev Notes

### Data is already available — pure frontend (+ optional backend perf)

`AdminUser.project_memberships` already carries `project_name` and `role` per membership (`frontend/src/types/project.ts:74-94`; backend `_to_admin_user_response`, `src/ai_qa/api/admin.py:257-279`). So both the sort and the project-name display are **client-side** over data already fetched by `listAdminUsers()`. No new endpoint, no type change.

`list_users` (`admin.py:282-289`) currently orders by `User.email`; that server order is irrelevant once the client sorts. Leave the server query's ordering as-is (or drop the `.order_by` — harmless either way); the only worthwhile backend touch is the `selectinload` perf guard (Task 4).

### Sort — implement as a non-mutating `useMemo`

`users` is React state; `Array.prototype.sort` mutates in place. Sort a copy:

```tsx
const ROLE_RANK: Record<string, number> = { admin: 0, project_admin: 1, standard: 2 };
const sortedUsers = useMemo(
  () =>
    [...users].sort((a, b) => {
      const ra = ROLE_RANK[a.role] ?? 3;
      const rb = ROLE_RANK[b.role] ?? 3;
      if (ra !== rb) return ra - rb;
      const aActive = a.is_active ? 0 : 1;
      const bActive = b.is_active ? 0 : 1;
      if (aActive !== bActive) return aActive - bActive;
      const tz = (a.timezone ?? "").localeCompare(b.timezone ?? "");
      if (tz !== 0) return tz;
      return a.display_name.localeCompare(b.display_name);
    }),
  [users],
);
```

Then `sortedUsers.map((u) => …)` instead of `users.map`. Keep the existing `users.length === 0` empty-state.

### Status badge — text + icon (design-system rule)

The current badge (`:811-815`) is color-only (emerald vs red). Per the design system (status = color **+ text + icon**), render an icon plus the word:

```tsx
<span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider ...">
  {u.is_active ? <CheckCircle className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
  {u.is_active ? "Active" : "Inactive"}
</span>
```

`CheckCircle` and `XCircle` are already imported from `lucide-react` (`AdminDashboard.tsx:12-13`).

### Administered-project display

Render comma-joined names — many-to-many means a project_admin may administer several projects (Story 15.3 / RBAC design). Keep it compact and near the role badge so the scan target (role → which project) is one glance. English-only label (e.g. "Admin of: X, Y").

### No UX canonical spec — follow these rules

The admin panel UI is explicitly deferred in the UX spec (Journey 4), so there is no canonical mock. Follow the general design system already used in this file: muted slate for secondary text, `text-[10px]`/`text-xs` badges, English-only labels, status = text + icon (not color alone). Don't introduce new color semantics.

### Coordination with sibling stories (same file)

This story shares `AdminDashboard.tsx` with 15.2 (copy removal), 15.3 (picker), 15.5 (edit/delete). The user-row region (`:791-832`) is also edited by 15.5 (adds Edit/Delete buttons). Keep the sorted-list `useMemo` and the row rendering changes localized; if 15.5 lands first, map over `sortedUsers` consistently. `isAdminUser` (`:793`) stays in use (15.5).

### Pyrefly/TS notes

- `noUncheckedIndexedAccess` is on — but `ROLE_RANK[a.role]` returns `number | undefined`, handled by `?? 3`. Good.
- `useMemo` import: add to the existing `import { useEffect, useState } from "react";` (`:1`) → include `useMemo`.

### Project Structure Notes

- Frontend: `AdminDashboard.tsx` only (sort + render). Optional backend: `admin.py` `list_users` `selectinload`.
- No migration, no type change, no `lib/projects.ts` change.

### References

- [Sprint change proposal — Story D](../planning-artifacts/sprint-change-proposal-2026-06-21.md)
- [Investigation — item 4](investigations/admin-dashboard-project-user-mgmt-investigation.md)
- [Epic 15 / Story 15.4](../planning-artifacts/epics.md) (lines 1648-1666)
- Code: `frontend/src/components/admin/AdminDashboard.tsx:1,12-13,791-832`, `frontend/src/types/project.ts:74-94`, `src/ai_qa/api/admin.py:257-289`
- Tests: `frontend/src/components/admin/AdminDashboard.test.tsx`

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story)

### Debug Log References

- `npm run typecheck` / `npm run lint` → clean; `npm run test src/components/admin/AdminDashboard.test.tsx` → 17 passed.
- `uv run pytest --no-cov tests/api/test_admin_users_api.py` → 16 passed; `uv run mypy src/ai_qa/api/admin.py` → clean; ruff clean.

### Completion Notes List

- **AC1** — Added module-level `ROLE_RANK` and a non-mutating `sortedUsers` `useMemo` (`[...users].sort`) keyed role (admin→project_admin→standard→other) → status (active first) → timezone (`localeCompare`, nullish-guarded) → display_name. The list now maps over `sortedUsers`; the `users.length === 0` empty-state is unchanged.
- **AC2** — Per row, `adminProjects = project_memberships.filter(role==="project_admin").map(project_name)`; when non-empty, a muted "Admin of: X, Y" span renders beside the badges (comma-joined for many-to-many). The badge row got `flex-wrap`.
- **AC3** — The active/inactive badge now renders `CheckCircle`/`XCircle` (already imported) + the word "Active"/"Inactive" (text + icon, not color alone).
- **Task 4 (perf)** — `list_users` eager-loads `selectinload(User.memberships).selectinload(ProjectMembership.project)` to avoid the per-row project N+1. No schema/response change.
- **Tests** — FE: a mixed-role/status fixture asserts DOM order (admin→project_admin→active-standard→inactive-standard, proving status beats alphabetical), the "Admin of: Alpha" display, and "Active"/"Inactive" text. BE: `test_list_users_includes_project_admin_membership` confirms the eager-loaded `project_name` is exposed.

### File List

- `frontend/src/components/admin/AdminDashboard.tsx` (modified — `useMemo` import, `ROLE_RANK`, `sortedUsers`, admin-project display, status text+icon)
- `src/ai_qa/api/admin.py` (modified — `list_users` selectinload; `selectinload` import)
- `tests/api/test_admin_users_api.py` (modified — `test_list_users_includes_project_admin_membership`)
- `frontend/src/components/admin/AdminDashboard.test.tsx` (modified — sort/display/status test)

### Review Findings

#### Deferred

- [x] `[Review][Defer]` No test covers a user with an unknown/`other` role in the sort comparator [`frontend/src/components/admin/AdminDashboard.tsx`] — deferred, the `?? 3` fallback is correct code; unknown roles are not possible in the current user model.
- [x] `[Review][Defer]` Status badge test asserts text presence only, not the icon (`CheckCircle`/`XCircle`) [`frontend/src/components/admin/AdminDashboard.test.tsx`] — deferred, testing SVG icons in JSDOM/Vitest is impractical; text verification covers AC3 intent for accessibility.

## Change Log

- 2026-06-21 — Story 15.4 implemented: multi-key sorted Users list, administered-project display, status text+icon, list_users N+1 guard, tests. Status → review. (claude-opus-4-8)
