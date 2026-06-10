---
baseline_commit: 1bbe14dd919afc8cd1e3728f15dfc8cd84298844
---

# Story 8.6: Admin E2E Test Execution

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an admin,
I want to trigger an automated E2E test run from the dashboard,
so that I can visually monitor the system's health in real-time and review the test reports.

## Acceptance Criteria

1. **Given** an authenticated admin is on the dashboard
   **When** they click "Run E2E Tests"
   **Then** the backend triggers the E2E test suite using Playwright in headed mode with slow motion
   **And** the admin can observe the browser execution (via UI or visual streaming)

2. **Given** the E2E test run completes
   **When** the report is generated
   **Then** the report file is automatically downloaded to the admin's client machine

## Tasks / Subtasks

- [x] Task 1: Add API endpoint to trigger E2E tests (AC: 1, 2)
  - [x] Implement `POST /api/v1/admin/tests/e2e` in admin router.
  - [x] Ensure only admins can trigger this endpoint.
  - [x] Use `subprocess` or Playwright API to run tests in headed mode with slow-mo.
- [x] Task 2: Update Admin Dashboard UI (AC: 1)
  - [x] Add "Run E2E Tests" button to the dashboard.
  - [x] Add loading state and visual feedback while tests are executing.
- [x] Task 3: Handle test report generation and download (AC: 2)
  - [x] Configure Playwright to generate an HTML or JSON report.
  - [x] Serve the generated report file back to the admin client as a downloadable file.

## Dev Notes

- **Architecture Patterns**: 
  - Ensure endpoint is protected by Admin role checks (Epic 8).
  - Backend is FastAPI, frontend is React with Vite.
  - Test framework is Playwright.
- **Source Tree Components**:
  - `src/ai_qa/api/routers/admin.py`
  - `src/ai_qa/frontend/src/pages/admin/AdminDashboard.tsx`
  - `src/ai_qa/frontend/src/api/adminApi.ts`

### Project Structure Notes

- Adhere to the existing unified project structure. Put API changes in the existing admin router.

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Epic 8: Admin Dashboard and Project Membership Management]
- [Source: _bmad-output/planning-artifacts/architecture.md]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

- Added `/api/admin/tests/e2e` and `/api/admin/tests/e2e/report` endpoints.
- Implemented `AdminDashboard.tsx` with E2E test execution UI and report download.
- Fixed a bug where `create_app()` hung during tests due to `boto3` without a timeout. All 6 frontend unit tests and 12 backend API tests for E2E endpoints are now passing successfully.

### File List

### Review Findings

- [x] [Review][Decision] No visual streaming or UI observation of browser execution — Violates AC 1: Admin should observe execution. However, the method (logs via WebSocket, video stream, etc.) is ambiguous and requires human input. (auditor)
- [x] [Review][Decision] UI network timeout on long test runs — The synchronous fetch will timeout on the browser for long test runs. Fix requires deciding between WebSockets, polling, or increasing timeouts. (edge)
- [x] [Review][Decision] Brittle Path Resolution Assumption — _FRONTEND_DIR relies on relative paths. Should we use an env var with a fallback, or configure via pydantic-settings? (blind)
- [x] [Review][Patch] Manual report download instead of automatic [AdminDashboard.tsx]
- [x] [Review][Patch] Missing Playwright configuration updates [playwright.config.ts]
- [x] [Review][Patch] Synchronous Subprocess Blocks Event Loop [src/ai_qa/api/admin.py]
- [x] [Review][Patch] Disk Leak via Unmanaged Temp Files [src/ai_qa/api/admin.py:1586]
- [x] [Review][Patch] Infinite E2E Execution Loop [frontend/e2e/story-8-6-admin-e2e-execution.spec.ts]
- [x] [Review][Patch] Amateur Inline Imports [src/ai_qa/api/admin.py]
- [x] [Review][Patch] Fragile Executable Resolution [src/ai_qa/api/admin.py]
- [x] [Review][Patch] Unconfigurable S3 Timeouts [src/ai_qa/api/app.py]
- [x] [Review][Patch] Missing Cache-Control Headers [src/ai_qa/api/admin.py]
- [x] [Review][Patch] Silent Exception Swallowing [frontend/src/lib/projects.ts]
- [x] [Review][Patch] Missing Pre-flight Token Validation [frontend/src/lib/projects.ts]
- [x] [Review][Patch] Missing UI Loading State for Downloads [frontend/src/components/admin/AdminDashboard.tsx]
- [x] [Review][Patch] Zombie Process Risk [src/ai_qa/api/admin.py:1519]
- [x] [Review][Patch] Memory exhaustion from in-memory zip buffering [src/ai_qa/api/admin.py:1571]
- [x] [Review][Patch] Download fails with 500 Server Error if report files deleted [src/ai_qa/api/admin.py:1574]
- [x] [Review][Patch] Unhandled 500 error if npx command lacks permissions [src/ai_qa/api/admin.py:1509]
