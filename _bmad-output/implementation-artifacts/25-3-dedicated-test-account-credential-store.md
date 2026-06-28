---
baseline_commit: current
---
# Story 25.3: Dedicated Test-Account Credential Store

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user,
I want to store my dedicated test-account credentials (username/password + optional TOTP secret) per (project, environment, role) as encrypted user-scoped secrets,
so that the tool can log in to the target app securely without exposing my passwords to Project Admins.

## Acceptance Criteria

1. Create a database schema/table for user-scoped test-account credentials, mapped to (user_id, project_id, environment, role).
2. Generate an Alembic migration for the new table AND to drop the old project-level `test_account_credentials` table.
3. Implement encrypted CRUD operations reusing the existing Fernet per-user-secret machinery.
4. Add user-level UI for entering and managing these credentials (likely in User Settings or dynamically when launching Sarah).
5. Update Project Admin UI to remove test credentials inputs and instead only configure `login_type` (`standard`, `sso_microsoft`, `sso_google`, etc.) and `login_hint` for the environment.
6. Implement leak-canary tests across API/WS/logs/artifacts to ensure credentials are never logged or echoed.

## Tasks / Subtasks

- [ ] Task 1: Database and Migration
  - [ ] Subtask 1.1: Define SQLAlchemy models for user-scoped credentials and login_type in Environment config.
  - [ ] Subtask 1.2: Generate Alembic migration to drop old table and add new ones.
- [ ] Task 2: Backend CRUD
  - [ ] Subtask 2.1: Implement API routes with Fernet encryption for user-scoped secrets.
- [ ] Task 3: Frontend UI
  - [ ] Subtask 3.1: Create UI components for users to manage their test credentials.
  - [ ] Subtask 3.2: Update Project Admin UI to manage `login_type` and `login_hint`.
- [ ] Task 4: Security and Testing
  - [ ] Subtask 4.1: Write leak-canary tests.

## Dev Notes

- **Relevant architecture patterns and constraints**: Crucial security requirement: Never log or expose credentials in plaintext. Use `db/types.py` Fernet integration.
- **Source tree components to touch**: `src/ai_qa/db/models.py`, `src/ai_qa/api/`, `src/ai_qa/frontend/`, `alembic/versions/`.
- **Testing standards summary**: Must have specific tests validating encryption and zero leakage.

### Project Structure Notes

- Integrates with existing role and environment concepts.

### References

- [Source: epics.md] Epic 25 description.
- [Source: sprint-change-proposal-2026-06-27-test-credentials.md]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
