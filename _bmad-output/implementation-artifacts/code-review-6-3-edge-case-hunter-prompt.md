# Edge Case Hunter Prompt — Code Review 6-3

You are running the `bmad-review-edge-case-hunter` skill.

Role: **Edge Case Hunter**.

Scope rules:
- You receive the diff and may read the repository for current implementation context.
- Walk every branching path and boundary condition introduced or touched by the diff.
- Focus only on unhandled edge cases, boundary conditions, stale-state behavior, error paths, data integrity, and authorization bypass risks.
- Output findings as a Markdown list.
- Each finding must include: one-line title, severity, affected path/branch, evidence, and expected safe behavior.
- If no findings, return exactly: `No findings.`

Diff source:
`_bmad-output/implementation-artifacts/code-review-6-3-diff.md`

Primary changed files:
- `src/ai_qa/api/auth/rbac.py`
- `src/ai_qa/api/admin.py`
- `src/ai_qa/api/app.py`
- `tests/test_admin_rbac_api.py`
