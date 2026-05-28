# Story 12.12: Fix frontend 401 Unauthorized API calls

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want the frontend API client to correctly include the authentication token for all project-scoped API calls,
So that data loads successfully without returning 401 errors.

## Acceptance Criteria

1. Given a user is logged in, when the frontend makes a project-scoped request to `/api/projects/{id}/...`, then the request includes the proper Authorization header.
2. Given an API call returns 401, then the error is handled gracefully or prompts re-authentication.

## Tasks / Subtasks

- [x] Inspect frontend API client configuration and interceptors to ensure authentication tokens are attached to project-scoped endpoints.
- [x] Fix the request header configuration.
- [x] Implement or verify graceful handling/re-authentication on 401 response.
- [x] Test project-scoped API calls.

## Dev Notes

- This is a regression introduced during Epic 12 decoupling.
- The `GET /api/projects/...` requests are returning 401. Ensure token extraction and attachment works correctly.

### Project Structure Notes

- Frontend API client code is typically under `frontend/src/api` or `frontend/src/lib/api`.

### References

- [Source: _bmad-output/planning-artifacts/sprint-change-proposal-2026-05-29.md#Story 12.12]
- [Source: _bmad-output/planning-artifacts/epics.md#Story 12.12: Fix frontend 401 Unauthorized API calls]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

- ✅ Modified `LoginPage.tsx` to extract `access_token` from the login response and store it in `localStorage` under `aiqa_access_token`.
- ✅ Updated `apiFetch` in `api.ts` to automatically attach the `Authorization` bearer token to all requests if present.
- ✅ Updated `fetchWithAuth` and `logout` in `auth.ts` to use and clear the token from `localStorage`.
- ✅ Updated `apiFetch` to dispatch a global `auth-error` event when a 401 response is received.
- ✅ Modified `AuthContext.tsx` to listen for the `auth-error` event and trigger a session refresh, gracefully logging out the user if the session is invalid.

### File List

- `frontend/src/components/auth/LoginPage.tsx`
- `frontend/src/lib/api.ts`
- `frontend/src/lib/auth.ts`
- `frontend/src/contexts/AuthContext.tsx`
