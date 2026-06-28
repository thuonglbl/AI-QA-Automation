# Investigation: "Run E2E Tests" admin feature fails on both local and UAT

## Hand-off Brief

1. **What happened.** The in-app "Run E2E Tests" admin action fails in two different,
   independent ways — locally with `http://127.0.0.1:8000/auth/status is already used`
   (exit 1), and on UAT with `Frontend directory not found: /app/frontend` (exit -1).
2. **Where the case stands.** Both root causes are **Confirmed** from code. Local: the
   endpoint forces `CI=1` into the Playwright subprocess, which flips
   `reuseExistingServer` to `false`, so Playwright tries to boot a *second* backend on
   the already-occupied port 8000. UAT: the backend Docker image
   (`Dockerfile.backend`) ships only Python + `src/` at `/app` — no `frontend/` dir, no
   Node/`npx`, no Playwright — so the feature is architecturally inoperable in the
   split-image deployment.
3. **What's needed next.** Decide the feature's intended scope. Local is a one-line fix
   (stop forcing `CI=1`, or force `reuseExistingServer:true`). UAT requires a design
   decision — the in-process `npx playwright` runner cannot work in the Python-only
   backend container as built.

## Case Info

| Field            | Value                                                                                   |
| ---------------- | --------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                     |
| Date opened      | 2026-06-19                                                                              |
| Status           | Concluded (both root causes Confirmed)                                                  |
| System           | Local: Windows 11, backend on `:8000`, Vite on `:5173`. UAT: Debian 6.1, Docker Compose split-image deploy. |
| Evidence sources | Source code (`src/ai_qa/api/admin.py`, `frontend/playwright.config.ts`, `Dockerfile.backend`, `docker-compose-server.yml.example`), README.md, story 8-6 review notes, two UI screenshots, UAT SSH session. |

## Problem Statement

User report: *"Tính năng run e2e fail trên cả local lẫn uat. Trên server uat thì chỉ có
2 file config, không có source, do deploy bằng docker."* — The "Run E2E Tests" button
(E2E Test Execution card, admin dashboard) fails in both environments. The UAT host
holds only `docker-compose.yml` + `.env` (no source), because it runs from Docker
images.

Observed symptoms (screenshots):

- **Local (`localhost:5173`):** "Tests failed (exit code 1)" — output: `Error:
  http://127.0.0.1:8000/auth/status is already used, make sure that nothing is running
  on the port/url or set reuseExistingServer:true in config.webServer.` Plus a
  `[DEP0205] DeprecationWarning: module.register()` line under "Show errors".
- **UAT (`https://ai-qa.ai-uat.corpdev.local`):** "Tests failed (exit code -1)" —
  error: `Frontend directory not found: /app/frontend`.

The premise (feature fails in both) is **Confirmed** and the two failures are
**distinct root causes**, not the same bug surfacing twice.

## Evidence Inventory

| Source                                   | Status    | Notes                                                                                          |
| ---------------------------------------- | --------- | ---------------------------------------------------------------------------------------------- |
| `src/ai_qa/api/admin.py` (endpoint)      | Available | `run_e2e_tests` at `admin.py:453`; forces `CI:"1"` at `admin.py:496`; `_FRONTEND_DIR` at `admin.py:47-48`. |
| `frontend/playwright.config.ts`          | Available | `webServer` boots backend on `:8000` + Vite on `:5173`; `reuseExistingServer: !process.env.CI` (`:72`, `:81`). |
| `Dockerfile.backend`                     | Available | Python 3.14-slim; copies only `src/`, `alembic/`, configs; no `frontend/`, no Node/npx.        |
| `docker-compose-server.yml.example`      | Available | Split images: `backend` (port 8000) + `frontend` (Nginx, 8080:80) as separate containers.      |
| README.md                                | Available | Documents local 3-terminal E2E flow and split-image Docker deploy.                             |
| Story 8-6 review (`8-6-admin-e2e-test-execution.md:81`) | Available | Pre-existing flag: "Brittle Path Resolution Assumption — _FRONTEND_DIR relies on relative paths." |
| UAT runtime filesystem / container shell | Missing   | Not inspected directly; deduced from `Dockerfile.backend`. `docker exec backend ls /app` would confirm. |

## Confirmed Findings

### Finding 1: The admin endpoint injects `CI=1` into the Playwright subprocess

