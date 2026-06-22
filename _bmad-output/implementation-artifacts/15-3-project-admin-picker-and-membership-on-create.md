---
baseline_commit: 589e1f217f17453e3c06b2d2ffe66dea2f8f94d6
---
# Story 15.3: Project-Admin Project Picker and Membership on User Create

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want to assign a project when creating a project_admin user,
so that the new project_admin is linked to a project via a project_admin membership.

## Acceptance Criteria

1. **Conditional picker.** Given the Create User form, when the role is set to Project Admin, then a required project picker is shown; for the Standard role no project picker is shown.
2. **Atomic create + membership.** Given an admin submits a project_admin user with a selected project, when the request is processed, then the `User` (role=`project_admin`) and a `ProjectMembership(role="project_admin")` for that project are created atomically (the user is rolled back if the membership insert fails).
3. **Validation.** Given an admin submits a project_admin user without a project, OR a standard user WITH a project, when the request is validated, then it is rejected (422) with a clear message.
4. **Many-to-many — no 1:1 uniqueness.** Given the project_admin↔project linkage, when memberships are created, then no 1:1 uniqueness is enforced — a project may have multiple project_admins and a user may admin multiple projects (additional assignments happen via existing membership flows).
5. **No projects yet.** Given no projects exist, when the admin selects the Project Admin role, then the form prevents submission and explains a project must exist first.

## Tasks / Subtasks

- [x] **Task 1 — Backend request schema (AC: 1, 3)** in `src/ai_qa/api/admin.py`:
  - [x] `AdminUserCreateRequest` (`:177-216`): add `project_id: UUID | None = Field(default=None)`.
  - [x] Add a `@model_validator(mode="after")`: **require** `project_id` when `role == "project_admin"`; **forbid** it (must be `None`) when `role == "standard"`. Raise `ValueError` (FastAPI → 422) with a clear message in each case.
- [x] **Task 2 — Backend atomic create (AC: 2, 4)** in `create_user` (`:292-320`):
  - [x] After building the `User` and `db.add(user)`, when `role == "project_admin"`, `db.flush()` to get `user.id`, then `db.add(ProjectMembership(project_id=request.project_id, user_id=user.id, role=PROJECT_ADMIN_ROLE))` in the **same transaction**, then a single `db.commit()`.
  - [x] Validate the project exists first (`db.get(Project, request.project_id)`) → 404 / 422 if missing, before insert.
  - [x] Keep the existing duplicate-email pre-check + `except IntegrityError`/`except DuplicateUserError` → 409 (rollback rolls back BOTH inserts). **No** uniqueness check on the membership (many-to-many).
  - [x] Import `PROJECT_ADMIN_ROLE` (from `ai_qa.api.auth.rbac` or `ai_qa.auth.service`) — see Dev Notes.
- [x] **Task 3 — Frontend picker (AC: 1, 5)** in `frontend/src/components/admin/AdminDashboard.tsx`:
  - [x] Add `const [createUserProjectId, setCreateUserProjectId] = useState<string>("")`.
  - [x] Render a project `<select>` ONLY when `createUserRole === "project_admin"`, placed right after the Role `<select>` (`:903`). Options from `projects` (already in scope via `useProject()`, `:233`). Label "Project", `aria-label="Project"`.
  - [x] If `projects.length === 0` and role is `project_admin`: disable the submit button and show a helper message ("Create a project first before adding a project admin."). Reset `createUserProjectId` to `""` when switching role back to Standard.
  - [x] In `handleCreateUser` (`:392-417`) include `project_id` in the `createAdminUser` body only when role is `project_admin` (send the selected id; send `undefined`/omit for standard). Reset `createUserProjectId` on success.
- [x] **Task 4 — Lib + types (full-stack sync) (AC: 1, 2)**:
  - [x] `frontend/src/types/project.ts` — `CreateAdminUserRequest` (`:113-121`): add `project_id?: string | null`.
  - [x] `frontend/src/lib/projects.ts` — `createAdminUser` already forwards the request body; no signature change needed beyond the type.
- [x] **Task 5 — Tests (AC: 1-5)**:
  - [x] Backend (`tests/api/test_admin_users_api.py`): create project_admin WITH valid `project_id` → 200 + a `project_admin` membership row exists; project_admin WITHOUT `project_id` → 422; standard WITH `project_id` → 422; project_admin with a non-existent `project_id` → 404/422. Add a second project_admin to the SAME project → 200 (proves many-to-many; no uniqueness error).
  - [x] Frontend (`AdminDashboard.test.tsx`): the existing create-user test asserts the POST body — extend it so selecting Project Admin renders the picker, and the POST body includes `project_id`; Standard role shows no picker and omits `project_id`. Add the empty-projects guard case.
  - [x] Run `uv run pytest --no-cov tests/api/test_admin_users_api.py`, `npm run test`, `npm run typecheck`.

## Dev Notes

### Linkage model — reuse `ProjectMembership`, no new table

