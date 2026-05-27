# Story 12.10: User Project Selection in Alice Configuration Flow

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want project selection to happen inside Alice's configuration chat flow,
so that I can start the pipeline directly after login without a separate Project Workspace screen.

## Acceptance Criteria

1. Given a standard user logs in successfully, when routing completes, then the frontend bypasses the Project Workspace screen and opens the Home pipeline UI at Alice — Config.
2. Given Alice starts for an authenticated standard user, when the user's accessible projects are loaded, then Alice determines whether the user has zero, one, or multiple projects.
3. Given the user has zero accessible projects, then Alice shows: "You do not have access to any project yet. Please contact an administrator to assign you to a project." and does not show AI provider selection.
4. Given the user has exactly one accessible project, then Alice shows: "You have only one project called <project name>. Auto proceed with this project.", automatically selects that project, and then shows the AI provider selection message.
5. Given the user has two or more accessible projects, then Alice shows: "Please select one project to proceed" and renders a selectable list of project names.
6. Given the user clicks one project from the list, then the chat adds a right-aligned user message containing the selected project name.
7. Given a project has been selected manually or automatically, then all subsequent project-scoped API calls and WebSocket connections use the selected project ID.
8. Given Alice has not resolved a selected project yet, then Alice does not show "Which AI provider would you like to use?..." or provider options.
9. Given an admin logs in, then the existing admin dashboard routing remains unchanged.

## Tasks / Subtasks

- [x] Task 1: Remove standard-user Project Workspace gate from app routing (AC: 1, 9)
  - [x] Delete or bypass the `if (isAuthenticated && !isProjectReady) return <ProjectPicker />` branch in `frontend/src/App.tsx` for standard users.
  - [x] Keep the existing admin-first branch (`user.role === "admin" -> <AdminDashboard />`) before pipeline rendering.
  - [x] Keep `ProjectPicker` available only if explicitly retained for future/debug use; it must not be the happy path after login.
- [x] Task 2: Move project resolution into the Alice chat area (AC: 2, 3, 4, 5, 6, 8)
  - [x] Extend `ProjectContext` or app-level logic so Alice can observe `projects`, `isLoadingProjects`, `projectError`, `selectedProject`, `selectedProjectId`, and `selectProject` without forcing a separate screen.
  - [x] Add an Alice-rendered project resolution component or inline section above provider selection in `frontend/src/App.tsx`.
  - [x] For zero projects: render the exact no-access message and do not render `ProviderSelector`.
  - [x] For one project: auto-select it once, render the exact auto-proceed message with the project name, then allow provider selection.
  - [x] For multiple projects: render Alice's exact selection prompt and a selectable list of project names.
  - [x] On manual project selection: call `selectProject(project.id)` and add a right-aligned user message containing only or clearly containing the selected project name.
- [x] Task 3: Gate AI provider selection on resolved project context (AC: 4, 7, 8)
  - [x] Change `showProviderSelector` so it requires Alice step, provider options, and `selectedProjectId`.
  - [x] Ensure the provider prompt text from `ProviderSelector` is not mounted until a project is selected/auto-selected.
  - [x] Preserve existing provider submission payload fields: `projectId` and `project_id` both equal `selectedProjectId`.
- [x] Task 4: Preserve project-scoped API and WebSocket behavior (AC: 7)
  - [x] Keep `useWebSocket(selectedProjectId)` wired to the selected project.
  - [x] Keep start/approve/reject/navigate messages including selected project ID.
  - [x] Verify clearing/changing project resets context safely and prevents provider actions without a selected project.
- [x] Task 5: Update focused frontend tests (AC: 1-9)
  - [x] Update `frontend/src/App.test.tsx` expectations that currently require the ProjectPicker before pipeline.
  - [x] Add tests for zero, one, and multiple project flows in Alice.
  - [x] Assert provider options are hidden before selection and visible after auto/manual selection.
  - [x] Assert admin routing still bypasses project selection and opens Admin Dashboard.

### Review Findings

