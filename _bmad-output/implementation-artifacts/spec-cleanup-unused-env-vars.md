---
title: 'Remove unused environment variables from .env and .env.example'
type: 'chore'
created: '2026-06-21'
status: 'done'
baseline_commit: 'eed1ea39b967d629999ec74eed83f363f57a8cbe'
context: []
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** `.env` and `.env.example` declare several environment variables that no code reads — they are dead config that misleads readers of the template and leaves real, unused secret/URL values sitting in the local `.env`.

**Approach:** Statically verify which declared variables are never consumed (pydantic `AppSettings` fields, `os.getenv`/`os.environ`, `process.env`/`import.meta.env`, docker-compose, Dockerfiles, build scripts, playwright config, e2e helpers), then delete only the confirmed-dead ones from both files. Keep every variable that is still read through any channel.

## Boundaries & Constraints

**Always:** Treat a variable as "used" if it maps to an `AppSettings` field (pydantic loads it even with `extra="ignore"`) OR is referenced anywhere in `src/`, `tests/`, `frontend/`, `scripts/`, `docker-compose*.yml*`, `Dockerfile*`, or playwright config. Delete from BOTH `.env` and `.env.example`. Keep the surrounding comments/section headers coherent after removal.

**Ask First:** Removing any variable whose status is not a clean "zero references" — i.e. anything reachable through pydantic fields or any usage channel. Deleting a variable that is referenced only in docs/story files but a human may still want as a seed value.

**Never:** Do not touch any variable that is consumed by code. Do not change values of kept variables. Do not print, log, or echo real secret values from `.env`. Do not commit `.env` (it is gitignored). No code changes outside the two env files.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
| -------- | ------------- | -------------------------- | -------------- |
| Confirmed-dead var | Var has zero references in any code/config channel | Removed from both `.env` and `.env.example` | N/A |
| Field-backed var | Var name maps to an `AppSettings` field | Kept (pydantic consumes it) | N/A |
| Used-only-in-tests/e2e var | Var read via `process.env` / `os.getenv` in tests, e2e specs, or compose | Kept | N/A |
| App boot after edit | Backend started with edited `.env` | Starts normally; no `ValidationError`, no missing-var crash | N/A |

</frozen-after-approval>

## Code Map

- `.env.example` -- committed template; delete dead vars here (no real values present).
- `.env` -- local, gitignored; holds Thuong's real values; delete the same dead vars here.
- `src/ai_qa/config.py` -- `AppSettings` field list = the authoritative "used by pydantic" set.
- `scripts/build-docker-images.ps1` -- consumes all `DOCKER_*` build vars + `ARTIFACTORY_*` (keep).
- `docker-compose-server.yml.example` -- consumes `DOCKER_*` image/version vars + most app vars (keep).
- `tests/ai_connection/test_providers_live.py` -- maps `TEST_BROWSER_USE_KEY/CLAUDE/GEMINI/OPENAI/ON_PREMISES_KEY` (keep); has NO mcp entry.
- `frontend/e2e/*.spec.ts`, `frontend/support/helpers/*.ts`, `frontend/playwright.config.ts` -- consume `ADMIN_*`, `BASE_URL`, `API_URL`, `E2E_SERVER_MODE`, `TEST_CLAUDE_SSO_*`, `TEST_ON_PREMISES_KEY` (keep); resolve project Confluence/Jira URLs from the DB, not from env.

## Tasks & Acceptance

**Variables confirmed dead (zero references anywhere):** `TEST_ENV`, `TEST_MCP_KEY`, `TEST_PROJECT1_CONFLUENCE_URL`, `TEST_PROJECT2_CONFLUENCE_URL`, `TEST_PROJECT2_JIRA_URL`.

**Execution:**
- [x] `.env.example` -- delete the 5 dead variable lines under `# --- Testing Environment ---`; keep section header and the still-used `TEST_*`/`ADMIN_*`/`BASE_URL`/`API_URL`/`E2E_SERVER_MODE` lines.
- [x] `.env` -- delete the same 5 dead variable lines (real values discarded as intended); leave all other lines untouched.

**Acceptance Criteria:**
- Given the edited files, when grepping the repo for each removed name, then it appears only in `_bmad-output/`/`docs` history (no live code/config reference).
- Given the backend is started with the edited `.env`, when `AppSettings` loads, then it boots with no validation or missing-variable error.
- Given the kept variables, when diffing, then no kept line's value or name changed.

## Design Notes

Why each removed var is dead:

- `TEST_ENV` — never read; `playwright.config.ts` keys off `BASE_URL`/`CI`, not `TEST_ENV`.
- `TEST_MCP_KEY` — `test_providers_live.py` provider map covers only the 5 LLM/browser providers; no MCP entry and no e2e spec reads it.
- `TEST_PROJECT1_CONFLUENCE_URL`, `TEST_PROJECT2_CONFLUENCE_URL`, `TEST_PROJECT2_JIRA_URL` — the grouped e2e suite looks up the real "PT Tool"/"PTP" projects by name via `GET /api/projects` and reads their Confluence/Jira URLs from the DB (`projects.ts`), so these env vars are never consumed.

All `DOCKER_*` (12) and `ARTIFACTORY_*` (2) vars are intentionally kept — the PowerShell build script and the server compose file consume them.

## Verification

**Commands:**
- `rg -n "TEST_ENV|TEST_MCP_KEY|TEST_PROJECT1_CONFLUENCE_URL|TEST_PROJECT2_CONFLUENCE_URL|TEST_PROJECT2_JIRA_URL" --glob '!_bmad-output/**' --glob '!docs/**'` -- expected: no matches in `.env`, `.env.example`, or any code/config file.
- `uv run python -c "from ai_qa.config import AppSettings; AppSettings()"` -- expected: instantiates with no error (confirms `.env` still loads cleanly).

**Manual checks:**
- Diff `.env.example`: exactly 5 lines removed, section headers and all other vars intact.

## Suggested Review Order

- Entry point — the committed template; the 5 dead `TEST_*` vars were removed from the Testing Environment block (`TEST_ENV` at the top, four trailing lines after `TEST_ON_PREMISES_KEY`).
  [`.env.example:84`](../../.env.example#L84)

- Same 5 removals in the local (gitignored) file — its real values were discarded as intended; all other lines untouched.
  [`.env:84`](../../.env#L84)

- Why removal is safe — `AppSettings` uses `extra="ignore"` and has no field matching any removed name, so the vars never loaded; nothing else (tests/e2e/compose/CI) reads them.
  [`config.py:83`](../../src/ai_qa/config.py#L83)

## Review Outcome

Adversarial review (3 reviewers + 1 refutation skeptic per removed variable, run via workflow). All 5 verifiers returned `still_used=false` (high confidence); edge-case hunter found the cleanup safe across every channel; acceptance auditor reported full compliance. The blind hunter's 4 "might be used — verify" hypotheses were assumption-level (it had no code access) and were refuted by the verifiers and a `rg --no-ignore` whole-tree sweep (including the gitignored CI workflow), which returned zero matches. No `intent_gap`, `bad_spec`, `patch`, or `defer` findings.