The signed-off RBAC design (Decision 1, `design-projectadmin-rbac-redesign-2026-06-21.md:138`) settled the project_admin↔project link as a `ProjectMembership` row with `role = "project_admin"` — **no new table**. This is already how `require_project_admin_for_project` (`src/ai_qa/api/auth/rbac.py:56-80`) and the project-admin router (`src/ai_qa/api/projects_admin.py`) recognize a project_admin. Creating that membership here makes the new user immediately able to administer the project.

`PROJECT_ADMIN_ROLE = "project_admin"` is defined in `src/ai_qa/auth/service.py:17` and re-exported from `src/ai_qa/api/auth/rbac.py:10,84`. Import the constant — do not hard-code the string.

### Many-to-many (Decision, 2026-06-21) — DO NOT enforce 1:1

The original investigation (item 3) proposed 1:1 invariants ("one project_admin per project; one project per project_admin"). **That was overridden** — the final decision is **many-to-many**: a project may have several project_admins and a user may admin several projects (more assigned later via the existing `POST /admin/projects/{id}/memberships` and `POST /project-admin/projects/{id}/members` flows). So:

- No uniqueness check, no 409 conflict path for the membership, no partial index.
- The only uniqueness that exists is the pre-existing `uq_project_memberships_project_user` (one membership row per (project, user)) — irrelevant on create of a brand-new user.

### Atomicity pattern

`create_user` today (`admin.py:292-320`) does `db.add(user)` then a single `db.commit()` wrapped in `except IntegrityError/DuplicateUserError → 409`. Keep that envelope and add the membership before the commit:

```python
project = None
if request.role == PROJECT_ADMIN_ROLE:
    project = db.get(Project, request.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")

user = User(...)  # unchanged
db.add(user)
if request.role == PROJECT_ADMIN_ROLE:
    db.flush()  # assigns user.id without committing
    db.add(ProjectMembership(
        project_id=request.project_id, user_id=user.id, role=PROJECT_ADMIN_ROLE,
    ))
try:
    db.commit()
except (IntegrityError, DuplicateUserError) as exc:
    db.rollback()  # rolls back BOTH user and membership
    raise HTTPException(status_code=409, detail="User already exists") from exc
db.refresh(user)
return _to_admin_user_response(user)
```

`request.project_id` is `UUID | None`; inside the `project_admin` branch the model-validator has guaranteed it is set — but mypy/Pyrefly won't know. Narrow it (`assert request.project_id is not None`) before passing to a non-optional param to stay clean under both checkers (project-context "Narrow Optional before use").

### Model-validator (Pydantic v2)

`AdminUserCreateRequest` already uses `field_validator`s (`admin.py:186-215`). Add an after-validator:

```python
@model_validator(mode="after")
def validate_project_link(self) -> AdminUserCreateRequest:
    if self.role == "project_admin" and self.project_id is None:
        raise ValueError("A project is required when creating a project admin.")
    if self.role == "standard" and self.project_id is not None:
        raise ValueError("A standard user cannot be linked to a project at creation.")
    return self
```

`AdminUserRole = Literal["project_admin", "standard"]` (`admin.py:45`) already forbids creating another `admin` — leave that as-is.

### `_to_admin_user_response` already serializes memberships

`_to_admin_user_response` (`admin.py:257-279`) emits `project_memberships` with `project_name`, ordered by project name, including the new `project_admin` row — so the created project_admin's project shows up immediately (used by Story 15.4). It eager-reads `membership.project.name`; in tests, ensure the project row is committed/visible. No response-schema change needed.

### Frontend specifics

- `projects` comes from `useProject()` (`AdminDashboard.tsx:233`) — same source the Projects panel renders. Use `proj.id` / `proj.name`.
- Conditional render keeps the picker out of the DOM for Standard, satisfying AC1 and keeping the existing create-standard-user test green except for the new selector.
- Reset `createUserProjectId` in the role `onChange` (`:893-897`) when switching to Standard, and on successful create (alongside the other `setCreateUser*` resets at `:405-409`).
- The body sent to `createAdminUser` (`:398-404`) should include `project_id` only for project_admin: `...(createUserRole === "project_admin" ? { project_id: createUserProjectId } : {})`.

### Full-stack sync (project-context rule)

A backend payload change MUST update the matching TS interface in the same change. `CreateAdminUserRequest` (`types/project.ts:113-121`) gets `project_id?: string | null`. Run `npm run typecheck` to verify (Vite skips strict errors).

### Constraints / conventions

- FastAPI: `require_admin`-guarded (already `_admin: User = AdminDependency`). Do NOT `mock.patch` dependencies in tests — use `app.dependency_overrides` / the canonical fixtures (`client`, `admin_token`, `user_token` from `tests/api/conftest.py`; scaffold pattern in `tests/api/test_admin_rbac_api.py`).
- Async-DB rule: this router uses a **sync** `Session` (`DbSessionDependency`), so `db.flush()`/`db.get()` are fine (no `MissingGreenlet` concern here — these endpoints are `async def` but use the sync session dependency, consistent with the rest of `admin.py`).
- `uv` only; Python 3.14; English-only UI strings.

