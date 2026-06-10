# Investigation: Playwright e2e suite fails to load (collection-time errors)

## Hand-off Brief

1. **What happened.** Running `npx playwright test e2e` aborts during module loading with two
   independent, Confirmed errors: three specs import helpers that `support/helpers/users.ts` does not
   export, and the `mockJson` fixture in `support/fixtures/index.ts:29` uses `_` instead of `{}`,
   which Playwright rejects.
2. **Where the case stands.** Both root causes are Confirmed at source; blast radius is mapped (3
   specs blocked by the missing exports, all 17 fixture-based story specs blocked by the fixture
   error). No further diagnosis needed.
3. **What's needed next.** Apply two trivial fixes (rewrite/realign the 3 generic specs to the real
   helper API + fixtures; change `mockJson: async (_, use)` to `async ({}, use)`). Recommend handing
   off to `bmad-quick-dev`.

## Case Info

| Field            | Value                                                                                     |
| ---------------- | ----------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                       |
| Date opened      | 2026-06-10                                                                                |
| Status           | Active                                                                                    |
| System           | Windows 11; Node 26.1.0; Playwright 1.60.0; run from `frontend/`                          |
| Evidence sources | Console output (provided), source code, related prior case `e2e-test-failures-2026-06-09` |

## Problem Statement

User ran `$env:PLAYWRIGHT_SLOW_MO='2000'; npx playwright test e2e --headed --workers=1` from
`frontend/`. Setup cached the admin token, then collection failed with:

- `SyntaxError: The requested module '../support/helpers/users' does not provide an export named 'apiCreateUser'` (×3)
- `First argument must use the object destructuring pattern: _` at `support/fixtures/index.ts:5`

Teardown removed 0 users/projects (no test ever executed). The premise — "a test failed" — is
refuted: **no test ran**. The suite never loaded.

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| Console output (user-provided) | Available | Two distinct error classes; teardown confirms 0 tests executed |
| `frontend/support/helpers/users.ts` | Available | Exports only `CreatedUser`, `getAdminToken`, `createStandardUser` |
| `frontend/support/fixtures/index.ts` | Available | `mockJson` at line 29 uses `_` as first arg |
| `frontend/support/fixtures/factories/userFactory.ts` | Available | Clean; imports only `faker` (not implicated) |
| 3 generic specs (artifact-viewer, provider-selector, chat-input-area) | Available | Import 3 non-existent helpers; bypass fixtures |
| Prior case `e2e-test-failures-2026-06-09-investigation.md` | Partial | Same suite, prior day — not yet cross-referenced |

## Investigation Backlog

| # | Path to Explore                                                              | Priority | Status | Notes                                                            |
| - | ---------------------------------------------------------------------------- | -------- | ------ | ---------------------------------------------------------------- |
| 1 | Confirm full set of missing exports used by the 3 generic specs              | High     | Done   | `apiCreateUser`, `createProjectAndAddUser`, `getTestUserToken`   |
| 2 | Map fixture-error blast radius (specs importing `../support/fixtures`)       | High     | Done   | 17 story specs import the fixture barrel                         |
| 3 | Establish how `mockJson` came to use `_` (regression history)                | Medium   | Open   | Likely an ESLint `argsIgnorePattern: ^_` "fix"; needs `git log`  |
| 4 | Cross-reference prior case `e2e-test-failures-2026-06-09`                    | Low      | Open   | May overlap; confirm this isn't a re-open                        |

## Timeline of Events

| Time            | Event                                                              | Source            | Confidence |
| --------------- | ------------------------------------------------------------------ | ----------------- | ---------- |
| run start       | `[e2e setup] Admin token cached for workers.`                      | Console output    | Confirmed  |
| collection      | 3× `does not provide an export named 'apiCreateUser'`              | Console output    | Confirmed  |
| collection      | `First argument must use the object destructuring pattern: _`      | Console output    | Confirmed  |
| run end         | `[e2e teardown] Removed 0 test user(s) and 0 test project(s).`     | Console output    | Confirmed  |

## Confirmed Findings

### Finding 1: Three specs import helpers that `users.ts` does not export

**Evidence:** `frontend/e2e/artifact-viewer.spec.ts:2`, `frontend/e2e/provider-selector.spec.ts:2`,
`frontend/e2e/chat-input-area.spec.ts:2` —
`import { apiCreateUser, createProjectAndAddUser, getTestUserToken } from "../support/helpers/users";`.
`frontend/support/helpers/users.ts` exports only `CreatedUser` (type, line 25), `getAdminToken`
(line 55), and `createStandardUser` (line 125).

