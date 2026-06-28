# Story 25.6: External-App Authentication (Username/Password and Third-Party OAuth)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project user,
I want external (non-Azure) apps supported — direct username/password login, and third-party OAuth (Google/Apple) via dedicated test accounts or the app's own test login — with hard limits documented where automation is genuinely blocked,
so that the pipeline covers external as well as internal apps.

## Acceptance Criteria

1. Ensure the automated login routine supports standard HTML form username/password flows.
2. Implement handling for third-party OAuth providers (Google, Apple) if possible without human interaction.
3. Document hard limitations where automation is blocked (e.g., CAPTCHAs, strict bot detection).
4. Provide UI hints or documentation to users setting up credentials for these apps.

## Tasks / Subtasks

- [ ] Task 1: Support standard login forms
- [ ] Task 2: Investigate and support OAuth popups/redirects
- [ ] Task 3: Documentation and limits

## Dev Notes

- **Relevant architecture patterns and constraints**: Browser automation must be robust enough to handle different UI paradigms.
- **Source tree components to touch**: Login automation script, Documentation.
- **Testing standards summary**: Test against mocked or real external apps if available.

### Project Structure Notes

- Extends the capabilities built in 25.4.

### References

- [Source: epics.md] Epic 25 description.

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

### Completion Notes List

### File List