### Project Structure Notes

- Backend: `src/ai_qa/api/admin.py` only (schema + `create_user`). No migration (membership table exists).
- Frontend: `AdminDashboard.tsx`, `types/project.ts`. `lib/projects.ts` unchanged (generic body forwarding).
- Coordinates with 15.2 (same file) and feeds 15.4 (project name display) + 15.5 (role-flip membership rules reuse this create path's membership logic).

### References

- [Sprint change proposal — Story C](../planning-artifacts/sprint-change-proposal-2026-06-21.md)
- [RBAC design — Decisions §10 (linkage)](../planning-artifacts/design-projectadmin-rbac-redesign-2026-06-21.md) (line 138)
- [Investigation — item 3](investigations/admin-dashboard-project-user-mgmt-investigation.md) (note: the 1:1 invariant in the investigation is SUPERSEDED by the many-to-many decision)
- [Epic 15 / Story 15.3](../planning-artifacts/epics.md) (lines 1620-1646)
- Code: `src/ai_qa/api/admin.py:45,177-216,257-320`, `src/ai_qa/api/auth/rbac.py:10,56-92`, `src/ai_qa/auth/service.py:17`, `frontend/src/components/admin/AdminDashboard.tsx:233,392-417,882-903`, `frontend/src/types/project.ts:113-121`
- Tests: `tests/api/test_admin_users_api.py`, `frontend/src/components/admin/AdminDashboard.test.tsx`

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story)

### Debug Log References

- `uv run pytest --no-cov tests/api/test_admin_users_api.py tests/api/test_admin_projects_api.py` → 27 passed (5 new project_admin cases).
- `uv run mypy src/ai_qa/api/admin.py` → clean; `uv run ruff check/format` → clean.
- `npm run typecheck` / `npm run lint` → clean; `npm run test src/components/admin/AdminDashboard.test.tsx` → 16 passed.

### Completion Notes List

- **AC1/AC3** — `AdminUserCreateRequest` gained `project_id: UUID | None` plus a `@model_validator(mode="after")` that requires `project_id` for `project_admin` and forbids it for `standard` (both → 422). FE: a project `<select>` (aria-label "Project") renders only when role is `project_admin`.
- **AC2** — `create_user` creates the `User` and a `ProjectMembership(role="project_admin")` in one transaction (`db.flush()` then a single `db.commit()`); a commit failure rolls back BOTH. The target project is validated (`db.get(Project, …)` → 404) before any insert.
- **AC4** — Many-to-many: no uniqueness/409 path on the membership; `test_multiple_project_admins_same_project` proves two project_admins can share one project.
- **AC5** — When `projects.length === 0` and role is `project_admin`, the picker is disabled, an amber "Create a project first…" helper shows, and the submit button is disabled (also disabled until a project is selected, enforcing the required picker). Switching back to Standard resets `createUserProjectId`.
- **Full-stack sync** — `CreateAdminUserRequest` (types/project.ts) gained `project_id?: string | null`; `lib/projects.ts` forwards the body unchanged. The existing create-user test now selects a project and asserts `project_id` in the POST body; two focused tests cover picker visibility and the empty-projects guard.

### File List

- `src/ai_qa/api/admin.py` (modified — `AdminUserCreateRequest` schema/validator + `create_user` atomic membership; `PROJECT_ADMIN_ROLE` import)
- `frontend/src/components/admin/AdminDashboard.tsx` (modified — `createUserProjectId` state, conditional picker, submit guard, body)
- `frontend/src/types/project.ts` (modified — `CreateAdminUserRequest.project_id`)
- `tests/api/test_admin_users_api.py` (modified — `TestAdminUserCreateProjectAdmin` + `Project` import)
- `frontend/src/components/admin/AdminDashboard.test.tsx` (modified — picker selection + two new tests)

### Review Findings

#### Patch

- [x] `[Review][Patch]` `db.flush()` is outside the `try/except IntegrityError` block in `create_user` [`src/ai_qa/api/admin.py`] — if flush raises an IntegrityError (e.g. email race: two simultaneous requests both pass the pre-check then flush), it propagates as an unhandled 500 instead of the expected 409. The assert + project lookup + `db.flush()` + `db.add(ProjectMembership(...))` should all be inside the existing `try` block that wraps `db.commit()`.

#### Deferred

- [x] `[Review][Defer]` `DuplicateUserError` catch branch in `create_user` may be dead code [`src/ai_qa/api/admin.py`] — deferred, pre-existing; auth service raises `DuplicateUserError` only from `create_user_from_form`, not from plain ORM model construction; no regression introduced by this story.

## Change Log

- 2026-06-21 — Story 15.3 implemented: conditional project picker on Create User, atomic User+ProjectMembership(project_admin), many-to-many, full-stack types, tests. Status → review. (claude-opus-4-8)
