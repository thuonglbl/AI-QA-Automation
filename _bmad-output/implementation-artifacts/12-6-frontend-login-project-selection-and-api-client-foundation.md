# 12-6: Frontend Login, Project Selection, and API Client Foundation

## Header

```yaml
story_id: 12.6
story_key: 12-6-frontend-login-project-selection-and-api-client-foundation
epic: Epic 12 - Decoupled Backend, Database, Auth, and Project Foundation
status: ready-for-dev
created_by: BMad Story Agent
created_at: 2026-05-08
story_title: Frontend Login, Project Selection, and API Client Foundation
epic_title: Decoupled Backend, Database, Auth, and Project Foundation
epic_description: Pivot from single-user file-based workspace storage to a decoupled multi-user system with React frontend, FastAPI backend, PostgreSQL source of truth, and project-scoped artifacts.
```

## Requirements

### User Story

**As a** project member,  
**I want** to log in and select a project before running the agent pipeline,  
**So that** all generated results are scoped to the correct shared project.

### Acceptance Criteria (BDD)

**Scenario 1: Unauthenticated users see auth flow instead of the pipeline**
```gherkin
Given the React frontend starts
When an unauthenticated user opens the app
Then the pipeline workspace is not rendered
And a login/register flow is shown
And successful login refreshes authenticated user state without exposing tokens in UI state or logs
And failed authentication errors are shown as safe user-facing messages
```

**Scenario 2: Authenticated users select from accessible projects before pipeline use**
```gherkin
Given an authenticated standard user has one or more project memberships
When they open the app after login
Then the frontend loads only projects returned by the protected projects API
And the user must select one accessible project before the agent pipeline starts
And project name, membership role, and safe metadata are visible in the picker
And users with no projects see a clear empty state instructing them to contact an admin
```

**Scenario 3: Selected project context is attached to backend calls**
```gherkin
Given a project member selected a project
When the frontend makes project-scoped REST calls or opens the agent WebSocket
Then the selected project ID is included consistently
And the API client handles 401 by returning to auth flow
And 403/404 authorization failures clear or reject invalid project selection without revealing hidden project details
And no project-scoped call proceeds with a missing selected project ID
```

**Scenario 4: Admin users can access basic management screens**
```gherkin
Given an authenticated admin user opens the frontend
When they navigate to admin management
Then they can see users, create projects, and assign users to projects through existing admin APIs
And standard users cannot see or invoke admin management actions
And admin forms use safe validation and do not expose password hashes, session tokens, or secret fields
```

**Scenario 5: Frontend API client foundation targets current backend contracts safely**
```gherkin
Given frontend components need backend access
When they call auth, projects, admin, artifact, or future pipeline APIs
Then calls go through a centralized credentials-including API client
And auth errors, JSON parsing errors, non-JSON server responses, and network failures are handled consistently
And the client provides one compatibility boundary for the documented /api/v1 target versus the current mounted backend routes
And automated frontend tests cover auth gating, project selection, admin visibility, and API error handling
```

## Developer Context

### Epic 12 Context and Boundaries

Epic 12 is moving the product from a single-user `workspace/` folder into a multi-user project-scoped system. Stories 12.1-12.5 already created PostgreSQL persistence, local auth, RBAC, admin project/membership APIs, project listing/detail APIs, and project-scoped artifact service/API.

This story is the frontend bridge: users must authenticate, choose a project, and route all future pipeline/API behavior through a selected project context. It should make the UI ready for Story 12.7's backend pipeline refactor, but must not refactor Bob/Mary/Sarah/Jack storage behavior itself.

**Do implement:**
- A polished login/register gate that blocks the pipeline until authenticated.
- A project picker/context for authenticated users before pipeline use.
- A centralized frontend API client with credentials, typed helpers, and consistent error handling.
- Selected-project propagation into project-scoped REST calls and WebSocket connection/message payloads.
- Basic admin screens for user list, project creation, and membership assignment using existing backend APIs.
- Frontend tests for auth gating, project selection, API-client error behavior, and admin-only visibility.