**Evidence:** `src/ai_qa/api/admin.py:490-496` — `run_process_sync` runs
`[npx, "playwright", "test", "--headed", "--workers=1"]` with
`env={**os.environ, "PLAYWRIGHT_SLOW_MO":"500", "FORCE_COLOR":"0",
"PLAYWRIGHT_HTML_REPORT_OPEN":"never", "CI":"1"}`.

**Detail:** The in-app runner unconditionally sets `CI=1` for the spawned Playwright
process, regardless of whether the host is a developer machine or CI.

### Finding 2: `reuseExistingServer` is keyed off `CI`, and the config boots a backend on port 8000

**Evidence:** `frontend/playwright.config.ts:67-86` — `webServer[0]` = `{ command:
"uv run ai-qa", url: "http://127.0.0.1:8000/auth/status", reuseExistingServer:
!process.env.CI }`; `webServer[1]` = Vite on `:5173`, same `reuseExistingServer` rule.

**Detail:** With `CI` truthy, `!process.env.CI` is `false`, so Playwright will NOT reuse
a running server — it attempts to start its own backend on `:8000`. The comment at
`playwright.config.ts:64-66` states the explicit intent: *"reuseExistingServer keeps
already-running local servers (and the admin in-app runner) untouched."* Finding 1
defeats that intent.

### Finding 3: The backend Docker image contains no frontend, Node, or npx; package root is `/app`

**Evidence:** `Dockerfile.backend` — `WORKDIR /app` (`:16`); installs only
`ca-certificates curl` + `uv` (`:18-21`); `COPY src/ ./src/` (`:24`) with no
`COPY frontend/`; `CMD ["uvicorn", ...]` (`:35`). `src/ai_qa/api/admin.py:47-48` —
`_PROJECT_ROOT = Path(__file__).parents[3]`, `_FRONTEND_DIR =
Path(os.getenv("FRONTEND_DIR", _PROJECT_ROOT / "frontend"))`.

**Detail:** In the image the file lands at `/app/src/ai_qa/api/admin.py`, so
`parents[3]` = `/app` and the default `_FRONTEND_DIR` = `/app/frontend`. That directory
is never copied into the image, so `_FRONTEND_DIR.is_dir()` is `False` →
`admin.py:464-471` returns exit code -1 with `Frontend directory not found:
/app/frontend`. Even past that guard, `shutil.which("npx")` (`admin.py:474`) would
return `None` (no Node in the image) → "npx not found".

### Finding 4: UAT `.env` does not override `FRONTEND_DIR`

**Evidence:** The UAT error message shows the *default* path `/app/frontend`
(screenshot 2). Per `admin.py:48`, the default is only used when the `FRONTEND_DIR` env
var is unset.

**Detail:** Consistent with the user's report that UAT holds only `docker-compose.yml`
+ `.env`; neither sets `FRONTEND_DIR`. Overriding it would not help — there is no
frontend source anywhere in the backend container to point at.

## Deduced Conclusions

### Deduction 1 (Local root cause): port 8000 self-collision

**Based on:** Findings 1 + 2.

**Reasoning:** The backend that serves `POST /api/admin/tests/e2e` is itself listening
on `:8000`. The endpoint spawns Playwright with `CI=1` → `reuseExistingServer=false` →
Playwright's `webServer[0]` tries to launch a *new* `uv run ai-qa` and bind `:8000`,
which is already held by the serving backend.

**Conclusion:** Playwright aborts during web-server startup with
`http://127.0.0.1:8000/auth/status is already used … set reuseExistingServer:true`,
exit code 1 — exactly the local screenshot. The failure occurs before any test runs.

### Deduction 2 (UAT root cause): feature is incompatible with the split-image deploy

**Based on:** Findings 3 + 4 + README deploy section.

**Reasoning:** The feature shells out to `npx playwright test` inside a sibling
`frontend/` directory and relies on `webServer` booting `uv run ai-qa` + `npm run dev`.
None of these exist in the production backend container: no `frontend/`, no Node/npx, no
Vite, and `uv run ai-qa` is not the container entrypoint. The frontend is a *separate*
Nginx image with no Python/Playwright.

**Conclusion:** The in-process Playwright runner can never succeed in the current Docker
deployment. The `/app/frontend` guard fails first; removing it only surfaces the next
missing dependency (`npx`). This is an architectural mismatch, not a config typo.

## Hypothesized Paths

### Hypothesis 1: The `DEP0205 module.register()` deprecation is the cause

**Status:** Refuted.

