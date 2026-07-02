---
baseline_commit: 43e37ec
---
# Story 9.8: Dynamic Multi-Environment Model Sync Configuration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story Foundation

As a system administrator,
I want to enable or disable the Model Sync feature and dynamically configure multiple remote target databases via environment variables,
So that I can disable it on restricted environments (UAT) while syncing all environments simultaneously from my local machine with one click.

### Acceptance Criteria

**Given** the application starts
**When** the `ENABLE_MODEL_BENCHMARK_SYNC` environment variable is set to `false`
**Then** the frontend hides the "Sync models" button or feature
**And** the backend rejects requests to the sync endpoint with a 403 Forbidden

**Given** the application starts
**When** the `ENABLE_MODEL_BENCHMARK_SYNC` environment variable is set to `true`
**Then** the frontend displays the "Sync models" button
**And** the backend allows the sync operation

**Given** the user clicks the "Sync models" button
**When** `SYNC_TARGET_DATABASES` is configured with a valid JSON array of `{"name": "...", "url": "..."}` objects
**Then** the backend syncs the model benchmark data to the primary database
**And** iterates through the JSON array, dynamically creates a connection for each `url`, and syncs the data to those remote databases
**And** handles errors gracefully if one remote DB fails, without crashing the whole process.

## Dev Agent Guardrails

### Technical Requirements

1. **Configuration Integration:**
   - Add `enable_model_benchmark_sync: bool = Field(default=True)` to `AppSettings` in `src/ai_qa/config.py`.
   - Add `sync_target_databases: list[dict[str, str]] = Field(default_factory=list)` (or an appropriate Pydantic parsed JSON string) to `AppSettings`.
2. **Backend Sync Orchestration:**
   - Modify `sync_models_and_benchmarks` (or its surrounding endpoint call) in `src/ai_qa/admin/model_sync.py` to iterate through the array from `SYNC_TARGET_DATABASES`.
   - For each target, dynamically create a SQLAlchemy `create_engine(url)` and sync the newly fetched data.
   - **CRITICAL:** Call `engine.dispose()` after syncing to avoid connection leaks.
   - **CRITICAL:** Use a `try/except` block to catch and log any errors occurring for a specific remote DB so that the whole sync operation does NOT crash.
3. **Endpoint Security:**
   - Modify the REST API endpoint that triggers the sync (e.g., in `src/ai_qa/api/routes/admin.py`) to check `settings.enable_model_benchmark_sync`. If false, raise an `HTTPException(status_code=403, detail="Model sync is disabled in this environment.")`.
4. **Frontend Toggle:**
   - Expose the `enable_model_benchmark_sync` flag via a configuration endpoint (or include it in the existing `/api/admin/config` payload, if present).
   - The frontend Admin Dashboard MUST conditionally render the "Sync models" button based on this flag.

### Architecture Compliance

- **No Secrets Leaking:** URL connection strings in `SYNC_TARGET_DATABASES` may contain passwords. **MUST NOT** log the raw URLs. Use the existing `mask_database_url` from `src/ai_qa/config.py` when logging which target databases are being synced or failing.
- **Pydantic Settings:** All environment variables MUST be modeled in `AppSettings`. Do not use `os.environ` or `os.getenv` directly in business logic.
- **Custom Exceptions:** Do not raise generic exceptions. Use `ai_qa/exceptions.py`. For warning/errors, use the logger.
- **Error Handling:** Graceful degradation. If one DB sync fails, log the error using `logger.error("Failed to sync remote DB %s: %s", db_name, exc)` and continue with the next. 

### Files Being Modified

- `src/ai_qa/config.py`: Add the new configuration properties with Pydantic validations.
- `src/ai_qa/admin/model_sync.py`: Update the orchestration logic to loop over remote databases.
- `src/ai_qa/api/routes/admin.py`: Add the 403 Forbidden check.
- `frontend/src/features/admin/...` (e.g., Admin Dashboard TSX): Hide the Sync button when disabled. Add required types.

