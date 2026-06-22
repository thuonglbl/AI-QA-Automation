---
baseline_commit: 589e1f217f17453e3c06b2d2ffe66dea2f8f94d6
---
# Story 15.5: User Edit and Delete with Platform-Admin Immutability

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want to edit and delete project_admin and standard users,
so that I can manage the user directory while the platform admin account stays protected.

## Acceptance Criteria

1. **Update-user endpoint.** Given a project_admin or standard user, when the admin edits it, then a new update-user endpoint updates display name, role (project_admin↔standard only), timezone, active status, and optional password reset, returning a secret-free response (no password/hash echoed).
2. **Role-flip side effects.** Given a role change between project_admin and standard, when the update is applied, then standard→project_admin requires a project and creates the project_admin membership; project_admin→standard deletes the user's project_admin membership(s).
3. **Platform admin immutable.** Given the platform admin account (role=admin), when any actor attempts to edit or delete it, then the action is rejected (403); promoting any user to admin is also rejected.
4. **No self-lockout.** Given the current admin, when they attempt to deactivate or delete their own account, then the action is rejected.
5. **Endpoint RBAC.** Given a non-admin caller, when they call the update or delete user endpoints, then access is denied (403).
6. **Controls hidden for admin row.** Given the Users Management list, when rows render, then Edit and Delete controls appear for project_admin and standard users but NOT for the platform admin row, with distinct accessible labels.

## Tasks / Subtasks

