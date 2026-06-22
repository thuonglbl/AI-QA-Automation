---
baseline_commit: 589e1f217f17453e3c06b2d2ffe66dea2f8f94d6
---
# Story 15.2: Trim Obsolete Admin Dashboard Helper Copy

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want the Admin Dashboard to omit instructions about config it no longer owns,
so that the UI reflects that Confluence/Jira, providers, environments, roles, and membership are managed by the project admin.

## Acceptance Criteria

1. **Create/Edit Project helper copy removed.** Given the Create Project and Edit Project forms, when they render, then the helper sentences stating config is "configured/managed by the project admin after creation" are gone.
2. **Users-list per-user note removed.** Given the Users Management list, when a non-admin user row renders, then the "Project membership is managed by the project admin." note is removed — delete the whole conditional block, leaving no empty element.
3. **No test depends on the removed strings.** Given the removed copy, when the dashboard is tested, then no test asserts on those strings (optionally add a negative assertion confirming their absence).

## Tasks / Subtasks

- [x] **Task 1 — Remove the three user-facing strings (AC: 1, 2)** in `frontend/src/components/admin/AdminDashboard.tsx`:
  - [x] Create-Project helper `<p>` (`:761-764`): "Confluence/Jira links, providers, environments, app roles and members are configured by the project admin after creation." — delete the whole `<p>`.
  - [x] Edit-Project helper `<p>` (`:647-650`): "Confluence/Jira, providers, environments, roles and members are managed by the project admin." — delete the whole `<p>`.
  - [x] Users-Management per-user note (`:825-829`): delete the **entire** `{!isAdminUser && (<div className="text-xs text-slate-400">…</div>)}` block — not just the inner text. After removal, `isAdminUser` may become unused; if so, remove the now-dead `const isAdminUser = u.role === "admin";` (`:793`) too, unless Story 15.4/15.5 (worked in the same file) still needs it. Check before deleting.
- [x] **Task 2 — Optional comment cleanup**
  - [x] The internal comment at `:239-241` ("Project CONFIG … managed by the project_admin … only creates/edits name + description here") is accurate and may stay; no change required. (Not user-facing.)
- [x] **Task 3 — Tests (AC: 3)**
  - [x] Grep tests for the removed strings: no existing assertion depends on them. Optionally add a negative assertion `expect(screen.queryByText(/managed by the project admin/i)).not.toBeInTheDocument()` to `AdminDashboard.test.tsx`.
  - [x] Run `npm run test`, `npm run typecheck`, `npm run lint`.

## Dev Notes

### Exact strings + locations (verified against live code)

`frontend/src/components/admin/AdminDashboard.tsx`:

1. **Create Project form** (`:761-764`):
   ```tsx
   <p className="text-xs text-slate-400">
     Confluence/Jira links, providers, environments, app roles and members
     are configured by the project admin after creation.
   </p>
   ```
2. **Edit Project inline form** (`:647-650`):
   ```tsx
   <p className="text-xs text-slate-400">
     Confluence/Jira, providers, environments, roles and members are
     managed by the project admin.
   </p>
   ```
3. **Users Management row** (`:824-829`) — remove the full conditional block:
   ```tsx
   {!isAdminUser && (
     <div className="text-xs text-slate-400">
       Project membership is managed by the project admin.
     </div>
   )}
   ```

### Coordination with sibling stories (same file)

Stories 15.3, 15.4, 15.5 all edit `AdminDashboard.tsx`. Suggested implementation order is 15.1 → 15.2 → 15.3 → 15.4 → 15.5 (15.2 is trivial and first in the file). **Heads-up on `isAdminUser`:** it is referenced at `:793` and used by the block you delete here. Story 15.5 will RE-USE `isAdminUser` to hide Edit/Delete on the admin row, and 15.4 renders near the role badge. If you implement 15.2 before 15.5, leave `const isAdminUser = u.role === "admin";` in place (15.5 needs it) — only the JSX `<div>` block is removed by this story. Do NOT remove the `isAdminUser` declaration.

### Constraints / conventions

- App UI is **English-only** — no Vietnamese strings (no new strings here; pure deletion).
- ESLint 9 (pinned), `npm` only in `frontend/`. Prefix any unused var with `_` (or remove it).
- Do not touch the E2E `AdminDashboard` selectors that other tests rely on; this story removes only descriptive `<p>`/`<div>` copy, not controls.

### Project Structure Notes

- Single-file frontend change; no backend, no types, no migration.
- No `lib/projects.ts` or `types/project.ts` change.

### References

- [Sprint change proposal — Story B](../planning-artifacts/sprint-change-proposal-2026-06-21.md)
- [Investigation — item 1, Source Code Trace](investigations/admin-dashboard-project-user-mgmt-investigation.md)
- [Epic 15 / Story 15.2](../planning-artifacts/epics.md) (lines 1600-1618)
- Code: `frontend/src/components/admin/AdminDashboard.tsx:647-650, 761-764, 824-829`

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story)

### Debug Log References

- `npm run typecheck` → clean; `npm run test src/components/admin/AdminDashboard.test.tsx` → 14 passed; `npm run lint` → clean.
- Grep `frontend/` for the removed strings → no test or code dependency.

### Completion Notes List

- **AC1** — Deleted both helper `<p>` blocks: the Create-Project copy ("…configured by the project admin after creation") and the Edit-Project copy ("…managed by the project admin").
- **AC2** — Deleted the entire `{!isAdminUser && (<div>Project membership is managed by the project admin.</div>)}` block (not just the inner text). `const isAdminUser = u.role === "admin";` was **kept** — it is still referenced by the role-badge color expression (and is needed by Story 15.5), so removing the block left no unused var.
- **AC3** — No existing test depended on the strings; added negative test `"AdminDashboard omits obsolete 'project admin' helper copy (Story 15.2)"` asserting all three are absent.
- Task 2 (internal comment at the `name`/`description` state) left as-is per spec — accurate and not user-facing.

### File List

- `frontend/src/components/admin/AdminDashboard.tsx` (modified — removed 3 obsolete helper strings)
- `frontend/src/components/admin/AdminDashboard.test.tsx` (modified — added negative-assertion test)

## Change Log

- 2026-06-21 — Story 15.2 implemented: removed 3 obsolete "project admin" helper strings from AdminDashboard; added negative-assertion test. Status → review. (claude-opus-4-8)
