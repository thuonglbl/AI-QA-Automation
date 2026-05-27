# Story 12.9: Admin Dashboard Refinement and Fixes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin,
I want the dashboard UI and APIs to be fully functional and streamlined,
so that I can effectively manage users and projects.

## Acceptance Criteria

1. Given an admin is on the dashboard, when they click Edit or Delete on a project, then the action calls the implemented backend API (`PUT /projects/{id}`, `DELETE /projects/{id}`) and updates the UI successfully.
2. Given a success notification appears, then it automatically hides after 3 seconds.
3. Given the user management area, then the "Manage Membership" section is replaced by a "Create User" form (with Email, Display Name, Initial Password fields).
4. Given the "Create User" form, then there is a disabled button "Sync existing company's users" that displays "This feature is not available at the moment, please add manually." on hover.
5. Given the user list, then the UI is restructured so each user card has a "Projects" section with a "+" button to assign a project and an "x" button on assigned projects to unassign them.
6. Given the login screen, then the "Need an account? Create one" link is removed, enforcing that only admins can create new accounts.

## Tasks / Subtasks

- [x] Task 1: Implement Backend APIs for Edit and Delete Projects (AC: 1)
  - [x] Subtask 1.1: Add `PUT /projects/{id}` endpoint to update project details in `src/ai_qa/api/routes.py` (or similar admin route)
  - [x] Subtask 1.2: Add `DELETE /projects/{id}` endpoint to remove projects.
- [x] Task 2: Implement Admin user creation Backend API (AC: 3)
  - [x] Subtask 2.1: Add `POST /admin/users` endpoint to create a user.
- [x] Task 3: Refine Dashboard UI for Projects (AC: 1, 2)
  - [x] Subtask 3.1: Connect Edit and Delete UI actions to new APIs in `AdminDashboard.tsx`.
  - [x] Subtask 3.2: Implement auto-hiding success notifications (3 seconds).
- [x] Task 4: Refine Dashboard UI for Users (AC: 3, 4, 5)
  - [x] Subtask 4.1: Replace "Manage Membership" section with "Create User" form.
  - [x] Subtask 4.2: Add disabled "Sync existing company's users" button with hover tooltip.
  - [x] Subtask 4.3: Restructure user cards with "Projects" section, adding "+" and "x" buttons for assignment/unassignment.
- [x] Task 5: Restrict Account Creation (AC: 6)
  - [x] Subtask 5.1: Remove "Need an account? Create one" link from the Login screen component.

### Review Findings

- [x] [Review][Decision] Edit action does not provide editable project fields — resolved by adding inline edit fields per project card.
- [x] [Review][Decision] Project assignment `+` button silently chooses a project — resolved by adding per-user project dropdown/select before assignment.
- [x] [Review][Patch] Admin project list uses user-scoped project data [frontend/src/components/admin/AdminDashboard.tsx:21]
- [x] [Review][Patch] Fully assigned or inactive users can still trigger assignment [frontend/src/components/admin/AdminDashboard.tsx:148]
- [x] [Review][Patch] Remove membership buttons are not disabled while busy [frontend/src/components/admin/AdminDashboard.tsx:343]
- [x] [Review][Patch] Disabled sync button relies only on native title tooltip [frontend/src/components/admin/AdminDashboard.tsx:380]
- [x] [Review][Patch] Backend update/delete/remove membership commits lack rollback handling [src/ai_qa/api/admin.py:198]
- [x] [Review][Defer] Project deletion has no confirmation [frontend/src/components/admin/AdminDashboard.tsx:132] — deferred, pre-existing/product UX decision
- [x] [Review][Defer] Project deletion may conflict with future dependent data beyond memberships [src/ai_qa/api/admin.py:209] — deferred, pre-existing/domain modeling concern
- [x] [Review][Defer] Admin-created password flow lacks forced reset/invite semantics [frontend/src/components/admin/AdminDashboard.tsx:94] — deferred, pre-existing/auth policy concern

## Dev Notes

- **Architecture:** 
  - API additions should be added to the admin routes.
  - `Project` models and `User` models are likely defined in `src/ai_qa/models.py` or similar DB models under `src/ai_qa`. 
  - Ensure API responses align with `StageResult` or project standards, using custom exceptions from `ai_qa/exceptions.py`.
- **Previous Story Intelligence:**
  - `AdminDashboard.tsx` is located at `frontend/src/components/admin/AdminDashboard.tsx`.
  - Placeholder UI actions for Edit, Delete, and Remove User currently show a `notImplemented` alert. They need to be fully hooked up.
  - Fix performance issue: O(N*M) nested filter for userProjects in `AdminDashboard.tsx`.
  - Fix stale state: Users list must be refreshed after project/membership updates.
  - Fix loading states: `listAdminUsers()` is currently called without setting a loading state.
  - Fix error state: Add "Close" button to error messages. Single error string blindly overwrites previous errors.
  - Fix layout: Hardcoded `h-[500px]` is too rigid, make it responsive.
  - Fix names: Mismatch between `user.name` and `u.display_name`.
  - Handle logout unhandled promise.
  - Fix "Create Project" form placement.
- **Frontend Styling:** Use Shadcn/ui and Tailwind CSS.
- **Security:** Ensure new admin APIs are properly protected and role-checked (must be `admin`).

### Project Structure Notes

- Keep admin components in `frontend/src/components/admin/`.
- FastAPI endpoints for projects and users should be well isolated and protected.

### References

- Epic 12 context: `_bmad-output/planning-artifacts/epics.md#Story-12.9-Admin-Dashboard-Refinement-and-Fixes`

## Dev Agent Record

### Agent Model Used

GitHub Copilot (GPT-4.1)

### Debug Log References

- Focused frontend test: `npx vitest run src/components/admin/AdminDashboard.test.tsx --reporter=json --outputFile=vitest-admin-result.json`
- Backend focused tests: `python -m pytest tests/test_admin_rbac_api.py --no-cov`
- Frontend lint: `npm run lint`
- Frontend build: `npm run build`

### Completion Notes List

- Verified existing protected admin backend APIs for project update/delete, user creation, membership assignment, and membership removal.
- Connected project Edit/Delete actions to admin API calls and refresh flows.
- Added 3-second auto-hide behavior for success notifications.
- Replaced membership management form with a Create User form and disabled company sync action with required hover text.
- Added per-user Projects sections with assignment and unassignment controls.
- Removed self-registration toggle/link from the login screen.
- Added/updated focused frontend coverage for project/user/membership dashboard behavior.

### File List

- frontend/src/components/admin/AdminDashboard.tsx
- frontend/src/components/admin/AdminDashboard.test.tsx
- frontend/src/components/auth/LoginPage.tsx

### Change Log

- 2026-05-14: Implemented admin dashboard refinement, login registration removal, and focused validation updates.
