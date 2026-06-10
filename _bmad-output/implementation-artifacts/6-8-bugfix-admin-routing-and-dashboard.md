# Story 6.8: Bugfix - Admin Routing and Dashboard Enhancements

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin,
I want to be routed directly to an administrative dashboard when logging in,
so that I can bypass project selection and manage users and projects effectively.

## Acceptance Criteria

1. Given an authenticated user with the 'admin' role logs in, When the frontend routes the user, Then the admin bypasses the Project Picker and goes straight to the Admin Dashboard.
2. Given the admin is on the Admin Dashboard, When they view the interface, Then there is a functional "Logout" button.
3. And the admin's email, display name, and role are displayed next to the "Logout" button.
4. And there is a vertical list on the left showing projects with create, edit name, and delete buttons.
5. And there is a vertical list on the right showing users and the projects they belong to.
6. And there are buttons to assign projects to members and remove users from projects.

## Tasks / Subtasks

- [x] Task 1: Refactor routing to bypass ProjectPicker for admins (AC: 1)
  - [x] Update `App.tsx` logic to check `user.role === 'admin'`. If true, render `AdminDashboard` instead of `ProjectPicker` or the main chat pipeline.
- [x] Task 2: Create full-page AdminDashboard component (AC: 2, 3)
  - [x] Move/refactor the current `AdminPanel` logic into a full-page `AdminDashboard` component.
  - [x] Add an admin header with the user's email, display name, and role.
  - [x] Add a functional "Logout" button that calls the existing `logout()` from `useAuth`.
- [x] Task 3: Enhance projects and users lists (AC: 4, 5, 6)
  - [x] Render a vertical list of projects on the left, adding UI for editing the project name and deleting projects.
  - [x] Render a vertical list of users on the right, displaying their details and the projects they belong to.
  - [x] Enhance the membership assignment section to allow adding/removing users to/from projects.

## Dev Notes

- **Architecture:** The current `AdminPanel` is rendered at the bottom of the main chat view in `App.tsx`. This story elevates it to a dedicated full-page view for admins, skipping the project selection step entirely.
- **Components to Touch:** `frontend/src/App.tsx`, `frontend/src/components/admin/AdminPanel.tsx` (or renamed to `AdminDashboard.tsx`). You might need to update API client methods in `frontend/src/lib/projects.ts` if edit/delete projects or list users' projects endpoints are missing.
- **Testing:** Ensure `AdminPanel.test.tsx` (or its equivalent) is updated to reflect the new layout and logout functionality. Verify that non-admin users still see the `ProjectPicker` and the chat pipeline.

### Project Structure Notes

- Keep all new admin components in `frontend/src/components/admin/`.
- Rely on Shadcn/ui + Tailwind CSS for styling to maintain the "Professional Calm" design system.

### References

- Epic 12 context: `_bmad-output/planning-artifacts/epics.md#Epic-12-Decoupled-Backend-Database-Auth-and-Project-Foundation`
- Routing logic reference: `frontend/src/App.tsx`
- Existing Admin logic: `frontend/src/components/admin/AdminPanel.tsx`

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

- Implemented `AdminDashboard` to replace `AdminPanel` for full-page routing.
- Refactored `App.tsx` to display `AdminDashboard` for `admin` role users directly after login, bypassing `ProjectPicker`.
- Enhanced dashboard UI with 2-column layout displaying "Projects", "Users Management", "Create Project", and "Manage Membership" panels.
- Placed placeholder UI actions for "Edit", "Delete" (project), and "Remove User" with `notImplemented` alert since the backend APIs are not implemented yet.
- Updated component tests and mocked `localStorage` properly for Vitest testing setup.

### File List

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/test-setup.ts`
- `frontend/src/components/admin/AdminDashboard.tsx`
- `frontend/src/components/admin/AdminDashboard.test.tsx`
- `frontend/src/components/admin/AdminPanel.tsx` (Deleted)
- `frontend/src/components/admin/AdminPanel.test.tsx` (Deleted)

### Review Findings

- [x] [Review][Patch] Deviation in "Create Project" UI placement — Move "Create Project" form into the left list to match AC4 exactly. [frontend/src/components/admin/AdminDashboard.tsx]
- [x] [Review][Patch] O(N*M) Performance Issue — Nested `filter` inside `map` for userProjects in AdminDashboard.tsx.
- [x] [Review][Patch] Stale User State on Updates — Users list is not refreshed after project/membership updates.
- [x] [Review][Patch] No Initial Loading State — listAdminUsers() is called without setting a loading state.
- [x] [Review][Patch] Missing Error Dismissal UI — Error messages have no "Close" button.
- [x] [Review][Patch] Hardcoded Height Layout Breaks — `h-[500px]` is too rigid for responsiveness.
- [x] [Review][Patch] Inconsistent Name Properties — Mismatch between `user.name` and `u.display_name`.
- [x] [Review][Patch] Poor Error State Management — Single error state string blindly overwrites previous errors.
- [x] [Review][Patch] Unhandled logout() promise rejection — `logout()` could throw unhandled rejection.
- [x] [Review][Patch] Project name/description whitespace handling — Potential issues with whitespace-only inputs.
- [x] [Review][Patch] Admin role string differently cased — Route check might fail if `user.role` case differs.
- [x] [Review][Patch] Redundant second "Remove User" button — Confusing placement inside the Assign form.
- [x] [Review][Patch] Incomplete localStorage Mocking — test-setup.ts mock is missing standard properties.
- [x] [Review][Defer] Fake/Missing functional implementation for Edit, Delete, and Remove User actions — deferred, backend APIs are not implemented yet.
- [x] [Review][Defer] Tight Coupling to Hardcoded String Roles — deferred, pre-existing architectural choice.
