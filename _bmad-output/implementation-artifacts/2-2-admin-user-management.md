---
baseline_commit: e9731777aa6516d25d6aca0189012a401cfaf907
---

# Story 2.2: Admin User Management

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin,
I want to view and create local user accounts,
so that I can control who can access the AI QA Automation system.

## Acceptance Criteria

1. Given an authenticated admin opens user management, when the frontend requests the user list, then the backend returns users with id, email, display name, role, status, and project memberships, and password hashes and secret values are never returned.
2. Given an authenticated admin submits a new user with email, display name, role, and initial password, when the backend validates the request, then a user is created with the password stored only as a secure hash, and duplicate emails are rejected with a safe validation message.
3. Given the user management screen is displayed, when the admin views available actions, then self-service registration is not shown, and user creation is available only to admins.

## Tasks / Subtasks

- [x] Task 1: Reconcile sprint-story scope with existing implementation state (AC: 1-3)
  - [x] Confirm whether this story should validate and harden existing code rather than reimplement it: backend admin user list/create and frontend create-user UI already exist from Stories 12.8 and 12.9.
  - [x] Do not overwrite or recreate the existing admin dashboard, auth flow, or user APIs unless a specific AC gap is found.
- [x] Task 2: Ensure admin user list response includes project memberships without secrets (AC: 1)
  - [x] Inspect `GET /api/admin/users` in `src/ai_qa/api/admin.py` and decide whether to extend `AdminUserResponse` with `project_memberships` or `memberships` data required by the AC.
  - [x] If extending the response, include only membership/project identifiers and display-safe fields; never include password hashes, encrypted secrets, secret status internals, or token material.
  - [x] Keep admin-only protection through `require_admin`; standard and unauthenticated users must receive 403/401 respectively.
- [x] Task 3: Ensure admin-created users support the required request contract (AC: 2)
  - [x] Verify whether the story requires admin-selected `role`; current `AdminUserCreateRequest` creates only `standard` users.
  - [x] If role selection is required, restrict accepted roles to approved non-escalating values or explicitly document product decision that admin-created accounts are standard-only.
  - [x] Preserve normalized email handling, minimum password length, secure password hashing, active user default, and safe duplicate-email 409 responses.
- [x] Task 4: Validate frontend user management flow (AC: 1-3)
  - [x] Update `frontend/src/components/admin/AdminDashboard.tsx` only if current UI fails the ACs.
  - [x] Ensure the user list displays email, display name, role, status, and project memberships from authoritative API/project data.
  - [x] Ensure the create-user form remains admin-dashboard-only and collects email, display name, initial password, and role only if backend supports role selection.
  - [x] Ensure no self-service registration link or toggle is present in `frontend/src/components/auth/LoginPage.tsx`.
- [x] Task 5: Add or adjust focused tests (AC: 1-3)
  - [x] Backend: extend `tests/test_admin_rbac_api.py` for membership-inclusive, secret-free user list, admin create-user success, duplicate-email 409, and standard/unauthenticated denial.
  - [x] Frontend: extend `frontend/src/components/admin/AdminDashboard.test.tsx` for displayed user fields, project membership display, create-user POST payload, no Manage Membership/self-registration affordance, and safe error handling.
  - [x] Run backend focused tests and frontend focused tests/build before moving to review.

## Dev Notes

### Current State and Existing Implementation

This story is a backlog-status duplicate/renumbering hazard. The implementation already contains substantial admin user management from later Epic 12 stories:

- `src/ai_qa/api/admin.py` already defines admin-only `GET /admin/users` and `POST /admin/users`, mounted under `/api` by `create_app()`.
- `AdminUserResponse` currently returns `id`, `email`, `display_name`, `role`, `is_active`, `created_at`, and `updated_at`; it intentionally omits `password_hash` and secrets.
- `AdminUserCreateRequest` currently accepts `email`, `display_name`, and `initial_password`; created users are always `role="standard"` and `is_active=True`.
- `frontend/src/components/admin/AdminDashboard.tsx` already has a full-page admin dashboard, user list, user create form, and per-user project assignment/unassignment controls.
- `frontend/src/lib/projects.ts` already has `listAdminUsers()` and `createAdminUser()` using `/admin/users` through the shared `apiFetch()` helper.
- `frontend/src/types/project.ts` already defines `AdminUser` and `CreateAdminUserRequest` types.
- `frontend/src/components/auth/LoginPage.tsx` was previously updated to remove self-service account creation.