- [x] **Task 1 — Backend request schema `AdminUserUpdateRequest` (AC: 1, 3)** in `src/ai_qa/api/admin.py`:
  - [x] Fields: `display_name: str` (reuse the blank-check validator pattern), `role: AdminUserRole` (the existing `Literal["project_admin", "standard"]` at `:45` — excludes `admin`, satisfying AC3's "promote-to-admin rejected"), `timezone: str` (reuse the IANA validator), `is_active: bool`, `new_password: str | None = Field(default=None, min_length=8, max_length=1024)`, `project_id: UUID | None = Field(default=None)`.
  - [x] `@model_validator(mode="after")`: forbid `project_id` when `role == "standard"` (422). (project_id requirement for the standard→project_admin transition is enforced in the endpoint, which knows the current role.)
- [x] **Task 2 — New `PUT /admin/users/{user_id}` endpoint (AC: 1, 2, 3, 4, 5)**, placed near `delete_user` (`:323-338`), `require_admin`-guarded with `admin: User = AdminDependency`:
  - [x] `target = db.get(User, user_id)` → 404 if None.
  - [x] **Immutability:** if `target.role == ADMIN_ROLE` → 403 (no edit, no demote).
  - [x] **Self-lockout:** if `target.id == admin.id` and `request.is_active is False` → 403.
  - [x] **Role-flip side effects (many-to-many):**
    - standard→project_admin: require `request.project_id` (422 if missing); `db.get(Project, project_id)` → 404 if missing; create `ProjectMembership(role=PROJECT_ADMIN_ROLE)` if not already present (idempotent — no uniqueness error).
    - project_admin→standard: delete ALL `ProjectMembership` rows for this user where `role == PROJECT_ADMIN_ROLE`.
    - role unchanged: no membership change (ignore `project_id`).
  - [x] Apply field updates: `display_name`, `timezone`, `is_active`, `role`. If `new_password` set → `target.password_hash = hash_password(request.new_password)` (already imported `:24`). NEVER echo the password.
  - [x] `db.commit()`, `db.refresh(target)`, return `_to_admin_user_response(target)` (secret-free).
- [x] **Task 3 — Harden `delete_user` (AC: 3, 4, 5)** (`:323-338`):
  - [x] Fetch `target = db.get(User, user_id)` first → 404 if None.
  - [x] 403 if `target.role == ADMIN_ROLE` (immutable) OR `target.id == admin.id` (self-delete). Change the signature to bind the admin: `admin: User = AdminDependency` (currently `_admin`).
  - [x] Then delete (keep the existing raw delete-by-id + `except IntegrityError → 409`). FK cascade is safe (see Dev Notes).
- [x] **Task 4 — Lib + types (full-stack sync) (AC: 1)**:
  - [x] `frontend/src/lib/projects.ts`: add `updateAdminUser(userId, req)` → `PUT /admin/users/{id}` (mirror `updateAdminProject`, `:46-57`) and `deleteAdminUser(userId)` → `DELETE /admin/users/{id}` (mirror `deleteAdminProject`, `:59-63`). Both are new — neither exists today.
  - [x] `frontend/src/types/project.ts`: add `UpdateAdminUserRequest { display_name: string; role: "project_admin" | "standard"; timezone: string; is_active: boolean; new_password?: string | null; project_id?: string | null }`.
- [x] **Task 5 — Frontend Edit/Delete (AC: 1, 2, 6)** in `frontend/src/components/admin/AdminDashboard.tsx`:
  - [x] Per-user edit state + handlers mirroring the project pattern (`startEditingProject`/`handleEditProject`/`handleDeleteProject`, `:419-474`): `editingUserId`, `editUserDisplayName`, `editUserRole`, `editUserTimezone`, `editUserIsActive`, `editUserPassword`, `editUserProjectId`.
  - [x] Inline edit form per `<li>` (role `<select>` project_admin/standard, timezone `<select>`, active toggle, optional new-password input, conditional project picker when switching standard→project_admin). On submit call `updateAdminUser(u.id, body)` then `loadUsers()`.
  - [x] Edit + Delete buttons per row, **hidden when `isAdminUser`** (`u.role === "admin"`, `:793`). `handleDeleteUser(u)` → `deleteAdminUser(u.id)` then `loadUsers()`.
  - [x] **Distinct aria-labels**: `Edit user ${u.display_name}` / `Delete user ${u.display_name}` — must NOT collide with the project card's `Edit ${proj.name}` / `Delete ${proj.name}` (`:685,695`).
- [x] **Task 6 — Tests (AC: 1-6)**:
  - [x] Backend (`tests/api/test_admin_users_api.py`): valid update (200, fields changed, no secret in body); invalid timezone (422); `role:"admin"` rejected (422, Literal); edit the platform admin → 403; delete the platform admin → 403; self-deactivate → 403; non-admin caller (`user_token`) on PUT and DELETE → 403; standard→project_admin with `project_id` creates a project_admin membership; project_admin→standard removes the project_admin membership(s); password reset changes the hash (login with the new password, or assert hash changed).
  - [x] Frontend (`AdminDashboard.test.tsx`): Edit + Delete render for a non-admin row; the admin row has NO Edit/Delete; PUT and DELETE fetch-mock branches fire on submit/click; verify aria-labels are distinct from the project buttons.
  - [x] Run `uv run pytest --no-cov tests/api/test_admin_users_api.py`, `npm run test`, `npm run typecheck`.

## Dev Notes

### Highest-risk story in the epic — sequence it LAST

It couples with Story 15.3's role/membership rules (reuse the same `ProjectMembership(role="project_admin")` linkage and `PROJECT_ADMIN_ROLE` constant) and with the same user-row region edited by 15.2/15.4. Implement after 15.1-15.4. Risk is lockout / role-transition coupling — mitigated by the immutability + self-guards below.

### Why immutability mostly comes for free (but implement the guards explicitly)

Both endpoints are gated by `require_admin` (`src/ai_qa/api/auth/rbac.py:47-53`), so the ONLY caller is the platform admin (role=`admin`). The platform admin editing/deleting itself = operating on an `admin`-role target → already blocked by the `target.role == ADMIN_ROLE → 403` guard. The explicit self-`is_active`/self-delete checks are defense-in-depth and make AC4 hold literally. `AdminUserRole = Literal["project_admin", "standard"]` (`admin.py:45`) means a request body can never carry `role:"admin"` — promotion is rejected at the schema boundary (422), satisfying AC3's promotion clause. The platform admin is provisioned solely by `bootstrap_admin` (`src/ai_qa/auth/service.py`), never via these endpoints.

### Role constants

`ADMIN_ROLE = "admin"`, `PROJECT_ADMIN_ROLE = "project_admin"`, `STANDARD_ROLE = "standard"` live in `src/ai_qa/auth/service.py:13-17` and re-export from `src/ai_qa/api/auth/rbac.py:10,84`. Import them — do not hard-code. `admin.py` currently imports `hash_password` (`:24`) and `require_admin` (via `AdminDependency`); add `ADMIN_ROLE`/`PROJECT_ADMIN_ROLE`/`STANDARD_ROLE` imports (all three are used by the role-flip sketch below).

### FK cascade — user delete is safe (confirmed)

- `project_memberships.user_id` → `ondelete=CASCADE` (`src/ai_qa/db/models.py:191-193`): deleting a user cascades its memberships at the DB — no orphan `IntegrityError`.
- `projects.created_by_user_id` → `ondelete=CASCADE` (`:87-89`): would cascade-delete a user's *created* projects, BUT projects are created by the platform admin (`create_project` sets `created_by_user_id=admin.id`, `admin.py:362`) and the admin is immutable — so deleting a project_admin/standard user never cascade-deletes a project. Hazard closed.
- `user_secrets` (`cascade="all, delete-orphan"`) and `captured_sessions.user_id` (`ondelete=CASCADE`) also clean up. Keep the existing raw delete-by-id (`db.query(User).filter(...).delete(synchronize_session=False)`) — but FETCH the target first for the guards. SQLite tests rely on `PRAGMA foreign_keys=ON` for DB-level cascade; the existing delete-user test already exercises this path, so the conftest handles it.

### Role-flip implementation sketch

```python
@router.put("/users/{user_id}", response_model=AdminUserResponse)
async def update_user(
    user_id: UUID,
    request: AdminUserUpdateRequest,
    admin: User = AdminDependency,
    db: Session = DbSessionDependency,
) -> AdminUserResponse:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    if target.role == ADMIN_ROLE:
        raise HTTPException(status_code=403, detail="The platform admin account cannot be modified.")
    if target.id == admin.id and not request.is_active:
        raise HTTPException(status_code=403, detail="You cannot deactivate your own account.")

    old_role, new_role = target.role, request.role
    if old_role == STANDARD_ROLE and new_role == PROJECT_ADMIN_ROLE:
        if request.project_id is None:
            raise HTTPException(status_code=422, detail="A project is required to make this user a project admin.")
        if db.get(Project, request.project_id) is None:
            raise HTTPException(status_code=404, detail="Project not found")
        exists = db.execute(
            select(ProjectMembership).where(
                ProjectMembership.project_id == request.project_id,
                ProjectMembership.user_id == target.id,
                ProjectMembership.role == PROJECT_ADMIN_ROLE,
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(ProjectMembership(project_id=request.project_id, user_id=target.id, role=PROJECT_ADMIN_ROLE))
    elif old_role == PROJECT_ADMIN_ROLE and new_role == STANDARD_ROLE:
        db.query(ProjectMembership).filter(
            ProjectMembership.user_id == target.id,
            ProjectMembership.role == PROJECT_ADMIN_ROLE,
        ).delete(synchronize_session=False)

    target.display_name = request.display_name
    target.timezone = request.timezone
    target.is_active = request.is_active
    target.role = new_role
    if request.new_password:
        target.password_hash = hash_password(request.new_password)
    db.commit()
    db.refresh(target)
    return _to_admin_user_response(target)
```

Narrow `request.project_id` (`assert ... is not None`) before passing to non-optional params to satisfy Pyrefly (project-context "Narrow Optional before use").

### Secret-free response

Return via `_to_admin_user_response` (`admin.py:257-279`) — it never includes `password_hash`. Never log/echo `new_password`. (project-context security rule: secrets never in responses, logs, messages, artifacts.)

### Frontend — mirror the project card pattern

The project card already has inline-edit + delete with the exact shape to copy:
- handlers `startEditingProject`/`cancelEditingProject`/`handleEditProject`/`handleDeleteProject` (`:419-474`)
- buttons with `aria-label={`Edit ${proj.name}`}` / `aria-label={`Delete ${proj.name}`}` (`:685,695`)

For users, use `aria-label={`Edit user ${u.display_name}`}` / `aria-label={`Delete user ${u.display_name}`}` so test queries don't collide with the project buttons. Hide both controls when `isAdminUser` (`:793`) — that's the admin-row immutability in the UI. The edit form reuses the role `<select>` (Standard/Project Admin) and timezone `<select>` (`TIMEZONE_OPTIONS`, already imported `:33`) from the Create User form; the conditional project picker (Story 15.3) reappears when switching a standard user to Project Admin.

### Coordination

Same-file siblings: 15.2 (copy removal — keep `isAdminUser`!), 15.3 (picker + membership-on-create — reuse its picker + body shape), 15.4 (sorted list — map over the sorted copy when adding the Edit/Delete buttons). The `_to_admin_user_response` membership shape this story mutates is what 15.4 renders.

### Constraints / conventions

- FastAPI: dependencies via `AdminDependency`; in tests use `app.dependency_overrides` / canonical fixtures (`client`, `admin_token`, `user_token`, `db_user` from `tests/api/conftest.py`; scaffold in `tests/api/test_admin_rbac_api.py`). Never `mock.patch` a dependency.
- `pytest.raises(Exception)` is prohibited — assert on `response.status_code` / specific types.
- Full-stack sync: types + lib + component land together; `npm run typecheck`.
- `uv` only; Python 3.14; English-only UI strings; no `# type: ignore`/`@ts-ignore`.

### Project Structure Notes

- Backend: `src/ai_qa/api/admin.py` (new `AdminUserUpdateRequest` + `update_user` endpoint + `delete_user` guards). No migration (reuses `users`/`project_memberships`).
- Frontend: `AdminDashboard.tsx` (edit/delete UI), `lib/projects.ts` (`updateAdminUser` + `deleteAdminUser`), `types/project.ts` (`UpdateAdminUserRequest`).

### References

- [Sprint change proposal — Story E](../planning-artifacts/sprint-change-proposal-2026-06-21.md)
- [Investigation — item 5 + Backlog #2 (FK cascade)](investigations/admin-dashboard-project-user-mgmt-investigation.md)
- [RBAC design — Decisions §10](../planning-artifacts/design-projectadmin-rbac-redesign-2026-06-21.md) (line 138; many-to-many; immutable admin)
- [Epic 15 / Story 15.5](../planning-artifacts/epics.md) (lines 1668-1698)
- Code: `src/ai_qa/api/admin.py:24,45,257-338`, `src/ai_qa/api/auth/rbac.py:10,47-53,84`, `src/ai_qa/auth/service.py:13-17`, `src/ai_qa/db/models.py:87-89,191-193`, `frontend/src/components/admin/AdminDashboard.tsx:419-474,685,695,791-832`, `frontend/src/lib/projects.ts:46-63`, `frontend/src/types/project.ts:113-121`
- Tests: `tests/api/test_admin_users_api.py`, `tests/api/test_admin_rbac_api.py` (scaffold), `frontend/src/components/admin/AdminDashboard.test.tsx`

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story)

### Debug Log References

- `uv run pytest --no-cov tests/api/test_admin_users_api.py` → 29 passed (13 new update/delete cases).
- Full regression: `uv run pytest` → **1731 passed**, coverage 84.71% (≥80% gate); `uv run mypy src` → clean (95 files); ruff clean.
- `npm run typecheck` / `npm run lint` → clean; `npm run test` (full) → **349 passed** (34 files).

### Completion Notes List

- **AC1** — New `PUT /admin/users/{user_id}` + `AdminUserUpdateRequest` (display_name, role, timezone, is_active, optional new_password, optional project_id). Returns the secret-free `_to_admin_user_response` (no hash/password echoed).
- **AC2 (role flips, many-to-many)** — standard→project_admin requires `project_id` (422 if missing, 404 if project absent) and links a membership; project_admin→standard deletes ALL the user's `project_admin` memberships. **Hardening beyond the story sketch:** because `uq_project_memberships_project_user` is UNIQUE(project_id, user_id), a standard→project_admin promotion now **promotes an existing (project,user) row in place** (or inserts when none) instead of blindly inserting — avoids an IntegrityError when the user already has a non-admin membership on that project.
- **AC3 (immutable admin)** — `target.role == ADMIN_ROLE → 403` on both PUT and DELETE; promotion to admin is impossible at the schema boundary (`AdminUserRole` Literal → 422).
- **AC4 (no self-lockout)** — `target.id == admin.id and not is_active → 403` on PUT; `target.id == admin.id → 403` on DELETE (defense-in-depth; the admin is also caught by the immutability guard).
- **AC5 (endpoint RBAC)** — both endpoints are `AdminDependency`-guarded → non-admin caller gets 403 (tested for PUT and DELETE).
- **AC6 (UI)** — inline edit form per row (role/timezone/active/optional-password + conditional project picker for standard→project_admin); Edit/Delete buttons hidden when `isAdminUser`; distinct `aria-label`s `Edit user ${name}` / `Delete user ${name}` (no collision with project card buttons).
- **`delete_user` hardened** — fetches the target first (404), enforces immutability + self-delete (403), then deletes; FK cascades handle memberships/secrets/sessions (confirmed in Dev Notes).
- **Regression fix (caught by full suite):** `tests/api/test_admin_rbac_api.py::test_admin_can_create_user_with_approved_role_without_leaking_password_hash` created a project_admin with no project (pre-Story-15.3 contract). Updated to create a project first and pass `project_id`, asserting the project_admin membership is present. This is a consequence of the Story 15.3 contract (project_admin must be linked to a project).

### File List

- `src/ai_qa/api/admin.py` (modified — `AdminUserUpdateRequest`, `update_user` endpoint, hardened `delete_user`; `ADMIN_ROLE`/`STANDARD_ROLE` imports)
- `frontend/src/lib/projects.ts` (modified — `updateAdminUser` + `deleteAdminUser`)
- `frontend/src/types/project.ts` (modified — `UpdateAdminUserRequest`)
- `frontend/src/components/admin/AdminDashboard.tsx` (modified — edit-user state/handlers, inline edit form, Edit/Delete buttons hidden for admin row)
- `tests/api/test_admin_users_api.py` (modified — `TestAdminUserUpdate` + `Session` import)
- `tests/api/test_admin_rbac_api.py` (modified — project_admin create test updated for the project-link contract)
- `frontend/src/components/admin/AdminDashboard.test.tsx` (modified — edit/delete UI test)

### Review Findings

#### Patch

- [x] `[Review][Patch]` `update_user` has no `try/except IntegrityError` around `db.commit()` [`src/ai_qa/api/admin.py`] — inconsistent with `create_user` and `delete_user` (both wrap commit); a concurrent unique-constraint violation on `uq_project_memberships_project_user` (race: two simultaneous promotes of the same user to the same project both seeing no existing membership) produces an unhandled 500.
- [x] `[Review][Patch]` Missing test for `PUT /admin/users/{nonexistent_id}` → 404 [`tests/api/test_admin_users_api.py`] — `TestAdminUserUpdate` tests many paths but omits the 404 case; `delete_user` has `test_delete_nonexistent_user` for parity; AC1 implies the 404 path.

#### Deferred

- [x] `[Review][Defer]` `project_admin → project_admin` same-role update silently ignores `project_id` in the PUT body [`src/ai_qa/api/admin.py`] — deferred, not covered by AC2 ("role change between project_admin and standard"); re-assignment is available via existing `/admin/projects/{id}/memberships` endpoints.
- [x] `[Review][Defer]` `cancelEditingUser` does not reset `editUserRole`, `editUserTimezone`, `editUserIsActive` state [`frontend/src/components/admin/AdminDashboard.tsx`] — deferred, stale values not visible (guarded by `editingUserId === null`); `startEditingUser` always resets all fields before re-display.
- [x] `[Review][Defer]` N+1 queries on `create_user`/`update_user` response: `_to_admin_user_response` accesses `membership.project.name` without `selectinload` (unlike `list_users`) [`src/ai_qa/api/admin.py`] — deferred, performance concern only; admin-only code, low user volume; no correctness regression.
- [x] `[Review][Defer]` Self-deactivation guard in `update_user` and self-delete guard in `delete_user` are dead code (immutability guard `target.role == ADMIN_ROLE` fires first) [`src/ai_qa/api/admin.py`] — deferred, defense-in-depth for potential future multi-admin design; 403 behavior is tested via immutability guard.
- [x] `[Review][Defer]` `_to_admin_user_response` would `AttributeError` if `membership.project` is `None` [`src/ai_qa/api/admin.py`] — deferred, theoretical; `ondelete=CASCADE` on the FK prevents orphan memberships.
- [x] `[Review][Defer]` No test for demoting a project_admin who also has non-`project_admin` memberships on the same project (verifying `member`/`owner` rows survive) [`tests/api/test_admin_users_api.py`] — deferred, correct behavior; filter-delete only targets `role == project_admin` rows.
- [x] `[Review][Defer]` No confirmation dialog before `handleDeleteUser` fires [`frontend/src/components/admin/AdminDashboard.tsx`] — deferred, UX enhancement not required by AC; `handleDeleteProject` also lacks one (pre-existing pattern).
- [x] `[Review][Defer]` No project picker in edit form for an existing project_admin (cannot re-assign to a different project via the UI) [`frontend/src/components/admin/AdminDashboard.tsx`] — deferred, not covered by AC2 (which specifies standard↔project_admin transitions); alternative flow via membership endpoints.
- [x] `[Review][Defer]` `AdminUserUpdateRequest` model validator does not require `project_id` for the standard→project_admin promotion case (checked imperatively in the endpoint instead) [`src/ai_qa/api/admin.py`] — deferred, design decision; endpoint validation is sufficient and correct.
- [x] `[Review][Defer]` No test for promoting a standard user who already has a non-`project_admin` membership on the target project (verifying the upsert overwrites the role correctly) [`tests/api/test_admin_users_api.py`] — deferred, idempotent upsert is by design (per dev notes; avoids `uq_project_memberships_project_user` IntegrityError).

## Change Log

- 2026-06-21 — Story 15.5 implemented: PUT/DELETE user endpoints with platform-admin immutability + self-lockout + role-flip membership rules, FE inline edit/delete, full-stack types/lib, tests; updated a stale RBAC test for the project_admin project-link contract. Status → review. (claude-opus-4-8)