**Detail:** All three imported names (`apiCreateUser`, `createProjectAndAddUser`, `getTestUserToken`)
are absent. ESM surfaces only the first missing name (`apiCreateUser`), which is why the console
shows just that one ×3 (once per offending spec). These 3 specs also bypass the fixture barrel —
they import `test`/`expect` directly from `@playwright/test` and use an `httpCredentials` auth
pattern not seen anywhere else — whereas the 17 working story specs use `createStandardUser` +
the `userFactory`/`apiClient` fixtures. The 3 generic specs appear to have been written against a
helper API contract that does not exist in this repo.

### Finding 2: `mockJson` fixture uses `_` instead of object destructuring

**Evidence:** `frontend/support/fixtures/index.ts:29` — `mockJson: async (_, use) => {`. Playwright
requires every fixture's first argument to be an object-destructuring pattern so it can statically
resolve fixture dependencies. The error message literally echoes the offending parameter name:
`...pattern: _`. The sibling fixtures `userFactory` (line 19) and `blockUnexpectedApiCalls` (line 33)
correctly use `async ({}, use)`.

**Detail:** This single invalid fixture makes the whole `support/fixtures/index.ts` barrel fail to
load, which blocks every spec that imports `test` from `../support/fixtures` — 17 story specs.
Likely introduced to satisfy ESLint `@typescript-eslint/no-unused-vars` (`argsIgnorePattern: ^_`,
per project-context.md), which conflicts with Playwright's destructuring requirement. Correct form
is `async ({}, use)` — an empty destructuring pattern, which both tools accept.

## Source Code Trace

| Element | Detail |
| ------------- | ----------------------------------------------- |
| Error origin | (1) `frontend/support/helpers/users.ts` (missing exports); (2) `frontend/support/fixtures/index.ts:29` |
| Trigger | Playwright test collection loads each spec / the fixture barrel before any test body runs |
| Condition | (1) spec imports a name `users.ts` does not export; (2) a fixture's first arg is not a destructuring pattern |
| Related files | 3 generic specs (Finding 1); 17 `story-*` specs importing the fixture barrel (Finding 2) |

## Conclusion

**Confidence:** High

Two independent, Confirmed root causes block the entire `e2e` run at collection time — no test
executes. **Finding 1**: the specs `artifact-viewer`, `provider-selector`, and `chat-input-area`
import `apiCreateUser` / `createProjectAndAddUser` / `getTestUserToken`, none of which
`support/helpers/users.ts` exports (it exports `getAdminToken` and `createStandardUser`).
**Finding 2**: `support/fixtures/index.ts:29` declares `mockJson: async (_, use)`, but Playwright
demands an object-destructuring first argument (`async ({}, use)`), so the fixture barrel — and the
17 story specs depending on it — fails to load.

## Recommended Next Steps

### Fix direction

- **Finding 2 (trivial, unblocks 17 specs).** Change `frontend/support/fixtures/index.ts:29` from
  `mockJson: async (_, use) =>` to `mockJson: async ({}, use) =>`. ESLint accepts empty destructuring;
  Playwright requires it.
- **Finding 1 (small, unblocks 3 specs).** Decide the intended contract for the 3 generic specs.
  Either (a) realign them to the real API — `createStandardUser` + the `userFactory`/`apiClient`
  fixtures + a proper token helper — matching the 17 story specs, or (b) add the missing helpers
  (`apiCreateUser`, `createProjectAndAddUser`, `getTestUserToken`) to `users.ts`. Option (a) is
  consistent with the rest of the suite; (b) risks reintroducing public-registration assumptions
  that Story 8.7 removed (see `users.ts` docstring, lines 18-24).

### Diagnostic

- Run `cd frontend; npx tsc --noEmit -p e2e` (or `npm run typecheck`) — TypeScript will flag all
  missing-export references at once, confirming the full set before editing.
- `git log -p -- frontend/support/fixtures/index.ts` to confirm whether `_` replaced `{}` recently
  (Backlog #3).

## Reproduction Plan

From `frontend/`: `npx playwright test e2e --workers=1`. Expected (current): collection fails with
the two error classes above and 0 tests run. After fixes: the barrel loads and specs collect.

## Side Findings

- A prior investigation exists for this suite — `e2e-test-failures-2026-06-09-investigation.md`
  (one day earlier). Worth confirming this is not a re-open of the same defect class. (Backlog #4)
- The 3 generic specs use `httpCredentials: { username: token, password: "" }` to pass a bearer
  token — an unusual auth approach versus the rest of the suite. Flag for review if Finding 1 is
  fixed via option (a). Unconfirmed whether the app honors this; requires a run to verify.