**Do not implement:**
- New backend project/admin/auth endpoints unless a small contract correction is required by tests.
- Full pipeline refactor from workspace paths to artifact service; Story 12.7 owns backend pipeline migration.
- Artifact browser/editor UX; this story may add client helpers only if needed.
- Enterprise Azure Entra SSO; Epic 11 remains deferred.
- Complex routing/dashboard redesign beyond what is needed for auth/project/admin foundations.

### Existing Codebase Intelligence

Relevant current files and patterns:

```text
frontend/src/
├── App.tsx                         # currently gates on auth but immediately renders Alice pipeline after login
├── components/auth/LoginPage.tsx    # existing local login/register UI using fetchWithAuth
├── contexts/AuthContext.tsx         # auth state provider using checkAuthStatus/logout
├── hooks/useAuth.ts                 # context hook wrapper
├── hooks/useWebSocket.ts            # current WebSocket hook; must accept/project context safely
├── hooks/usePipelineState.ts        # pipeline state for Alice/Bob/etc.
├── lib/auth.ts                      # current minimal auth fetch helpers; should become/reuse API client foundation
├── components/ui/                   # Shadcn/Radix primitives already available
└── types/                           # pipeline/provider types

src/ai_qa/api/
├── auth/local.py                    # /auth/register, /auth/login, /auth/logout, /auth/me, /auth/status
├── projects.py                      # /api/projects and /api/projects/{project_id}
├── admin.py                         # /api/admin/users, /api/admin/projects, /api/admin/projects/{id}/memberships
├── artifacts.py                     # /api/projects/{project_id}/artifacts...
├── websocket.py                     # current WebSocket entrypoint for live agent messages
└── app.py                           # router mounting and auth middleware configuration
```

Important current contract observations:
- Frontend currently calls `/auth/status`, `/auth/me`, `/auth/login`, and `/auth/logout` directly. Backend auth router is mounted separately from `/api`.
- Protected project/admin/artifact routes are mounted under `/api`, not `/api/v1` yet. The epics AC says API client targets `/api/v1`; implement a single base-path compatibility boundary instead of scattering literals.
- `AuthUser` in `frontend/src/lib/auth.ts` currently lacks `id`, `role`, `is_active`, and `display_name`, while backend `/auth/me` has those fields and `/auth/status` returns `email`, `name`, and `role` only.
- Current `App.tsx` already blocks unauthenticated users with `<LoginPage />`, but there is no project picker, selected-project state, or admin UI.
- Current UI contains `console.log` navigation debugging in `App.tsx`; avoid adding more console logs and remove or guard noisy logs if touched.

### Architecture and UX Guardrails

- Frontend remains React 18 + TypeScript + Vite + Shadcn/ui + Tailwind CSS.
- Preserve the existing Professional Calm design language unless improving it: slate surfaces, blue primary, green success, amber warning, red error, system font stack.
- The result should feel premium and deliberate, not like a plain form bolted onto the app. Use responsive cards, clear hierarchy, empty/loading/error states, focus rings, and smooth transitions.
- Accessibility remains WCAG 2.1 AA:
  - labels associated with inputs;
  - visible focus rings;
  - 44px minimum interactive targets;
  - `aria-live="polite"` for auth/project loading and errors;
  - no placeholder-only fields;
  - keyboard-usable project cards and admin forms.
- Keep one `<h1>` per page-level view where practical and preserve semantic structure (`main`, `section`, `nav`, `form`).
- Do not store session tokens in localStorage/sessionStorage. Authentication uses HTTP-only cookie semantics from the backend session cookie; frontend state stores only safe profile/project metadata.
- Do not log credentials, password fields, API keys, token-like values, or raw response bodies that may contain secrets.
- Keep admin UI strictly role-gated by authenticated user role from the backend. Hiding UI is not authorization; backend remains source of truth.

### Recommended Implementation Shape

Suggested new/updated frontend modules:

