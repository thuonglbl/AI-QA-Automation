# Sprint Change Proposal - 2026-06-03

## Section 1: Issue Summary
- **Triggering Issue 1:** New requirement: The admin needs the ability to trigger a full E2E test run directly from the Admin Dashboard. The tests must run in headed mode with slow motion so the admin can visually monitor them. Upon completion, the test report should be automatically downloaded to the admin's machine.
- **Triggering Issue 2:** Technical Pivot: The currently chosen S3-compatible storage solution, MinIO, has been archived on GitHub and is no longer actively maintained. We need to replace it with a robust, actively maintained open-source alternative (SeaweedFS is recommended).

## Section 2: Impact Analysis
- **Epic Impact:**
  - **Epic 8 (Admin Dashboard):** Requires the addition of a new user story (Story 8.6) to implement the E2E test execution and report download features.
  - **Epic 10 (Project Artifact Collaboration):** References to MinIO need to be updated to SeaweedFS across the board.
- **Artifact Conflicts:**
  - **PRD:** Must be updated to include the new Admin E2E feature and replace MinIO with SeaweedFS in the tech stack.
  - **Architecture / UX Design:** The dashboard layout needs a new button/flow. Backend architecture diagrams and texts need to swap MinIO for SeaweedFS.
- **Technical Impact:**
  - `README.md`, `docker-compose.yml`, and any `docker-compose.override.yml` files must be updated to remove MinIO services and replace them with SeaweedFS services. The S3 client implementation in the backend should be verified for compatibility with SeaweedFS, though standard boto3/S3 clients usually work seamlessly.
  - The backend needs a new endpoint to trigger Playwright in headed mode and stream/return the results. Note: Running headed browsers from a backend container might require specific X11/display forwarding configurations, which adds technical complexity.

## Section 3: Recommended Approach
- **Direct Adjustment:** We will integrate the new Admin E2E feature directly into Epic 8 as it aligns with administrative monitoring capabilities. We will replace MinIO with SeaweedFS globally.
- **Rationale:** 
  - **Storage Pivot:** Moving away from abandoned software early is critical. SeaweedFS is highly performant, fully S3-compatible, and actively maintained.
  - **E2E Trigger:** Adding this to the admin dashboard provides immediate value for system health verification.
- **Effort Estimate:** Medium
- **Risk Level:** Medium (Running headed browsers in a typical backend server environment requires a virtual display setup or tight coupling with the host machine).

## Section 4: Detailed Change Proposals

### Story Changes
**Epic 8**
```diff
+ ### Story 8.6: Admin E2E Test Execution
+ 
+ As an admin,
+ I want to trigger an automated E2E test run from the dashboard,
+ So that I can visually monitor the system's health in real-time and review the test reports.
+ 
+ **Acceptance Criteria:**
+ 
+ **Given** an authenticated admin is on the dashboard
+ **When** they click "Run E2E Tests"
+ **Then** the backend triggers the E2E test suite using Playwright in headed mode with slow motion
+ **And** the admin can observe the browser execution (via UI or visual streaming)
+ 
+ **Given** the E2E test run completes
+ **When** the report is generated
+ **Then** the report file is automatically downloaded to the admin's client machine
```

**Epic 10**
```diff
- FR42: The MinIO artifact tree is shared at project level.
+ FR42: The SeaweedFS artifact tree is shared at project level.
- FR44: If a PostgreSQL project exists but MinIO has no objects for it, the UI still shows the required empty folders for the selected project.
+ FR44: If a PostgreSQL project exists but SeaweedFS has no objects for it, the UI still shows the required empty folders for the selected project.
- FR67: Direct external MinIO notifications and artifact version rollback are out of MVP scope.
+ FR67: Direct external SeaweedFS notifications and artifact version rollback are out of MVP scope.
```

### PRD Changes
```diff
- - Backend uses Python 3.12+, `uv`, Hatchling, FastAPI, SQLAlchemy/Alembic, PostgreSQL, MinIO, Pydantic Settings, Ruff, mypy, pytest, and pytest-asyncio.
+ - Backend uses Python 3.12+, `uv`, Hatchling, FastAPI, SQLAlchemy/Alembic, PostgreSQL, SeaweedFS, Pydantic Settings, Ruff, mypy, pytest, and pytest-asyncio.
- - MinIO stores project-level artifact bytes under `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/`.
+ - SeaweedFS stores project-level artifact bytes under `projects/{project_id}/requirements/`, `projects/{project_id}/test_cases/`, and `projects/{project_id}/test_scripts/`.
```

## Section 5: Implementation Handoff
- **Scope Categorization:** Moderate
- **Handoff Recipients:**
  - **Product Owner (PM Agent):** Update the PRD, Epics, and Architecture artifacts to reflect the addition of Story 8.6 and the replacement of MinIO with SeaweedFS.
  - **Developer Agent:** Implement the code changes, specifically modifying `docker-compose.yml`, `docker-compose.override.yml`, `README.md`, and adding the new API endpoints and UI elements for the E2E feature.
