# Epic 8 Retrospective

## Epic Title

Epic 8 - Admin Dashboard and Project Membership Management

## Summary

Epic 8 verified and hardened the admin dashboard, user management, project management, membership assignment, dashboard UI layout, and E2E test execution, then locked down the public self-service registration endpoint. All 7 stories done (100%).

## What Went Well

- Verification-story pattern (8-1 through 8-5) was efficient: confirm existing impl, add focused test gap + consolidated e2e, reuse helpers verbatim.
- Helper reuse across stories was excellent: `ADMIN_DASHBOARD_E2E` skip guard became project-wide convention, denial-matrix body assertion pattern reused in 8-2/8-3/8-4.
- Backend reached 644 tests at 81.26% coverage (≥80% gate). E2E suite: 30/30 passing.
- Story 8.7 cleanly removed the public register endpoint and migrated all 8 affected e2e specs without breaking anything.

## What Could Be Improved

- Sprint-status.yaml was missing entries for stories 8-1, 8-2, 8-3, 8-4, and 8-5 — all had to be manually added. This tracking gap should not happen.
- Story 8.6 (admin E2E test execution) had 18 review findings — the most of any story in Epic 8. Critical issues included infinite self-trigger loop, synchronous subprocess blocking event loop, zombie process risk, and memory exhaustion from in-memory zip buffering.
- Argon2 CPU saturation was discovered late (8.7) — parallel e2e workers cause authentication timeouts, forcing the entire suite to run serially (`--workers=1`).
- AC3 tension between 8-2 (public register endpoint) and 8-7 (lock it down) was a planning concern that could have been resolved earlier.

## Key Lessons

- The `ADMIN_DASHBOARD_E2E` skip guard pattern (env variable check) prevents in-app test runners from triggering themselves recursively. This became a project-wide convention.
- Argon2 password hashing is intentionally CPU/memory heavy — parallel e2e workers cause authentication timeouts. Serial execution is required for stability.
- Admin login in e2e helpers must use isolated Playwright request contexts to prevent session cookie leakage into test contexts (middleware reads cookie before Authorization header).
- When building in-app test runners, the self-trigger loop is a real architectural hazard that must be addressed before first deployment.

## Action Items

- [ ] Automate sprint-status.yaml updates when stories are created (eliminate manual add pattern).
- [ ] Add visual streaming or polling for admin E2E test execution (deferred from 8.6).
- [ ] Address synchronous fetch timeout on long-running E2E test executions (deferred from 8.6).
- [ ] Document Argon2 serial execution requirement in README and e2e configuration.
- [ ] Resolve AC3 planning tension pattern — when a story depends on another story's scope, plan both together.

## Status

Epic 8 retrospective: done