```text
frontend/src/lib/api.ts                 # central apiFetch/APIError/base path helpers
frontend/src/lib/auth.ts                # auth helpers using apiFetch or compatibility wrapper
frontend/src/types/project.ts           # Project, membership, admin request/response types
frontend/src/contexts/ProjectContext.tsx
frontend/src/hooks/useProject.ts
frontend/src/components/projects/ProjectPicker.tsx
frontend/src/components/admin/AdminPanel.tsx
frontend/src/components/layout/AppShell.tsx        # optional if extracting nav/layout from App.tsx
frontend/src/test-setup.ts and component tests      # reuse existing Vitest setup
```

Recommended API client behavior:

```ts
type ApiErrorKind = "auth" | "forbidden" | "not_found" | "validation" | "network" | "server";

async function apiFetch<T>(path: string, options?: ApiRequestOptions): Promise<T> {
  // Use credentials: "include" for every request.
  // Prefix project/admin/artifact routes with one configured API base.
  // Parse JSON only when content type is JSON.
  // Convert 401, 403, 404, 422, 5xx, and network failures into typed errors.
}
```

Recommended base-path rule:
- Define one `API_BASE_PATH` for protected API routes. Default to `/api` because that is the current backend contract.
- Leave a clear compatibility note or environment override for future `/api/v1`, e.g. `import.meta.env.VITE_API_BASE_PATH ?? "/api"`.
- Do not hardcode `/api` or `/api/v1` throughout components.

Recommended project context behavior:
- Load projects only after `isAuthenticated === true`.
- If exactly one accessible project exists, auto-selecting is acceptable only if visible and reversible; otherwise require explicit selection for clarity.
- Persist selected project ID only as non-secret convenience state. If using `localStorage`, validate it against freshly loaded projects before trusting it.
- Expose `selectedProject`, `selectProject(projectId)`, `clearSelectedProject()`, `isProjectReady`, `projectError`, and `reloadProjects()`.
- On logout, clear selected project state.

Recommended WebSocket/project propagation:
- Inspect `useWebSocket` and backend `websocket.py` before editing.
- Include project ID in a way current backend can ignore safely until Story 12.7 uses it, such as:
  - `ws://.../ws?project_id=<uuid>` if accepted by current endpoint; and/or
  - adding `projectId` / `project_id` to outbound action messages.
- Do not break existing Alice provider-selection flow.
- Add tests/mocks proving no WebSocket connection or pipeline start occurs before project selection.

Recommended admin UI scope:
- Users list: read-only table/card list with email, display name, role, active status.
- Project creation: name and optional description form.
- Membership assignment: select existing project, select existing active user, choose role (`member`/`owner`), submit.
- Use existing endpoints:
  - `GET /api/admin/users`
  - `POST /api/admin/projects`
  - `POST /api/admin/projects/{project_id}/memberships`
  - `GET /api/projects` to display projects after creation/assignment.
- Keep scope basic. No user editing/deactivation or membership removal unless backend already supports it.

### Previous Story Intelligence (12.5)

Story 12.5 established:
- `ArtifactService` and `LocalArtifactStorage` as the future storage contract for generated outputs.
- Protected routes under `/api/projects/{project_id}/artifacts` using `require_project_member_or_admin`.
- Safe Pydantic response models without storage-key leakage.
- Strong project membership behavior: standard users cannot see other projects; admins can access any project; unauthenticated/stale users are rejected.

Review lessons to preserve:
- Revalidate identities through backend dependencies; frontend role checks are only UX, not security.
- Avoid leaking hidden project/resource existence to outsiders.
- Keep response schemas secret-free; never expose password hashes, raw tokens, storage paths, or ORM graphs in UI state.
- Existing full regression after 12.5 passed with `.\.venv\Scripts\python.exe -m pytest --no-cov` (`474 passed, 2 skipped`), and Ruff passed for changed files.

### Git Intelligence

Recent commits show the current implementation direction:

```text
db8a8d2 feat 12-5: Project-Scoped Artifact Service
4aee719 fix security scan from Bitbucket
ef655c1 feat 12-4: Project and Membership Management API
db1a9ab feat 12-3: Role-Based Access Control for Admin and Standard Users
172b73b refactor: 12-2: Local Authentication and Admin Bootstrap
```

