---
baseline_commit: ca4f0f08e59168b9fbd4fde1be92b4d75fc952ee
---
# Story 7.1: Local Login and Authenticated Session Foundation

## 1. Story Requirements

**Epic 7: Secure Multi-User Workspace Foundation**
Users can securely access the system, select and bind projects to threads, resume private conversation history, and operate inside a project-scoped collaborative workspace shell.
**FRs covered:** FR30, FR31, FR32, FR33, FR34, FR37, FR38, FR39, FR40, FR41, FR47, FR48, FR49, FR50, FR51, FR53

**User Story:**
As a project user,
I want to log in with local email/password credentials,
So that I can access the system securely before entering any workspace.

**Acceptance Criteria:**

* **Given** a seeded user account exists with an email, display name, role, and password hash
    **When** the user submits valid login credentials
    **Then** the backend authenticates the user and returns a session/token suitable for protected API calls
    **And** the frontend stores and applies the session/token through the API client
* **Given** a user submits an invalid email or password
    **When** login is attempted
    **Then** authentication is rejected with a safe, consistent error message
    **And** the response does not reveal whether the email exists
* **Given** an authenticated user calls the current-user endpoint
    **When** the session/token is valid
    **Then** the backend returns the user's email, display name, and role
    **And** no password hash or secret data is returned

## 2. Developer Context & Guardrails

> [!WARNING]
> **Duplicate Scope Warning:** Looking at the sprint status, Epic 6 already completed `6-2-local-authentication-and-admin-bootstrap` and `6-6-frontend-login-project-selection-and-api-client-foundation`. The functionality described in this story (login endpoint, frontend token storage, current-user endpoint) appears to have already been built.
> **Action Required:** First evaluate `src/ai_qa/api/auth/local.py`, `src/ai_qa/api/auth/session.py`, and the frontend login components. If they already satisfy the ACs above, your implementation may just be a verification pass or minor refactoring to ensure it fits the Epic 7 workspace shell context. Do not rebuild existing login systems.

### Technical Requirements

* **Authentication:** Must use existing local auth service (`src/ai_qa/auth/service.py` and `src/ai_qa/api/auth/`) and password hashing.
* **Secrets:** Passwords are one-way hashed. Tokens must be handled securely based on current established patterns.
* **API Client:** Frontend API client must attach the session/token to all protected requests.

### Architecture Compliance

* **Frontend:** React 18+ with TypeScript, Vite, Shadcn/ui.
* **Backend:** FastAPI. Route endpoints must be in the correct `api/routes/` or `api/auth/` files.
* **No generic exceptions:** Use custom exceptions from `ai_qa/exceptions.py`.
* **Data Models:** Exchange data using Pydantic models (e.g., `Token`, `UserLogin`, `UserResponse`), never raw dicts.
* **Security:** Ensure the current-user endpoint strips out the password hash before returning the user object.

### File Structure Requirements

* **Backend Auth:** `src/ai_qa/api/auth/local.py` (and related route files)
* **Frontend Auth:** `frontend/src/features/auth/` or `frontend/src/features/workspace/`

### Testing Requirements

* **Backend:** pytest tests for successful login, invalid login (safe error message), and current-user endpoint.
* **Security Test:** Assert that the password hash is NOT returned in the current-user response.

## 3. Previous Story Intelligence

### Epic 7 Context

First story in Epic 7 - pulling context from Epic 6.

* Epic 6 heavily built out PostgreSQL persistence, auth bootstrap, RBAC, and project-scoped artifact services.
* **Lesson:** Maintain the established pattern of using Dependency Injection in FastAPI for getting the DB session and current user.

## 4. Git Intelligence Summary

Recent commits established the `src/ai_qa/api/auth` structure and session middleware. Be sure to reuse these instead of creating new auth mechanisms.

## 5. Dev Agent Record

### Debug Log

* Investigated existing implementation as suggested by the Duplicate Scope Warning.
* Checked backend: `src/ai_qa/api/auth/local.py` contains `/login`, `/register`, and `/me` endpoints that properly hash passwords and set HttpOnly session cookies + return tokens.
* Checked backend tests: `tests/test_auth_api.py` fully tests the required ACs, asserting that the password hash is excluded and login errors are safely reported.
* Checked frontend: `frontend/src/lib/api.ts` correctly extracts token from `localStorage` and includes it in headers.
* Frontend auth contexts also correctly manage state.

### Completion Notes

All ACs were already implemented in Epic 6. The verification pass was completed successfully. Story marked as review.

## 6. File List

* (No code files were modified, only verification steps were performed.)

## 7. Change Log

* Added YAML frontmatter for baseline commit.
* Completed verification of existing implementation.
* Changed Status from ready-for-dev to review.

## 8. Status

**Status:** `done`
