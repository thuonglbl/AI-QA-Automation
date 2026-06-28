---
stepsCompleted: ['step-01-preflight-and-context', 'step-02-identify-targets', 'step-03-generate-tests']
lastStep: 'step-03-generate-tests'
lastSaved: '2026-06-20'
task: 'Regroup frontend/e2e into 7 login-once flow groups'
status: 'generated — statically verified (typecheck + eslint + playwright --list, 28 tests/7 files); NOT yet live-validated'
inputDocuments:
  - project-context.md
  - frontend/playwright.config.ts
  - frontend/e2e/global-setup.ts
  - frontend/e2e/global-teardown.ts
  - frontend/support/helpers/users.ts
  - frontend/support/fixtures/index.ts
  - frontend/e2e/*.spec.ts (23 existing specs)
  - DB tables: projects, project_memberships, users
  - knowledge: test-levels-framework, test-priorities-matrix, data-factories, selective-testing, ci-burn-in, test-quality
---

# E2E Regroup — Coverage Plan

## Step 1 — Preflight & Context

- **Stack:** fullstack (React 19 + Vite FE, FastAPI/Python BE). Target = frontend E2E.
- **Framework:** Playwright (`playwright.config.ts`, `@playwright/test ^1.60`). `workers: 1`, `fullyParallel: true`, test timeout 60s, expect 5s. Auto-boots `uv run ai-qa` + `npm run dev` unless `E2E_DISABLE_WEBSERVER=1`.
- **Mode:** Standalone refactor (no new story); driven by user goal — consolidate the existing suite.
- **Shared infra present:** `support/helpers/users.ts` (`createStandardUser`, `getAdminToken` w/ worker+file token cache), `support/fixtures` (`userFactory`), `global-setup` (admin token pre-auth), `global-teardown` (sweeps `@example.(com|test)` users + `^(S\d|Story \d)` projects).
- **Cleanup cascade (verified):** delete user → CASCADE `threads` → `agent_runs` → `artifacts`. A user delete never touches `projects`.

## Problem (user-reported)

`frontend/e2e` has 23 story-oriented specs with heavy duplication: every spec re-creates an account + logs in (slow, Argon2-bound) and no spec walks one continuous journey. Goal: **log in once per group, then walk the whole flow.**

## Decisions (confirmed with Thuong)

1. **`PT` / `PTP` are real DB projects** (not pipeline depth):
   - `PT Tool` — id `b36c53d7-2e2e-4895-9825-fad59dd524b9`; providers `['on-premises','claude-sso']`; Confluence `…/CORPHRSOL/…/PT+Business+requirements`; Jira `CORP_PT_TOOL`.
   - `PTP Personal Travel Plan` — id `24c60499-36f1-4abc-9161-75d9845a5735`; providers `[browser-use-cloud, claude, gemini, openai, on-premises, claude-sso]`; Confluence `…/EXPERTGROUP/…/PTP+-+Personal+Travel+Plan`; no Jira.
2. **Replace:** delete all 23 story specs; rebuild as 7 grouped specs.
3. **On-prem groups (4 & 5) run the REAL full pipeline** (slow, real keys, skip-when-missing).

## Architecture

- **Login once per group:** `test.describe.serial(...)` + a single `page` created in `beforeAll`; each `test()` is one stage of the journey sharing that page. `workers:1` already guarantees order.
- **Real projects + ephemeral user:** look up `PT Tool` / `PTP` by name via the admin API (never create/delete them); create an ephemeral `@example.com` user per group, assign membership to the real project(s), run, then delete the user in `afterAll` → cascade cleans generated threads/runs/artifacts while real projects stay intact. Project count (single vs multiple) is controlled by how many memberships the ephemeral user gets.
- **Jack note:** the standard-user conversation pipeline is Alice→Bob→Mary→Sarah only. Step 5 (Jack/execution) is **not** in the chat — it is the admin "Run E2E Tests" button (`#run-e2e-tests-button`), covered by Group 1.

## Coverage Plan — 7 groups

| # | File | Login (once) | Project(s) | Provider | Depth | Pri | Speed |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | `group-1-admin-flow.spec.ts` | admin | ephemeral test projects | n/a | Admin dashboard CRUD + membership + Run-E2E button visible | P0/P1 | fast |
| 2 | `group-2-invalid-acc.spec.ts` | none (negative) | none | n/a | Wrong password / unknown email → generic error, no token | P0 | fast |
| 3 | `group-3-valid-acc-no-project.spec.ts` | standard (0 projects) | none | n/a | "You do not have access to any project yet." | P0 | fast |
| 4 | `group-4-multiple-projects-ptp-on-prem.spec.ts` | standard (PT Tool + PTP) | **PTP** driven | on-premises | FULL pipeline Alice→Bob→Mary→Sarah | P0 | slow (live) |
| 5 | `group-5-one-project-pt-on-prem.spec.ts` | standard (PT Tool only) | **PT Tool** | on-premises | FULL pipeline Alice→Bob→Mary→Sarah | P0 | slow (live) |
| 6 | `group-6-one-project-ptp-claude-sso.spec.ts` | standard (PTP only) | **PTP** | claude-sso | SSO card → Login SSO → mock IdP → SPA proceeds (seam only) | P1 | fast |
| 7 | `group-7-multiple-projects-pt-claude-sso.spec.ts` | standard (PT Tool + PTP) | **PT Tool** driven | claude-sso | Multi-project sidebar + SSO login seam (no full pipeline) | P1 | fast |

### Per-group flow detail

- **Group 1 (admin):** layout (Projects left / Users right, Sync disabled w/ helper text, nav shows admin email + Logout) → create user (+ duplicate-email safe error) → create / rename / delete project → assign + remove membership (chip toggles, member gains/loses access) → assert `#run-e2e-tests-button` visible & enabled (do **not** click — avoids E2E recursion). Replaces story-8-1..8-6.
- **Group 2 (invalid):** API `POST /auth/login` → 401 `Invalid email or password`; UI wrong password → `Invalid username or password.` + `aiqa_access_token` stays null + no-access text hidden; unknown email → same generic message. One ephemeral user for the wrong-password case. Replaces story-7-1 negative.
- **Group 3 (no project):** ephemeral user, zero memberships → login → no chooser, no provider step, `You do not have access to any project yet.` Replaces story-7-2/7-3/7-7 zero-project.
- **Group 4 (PTP, on-prem, full):** assert both projects in sidebar → open the PTP thread → `configureOnPremProvider` (select `provider-card-on-premises`, fill `TEST_ON_PREMISES_KEY`, Start, "Connected successfully", OK on ModelAssignmentReview) → `runBobExtraction` (MCP key `TEST_MCP_KEY`, confirm parent, extract, fill Confluence page id from PTP `confluence_base_url`, wait "Handing off to Mary") → `approveAllMaryTestCases` (loop "Approve" through "Review Test Case (n of N)" until "Proceed to Sarah →") → click "Proceed to Sarah →" → Sarah inputs form → select test cases → "Confirm & Generate →" → script review → "Approve". `test.setTimeout(~30min)`; `test.skip` when `TEST_ON_PREMISES_KEY`/`TEST_MCP_KEY` missing.
- **Group 5 (PT Tool, on-prem, full):** ephemeral user → PT Tool only → auto-bind single project → straight to provider step → same full drive against PT Tool's Confluence root id. (Jira select-id leg deferred — same as epic-11 note.)
- **Group 6 (PTP, claude-sso):** provider step → click `provider-card-claude-sso` → assert `sso-login-button` → click → capture popup → fill `sso-email`/`sso-password` (`TEST_CLAUDE_SSO_*`) → submit → `sso-success` → SPA shows `Testing connection to|Connected successfully to|not configured`. Skip if SSO creds missing. Replaces claude-sso-login.spec.
- **Group 7 (PT Tool, claude-sso):** member of both projects → assert multi-project sidebar → open PT Tool thread → same SSO login-seam check.

### Coverage carried over / dropped vs the 23 old specs

- **Folded into groups:** story-7-1 (→2,3), 7-2/7-3/7-3-thread/7-5/7-6/7-7 (→3,4,5,7 journey steps), 8-1..8-6 (→1), 9-4/9-5/9-7 (→4,5 provider config), epic-11 Bob (→4,5), epic-13 Sarah happy path (→4,5), claude-sso (→6,7).
- **Proposed drop from E2E (keep Vitest equivalents):** story-10-2/10-3/10-7/10-8 (artifact tree / preview / refresh / notice) + story-7-6 granular RBAC 404-leak assertions — these are seam/component checks that don't fit a "login once → walk the flow" group. **← awaiting OK.**

## Risks & mitigations

1. **Runtime (Groups 4&5):** real on-prem pipeline ≈ 20–40 min each (Bob multi-page extract + Mary per-test-case gen ~200–350s each + Sarah gen). Mitigation: large `test.setTimeout`, skip-when-no-key, `test.slow()`, nightly/live lane not every PR.
2. **LLM nondeterminism:** test-case count + script content vary. Mitigation: loop approvals + assert progression/handoff markers, never exact content.
3. **Real-project pollution:** mitigated by ephemeral-user cascade delete; real projects never created/deleted by the suite.
4. **Sarah browser-use exploration** needs chrome/target URL; falls back to LLM-only — provide app URL or rely on fallback.
5. **Multi-project thread selection:** need a stable selector to pick the PTP vs PT Tool thread in the sidebar (resolve during generation).

## New shared helpers (Step 3)

- `support/helpers/projects.ts` — `getProjectByName`, `assignMembership`, `removeMembership`.
- `support/helpers/pipeline.ts` — `loginViaUI`, `configureOnPremProvider`, `runBobExtraction`, `approveAllMaryTestCases`, `runSarahToScriptApproval`, `loginViaClaudeSso`.
- Reuse existing `createStandardUser`, `getAdminToken`, `userFactory`, global setup/teardown.

## Step 3 — Generated (2026-06-20)

**Created:**

- `frontend/support/helpers/projects.ts` — `getProjectByName`, `assignMembership`, `removeMembership`, `confluencePageId`, `threadIdForProject`, `PROJECT_PT_TOOL`/`PROJECT_PTP` constants.
- `frontend/support/helpers/pipeline.ts` — `loginViaUI`/`loginViaApi`, `makeTestUser`, `openProjectThread`, `configureOnPremProvider`, `runBobExtraction`, `approveAllMaryTestCases` (loops Approve, auto-skips Mary clarify questions), `runSarahToScriptApproval` (inputs → optional selection → approve one script + confirm caption), `loginViaClaudeSso`.
- `frontend/e2e/group-1-admin-flow.spec.ts` … `group-7-multiple-projects-pt-claude-sso.spec.ts` (7 files, 28 tests).

**Deleted:** the 23 old `story-*` / `epic-*` / `claude-sso-login` specs. Kept `global-setup.ts`, `global-teardown.ts`, `types.d.ts`.

**Static verification (all green):** `npm run typecheck`; `tsc -p tsconfig.node.json` (e2e + support); `npx eslint`; `npx playwright test --list` → 28 tests / 7 files.

**Live drivers (cannot be statically verified — assert progression markers, not LLM content):**

- `approveAllMaryTestCases`: races Approve / Proceed / Skip-clarify; waits for the header index to change between approvals so it never double-approves; tolerates a clarify question by skipping it.
- `runSarahToScriptApproval`: leaves Chrome/CDP blank (LLM-only fallback), handles the optional test-case selection panel, approves ONE script and asserts the "Approved …" caption registers.
- Bob keeps the proven epic-11 flow (no clarify handling — those projects extracted clean).

**Not yet live-validated.** Groups 4 & 5 need VPN to `confluence.svc.corp.ch` + on-prem LLM and run ~20–40 min each; groups 6 & 7 need the SSO mock-IdP creds. Run command: `cd frontend && npx playwright test e2e/group-1 e2e/group-2 e2e/group-3` (fast) or a single group, e.g. `npx playwright test e2e/group-5-one-project-pt-on-prem.spec.ts`.

**Known residual risks:** multi-project thread selection relies on `data-testid=thread-<id>` after the browser bootstraps starter threads (polled via API first); Mary/Sarah selectors had no prior E2E coverage, so the first live run is the real validation.

## Update 2026-06-20 (post-rename + WIP scope-down)

Thuong renumbered the group files: **SSO groups are now 4 & 5**, **on-prem groups are now 6 & 7** —
`group-4-one-project-ptp-claude-sso`, `group-5-multiple-projects-pt-claude-sso`,
`group-6-multiple-projects-ptp-on-prem`, `group-7-one-project-pt-on-prem`.

The two on-prem groups (6 & 7) now **stop at Bob**: they drive login → project → Alice on-prem
provider config → assert the Alice→Bob hand-off (`getByPlaceholder(/Enter MCP API Key/i)` visible),
then stop. The Bob extraction → Mary → Sarah → artifact stages were removed because that backend
flow is still in development; re-add them later using the retained (currently unused) exports
`runBobExtraction` / `approveAllMaryTestCases` / `runSarahToScriptApproval` in `pipeline.ts`. The
on-prem skip-guard now requires only `TEST_ON_PREMISES_KEY` (MCP is no longer exercised). Suite is
now **22 tests / 7 files** (was 28); typecheck + eslint + `playwright --list` green.
