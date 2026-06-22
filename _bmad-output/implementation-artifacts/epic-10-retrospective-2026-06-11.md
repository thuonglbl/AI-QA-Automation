# Epic 10 Retrospective: Project Artifact Collaboration and Realtime Sync

**Date**: 2026-06-11
**Participants**: Thuong (Project Lead), Amelia (Facilitator/Dev), John (Product), Winston (Architecture/Security), Murat (Quality)

## Executive Summary
Epic 10 successfully delivered the collaborative artifact management system, enabling project-scoped viewing, editing, deleting, and realtime updates of test assets. However, the execution order—shipping the frontend realtime UX (Stories 10.7, 10.8) before the backend API foundations (10.1 - 10.4)—caused significant "frozen contract" friction, requiring difficult backend retrofitting to satisfy established frontend assumptions.

## Key Findings

### 1. The Cost of Out-of-Order Execution
- **Observation**: Building the UI first forced the backend to adapt to frozen mock schemas and hardcoded Playwright assertions.
- **Impact**: We had to awkwardly map backend concepts to frozen frontend labels (e.g., hiding `raw_html` under `Requirements`). We also had to implement a completely new `/artifacts/tree` endpoint just to hydrate creator names on the client, which wasn't in the original backend design.
- **Lesson**: Do not build the roof before the foundation. Always establish the core data model and API contracts before finalizing the UI implementation.

### 2. Architecture & Security Wins
- **Observation**: We successfully upheld Epic 9's leak canary standards. 
- **Impact**: In 10.1, the adversarial review caught a minor leak where canary checks only looked at field names, not values. This was patched. We successfully delivered robust project-scoped isolation without leaking internal `storage_path` or PII.
- **Lesson**: The adversarial review process is working and essential for maintaining security invariants.

### 3. Edge Cases Discovered & Resolved
- **Storage Keys**: The initial flat storage key design led to silent data overwrites. We successfully pivoted to collision-safe nested keys (`v{version}/{name}`).
- **Self-Echo Trap**: In 10.4, a user's own save would trigger a "newer version available" notice via WebSocket. We had to carefully suppress self-events to preserve the 10.8 UX.
- **Cold Load Auto-Open**: Multi-project auto-open failed on cold loads, which required patching in 10.2.

### 4. Accumulating Test Debt
- **Observation**: In 10.4, we uncovered 5 pre-existing stub tests for artifact deletion that *never actually called DELETE*, providing a false sense of security.
- **Impact**: We are carrying known, unrelated test failures (like the `AdminDashboard` timeout) across Epics, causing CI noise and reviewer fatigue.
- **Decision**: The Project Lead explicitly requested that a dedicated technical debt sweep be added to the *next* Epic (Epic 11).

## Action Items
1. **Tech Debt Sweep in Epic 11**: Add a dedicated story to Epic 11 to clean up stale test stubs and resolve the `AdminDashboard` timeout. *(Assigned to: Epic 11 Planner)*
2. **Strict Sequential Delivery**: For Epic 11 (MCP Context Retrieval), we must build the MCP client foundation and backend parsers *before* building the review UX. *(Assigned to: Dev Team)*
3. **Validate Test Stubs**: Require that all test stubs actually assert the core mutation or behavior they claim to test, or mark them explicitly as `@pytest.mark.skip(reason="TODO")`. *(Assigned to: Murat / Test Architecture)*