**Theory:** The deprecation warning under local "Show errors" is the failure.

**Supporting indicators:** It appears in the red "Show errors" panel.

**Would confirm:** Removing it changes the exit code.

**Would refute:** It is a known, benign warning.

**Resolution:** Refuted. `project-context.md:33` lists `DEP0205` (Playwright) under
"Known Warnings (DO NOT fix)". The real local fatal is the port-8000 collision
(Deduction 1); the warning is incidental noise on stderr.

## Missing Evidence

| Gap                                          | Impact                                                              | How to Obtain                                                                 |
| -------------------------------------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Direct view of UAT backend container FS      | Would turn Deduction 2 from Confirmed-by-Dockerfile to directly observed. | `docker compose exec backend ls -la /app` and `docker compose exec backend which npx` on UAT. |
| Why `CI=1` was added to the runner           | Clarifies safest local fix (retries/forbidOnly were likely wanted). | `git log -p -- src/ai_qa/api/admin.py` around the 8-6 implementation.         |

## Source Code Trace

| Element       | Detail                                                                                             |
| ------------- | -------------------------------------------------------------------------------------------------- |
| Error origin (UAT)   | `src/ai_qa/api/admin.py:464-471` — `if not _FRONTEND_DIR.is_dir(): return … "Frontend directory not found"`. |
| Error origin (local) | `frontend/playwright.config.ts:67-76` (`webServer[0]`) — Playwright web-server boot, with `reuseExistingServer:false` from `CI=1`. |
| Trigger       | `POST /api/admin/tests/e2e` → `run_e2e_tests` (`admin.py:453`) → `run_process_sync` spawns `npx playwright test` (`admin.py:484-498`). |
| Condition (local) | A backend is already bound to `:8000` AND the subprocess env has `CI=1` (always, per `admin.py:496`). |
| Condition (UAT)   | Running inside `Dockerfile.backend` image where `/app/frontend` is absent and Node/npx is not installed. |
| Related files | `src/ai_qa/api/admin.py:47-48` (`_FRONTEND_DIR`), `frontend/playwright.config.ts`, `Dockerfile.backend`, `docker-compose-server.yml.example`, `frontend/Dockerfile`. |

## Conclusion

**Confidence:** High (both root causes Confirmed from code with matching error strings).

Two independent root causes under one symptom:

- **Local — Confirmed.** The endpoint forces `CI=1` (`admin.py:496`), which makes
  `reuseExistingServer=false` (`playwright.config.ts:72`), so Playwright tries to start a
  second backend on the already-occupied port 8000 → "is already used", exit 1. The
  config comment shows the *opposite* was intended.
- **UAT — Confirmed.** The split-image backend container (`Dockerfile.backend`) has no
  `frontend/`, no Node, no npx, no Playwright; `_FRONTEND_DIR` resolves to the
  non-existent `/app/frontend` → exit -1. The feature, as an in-process `npx playwright`
  runner, is architecturally incompatible with the production Docker deployment.

The `DEP0205` warning is a known benign red herring (Refuted hypothesis).

## Recommended Next Steps

### Fix direction

- **Local (trivial, one-line).** Stop forcing CI semantics on the in-app runner. Either
  remove `"CI": "1"` from the env at `admin.py:496`, or add an explicit
  `"PLAYWRIGHT_REUSE_SERVER": "1"` and have `playwright.config.ts` honor it so
  `reuseExistingServer` stays `true` when launched in-app. (If `CI=1` was added only for
  `retries`/`forbidOnly`, decouple those from the server-reuse decision.) Confirm the
  motivation via `git log` before editing.
- **UAT (design decision required).** The current in-process runner cannot work in the
  Python-only backend image. Options, by mechanism: **(a)** scope the feature to local
  dev only and hide/disable the card in the deployed UI (cheapest); **(b)** ship a
  dedicated test-runner image that contains the frontend source + Node + Playwright
  browsers and invoke it as a separate service/job (heaviest, but makes UAT runs real);
  **(c)** decouple the runner from the monorepo layout entirely (run Playwright against
  the deployed URL from a CI job rather than from inside the backend process).

### Diagnostic

- On UAT: `docker compose exec backend ls -la /app && docker compose exec backend which
  npx` — directly confirms Finding 3.
- Locally: re-run with `CI` removed from `admin.py:496` and observe that
  `reuseExistingServer:true` lets the suite proceed against the running `:8000`/`:5173`.

