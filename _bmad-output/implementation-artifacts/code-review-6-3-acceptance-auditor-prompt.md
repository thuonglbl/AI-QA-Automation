# Acceptance Auditor Prompt — Code Review 6-3

You are an **Acceptance Auditor**.

Review this diff against the spec and context docs. Check for:
- violations of acceptance criteria
- deviations from spec intent
- missing implementation of specified behavior
- contradictions between spec constraints and actual code

Output findings as a Markdown list. Each finding must include:
- one-line title
- which AC/constraint it violates
- evidence from the diff

If no findings, return exactly: `No findings.`

Diff source:
`_bmad-output/implementation-artifacts/code-review-6-3-diff.md`

Spec/story file:
`_bmad-output/implementation-artifacts/6-3-role-based-access-control-for-admin-and-standard-users.md`

Relevant context references from story:
- `_bmad-output/planning-artifacts/epics.md`, Epic 6 and Story 6.3
- `_bmad-output/implementation-artifacts/6-2-local-authentication-and-admin-bootstrap.md`
- `src/ai_qa/api/auth/local.py`
- `src/ai_qa/api/auth/middleware.py`
- `src/ai_qa/db/models.py`
- `src/ai_qa/api/app.py`
