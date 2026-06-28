# Story 25.4: Automated Login to Generate a Session

Status: complete

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the system,
I want an automated login routine (browser-use/Playwright) that, given a target-app login URL + stored test-account credentials (+ TOTP when configured), authenticates in a clean isolated browser and exports the resulting `storageState`,
so that a session is produced without reading any employee browser.

## Acceptance Criteria

1. Implement automated login routine using browser-use or raw Playwright.
2. The routine must fetch decrypted test credentials securely from the store.
3. The routine must support TOTP generation if configured.
4. The routine must export a valid Playwright `storageState` object upon successful authentication.
5. The routine must run in an isolated browser context.
6. Graceful error handling for login failures (e.g., bad credentials, unexpected UI).

## Tasks / Subtasks

- [x] Task 1: Automation Routine
  - [x] Subtask 1.1: Develop the core login script
  - [x] Subtask 1.2: Add TOTP support
- [x] Task 2: Storage State Export
  - [x] Subtask 2.1: Capture and format the session state
- [x] Task 3: Error Handling and Resilience

## Dev Notes

- **Relevant architecture patterns and constraints**: Should run on the server. The session should optionally be cached in the `CapturedSession` table (repurposed).
- **Source tree components to touch**: `browser/` or a new module for login automation.
- **Testing standards summary**: Needs reliable integration tests, possibly with a mock IdP or target app.

### Project Structure Notes

- Will feed into the consumption seams in Story 25.5.

### References

- [Source: epics.md] Epic 25 description.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

### File List