- [x] [Review][Patch] Stale persisted project ID is treated as resolved before accessible projects load [frontend/src/App.tsx:270]
- [x] [Review][Patch] Multiple-project users with a valid stored project bypass the required Alice selection prompt [frontend/src/App.tsx:423]
- [x] [Review][Patch] Changing projects leaves stale Alice provider/model review state visible [frontend/src/App.tsx:318]
- [x] [Review][Patch] Rejecting model assignments does not clear submitted provider selection [frontend/src/App.tsx:246]
- [x] [Review][Patch] Late WebSocket messages can mutate Alice state after project changes [frontend/src/App.tsx:166]
- [x] [Review][Patch] Missing verification that subsequent project-scoped calls use selected project IDs [frontend/src/App.test.tsx:70]
- [x] [Review][Defer] Conversation persistence API is not scoped to selected project [frontend/src/hooks/usePipelineState.ts:34] — deferred, pre-existing

## Dev Notes

### Source Requirements

- Story source: `_bmad-output/planning-artifacts/epics.md`, Story 12.10.
- Epic 12 goal: complete the multi-user database/auth/project foundation before resuming Epic 6+.
- Course-correction context: the Project Workspace screen should be removed from the standard-user happy path; project selection belongs inside Alice.

### Current State / Files to Update

- `frontend/src/App.tsx`
  - Currently imports and renders `ProjectPicker` when `isAuthenticated && !isProjectReady`.
  - Currently initializes `useWebSocket(selectedProjectId)` and all Alice provider actions already include both `projectId` and `project_id`.
  - Currently computes `showProviderSelector = isAliceStep && aliceState.providerOptions`, so provider options can render before project resolution unless the whole page is gated by ProjectPicker.
  - Currently filters user messages so only approve/reject messages are specially shown; project-selection user messages may be shown in the general message list if added via `addUserMessage`.
- `frontend/src/contexts/ProjectContext.tsx`
  - Loads accessible projects through `listProjects()` when authenticated.
  - Persists selected project in `localStorage` under `ai-qa-selected-project-id`.
  - `selectProject(projectId)` validates membership against loaded `projects` and clears errors.
  - `isProjectReady` is currently `Boolean(selectedProject)`; do not rely on this to route standard users away from Alice.
- `frontend/src/components/ProviderSelector.tsx`
  - Contains the exact provider prompt text that must be hidden until project selection is resolved.
  - Keep credential validation and submitted-selection behavior unchanged.
- `frontend/src/components/projects/ProjectPicker.tsx`
  - Existing standalone Project Workspace UI. Do not reuse it wholesale inside Alice because the acceptance criteria require chat-style Alice messages, exact copy, and right-aligned selected-project user message.
- `frontend/src/App.test.tsx`
  - Existing tests currently assert the old project picker behavior and must be updated.

### Architecture Compliance

- Frontend route `/` remains the main 5-agent pipeline UI; standard users route there directly after login.
- Admin route behavior is unchanged: authenticated admins go directly to `AdminDashboard`.
- Alice must resolve standard-user project context before AI provider selection.
- All project-scoped API/WebSocket calls must use the selected project ID.
- Maintain React 18 + TypeScript + Vite patterns, existing Tailwind/Shadcn styling, and WCAG-friendly controls with descriptive IDs.
- Do not add new backend endpoints unless testing reveals a missing contract; `GET /api/projects` already supports accessible project loading.

### UX Requirements

- Required exact Alice messages:
  - Zero projects: `You do not have access to any project yet. Please contact an administrator to assign you to a project.`
  - One project: `You have only one project called <project name>. Auto proceed with this project.`
  - Multiple projects: `Please select one project to proceed`
- Manual selection must add a right-aligned user message containing the selected project name.
- Project options should look like chat interaction controls, not a separate full-page workspace.
- Provider selection prompt (`Which AI provider would you like to use?...`) must not appear until after project resolution.

### Previous Story Intelligence

- Story 12.9 completed admin dashboard fixes and removed login self-registration.
- Recent files modified by 12.9: `frontend/src/components/admin/AdminDashboard.tsx`, `frontend/src/components/admin/AdminDashboard.test.tsx`, `frontend/src/components/auth/LoginPage.tsx`.
- Do not regress admin user/project management, admin-only user creation, or admin dashboard routing.
- Recent review findings emphasized avoiding placeholder UI actions, stale state after project/membership updates, missing loading states, and unhandled promise flows.