The security-scan remediation commit is recent. Do not add example credentials, real Basic auth values, tokens, or secret-looking strings in docs, tests, snapshots, or fixtures.

## Tasks / Subtasks

- [x] Add centralized frontend API client. (AC: 3, 5)
  - [x] Create or refactor `frontend/src/lib/api.ts` with `apiFetch`, typed `ApiError`, credentials inclusion, JSON/non-JSON handling, and `VITE_API_BASE_PATH` compatibility defaulting to `/api`.
  - [x] Move protected API calls away from scattered `fetch` literals; keep auth route exceptions centralized because auth currently lives outside `/api`.
  - [x] Ensure 401, 403, 404, validation, network, and server errors map to safe UI messages.
- [x] Normalize authenticated user state. (AC: 1, 4)
  - [x] Update `AuthUser` to include safe backend profile fields (`id` if available, `email`, `display_name`/`name`, `role`, `is_active`).
  - [x] Update `checkAuthStatus`, `getCurrentUser`, login, and logout behavior to use the client and clear project state on logout.
  - [x] Ensure tokens/passwords are never stored in React state beyond form inputs and never logged.
- [x] Implement project selection foundation. (AC: 2, 3)
  - [x] Add project types and API helpers for list/get project responses from `/api/projects`.
  - [x] Add `ProjectContext`/`useProject` for loading accessible projects, selected project, selection validation, empty state, and reload.
  - [x] Add `ProjectPicker` UI shown after login and before pipeline workspace.
  - [x] Prevent pipeline UI, WebSocket connection, and project-scoped actions until a valid selected project exists.
- [x] Propagate selected project into backend communication. (AC: 3)
  - [x] Update `useWebSocket` to accept selected project ID and include it in query string and/or outbound messages without breaking current backend handling.
  - [x] Ensure Alice provider selection, approve/reject, and future pipeline messages include selected project context.
  - [x] Handle invalid/expired project access by clearing selected project and showing a safe error.
- [x] Add basic admin management UI. (AC: 4)
  - [x] Add admin API helpers for users, project creation, and membership assignment using existing `/api/admin/*` endpoints.
  - [x] Add `AdminPanel` visible only when authenticated user role is `admin`.
  - [x] Provide users list, create-project form, and assign-membership form with loading/success/error states.
  - [x] Ensure standard users cannot access admin actions from UI and backend errors remain handled if requests fail.
- [x] Preserve and polish the existing pipeline UI. (AC: 1, 2, 3)
  - [x] Keep Alice provider-selection flow working after project selection.
  - [x] Keep top navigation/logout behavior; add selected project display and change-project action.
  - [x] Remove or guard noisy debug `console.log` calls touched in `App.tsx`.
  - [x] Maintain Professional Calm styling and accessibility requirements.
- [x] Add automated tests. (AC: 1, 2, 3, 4, 5)
  - [x] Test unauthenticated users see login and not pipeline content.
  - [x] Test authenticated users see project picker before pipeline and can select accessible projects.
  - [x] Test no-project empty state.
  - [x] Test admin panel visibility and basic admin API submit behavior with mocked responses.
  - [x] Test `apiFetch` maps auth, forbidden/not-found, validation, non-JSON, and network errors consistently.
  - [x] Run `npm run typecheck` and `npm run test` from `frontend/`; run targeted backend tests only if backend contracts are touched.

### Review Findings

- [x] [Review][Patch] Admin project creation response type does not match backend response [frontend/src/lib/projects.ts:16]
- [x] [Review][Patch] Backend 401 from project reload does not return users to auth flow [frontend/src/contexts/ProjectContext.tsx:70]
- [x] [Review][Patch] Invalid selected project access is not cleared on WebSocket authorization failures [frontend/src/App.tsx:372]
- [x] [Review][Patch] Story tests do not cover App-level auth/project/admin gating required by AC 1-4 [frontend/src/App.test.tsx:1]

## Out of Scope

