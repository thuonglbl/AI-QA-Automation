---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.13: Fix Project Selection When Editing a Project-Admin User

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Priority: low — work at the END of Epic 16 (after 16-1 … 16-11).** Bug found 2026-06-22 on the Admin Dashboard. FE + BE fix; preserve the many-to-many `project_admin`↔project model and platform-admin immutability from Epic 15 ([[epic-15-admin-rbac-sprint-change]]).

## Story

As a platform administrator,
I want to choose a project for a user whose role is already Project Admin when I edit them in Users Management,
so that I can assign or change which project that project admin manages, not only at creation or while promoting a standard user.

### Observed bug

In Admin Dashboard → Users Management → Edit, selecting role "Project Admin" shows NO project selector when the user is *already* a Project Admin, so there is no way to assign/change their managed project on edit. The picker only renders while promoting a standard user (`u.role === "standard" && editUserRole === "project_admin"`); the create-user form has its own picker. As a result an existing project admin's project assignment cannot be viewed or changed through the edit form.

## Acceptance Criteria

1. **Picker present + pre-filled when editing a project admin.** Given I edit a user whose current role is Project Admin, when the edit form is shown, then a project selector is present and reflects the project(s) the user currently administers, so I can assign or change the managed project.

2. **Reassignment persists.** Given I change the selected project for an existing Project Admin and save, when the update is persisted, then the user's `project_admin` project membership is updated accordingly, consistent with the many-to-many `project_admin`↔project model, and the change is reflected in the Users Management list.

3. **Promotion flow preserved.** Given I promote a standard user to Project Admin (the existing flow), when I edit and save, then behavior is preserved — a project is still required and the membership is created as before.

4. **Platform admin stays immutable.** Given the immutable platform admin account, when it is viewed in Users Management, then it remains non-editable (no project selector, no role change) per the Epic 15 immutability decision.

5. **Invalid/missing selection rejected cleanly.** Given an invalid or missing project selection on save, when the request is submitted, then the form/API rejects it with a clear, actionable message and no partial/inconsistent membership state is left behind.

## Tasks / Subtasks

- [ ] **Task 1 — FE: show the picker whenever the (new) role is project_admin (AC: 1, 3)**
  - [ ] Change the edit-form picker gate from `u.role === "standard" && editUserRole === "project_admin"` to just `editUserRole === "project_admin"` ([frontend/src/components/admin/AdminDashboard.tsx:949](frontend/src/components/admin/AdminDashboard.tsx:949)). Check the sibling gates at ~935/1042 for the same condition and align them.
  - [ ] Pre-populate `editUserProjectId` in `startEditingUser` from the user's current `project_admin` membership instead of clearing it to `""` ([AdminDashboard.tsx:493](frontend/src/components/admin/AdminDashboard.tsx:493)). The data is already on `u.project_memberships` (filter `role === "project_admin"`).

- [ ] **Task 2 — FE: send project_id on reassignment, not only on promotion (AC: 2, 3)**
  - [ ] Update the `promoting`/submit logic so `project_id` is included in the `UpdateAdminUserRequest` body when the edited role is `project_admin` AND a project is selected — covering both standard→project_admin (existing) and project_admin→project_admin reassignment ([AdminDashboard.tsx:517-525](frontend/src/components/admin/AdminDashboard.tsx:517)).
  - [ ] Keep the `project_admin`→standard demote path untouched (no project_id needed).

- [ ] **Task 3 — BE: handle project_admin→project_admin reassignment (AC: 2, 5)**
  - [ ] In `update_user`, add a branch for `old_role == PROJECT_ADMIN_ROLE and new_role == PROJECT_ADMIN_ROLE and request.project_id is not None` that idempotently ensures a `project_admin` membership for the selected project (find-or-update the `(project, user)` row, validate the project exists → 404 if not) ([src/ai_qa/api/admin.py](src/ai_qa/api/admin.py) update_user, ~line 445-476). Mirror the existing promotion branch's idempotent membership logic.
  - [ ] **Reassignment semantics DECIDED (Thuong 2026-06-22): keep many-to-many.** Ensure the selected project's `project_admin` membership exists (add it if missing, keep it if present). **Do NOT delete the user's other `project_admin` memberships** — a project admin may manage multiple projects. The edit adds/keeps the selected project; it never strips existing assignments.
  - [ ] Confirm `AdminUserUpdateRequest.validate_project_link` already permits `project_id` for the `project_admin` role (it rejects it only for `standard`) — no validator change expected.

- [ ] **Task 4 — Preserve immutability + parity (AC: 3, 4)**
  - [ ] Confirm the platform-admin guard still rejects any edit (`target.role == ADMIN_ROLE` → 403) before role logic ([admin.py](src/ai_qa/api/admin.py) ~line 437) and the FE hides Edit/Delete for the admin row ([AdminDashboard.tsx](frontend/src/components/admin/AdminDashboard.tsx) ~line 1069).
  - [ ] Keep create-user parity (its simple `createUserRole === "project_admin"` gate is the model to match).

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Backend: add `test_edit_project_admin_reassign_project` to [tests/api/test_admin_users_api.py](tests/api/test_admin_users_api.py) — create a project_admin for project A, PUT with `role=project_admin, project_id=B`, assert the membership reflects B (and the chosen semantics for A). Keep the existing promote/demote tests green.
  - [ ] Frontend: add an `AdminDashboard.test.tsx` test — editing a project_admin shows the picker pre-selected with the current project; changing it fires PUT with the new `project_id`; the admin row still has no controls.
  - [ ] `uv run pytest` (whole suite or `--no-cov`) + `npm run typecheck` + `npm test`.

