# Testing Architecture

This repository uses a dual testing framework architecture:

1. **Frontend (E2E):** Playwright (`frontend/e2e/`)
2. **Backend (API/Integration/Unit):** Pytest (`tests/`)

## Setup Instructions

### Frontend

- Ensure Node LTS is installed (see `frontend/.nvmrc`).
- Run `npm install` inside the `frontend/` directory.
- Run `npx playwright install` to install browser binaries.

### Backend

- Ensure Python 3.12+ is installed.
- Install dependencies: `uv pip install -e ".[dev]"` (or equivalent pip install).

## Running Tests

### Frontend (Playwright)

- Execute `npm run test:e2e` in the `frontend` folder.
- Add `--headed` to view execution, or `--ui` for interactive mode.

### Backend (Pytest)

- Execute `uv run pytest tests -q` in the root folder to run all backend tests with the configured coverage gate.
- Execute `uv run pytest tests -q --no-cov` to run all backend tests without the coverage gate during local story validation.
- Execute `uv run pytest tests/unit --no-cov` to run only unit tests.
- Execute `uv run pytest tests/integration --no-cov` to run integration tests.
- Execute `uv run pytest tests -k api --no-cov -q` to run API-related tests without listing individual files.
- Do not use `pytest tests/api` for the current suite; that folder currently contains documentation only, so it collects zero tests and can fail the global coverage gate.

## Architecture & Best Practices

- **Fixtures:** Composable frontend fixtures live in `frontend/support/fixtures/index.ts`; backend fixtures live in `tests/conftest.py`.
- **Factories:** Frontend data factories live in `frontend/support/fixtures/factories/` and must expose cleanup behavior.
- **Helpers:** API, auth, and network helpers live in `frontend/support/helpers/`.
- **Isolation:** Tests should not depend on each other. Clean up state post-execution if required.
- **Selectors:** Rely on `data-testid` or accessible role/name selectors instead of classes for UI tests.
- **Network:** Register route mocks before navigation so requests cannot race ahead of interception.
- **Artifacts:** Playwright traces, screenshots, and videos are retained only for failure diagnostics.

## CI Integration

A quality pipeline should run these commands before merge:

```bash
cd frontend
npm ci
npx playwright install --with-deps chromium
npm run test
npm run test:e2e

cd ..
uv run pytest tests -q
```

Store Playwright HTML reports and JUnit XML from `_bmad-output/test-artifacts/` as CI artifacts when available.

## Knowledge Base Alignment

The framework follows these TEA patterns:

- Fixture architecture: pure helper/factory code is wrapped by Playwright fixtures.
- Data factories: factories track generated entities and provide cleanup.
- Network-first testing: route mocks are registered before page navigation.
- Test quality: tests use Given/When/Then structure and avoid hard-coded waits.

## Troubleshooting

- If Playwright cannot find browsers, run `npx playwright install` from `frontend/`.
- If E2E tests cannot reach the app, verify `BASE_URL` in `.env` or `.env.example`.
- If API-backed tests fail locally, verify `API_URL` and backend server status.
- If pytest imports fail, reinstall the backend package with dev dependencies.
