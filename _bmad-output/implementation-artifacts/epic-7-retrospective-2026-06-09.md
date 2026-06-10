# Epic 7 Retrospective

## Epic Title

Epic 7 - Secure Multi-User Workspace Foundation

## Summary

Epic 7 completed the secure multi-user workspace foundation: login/session, project membership access, thread creation with project binding, thread-scoped messages and agent runs, conversation history/resume, membership removal enforcement, workspace shell routing, and agent runs refactoring. All 8 stories done (100%).

## What Went Well

- Security was progressively tightened across stories — from ownership-only to ownership+membership checks (7.2, 7.6, 7.7).
- Story 7.1 correctly identified duplicate scope (Epic 6 had already built login), avoiding wasted effort.
- Story 7.7 made a decisive product call: removed the project chooser entirely in favor of automatic starter threads per project.
- Migration in 7.8 preserved legacy `pipeline_run_id` as `legacy_pipeline_run_id` instead of destructive removal.
- Authorization patterns (`assert_thread_access`, `_authorize_thread` helper) emerged as reusable infrastructure.

## What Could Be Improved

- Story 7.3 had 16 review patches — the highest of any story in the project. Many were security gaps (auth bypass, WebSocket leakage, cross-thread mutation) that should have been caught earlier.
- Frontend race conditions were pervasive in 7.3 (thread creation during render, refs not reset, localStorage not cleared on logout).
- Authorization was missed multiple times: membership check missing in thread binding (7.3), cross-thread run mutation allowed (7.6), WebSocket broadcast leaked private updates (7.3).
- Deferred technical debt accumulated in every story: pagination, live E2E, JWT staleness, partial bootstrap recovery.

## Key Lessons

- Security review should be a dedicated pass, not mixed with functional review. Story 7.3's 16 patches suggest the initial implementation was not defensive enough on auth/authz.
- WebSocket broadcast security requires explicit scoping — default broadcasting leaks private data to other users.
- Migrations should never destroy historical linkage. Always preserve legacy references with a clear deprecation path.
- When removing a feature (e.g., project chooser in 7.7), plan for test rewrites — existing tests will break.

## Action Items

- [ ] Add focused regression tests for project resolution flows (zero-project, single-project auto-select, multi-project selection).
- [ ] Harden project ID persistence and stale-state handling in `ProjectContext` and Alice message state.
- [ ] Document the API payload contract for `projectId`/`project_id` in WebSocket and REST calls.
- [ ] Address pagination for unbounded result sets (deferred from 7.2).
- [ ] Run live E2E tests against real stack (deferred from multiple stories).

## Status

Epic 7 retrospective: done
