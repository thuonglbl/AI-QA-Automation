# Epic 11 Retrospective: Confluence and Jira Requirements Extraction with Bob

**Date**: 2026-06-12
**Participants**: Thuong (Project Lead), Amelia (Facilitator/Dev), John (Product), Winston (Architecture/Security), Murat (Quality), Mary (Analyst)

## Executive Summary

Epic 11 delivered the full Confluence + Jira requirements-extraction pipeline for Bob across 8 stories (11.1 MCP client foundation → 11.2 intake → 11.3 content parsing → 11.4 Jira retrieval → 11.5 input-quality detection → 11.6 review UX → 11.7 provenance-aware artifact save → 11.8 technical-debt sweep). All 8 stories are `done`; local gates are green (`uv run pytest` **1188 passed, 83.79% coverage**, `mypy src` clean, frontend lint/typecheck/test green).

The epic **applied Epic 10's hard-won lessons** — it followed strict sequential delivery (backend/MCP foundations before review UX), avoiding the "frozen contract" friction of Epic 10. The adversarial code review of 11.7 and 11.8 caught **two CRITICAL issues that all green local gates and the dev's own `[x]` checkboxes missed** (an AC3 atomicity regression and a fully non-functional CI), both now fixed.

The dominant open risk, surfaced by the Project Lead, is **extraction quality**: against the real internal (heavily-customized) MCP, Bob *can* read, but the extracted results are below expectations, and the fault has not been localized between our code/LLM-prompt and the MCP server's output. The entire MCP/Confluence/Jira test surface is mocked, so the green suite provides **zero** evidence about real-server behaviour.

## Delivery Metrics

- Stories: **8/8 done** (11.1–11.8).
- Backend tests: **1188 passed**, coverage **83.79%** (≥80 gate). `mypy src` clean.
- Frontend: lint + typecheck clean, **171** vitest passed.
- Review: 11.7 + 11.8 adversarially code-reviewed (2026-06-12). 2 CRITICAL fixed, 9 LOW deferred.
- Git state: **all of Epic 11 is uncommitted** in the working tree on top of `b4ce65f`.

## Previous Retrospective (Epic 10) — Follow-Through

| Epic 10 action item | Status | Evidence |
| --- | --- | --- |
| 1. Tech-debt sweep in Epic 11 | ✅ Done (mostly) | Became Story 11.8 — OutputWriter deleted, AdminDashboard timer fixed, testpaths deduped, ToolCache clock seam, `assert True` canaries replaced. **But the CI fix (D6) was botched** — written into a gitignored `.github/`. |
| 2. Strict sequential delivery (foundations before UX) | ✅ Done | Epic 11 ran 11.1 MCP foundation → … → 11.6 review UX last. No repeat of Epic 10's out-of-order pain. |
| 3. Validate test stubs (assert real behaviour or skip-TODO) | ⚠️ Partial | 11.8 replaced the `assert True` canaries — but the "false sense of security" **recurred in subtler forms**: `test_coverage_tracking_active` asserts only that pytest-cov is *loaded* (not enforced), and an 11.6 reject test contained `is_review_calls = [c.kwargs for c in MagicMock().mock_calls]` (always empty — asserts nothing). The rule was honoured in spirit but lacks an enforcement mechanism. |

## What Went Well