### Testing Requirements

- **Backend Unit Tests:** 
  - Ensure `config.py` properly parses valid and invalid JSON for `SYNC_TARGET_DATABASES`.
  - Ensure the admin route returns 403 when the feature is disabled.
  - Test the `sync_models_and_benchmarks` loop using mock remote engines, ensuring failure on one engine still allows the other engines (and the primary DB) to sync successfully.
- **Frontend Unit/E2E Tests:**
  - Mock the configuration endpoint to return `true` then `false`, asserting the "Sync models" button appears and disappears respectively.

## Previous Story Intelligence

- **Secret Hygiene:** From Story 9.7 review feedback, secret leakage is rigorously tested. Remember to mask target URLs when logging `SYNC_TARGET_DATABASES`.
- **UX Consistency:** Do not use `window.alert` or unstyled messages. If a remote sync fails but primary succeeds, decide how to surface this in the summary payload (e.g. adding a `warnings` array to the result payload). 

## Git Intelligence Summary

- Recent commits (`2adec3e`, `2c771f0`) highlight a focus on logging detailed errors and friendly UI. Apply this to the admin dashboard if warnings occur during sync, but prioritize secure logging (no secret leaking).

## Project Context Reference

- Language: Python 3.14+, React 19+, TypeScript
- Dependency Management: `uv`
- Frameworks: FastAPI, SQLAlchemy, browser-use
- Standard: Adhere to strict type hints (`mypy` compliant) and formatting (`ruff`).

## Story Completion Status
Ultimate context engine analysis completed - comprehensive developer guide created.

## Tasks / Subtasks

- [x] **Task 1: Configuration Integration**
  - [x] Update `src/ai_qa/config.py` to add `enable_model_benchmark_sync` (bool, default True) to `AppSettings`.
  - [x] Update `src/ai_qa/config.py` to add `sync_target_databases` (list of dicts, default empty) to `AppSettings`, ensuring parsing of valid/invalid JSON.
  - [x] Write/update unit tests for config parsing in `tests/test_config.py`.
- [x] **Task 2: Backend Sync Orchestration**
  - [x] Update `src/ai_qa/admin/model_sync.py` to iterate over `SYNC_TARGET_DATABASES`.
  - [x] For each remote DB, create `create_engine(url)`, perform sync, and call `engine.dispose()`.
  - [x] Implement `try/except` to catch and log errors securely using `mask_database_url`.
  - [x] Write/update unit tests to mock remote engines, ensuring failure on one doesn't crash others.
- [x] **Task 3: Endpoint Security & Config Exposure**
  - [x] Modify `src/ai_qa/api/routes/admin.py` to enforce 403 Forbidden on the sync endpoint if `enable_model_benchmark_sync` is false.
  - [x] Ensure the configuration endpoint exposes `enable_model_benchmark_sync` for the frontend.
  - [x] Update API tests in `tests/api/routes/test_admin.py`.
- [x] **Task 4: Frontend Toggle**
  - [x] Update frontend Admin Dashboard (`frontend/src/components/admin/AdminDashboard.tsx`) to conditionally render the "Sync models and benchmarks" button.
  - [x] Add necessary TS types for the new config flag in the API response type.
  - [x] Add/update frontend tests in `AdminDashboard.test.tsx` to verify the button appears/disappears based on the mocked config.
- [x] **Task 5: Final Testing & Review**
  - [x] Unit/Integration Tests:
    - [x] Update API tests in `tests/api/routes/test_admin.py` or equivalent to verify authorization checks (403 when disabled) and valid response format.
    - [x] Write tests for `sync_models_and_benchmarks` verifying multi-database looping logic and error handling.
  - [x] E2E Testing / UI Verification:
    - [x] Launch the dev server.
    - [x] Verify the UI toggles when `enable_model_benchmark_sync` is changed in `src/ai_qa/config.py`.
    - [x] Verify that clicking "Sync models and benchmarks" properly triggers the `/api/admin/models/sync` route and reports success even if some environments fail.