- Backend pipeline refactor to consume selected project/artifact context end-to-end.
- Artifact browser/editor, artifact diffing, version restore, approval workflows, or comments.
- Enterprise SSO / Azure Entra UI.
- Admin user creation/deactivation, password reset, membership removal, or role editing unless already supported by backend.
- Metrics dashboard and leadership reporting.
- Changing backend route mounting globally from `/api` to `/api/v1`; this story creates the client compatibility boundary only.

## Project Context Reference

- `_bmad-output/planning-artifacts/epics.md`, Epic 12 Story 12.6: login/register gate, project picker, project ID in API/WebSocket calls, admin screens, API client targeting `/api/v1` concept.
- `_bmad-output/planning-artifacts/architecture.md`: React 18 + TypeScript + Vite + Shadcn/Tailwind, FastAPI REST/WebSocket, WCAG 2.1 AA, Professional Calm design system, credentials/secrets constraints.
- `_bmad-output/implementation-artifacts/12-5-project-scoped-artifact-service.md`: project-scoped artifact route patterns and membership/security lessons.
- `frontend/src/App.tsx`: current authenticated pipeline shell and Alice flow to preserve.
- `frontend/src/components/auth/LoginPage.tsx`: existing local login/register UI to improve/reuse.
- `frontend/src/lib/auth.ts`: current minimal auth helper that should be consolidated with the API client.
- `src/ai_qa/api/projects.py`: accessible project list/detail contract and membership guard behavior.
- `src/ai_qa/api/admin.py`: existing admin user/project/membership endpoints.
- `src/ai_qa/api/auth/local.py`: local auth route contracts and safe profile fields.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro

### Debug Log References

- `npm run typecheck` from `frontend/` passed after review fixes.
- Targeted frontend tests passed after review fixes: `npx vitest run src/App.test.tsx src/lib/api.test.ts src/components/projects/ProjectPicker.test.tsx src/components/admin/AdminPanel.test.tsx`.
- Earlier full `npm run test` failed in pre-existing component tests unrelated to this story (`ProviderSelector`, `ProcessingIndicator`, `ModelAssignmentReview`, `ErrorFeedback` expectations mismatch current components). New and review-added story tests pass.

### Completion Notes List

- Implemented centralized API client with credentials, base-path compatibility (`VITE_API_BASE_PATH` default `/api`), JSON/non-JSON parsing, and safe typed errors.
- Normalized frontend auth profile state to include safe backend fields and removed logout redirect side effect.
- Added project API helpers, project types, `ProjectContext`, `useProject`, and a polished project picker gate shown before the pipeline.
- Prevented WebSocket connection and pipeline start until project selection, and propagated selected project ID in WebSocket query strings and outbound messages.
- Added admin-only management panel for user listing, project creation, and membership assignment using existing protected admin endpoints.
- Preserved Alice provider flow while adding selected-project display/change action and removing noisy navigation console logs.
- Added automated tests for API client behavior, project picker states, and admin submit behavior.

### File List

- `frontend/src/App.tsx`
- `frontend/src/App.test.tsx`
- `frontend/src/main.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/api.test.ts`
- `frontend/src/lib/auth.ts`
- `frontend/src/lib/projects.ts`
- `frontend/src/types/project.ts`
- `frontend/src/contexts/ProjectContext.tsx`
- `frontend/src/hooks/useProject.ts`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/components/projects/ProjectPicker.tsx`
- `frontend/src/components/projects/ProjectPicker.test.tsx`
- `frontend/src/components/admin/AdminPanel.tsx`
- `frontend/src/components/admin/AdminPanel.test.tsx`
- `_bmad-output/implementation-artifacts/sprint-status.yaml`
- `_bmad-output/implementation-artifacts/12-6-frontend-login-project-selection-and-api-client-foundation.md`

## Story Completion Status

```yaml
status: done
completion_notes: |
  Story 12.6 implementation completed and code review patches resolved. TypeScript validation passes and targeted frontend tests for App auth/project/admin gating, API client behavior, project picker states, and admin submit behavior pass. Full frontend suite still has unrelated pre-existing component expectation failures outside this story scope.
```