### Git Intelligence

Recent commits:

- `d529171 feat Story 12.9: Admin Dashboard Refinement and Fixes`
- `24b552e Story 12.8: Bugfix - Admin Routing and Dashboard Enhancements`
- `22b0ec4 feat update document for local env`
- `6a91d3c completed epic 12`
- `4e05362 feat Story 12.7: Refactor Existing Pipeline from Workspace Paths to Project Context`

Actionable implications:

- Build on the existing Epic 12 frontend auth/project context rather than creating a new project store.
- Preserve Story 12.7 project-scoped payload conventions (`projectId` and `project_id`).
- Preserve Story 12.8/12.9 admin routing and dashboard behavior.

### Testing Requirements

- Run focused frontend tests from `frontend/`:
  - `npm run test -- App.test.tsx` or the project's Vitest equivalent.
  - `npm run lint` if available.
- Update tests to cover:
  - Standard user with zero projects sees Alice no-access message and no provider prompt.
  - Standard user with one project sees auto-proceed message and provider options.
  - Standard user with multiple projects sees selectable project list; clicking a project adds the selected project name as a user message and reveals provider options.
  - Admin user still sees Admin Dashboard directly.
- If tests mock `WebSocket`, ensure the mock tolerates `selectedProjectId` being null before project resolution.

### Anti-Patterns to Avoid

- Do not keep the standard-user ProjectPicker as a required intermediate screen.
- Do not show provider options before `selectedProjectId` is resolved.
- Do not invent a second project API client or duplicate project state outside `ProjectContext` unless absolutely necessary.
- Do not remove `projectId`/`project_id` from existing WebSocket payloads.
- Do not change admin routing or login self-registration behavior.

### References

- `_bmad-output/planning-artifacts/epics.md#Story-12.10-User-Project-Selection-in-Alice-Configuration-Flow`
- `_bmad-output/planning-artifacts/architecture.md#Frontend-&-API-Layer`
- `_bmad-output/planning-artifacts/architecture.md#Agent-Orchestration-Layer`
- `_bmad-output/planning-artifacts/sprint-change-proposal-2026-05-14.md`
- `_bmad-output/implementation-artifacts/12-9-admin-dashboard-refinement.md`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- `npm run test -- App.test.tsx` (initial focused baseline before implementation): passed with old expectations.
- `npm run test -- App.test.tsx` (after implementation and test update): passed, 5 tests.
- `npm run lint`: passed.
- `npm test -- --run`: executed full frontend regression suite; App tests passed, but pre-existing component test failures remain in `ModelAssignmentReview`, `ProviderSelector`, `ProcessingIndicator`, and `ErrorFeedback`.

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created.
- Removed the standard-user Project Workspace routing gate so authenticated non-admin users enter the pipeline UI directly at Alice.
- Added Alice chat-style project resolution inside `App.tsx` using existing `ProjectContext` state for zero, one, and multiple project cases.
- Auto-selects the only accessible project once and displays the required auto-proceed message before provider selection.
- Renders the exact no-access and multi-project prompt copy and hides `ProviderSelector` until `selectedProjectId` is resolved.
- Manual project selection calls `selectProject(project.id)` and records the selected project name as a right-aligned user message.
- Preserved `useWebSocket(selectedProjectId)` and existing `projectId`/`project_id` payload behavior for start, approve, reject, and navigation messages.
- Reset submitted Alice state and model assignments when project authorization errors clear the selected project.
- Updated focused `App.test.tsx` coverage for unauthenticated, zero-project, single-project auto-select, multi-project manual selection, and admin dashboard routing flows.

### File List

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `_bmad-output/implementation-artifacts/12-10-user-project-selection-in-alice-configuration-flow.md`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`

### Change Log

- 2026-05-15: Implemented Story 12.10 Alice-integrated project selection flow and updated sprint/story status to review.