## Reproduction Plan

- **Local:** Start backend (`uv run uvicorn ai_qa.api:app --port 8000`) and Vite
  (`npm run dev`). Log in as admin, open the E2E Test Execution card, click "Run E2E
  Tests". Expect exit 1 with the "is already used" message — fails during webServer
  boot, before tests.
- **UAT:** On a split-image Docker deploy, log in as admin and click "Run E2E Tests".
  Expect exit -1 with `Frontend directory not found: /app/frontend`.

## Side Findings

- `playwright.config.ts:64-66` comment explicitly intends `reuseExistingServer` to keep
  "the admin in-app runner" servers untouched — directly contradicted by `admin.py:496`
  setting `CI=1`. (Confirmed.)
- Story 8-6 review already flagged the fragile path resolution:
  `8-6-admin-e2e-test-execution.md:81` — *"Brittle Path Resolution Assumption —
  _FRONTEND_DIR relies on relative paths."* The `FRONTEND_DIR` env fallback that was
  added does not help in Docker because no frontend source exists in the backend image.
  (Confirmed.)
- Even with `CI=1`, `forbidOnly:true` (`playwright.config.ts:36`) and `retries:2`
  (`:37`) are silently activated for in-app local runs — a behavior change unrelated to
  the failure but worth noting. (Confirmed.)

## Follow-up: 2026-06-19 — Fix implemented (both environments)

### Approach (decided with Thuong)

Make the in-app Playwright runner work **in-process** on both environments by (1)
reusing the already-running servers, and (2) bundling a Playwright toolchain into the
backend Docker image. UAT test target = the deployed **HTTPS** URL (Secure cookies need
HTTPS), with `ignoreHTTPSErrors`. Everything env-driven via one switch, `E2E_SERVER_MODE`.

### Changes

- `frontend/playwright.config.ts` — `webServer` gated on `E2E_DISABLE_WEBSERVER` (so the
  runner never boots a second backend/Vite → kills the local port-8000 collision);
  `use.ignoreHTTPSErrors` from `PLAYWRIGHT_IGNORE_HTTPS_ERRORS`; chromium
  `launchOptions.args = [--no-sandbox, --disable-dev-shm-usage]` from `E2E_NO_SANDBOX`.
- `src/ai_qa/api/admin.py` — removed forced `CI=1`; always sets `E2E_DISABLE_WEBSERVER=1`;
  `--headed` + slow-mo only off `E2E_SERVER_MODE`; in server mode defaults
  `E2E_NO_SANDBOX`/`PLAYWRIGHT_IGNORE_HTTPS_ERRORS` (overridable).
- `Dockerfile.backend` — installs Node (official tarball, glibc-safe), `npm ci` of the
  frontend, `playwright install --with-deps chromium` (browsers → `/ms-playwright`), and
  copies `e2e/`, `support/`, `playwright.config.ts`, `tsconfig.node.json` (NOT `src/`).
- `docker-compose-server.yml.example` — forwards `E2E_SERVER_MODE`/`BASE_URL`/`API_URL`/
  `ADMIN_*` to the backend; `shm_size: 1gb`; commented `extra_hosts` for hostname DNS.
- `.env.example`, `scripts/build-docker-images.ps1` (`--build-arg NODE_VERSION`),
  `README.md`, and `tests/api/test_admin_e2e_api.py` (+6 tests) updated.

### Verification

- `uv run mypy src/ai_qa/api/admin.py` — clean.
- `uv run pytest tests/api/test_admin_e2e_api.py --no-cov` — 17 passed.
- `tsc --noEmit -p frontend/tsconfig.node.json` — clean.
- **Not executed here:** the Docker image build (`scripts/build-docker-images.ps1`) and a
  live UAT run — no Docker in this session. Reasoned + design-probe-validated only. The
  operator must build/push the new backend image and run the button once on UAT.

### Residual risks / operator notes

- The backend container must resolve `BASE_URL`'s hostname; if not, uncomment
  `extra_hosts: ai-qa.ai-uat.corpdev.local:host-gateway`. (Hypothesized — depends on the
  UAT network.)
- E2E on UAT runs against the real Postgres but only creates/deletes **synthetic**
  `@example.com|test` users and `S<n>`/`Story <n>` projects (teardown never touches admin
  or real data). (Confirmed via `global-teardown.ts:32-35,70-73`.)
- Backend image grows substantially (Node + Chromium + node_modules). Accepted.
