---
title: 'Upgrade All Dependencies'
type: 'chore'
created: '2026-06-26T13:23:00+07:00'
status: 'done'
baseline_commit: '4887387a56e7e8378479e54249f86c0790517d20'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The Python backend libraries (`pyproject.toml`), JavaScript/TypeScript frontend libraries (`package.json`), Dockerfile base images, and documentation (`README.md`) might be outdated and need to be upgraded to their latest versions.

**Approach:** Upgrade all backend dependencies (via `uv`) and frontend dependencies (via `npm`), updating their respective lockfiles. Upgrade base images and tool versions in `Dockerfile.backend` and `frontend/Dockerfile` (as well as related docker-compose files). Update `README.md` to reflect any new versions or updated commands. Run the entire test suite and typechecks to identify and fix any breaking changes or compatibility issues introduced by these upgrades.

## Boundaries & Constraints

**Always:** Ensure all test cases (`pytest` on the backend, `vitest` & `playwright` on the frontend) and TypeScript compiler checks pass after the updates.
**Ask First:** If there are major breaking changes in core frameworks (e.g., FastAPI, React) that require extensive, large-scale rewrites of the codebase.
**Never:** Delete functional features or tests merely to bypass library compatibility errors.

</frozen-after-approval>

## Code Map

- `pyproject.toml` -- Python dependency management (backend).
- `uv.lock` -- Backend lockfile.
- `frontend/package.json` -- JavaScript/TypeScript dependency management (frontend).
- `frontend/package-lock.json` -- Frontend lockfile.
- `Dockerfile.backend` -- Backend Docker image configuration.
- `frontend/Dockerfile` -- Frontend Docker image configuration.
- `docker-compose.yml` -- Docker Compose configuration.
- `README.md` -- Project documentation.

## Tasks & Acceptance

**Execution:**
- [x] `pyproject.toml` -- Update dependency constraints and run the update via `uv` to get the latest versions.
- [x] `frontend/package.json` -- Update all dependencies to the latest version and run `npm install` to update the lockfile.
- [x] `Dockerfile.backend` -- Upgrade the Python base image version if applicable.
- [x] `frontend/Dockerfile` -- Upgrade the Node base image version if applicable.
- [x] `README.md` -- Review and update any mentioned framework/library versions, CLI commands, or base images to match the new upgrades.
- [x] `tests/` -- Run the backend test suite (`pytest`) and resolve any issues.
- [x] `frontend/src/` -- Run `npm run typecheck`, `npm run lint`, and `npm run test`, then resolve any frontend issues.

**Acceptance Criteria:**
- Given a project using outdated libraries, base images, and documentation, when dependencies, Dockerfiles, and `README.md` are upgraded to the latest versions, then the application (both backend and frontend) must build successfully, all automated tests must pass, and the documentation must accurately reflect the new states.

## Spec Change Log

## Verification

**Commands:**
- `uv run pytest` -- expected: All backend tests pass successfully.
- `cd frontend && npm run typecheck` -- expected: TypeScript compiles without errors.
- `cd frontend && npm run test` -- expected: All frontend unit tests pass successfully.
- `cd frontend && npm run test:e2e` -- expected: All E2E tests pass successfully (if configured).
- `docker compose build` -- expected: Docker images build successfully.

## Suggested Review Order

- Backend dependency updates
  [`pyproject.toml:11`](../../pyproject.toml#L11)

- Frontend dependency updates
  [`package.json:15`](../../frontend/package.json#L15)