- **Lessons applied:** strict sequential delivery (Epic 10 action #2) was followed and clearly paid off — no frozen-contract retrofitting this epic.
- **Adaptive MCP client design:** the MCP client discovers tools dynamically (`list_tools` / `discover_capabilities` / `check_tool_availability`), with a configurable tool prefix, transport choice, timeouts, and retry/backoff — built to adapt to a custom internal MCP rather than hard-coding tool names.
- **Human-in-the-loop quality backstop:** Bob saves nothing until the user approves the extracted markdown in the review UX (11.6), and 11.5's quality warnings render in the panel before approval — so poor extraction is caught at the review gate rather than silently shipped.
- **Adversarial review delivered real value:** it caught two CRITICAL issues invisible to green gates — 11.7's D8 delete-then-save AC3 regression (fixed: save-then-delete) and 11.8's gitignored/incomplete CI (fixed: scoped ignore + a self-contained Postgres-backed e2e job).
- **Graceful degradation:** Jira retrieval (11.4) is best-effort; provenance columns are nullable; quality detection is advisory and never blocks approval.

## Challenges & Growth Areas

- **Extraction quality is below expectations on the real MCP, root cause unlocalized (TOP RISK).** Bob reads the real internal custom MCP successfully, but the results are "chưa như ý." It is unknown whether the fault is in our code/LLM-prompt or in the MCP server's output, because the pipeline lacks per-stage observability to localize it.
- **MCP/Confluence/Jira is 100% mocked in tests.** No test exercises the real internal server. The 1188-passed suite says nothing about real retrieval or extraction fidelity — the largest "false sense of security" in the epic.
- **Quality detection is rule-based + advisory only.** 11.5 flags structural issues (vague language, missing expected results) but does not semantically validate extraction fidelity; LLM-based scoring was deferred to Mary/12.3. Structurally-clean-but-semantically-wrong extractions are not caught automatically.
- **Green local gates ≠ correct.** Both CRITICAL review findings passed all local gates and were marked `[x]` done by the implementing agent. The CI was a complete no-op (gitignored) yet reported as fixed.
- **No atomic commits.** All of Epic 11 sits uncommitted in one working tree despite the Dev Notes mandating atomic commits, which made AC3 scope unverifiable by diff and let a parallel 11.8 dev-story mutate 11.7's files mid-review.

## Key Insights

1. The "validate test stubs" rule needs enforcement teeth (a CI/lint check), not just intent — it self-defeated within the very epic meant to uphold it.
2. A green test suite over fully-mocked external dependencies is a confidence illusion for the integration that matters most (the custom MCP).
3. Adversarial, code-reading review is the only thing that caught the two CRITICAL issues; keep it as a gate, not an option.
4. Quality faults need stage-level observability to be localizable; "code vs MCP" is currently undiagnosable without ad-hoc work.

## Next Epic Preview — Epic 12: Test Case Generation with Mary

- **Dependency on Epic 11:** Story 12.1 ("Mary loads only project-scoped **approved** requirements through the artifact service; no workspace-path reads") consumes Bob's approved requirement artifacts directly. The 11.7 → 11.8 D8 change (the approved save now **deletes** the pre-approval draft) means 12.1's "approved requirements" filter should key on `source_type IS NOT NULL` and/or the `{page_id}/requirement.md` name pattern.
- **Risk cascade:** Mary's output quality is bounded by Bob's extraction quality. The unresolved extraction-quality risk makes 12.3 (confidence scoring / LLM-judge) more important, and means Mary should not assume high-fidelity inputs.
- **No hard blocker:** 12.1 can start in parallel; the MCP extraction-quality diagnosis (below) runs alongside, per the Project Lead's decision.

## Action Items

**High priority — extraction quality (runs in parallel with Story 12.1):**

1. **Diagnose extraction quality by dumping all four pipeline stages** on the real `.env` Confluence page + Jira ticket: (1) raw MCP response → (2) `ContentParser` output → (3) `RequirementFormatter.convert_page` LLM markdown → (4) `_detect_quality_issues` warnings. Compare stage 1 vs 3 to localize fault: MCP-source vs code/prompt. — _Owner: Thuong + Amelia_
2. **Fix per the diagnosis:** if code/prompt → tune the `convert_page` extraction prompt / `ContentParser`, then re-measure on the same sample; if MCP-source → document the server limitation and choose a mitigation (post-processing / different tool). — _Owner: Thuong_
3. **Enabler — add per-stage observability** (a debug dump / structured log of each pipeline stage's output) so quality faults are repeatably diagnosable, not ad-hoc. — _Owner: Amelia_

**CI / delivery:**

4. **Commit Epic 11 atomically and push** so the rebuilt 3-job workflow (backend / frontend / Postgres-backed e2e) actually runs on GitHub — the only way to prove the D6 fix is green. — _Owner: Thuong_
5. **Split Epic 11 into atomic commits** (OutputWriter deletion / CI fix / feature work) per the Dev Notes discipline that was skipped. — _Owner: Thuong_

**Quality / process:**

6. **Give the "validate test stubs" rule enforcement teeth** — a CI grep/lint rejecting tautological asserts (`assert True`, iterating a fresh `MagicMock()`), since the rule recurred this epic. — _Owner: Murat_
7. **Burn down the 9 deferred LOW items** ([deferred-work.md](deferred-work.md)) opportunistically — prioritize the test-ordering flakiness (CI-flake risk) and the D2 magic-`3000` coupling. — _Owner: Thuong_
8. **Process: do not run a parallel dev-story on the same uncommitted tree being code-reviewed** (the 11.7/11.8 entanglement). Commit a story before reviewing, or review the combined state knowingly. Captured in memory ([[code-review-concurrent-tree-edits]]). — _Team agreement_

## Readiness Assessment

- **Testing & quality:** local suites green (1188 backend + 171 frontend); **but** the integration that matters (real MCP) is unverified and extraction quality is below expectations.
- **CI:** rebuilt and locally validated (trackable, valid YAML, correct env/commands) but **unproven until a real push**.
- **Deployment:** N/A — internal tool, no production deploy yet.
- **Stakeholder acceptance:** the Project Lead does not yet accept extraction quality ("chưa như ý"); action items 1–2 are the feature-quality acceptance path. This does **not** block starting Epic 12 (parallel).
- **Technical health:** code clean (mypy/ruff); main hygiene gap is the fully-uncommitted tree.
- **Hard blockers for Epic 12:** none.

## Significant Discovery

The real-MCP extraction-quality gap is a **standing risk that spans into Epic 12** (Mary depends on Bob's output). It does not require redefining Epic 12, but Epic 12 should be built assuming inputs may be imperfect, elevating the importance of 12.3's confidence scoring. No epic re-planning session is required; the diagnosis (action 1) runs in parallel.

## Commitments & Next Steps

1. Run the 4-stage extraction-quality diagnosis (action 1) in parallel with Story 12.1.
2. Commit Epic 11 atomically and push to exercise the CI (actions 4–5).
3. Add per-stage pipeline observability (action 3).
4. Begin Epic 12 / Story 12.1 (Mary input selection), keeping the approved-requirement discriminator in mind.