Developer must treat this story as a gap-closing and validation task, not a greenfield build. Reuse and harden the existing code.

### Epic Context

Epic 2 is "Admin Dashboard and Project Membership Management". Story 2.2 specifically covers admin user management:

- Admin can view local users.
- Admin can create local users.
- API/UI must not expose password hashes or secret values.
- Duplicate emails must fail safely.
- Self-service registration is not available; user creation is admin-only.

Adjacent stories in the epic:

- Story 2.1 covers admin routing/access control.
- Story 2.3 covers project CRUD.
- Story 2.4 covers membership assignment/removal.

Because this repository already implemented these concerns under Stories 12.8 and 12.9, avoid breaking project CRUD and membership behavior while closing Story 2.2 gaps.

### Architecture Compliance

- Backend stack: Python 3.12+, FastAPI, SQLAlchemy ORM, Pydantic models, PostgreSQL/Alembic, pytest.
- Frontend stack: React 18, TypeScript, Vite, Shadcn/ui primitives, Tailwind CSS, Vitest + React Testing Library.
- Admin API routes belong in `src/ai_qa/api/admin.py` and must stay protected by `require_admin`.
- Auth/user domain helpers live under `src/ai_qa/auth/`; reuse `normalize_email()`, `get_user_by_email()`, and `hash_password()` rather than duplicating logic.
- User and project membership persistence uses SQLAlchemy models in `src/ai_qa/db/models.py`.
- Frontend admin components belong under `frontend/src/components/admin/`; do not move admin logic into the standard workspace flow.
- Shared frontend API helpers belong in `frontend/src/lib/projects.ts`; shared frontend types belong in `frontend/src/types/project.ts`.

### File Structure Requirements

Likely update files:

- `src/ai_qa/api/admin.py` — only if `GET /admin/users` must include project memberships or create-user must accept role.
- `frontend/src/components/admin/AdminDashboard.tsx` — only if displayed data or create-user payload must change.
- `frontend/src/types/project.ts` — if response/request schemas change.
- `frontend/src/lib/projects.ts` — if request/response types change.
- `tests/test_admin_rbac_api.py` — add/adjust backend coverage.
- `frontend/src/components/admin/AdminDashboard.test.tsx` — add/adjust frontend coverage.
- `frontend/src/components/auth/LoginPage.tsx` — inspect only; avoid changing unless self-registration appears.

Do not modify unrelated agent pipeline, artifact, provider, or project-selection code for this story.

### Data Contract Guidance

If AC1 is interpreted strictly, the admin user list must include project membership data directly in each user object. Current frontend derives project membership display from `/api/projects` project membership summaries, while `GET /api/admin/users` returns user identity/status only. The developer must choose one of these safe approaches and keep tests explicit:

1. Extend `AdminUserResponse` with a field such as `project_memberships: list[AdminUserProjectMembershipResponse]`, populated via `ProjectMembership` joins; or
2. Preserve split API design if product/architecture already treats `/api/projects` as the membership source, and document/test that the user management screen displays memberships by combining `listAdminUsers()` and `listProjects()`.

If the response is extended, use minimal safe fields only: `id`, `project_id`, optional `project_name`, `role`, `created_at`, `updated_at`. Never include `password_hash`, encrypted secret columns, raw API keys, session data, or internal token material.

### Security Requirements

- Passwords must be stored only as one-way hashes via `hash_password()`; never log or return plaintext or hashes.
- API and frontend error messages must be safe: duplicate email may say "User already exists" but must not leak internals.
- Standard users and unauthenticated requests must not access `/api/admin/users`.
- Admin-created users must not bypass validation; keep email normalization and password minimum length.
- Do not reintroduce self-registration or a public registration endpoint in the UI.
- API/WebSocket responses must never return user secrets or provider/MCP keys.

### UX Requirements

- Use the existing Professional Calm design system: slate surfaces/text, blue primary actions, green success, red error.
- Keep admin dashboard full-page routing for admin users only; standard users must remain in the workspace flow.
- User management should show users with display name, email, role badge, active/inactive status, and assigned projects.
- Form controls need labels, focus-visible styling, accessible buttons, and live status/error feedback.
- Do not add modal confirmation dialogs unless explicitly required; previous UX patterns favor inline, non-disruptive feedback.

### Previous Story Intelligence

From Story 12.8:

