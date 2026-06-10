# Test Summary

## Story 7.1: Local Login and Authenticated Session Foundation

Generated a true full-stack Playwright E2E spec with no backend API mocks:

- `frontend/e2e/story-7-1-auth.spec.ts`

Coverage:

- Registers a real standard user through `POST /auth/register` against the local FastAPI backend and PostgreSQL database.
- Logs in through the real React UI and real `/auth/login` endpoint.
- Verifies the frontend stores `aiqa_access_token` and can call the real `/auth/me` endpoint with `Authorization: Bearer <token>`.
- Verifies current-user response includes email, display name, role, and active status.
- Verifies password hash/secret fields are not returned from register/current-user responses.
- Verifies invalid credentials are rejected with a safe API error and user-facing UI error.

Validation command:

```powershell
Set-Location frontend
$env:BASE_URL='http://127.0.0.1:5173'
$env:API_URL='http://127.0.0.1:8000'
npx playwright test story-7-1-auth.spec.ts --reporter=line
```

Result: `2 passed (32.0s)`

Notes:

- This test requires Docker Compose PostgreSQL/SeaweedFS, migrated schema, real FastAPI backend on `127.0.0.1:8000`, and real Vite frontend on `127.0.0.1:5173`.
- The previous mocked project-selection browser workflow is not treated as true E2E.
