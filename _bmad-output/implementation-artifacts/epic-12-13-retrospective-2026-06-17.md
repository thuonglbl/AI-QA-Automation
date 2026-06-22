# Epic 12 & 13 Retrospective: Test Case Generation and Python Playwright Script Generation

**Date**: 2026-06-17
**Participants**: Thuong (Project Lead), Amelia (Facilitator/Dev), Alice (Product Owner), Charlie (Senior Dev), Dana & Murat (QA Engineering)

## Executive Summary

Epic 12 (Mary - Test Case Generation) and Epic 13 (Sarah - Script Generation) delivered the core end-to-end functionality for AI-assisted QA automation. All 13 stories across both epics have been marked `done`. 

While the functional goals were achieved, adversarial code review uncovered **50 confirmed issues** (6 High, 14 Medium, 30 Low), highlighting severe technical debt in Frontend State Management, File Idempotency, and Testing Configuration. 

The Project Lead (Thuong) directed the team to follow best practices and **resolve all technical debt completely** ("giải quyết dứt điểm toàn bộ") before proceeding to Epic 14.

## What Went Well

- **End-to-End Value Delivery:** We successfully closed the loop on generating test cases and automated scripts using Mary and Sarah agents.
- **Code Review Adversarial Value:** The multi-layered code review successfully caught 50 issues that slipped through local gates, preventing major state-loss bugs from reaching production.
- **Team Communication:** The team correctly escalated technical concerns rather than silently absorbing debt to meet deadlines.

## Challenges & Growth Areas

- **Frontend State Management:** Heavy reliance on React local state (`useState`) caused critical UX issues (e.g., Sarah's edit buffer being wiped, MaryReviewPanel losing state, `marySelectedId` leaking across threads).
- **Storage Idempotency:** Using artifact titles for filenames caused collisions and data loss when titles were duplicated.
- **Testing Illusion:** `npm run typecheck` was misconfigured (running as a no-op), hiding TypeScript errors. Lack of E2E tests for complex interactive UI workflows led to state bugs slipping through.
- **Logic Gaps:** Some backend handlers assumed `data[0]` was the only target, missing cases where one requirement maps to multiple test cases.

## Key Insights

1. **State Persistence:** Frontend state for long-running AI pipelines must be driven by server events or stable central context, not fragile local component state.
2. **Robust Identifiers:** Artifacts must be saved using robust, unique identifiers (e.g., ID or index) rather than user/AI-generated titles.
3. **Cross-Check CI Gates:** CI tools like typecheckers and linters must be tested to ensure they are actually scanning the intended source files.
4. **E2E is Mandatory for Interactive Agents:** Green unit tests over mock data are insufficient for multi-step interactive workflows (Edit -> Reject -> Approve).

## Next Epic Preview — Epic 14: Pipeline Audit Logging & Leadership Metrics

- **Dependency Risk:** Epic 14 requires tracking the audit trail of pipeline actions. If state management is unstable or artifact IDs are colliding, the audit logs will be inaccurate or orphaned.
- **Direction:** The Project Lead has authorized a Technical Debt Sprint (Prep Sprint) to resolve the 50 code review findings and shore up the foundations before beginning Epic 14 feature work.

## Action Items

These items will be added to the backlog and resolved immediately per the Project Lead's directive:

1. **Fix all 50 Code Review Findings:** Execute the patch plan from the adversarial code review, including the 6 High and 14 Medium severity issues.
2. **Fix Testing Infrastructure:** Correct the TypeScript `typecheck` command in `frontend/package.json` and ensure CI properly catches TS errors.
3. **Implement Robust Idempotency:** Refactor backend save mechanisms for Mary and Sarah to use unique identifiers instead of just titles.
4. **Enforce E2E UI Coverage:** Add Playwright E2E tests covering the complete interact/edit/reject/approve cycles for Mary and Sarah review panels.
5. **Centralize Frontend State:** Move complex agent review states out of local component state to prevent data loss on re-renders or thread switches.