- Admin routing already bypasses project selection via `App.tsx` when user role is admin.
- Full-page `AdminDashboard` replaced the older `AdminPanel`.
- Known fixes from review were applied: project form placement, user-project lookup performance, stale user refreshes, loading state, dismissible errors, responsive layout, display-name mismatch, and logout promise handling.

From Story 12.9:

- `PUT /admin/projects/{id}`, `DELETE /admin/projects/{id}`, `POST /admin/users`, membership assign/remove, and dashboard user/project actions were implemented.
- Create User form replaced Manage Membership.
- Disabled "Sync existing company's users" action exists with explanatory text.
- Per-user Projects section has assignment dropdown and remove controls.
- Self-registration link was removed from login.
- Deferred concern: admin-created password flow lacks forced reset/invite semantics. Do not implement forced reset unless requested; keep scope to Story 2.2 ACs.

### Git Intelligence

Recent commit titles show current work has focused on planning docs, UI popup sizing, Docker/MinIO, and MCP extraction fixes:

- `e973177 feat completed prd architect epics documents for multi-thread, shared output files`
- `a84e2ce fix flexible width for confirm popup`
- `6e9200d fix docker compose with minio`
- `473dd50 fix requirement extraction from mcp confluence`
- `2f4a6b5 fix confirm requirement url popup`

Do not assume recent commits changed admin user management; verify current files directly.

### Testing Requirements

Backend focused validation:

- `python -m pytest tests/test_admin_rbac_api.py --no-cov`
- Include tests that assert `password_hash` is absent from `GET /api/admin/users` responses.
- Include tests for duplicate email 409, blank/invalid input 422, and standard/unauthenticated denial.
- If membership fields are added to user responses, assert membership data is present and secret-free.

Frontend focused validation:

- From `frontend/`: `npm run test -- src/components/admin/AdminDashboard.test.tsx`
- From `frontend/`: `npm run build`
- If request schemas change, assert create-user POST body includes the intended fields and excludes secrets.
- Verify no self-service registration affordance is visible on login/admin flows.

### References

- Source: `_bmad-output/planning-artifacts/epics.md`, Story 2.2 Admin User Management.
- Source: `_bmad-output/planning-artifacts/architecture.md`, Frontend & API Layer and Unified Project Structure sections.
- Source: `_bmad-output/planning-artifacts/ux-design-specification.md`, Component Implementation Strategy and accessibility/design-system guidance.
- Source: `_bmad-output/implementation-artifacts/12-8-bugfix-admin-routing-and-dashboard.md`, previous admin routing/dashboard implementation notes.
- Source: `_bmad-output/implementation-artifacts/12-9-admin-dashboard-refinement.md`, previous admin user creation and dashboard refinement notes.

## Project Structure Notes

- This repository already has the frontend scaffold and admin dashboard. Do not create a new frontend project.
- Keep backend route paths consistent with the existing mounted API: route definitions use `/admin/...` in `admin.py`, and clients call `/api/admin/...` through `apiFetch()`.
- Preserve existing project/membership APIs while changing user-management data contracts.
- Avoid adding new dependencies; current stack is sufficient.

## Completion Status

Ultimate context engine analysis completed - comprehensive developer guide created.

## Dev Agent Record

### Agent Model Used

- GitHub Copilot (Claude Haiku 4.5)

### Debug Log References

- Backend focused tests: `.venv/Scripts/python.exe -m pytest tests/test_admin_rbac_api.py --no-cov` — 13 passed.
- Frontend focused tests: `npm run test -- src/components/admin/AdminDashboard.test.tsx` — 1 passed.
- Frontend build: `npm run build` — passed.
- Existing unrelated full-suite issues are outside this story scope.

### Completion Notes

- Admin user list now includes safe `project_memberships` without password hashes or secret fields.
- Admin created user flow now accepts explicit `role` and preserves secure password hashing and duplicate-email safety.
- Admin dashboard UI now hides project assignment controls for `admin` users while standard users keep existing project management UI.
- No self-service registration or invite flow was reintroduced.

### File List

- `src/ai_qa/api/admin.py`
- `tests/test_admin_rbac_api.py`
- `frontend/src/types/project.ts`
- `frontend/src/components/admin/AdminDashboard.tsx`
- `frontend/src/components/admin/AdminDashboard.test.tsx`
- `_bmad-output/implementation-artifacts/2-2-admin-user-management.md`
