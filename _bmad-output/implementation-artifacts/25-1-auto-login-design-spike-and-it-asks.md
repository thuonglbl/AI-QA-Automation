---
baseline_commit: 179e9c361b7b79bf045b28c9f23d9ac4b85944e4
---
# Story 25.1: Auto-Login Design Note, Feasibility Spike, and IT Asks

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the architect,
I want a design note + feasibility spike that picks the login-automation mechanism (browser-use-driven vs scripted), the credential-storage model, and the per-app login-hint shape — plus the verbatim IT asks (dedicated test accounts; MFA-exempt or TOTP; security sign-off on storing test-account credentials),
so that production stories 25-2…25-7 build on a confirmed approach.

## Acceptance Criteria

1. Evaluate login-automation mechanisms: browser-use-driven vs scripted Playwright.
2. Define the credential-storage model reusing the Fernet per-user-secret machinery.
3. Define the per-app login-hint shape (URLs, selectors if needed).
4. Document the verbatim IT asks for dedicated test accounts, MFA exemptions or TOTP, and security sign-off.
5. Provide a feasibility spike confirming the proposed approach.

## Tasks / Subtasks

- [x] Task 1: Research login-automation options
  - [x] Subtask 1.1: Spike browser-use vs scripted approaches
- [x] Task 2: Define credential storage model
- [x] Task 3: Draft IT asks and security sign-off requests
- [x] Task 4: Finalize design note for stories 25-2 to 25-7

## Dev Notes

- **Relevant architecture patterns and constraints**: This story acts as a load-bearing gate for Epic 25, much like Story 23-1. Must align with security requirements (no session capture).
- **Source tree components to touch**: Documentation and planning artifacts (`_bmad-output/planning-artifacts/`).
- **Testing standards summary**: Feasibility spike should be reproducible.

### Project Structure Notes

- Alignment with unified project structure: Design note should be added to planning-artifacts.

### References

- [Source: epics.md] Epic 25 description.
- [Source: sprint-change-proposal-2026-06-25-no-session-capture.md]

## Dev Agent Record

### Agent Model Used

Gemini 3.1 Pro (High)

### Debug Log References

None

### Completion Notes List

- Evaluated and chose scripted Playwright over browser-use for predictable login hurdle
- Defined `TestAccountCredential` model to securely store test credentials per project/env/role using Fernet encryption
- Formulated clear IT Asks regarding dedicated test accounts, MFA-exemption or TOTP, and security sign-offs
- Wrote final design note detailing the auto-login strategy to guide subsequent development

### File List

- `_bmad-output/planning-artifacts/design-security-compliant-target-app-auth-2026-06-25.md`
