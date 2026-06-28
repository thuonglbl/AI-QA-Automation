---
baseline_commit: 179e9c361b7b79bf045b28c9f23d9ac4b85944e4
---
# Story 25.2: Remove the Prohibited Session-Capture Surface

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want the session-capture/import surface removed (`browser/session_capture.py`; the `capture`/`import`/`import-token`/`import-with-token` routes in `api/sessions.py`; `frontend/public/capture-session.{mjs,cmd}`; `ImportSessionForm.tsx`) while keeping the consumption seams and `check-connections`,
so that the behaviour Group Security flagged no longer exists in the product.

## Acceptance Criteria

1. Remove `browser/session_capture.py`.
2. Remove `capture`, `import`, `import-token`, and `import-with-token` routes from `api/sessions.py`.
3. Remove `frontend/public/capture-session.mjs` and `frontend/public/capture-session.cmd`.
4. Remove `ImportSessionForm.tsx` and all references to it in the frontend.
5. Ensure `check-connections` and consumption seams (like Tier-1 `storage_state` temp-file injection) remain intact.
6. System builds and tests pass without the removed features.

## Tasks / Subtasks

- [x] Task 1: Backend cleanup
  - [x] Subtask 1.1: Delete `browser/session_capture.py`
  - [x] Subtask 1.2: Remove routes from `api/sessions.py`
- [x] Task 2: Frontend cleanup
  - [x] Subtask 2.1: Delete capture scripts in `public/`
  - [x] Subtask 2.2: Remove `ImportSessionForm.tsx` and update UI

## Dev Notes

- **Relevant architecture patterns and constraints**: This is a direct removal to comply with Group Security. The backend CDP pull reading the employee's live cookies is prohibited.
- **Source tree components to touch**: `browser/`, `api/`, `frontend/public/`, `frontend/src/components/`.
- **Testing standards summary**: Ensure all existing backend and frontend tests pass after removal. Update or remove any tests that specifically targeted the capture routes.

### Project Structure Notes

- Keep `CapturedSession` table for now as it will be repurposed later for caching the tool-generated session.

### References

- [Source: epics.md] Epic 25 description.
- [Source: sprint-change-proposal-2026-06-25-no-session-capture.md]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

None

### Completion Notes List

- Deleted `src/ai_qa/browser/session_capture.py`
- Cleaned up `src/ai_qa/api/sessions.py` to remove `capture_session`, `import_session`, `create_import_token`, `import_session_with_token` routes, alongside their requests models, imports, and helper functions
- Deleted `frontend/public/capture-session.mjs` and `frontend/public/capture-session.cmd`
- Deleted `frontend/src/components/sessions/ImportSessionForm.tsx` and removed references to it from `SessionMatrixPanel.tsx`, removing the UI capability to upload sessions

### File List

- `src/ai_qa/browser/session_capture.py` (deleted)
- `src/ai_qa/api/sessions.py`
- `frontend/public/capture-session.mjs` (deleted)
- `frontend/public/capture-session.cmd` (deleted)
- `frontend/src/components/sessions/ImportSessionForm.tsx` (deleted)
- `frontend/src/components/sessions/SessionMatrixPanel.tsx`
