---
title: 'Project Admin can only manage standard members'
type: 'feature'
created: '2026-06-21'
status: 'done'
baseline_commit: '7f8b286074a2a9232b971d4cf6630156af29203f'
context: ['{project-root}/project-context.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** On the Project Admin Dashboard a `project_admin` can currently remove other `project_admin` members (and is only blocked from removing *their own* project-admin row), and the "add member" dropdown offers `admin` / `project_admin` users as assignable. A project_admin should only ever manage standard members.

**Approach:** Constrain both membership operations for callers whose global role is `project_admin` (platform `admin` keeps full control): removal is allowed only when the target membership role is `member`; assignment is allowed only for target users whose global role is `standard` and only with membership role `member`. Enforce on the backend (authoritative) and mirror in the UI (filter the dropdown, disable disallowed remove buttons).

## Boundaries & Constraints

**Always:**
- Backend is the source of truth — every restriction enforced in `projects_admin.py` returns HTTP 403; the UI changes are a usability mirror, not the gate.
- Restrictions apply ONLY when `current_user.role == PROJECT_ADMIN_ROLE`. A platform `admin` retains full control of both endpoints (unchanged behavior).
- "standard member" = `ProjectMembership.role == "member"`. "standard user" = `User.role == STANDARD_ROLE` (`"standard"`).
- The new removal rule subsumes and replaces the existing self-removal guard (a project_admin's own row has role `project_admin`, so it is already non-`member`).
- `GET /project-admin/users` keeps returning the full active directory (it is display-safe and feeds member-name resolution); the standard-only restriction is applied to the *assign dropdown* in the FE, not to this endpoint's payload.

**Ask First:**
- (none expected — if a third role concept surfaces, HALT)

**Never:**
- Do not let a project_admin remove themselves, another project_admin, or an `owner` membership.
- Do not let a project_admin assign an `admin` / `project_admin` user, nor create a non-`member` membership role.
- Do not change the platform-admin AdminDashboard, the `require_project_admin_for_project` dependency, or any DB schema.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| -------- | ------------- | -------------------------- | -------------- |
| Remove standard member (project_admin caller) | `DELETE .../members/{uid}`, target membership role `member` | 204, membership deleted | N/A |
| Remove project_admin member (project_admin caller) | target membership role `project_admin` (self or other) | 403, membership untouched | `detail` = standard-members-only message |
| Remove owner member (project_admin caller) | target membership role `owner` | 403, untouched | standard-members-only message |
| Remove any member (platform admin caller) | any target role | 204, deleted | N/A |
| Add standard user as member (project_admin caller) | `POST .../members` body `{user_id: <standard>, role: "member"}` | 200, membership created/updated | N/A |
| Add admin/project_admin user (project_admin caller) | target `User.role` in {`admin`,`project_admin`} | 403, no membership written | standard-users-only message |
| Add with elevated membership role (project_admin caller) | body `role` != `member` | 403, no membership written | member-role-only message |
| Assign dropdown (FE) | users list incl. admin/project_admin/standard | only non-member `standard` users listed | empty/disabled select if none |
| Remove button (FE) | member row role `project_admin`/`owner` (project_admin viewer) | button disabled with explanatory title | N/A |

</frozen-after-approval>

## Code Map

- `src/ai_qa/api/projects_admin.py` -- `add_project_member` + `remove_project_member`; add the project_admin role guards here (authoritative enforcement).
- `src/ai_qa/api/auth/rbac.py` -- exports `ADMIN_ROLE` / `PROJECT_ADMIN_ROLE` / `STANDARD_ROLE`; `_admin.role` is the caller's global role. No change.
- `src/ai_qa/api/admin.py` -- `ProjectMembershipRole = Literal["member","owner","project_admin"]`, `MembershipCreateRequest.role` default `"member"`. Reference only.
- `frontend/src/components/admin/ProjectAdminDashboard.tsx` -- `assignable` memo (dropdown filter) + member-row remove `<button>` disable/title logic.
- `tests/api/test_project_admin_rbac.py` -- backend tests for add/remove member; extend with the new role-restriction cases.
- `frontend/src/components/__tests__/ProjectAdminDashboard.test.tsx` -- component tests; extend dropdown + remove-button assertions.

## Tasks & Acceptance

**Execution:**
- [x] `src/ai_qa/api/projects_admin.py` -- in `add_project_member`, after the 404 check, when `_admin.role == PROJECT_ADMIN_ROLE`: 403 if `target_user.role != STANDARD_ROLE` ("Project admins can only assign standard users."), and 403 if `request.role != "member"` ("Project admins can only assign the standard member role."). Import `STANDARD_ROLE`; introduce a `MEMBER_ROLE = "member"` module constant for both endpoints. Platform admin path unchanged.
- [x] `src/ai_qa/api/projects_admin.py` -- rewrite `remove_project_member`: load the `ProjectMembership` row by `(project_id, user_id)` first; 404 if absent; when `_admin.role == PROJECT_ADMIN_ROLE` and `membership.role != MEMBER_ROLE`, raise 403 ("Project admins can only remove standard members."); else `db.delete(membership); db.commit()`. Removes the old self-only 409 guard.
- [x] `frontend/src/components/admin/ProjectAdminDashboard.tsx` -- narrow `assignable` memo to `!memberIds.has(u.id) && u.role === "standard"`; for the member-row remove button compute `removable = user?.role === "admin" || m.role === "member"` and set `disabled={isBusy || !removable}` with a `title` explaining the restriction when not removable (replace the current self-only condition).
- [x] `tests/api/test_project_admin_rbac.py` -- add tests: project_admin removing a project_admin member → 403; project_admin adding an admin/project_admin user → 403; project_admin adding with `role:"project_admin"` → 403; platform admin removing a project_admin member → 204 (unrestricted). Keep `test_add_and_remove_member` green.
- [x] `frontend/src/components/__tests__/ProjectAdminDashboard.test.tsx` -- extend fixtures with an admin/project_admin user + a project_admin member; assert the dropdown excludes non-standard users and that the remove button for a project_admin member is disabled while a standard member's is enabled.

**Acceptance Criteria:**
- Given a project_admin caller, when they DELETE a membership whose role is `project_admin` or `owner` (including their own), then the API returns 403 and the row is preserved.
- Given a project_admin caller, when they POST a member whose global role is `admin` or `project_admin`, or with a membership role other than `member`, then the API returns 403 and no membership is written.
- Given a platform admin caller, when they add or remove any membership, then behavior is unchanged (no new 403s).
- Given a project_admin viewing the dashboard, when the member list renders, then only standard non-member users appear in the assign dropdown and remove buttons for non-`member` rows are disabled with an explanatory title.

## Verification

**Commands:**
- `uv run pytest tests/api/test_project_admin_rbac.py -p no:base_url --no-cov` -- expected: all green incl. new cases
- `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/` -- expected: clean
- `uv run mypy src` -- expected: clean
- `cd frontend && npx vitest run src/components/__tests__/ProjectAdminDashboard.test.tsx` -- expected: all green
- `cd frontend && npm run typecheck` -- expected: clean

## Suggested Review Order

**Authorization rules (backend — source of truth)**

- Start here: the core removal rule — project_admin may delete only `member` rows.
  [`projects_admin.py:308`](../../src/ai_qa/api/projects_admin.py#L308)

- Assign guard: project_admin may add only standard users, only as `member`.
  [`projects_admin.py:240`](../../src/ai_qa/api/projects_admin.py#L240)

- Defense-in-depth: blocks rewriting an already-elevated membership via upsert.
  [`projects_admin.py:267`](../../src/ai_qa/api/projects_admin.py#L267)

- The single membership-role constant both guards key off.
  [`projects_admin.py:38`](../../src/ai_qa/api/projects_admin.py#L38)

**UI mirror (frontend)**

- Dropdown shows only standard non-members; platform admin stays unrestricted.
  [`ProjectAdminDashboard.tsx:245`](../../frontend/src/components/admin/ProjectAdminDashboard.tsx#L245)

- Remove button disabled for non-`member` rows with an explanatory title.
  [`ProjectAdminDashboard.tsx:455`](../../frontend/src/components/admin/ProjectAdminDashboard.tsx#L455)

**Tests (peripheral)**

- Backend: remove/assign 403s, upsert-downgrade block, platform-admin unrestricted.
  [`test_project_admin_rbac.py:210`](../../tests/api/test_project_admin_rbac.py#L210)

- Frontend: dropdown filtering + remove-button disabled/enabled states.
  [`ProjectAdminDashboard.test.tsx:121`](../../frontend/src/components/__tests__/ProjectAdminDashboard.test.tsx#L121)