## Dev Notes

### Root cause (verified against live code)

- **FE gate is too narrow.** The edit-form project picker renders only under `u.role === "standard" && editUserRole === "project_admin"` ([AdminDashboard.tsx:949-950](frontend/src/components/admin/AdminDashboard.tsx:949)) — so an already-`project_admin` user gets no picker. `startEditingUser` also clears `editUserProjectId = ""` ([:493](frontend/src/components/admin/AdminDashboard.tsx:493)) and never pre-fills from `u.project_memberships` (which IS available on the user payload).
- **FE submit drops project_id.** `const promoting = u.role === "standard" && editUserRole === "project_admin"` ([:517-518](frontend/src/components/admin/AdminDashboard.tsx:517)); `project_id` is spread into the body only when `promoting` ([:525](frontend/src/components/admin/AdminDashboard.tsx:525)). So a reassignment never reaches the backend.
- **BE ignores project_id off the promotion path.** `update_user` consumes `project_id` only in the `standard → project_admin` branch (~line 445); there is no branch for `project_admin → project_admin`, and the demote branch deletes memberships. So even if the FE sent it, nothing would persist.

### Data already available

`AdminUserResponse.project_memberships` (eager-loaded via `selectinload`) carries `{project_id, project_name, role, …}` per membership — the FE filters `role === "project_admin"` to show "Admin of: …" today, so pre-filling the picker needs no new endpoint.

### Membership model

`ProjectMembership` is the many-to-many junction with a UNIQUE `(project_id, user_id)` constraint and a `role` column (`member`/`owner`/`project_admin`). Epic 15: a project can have multiple project_admins; promote = add/update a row to `project_admin`; demote = delete the `project_admin` membership rows.

### Source tree components to touch

- `frontend/src/components/admin/AdminDashboard.tsx` — **UPDATE** (gate at ~949 + siblings ~935/1042; pre-fill at ~493; submit logic ~517-525).
- `frontend/src/types/project.ts` — **READ** (`AdminUser` + `AdminUserProjectMembership` already present); `frontend/src/lib/projects.ts` — **READ/VERIFY** the update request type carries `project_id`.
- `src/ai_qa/api/admin.py` — **UPDATE** (`update_user` reassignment branch). `AdminUserUpdateRequest` validator — **READ/VERIFY** (no change expected).
- `src/ai_qa/db/models.py` — **READ** (`ProjectMembership`).
- Tests: `tests/api/test_admin_users_api.py`, `frontend/src/components/admin/AdminDashboard.test.tsx` — **UPDATE/ADD**.

### Current behavior to PRESERVE (regression guardrails)

- Platform-admin immutability: `target.role == ADMIN_ROLE` → 403 on update AND delete; FE hides Edit/Delete for the admin row ([[epic-15-admin-rbac-sprint-change]]).
- Many-to-many `project_admin`↔project; idempotent membership (one row per `(project, user)`; never violate the unique constraint).
- Existing promote (standard→project_admin requires project, creates membership) and demote (project_admin→standard deletes membership) flows — keep green.
- `validate_project_link`: standard users cannot carry `project_id` — keep.
- App-UI-English-only ([[app-ui-english-only]]). Per [[e2e-login-user-email-test-tld-gotcha]], beware admin-form hydration clobbers — pre-filling state must use the per-id guard pattern already established there.

### Testing standards summary

- Backend: copy the canonical admin RBAC fixture (`admin_token`, projects); no bare `pytest.raises(Exception)`. Assert `project_memberships` in the response reflects the reassignment.
- FastAPI deps via `app.dependency_overrides`; `IntegrityError` → 409 path already handled.
- Frontend: Vitest + RTL; per the admin-dashboard gotchas, use `getByRole`/labels and the per-id form guard ([[e2e-login-user-email-test-tld-gotcha]]).

### Project Structure Notes

- FE + BE; no migration (uses the existing `ProjectMembership`); no new dependencies. Localized change in the admin user-edit path.

### References

- Epic + ACs: [epics.md#Story-16.13](_bmad-output/planning-artifacts/epics.md:1988)
- FE bug site: [AdminDashboard.tsx:949](frontend/src/components/admin/AdminDashboard.tsx:949), [:493](frontend/src/components/admin/AdminDashboard.tsx:493), [:517](frontend/src/components/admin/AdminDashboard.tsx:517)
- BE: [admin.py](src/ai_qa/api/admin.py) `update_user`; `ProjectMembership` in [models.py](src/ai_qa/db/models.py)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[epic-15-admin-rbac-sprint-change]], [[projectadmin-rbac-redesign-plan]], [[e2e-login-user-email-test-tld-gotcha]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
