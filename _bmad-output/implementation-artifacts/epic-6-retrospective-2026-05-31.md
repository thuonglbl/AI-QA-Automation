# Epic 6 Retrospective

## Epic title

Epic 6 - Decoupled Backend, Database, Auth, and Project Foundation

## Summary

This epic completed the core re-architecture from a single-user, file-backed workspace to a multi-user, project-scoped system with a decoupled React frontend, FastAPI backend, PostgreSQL persistence, local auth, RBAC, project membership, artifact service, and Alice-integrated project selection.

## What went well

- The PostgreSQL/Alembic persistence foundation was established cleanly and provided a solid source of truth for users, projects, pipeline runs, artifacts, and audit events.
- Local auth and admin bootstrap were implemented with password hashing, JWT cookie/bearer flows, `/auth/me`, and safe session handling.
- RBAC and project membership support enabled admin and standard user access patterns, with membership validation and project-scoped API filtering.
- The project-scoped artifact service and API layer moved artifact metadata out of file paths and into the new database-backed project model.
- Frontend login/project selection was integrated into Alice, removing the standalone Project Workspace gate and making project resolution a chat-native experience.
- Admin dashboard and routing fixes preserved existing admin behavior while supporting the new multi-project path.

## What could be improved

- Some project-selection and provider-state transitions were brittle, especially when project context changed or stale project IDs persisted across reloads.
- The Alice flow required extra validation to ensure provider options do not appear before project resolution.
- Admin dashboard refinements exposed the need for clearer separation between admin-only routing and standard-user project selection logic.
- WebSocket and API interactions still need more robust regression coverage around selected project ID propagation and race conditions during project changes.
- The epic scope grew to include several frontend and backend fix stories, suggesting that future infrastructure pivots should include a stronger early integration test plan.

## Key lessons

- Early investment in a shared project context and authorization guardrails paid off when connecting frontend login, API payloads, and WebSocket state.
- Keeping database schema, auth, and project-scoped APIs aligned helped avoid mismatched assumptions between backend and frontend.
- Retaining an exact admin route path and message flow made it easier to preserve previous behavior while introducing the new multi-project path.
- Optional retrospectives are useful for large architectural epics; capturing learnings now helps inform the next product-focused epics.

## Action items

- Add focused regression tests for project resolution flows, especially zero-project, single-project auto-select, and multi-project selection.
- Harden project ID persistence and stale-state handling in `ProjectContext` and Alice message state.
- Review and document the exact API payload contract for `projectId`/`project_id` in WebSocket and REST calls.
- Continue the next epic with a clean team story baseline, using this database/auth/project foundation as the platform for feature delivery.

## Status

Epic 6 retrospective: done
