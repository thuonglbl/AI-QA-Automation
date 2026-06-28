# Investigation: Bob blocks extraction — MCP key submitted via form is never committed

## Hand-off Brief

1. **What happened.** [Confirmed] Bob's E2E (`epic-11.spec.ts`) fails at the chat-input step because Bob still shows "required conditions are not met / Add your MCP key" after the user fills the MCP key and clicks Start — the submitted `mcp_pat` is persisted with `set_user_secret` but never committed/flushed, and with `autoflush=False` the precondition `SELECT` cannot see the pending row.
2. **Where the case stands.** Root cause Confirmed by code reading; deterministic for fresh users (E2E creates a new user every run → new-row path → invisible without flush).
3. **What's needed next.** Add `db.commit()` immediately after `set_user_secret` in `bob.py:510` — matches the established idiom in `secrets.py:143-144` and `alice.py:443-446`.

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A (Epic 11 E2E regression)                                               |
| Date opened      | 2026-06-12                                                                 |
| Status           | Concluded — root cause Confirmed                                           |
| System           | Windows 11, Python 3.14, FastAPI + SQLAlchemy 2.0, in-tree on top of `2a1f170` |
| Evidence sources | `results.xml`, runtime screenshot, source code, `set_user_secret` contract |

## Problem Statement

`npx playwright test e2e/epic-11.spec.ts --headed --workers=1` fails:
`expect(getByPlaceholder(/Type a message/i)).toBeVisible()` times out at `epic-11.spec.ts:152`.
On screen, after the test fills the MCP key and clicks Bob's **Start**, Bob responds:
"**What happened:** Bob cannot start requirements extraction. **Why:** One or more required conditions are not met.
**What to do:** Add your MCP key in provider configuration, then retry." — so the chat input never renders.

## Evidence Inventory

| Source                              | Status    | Notes                                                                                  |
| ----------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| `results.xml`                       | Available | Failure at `epic-11.spec.ts:152`, `getByPlaceholder(/Type a message/i)` not found.     |
| Runtime screenshot + Inspector log  | Available | Confirms MCP key filled + `Start` clicked, yet Bob shows the MCP blocker message.      |
| `src/ai_qa/agents/bob.py`           | Available | `handle_start` persists `mcp_pat` then runs `_check_preconditions`; no commit.         |
| `src/ai_qa/secrets/service.py`      | Available | `set_user_secret` doc: "caller must commit"; returns "not yet committed". `get_secret_status` is a fresh `SELECT`. |
| `src/ai_qa/db/session.py`           | Available | `sessionmaker(..., autoflush=False, ...)` — pending writes not flushed before queries. |
| Reference call-sites                | Available | `secrets.py:143-144` and `alice.py:443-446` both commit right after `set_user_secret`. |

## Confirmed Findings

### Finding 1: The session is configured with `autoflush=False`

**Evidence:** `src/ai_qa/db/session.py:26` — `sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)`

**Detail:** Pending ORM changes (e.g. `db.add(new_secret)`) are NOT auto-flushed before a subsequent `SELECT`. A query issued after an un-flushed insert will not see the new row.

### Finding 2: `set_user_secret` does not flush or commit — by contract

**Evidence:** `src/ai_qa/secrets/service.py:140` ("The caller must commit the session."), `:149` ("not yet committed"), `:157-164` (new row → `db.add(secret)`).

**Detail:** For a user with no existing MCP secret, `set_user_secret` only adds the row to the session's pending state. It relies on the caller to commit.

### Finding 3: Bob's `handle_start` persists `mcp_pat` but never commits

**Evidence:** `src/ai_qa/agents/bob.py:507-510` — `set_user_secret(db, ..., SECRET_TYPE_MCP, mcp_pat_input)` with no following `db.commit()`/`db.flush()`.

**Detail:** Immediately after, `_check_preconditions` (`bob.py:513`) calls `get_secret_status` (`service.py:90-102`), which issues a fresh `SELECT UserSecret WHERE ...`. With `autoflush=False` and no commit, the pending insert is invisible → `configured=False` → blocker appended (`bob.py:150-151`) → `handle_start` returns early with the "conditions not met" message → chat input never renders.

### Finding 4: The established idiom is to commit right after `set_user_secret`

**Evidence:** `src/ai_qa/api/secrets.py:143-144` and `src/ai_qa/agents/alice.py:443-446` both call `set_user_secret(...)` then `db.commit()`.

**Detail:** Bob's new code diverges from this idiom; that divergence is the defect.

## Deduced Conclusions

### Deduction 1: The bug is deterministic for fresh users, intermittent for returning users

**Based on:** Findings 1–3.

**Reasoning:** New-row path uses `db.add` → requires a flush to be visible. Existing-row path mutates an identity-mapped object already in the session, so `get_secret_status`'s `SELECT` returns the same in-memory object reflecting `status="configured"` even without a flush.

**Conclusion:** The E2E (fresh user per run) hits the new-row path every time → always blocked. A returning user with a prior MCP row might appear to "work," masking the missing commit and risking non-persistence on rollback.

## Source Code Trace

| Element       | Detail                                                                                 |
| ------------- | -------------------------------------------------------------------------------------- |
| Error origin  | `src/ai_qa/agents/bob.py:507-513` (`handle_start`: persist without commit → precondition SELECT misses row) |
| Trigger       | User submits MCP key via Bob's inline form → WS `start` with `inputData.mcp_pat` (`App.tsx:926-936`) |
| Condition     | No existing MCP `UserSecret` row for the user + `autoflush=False` + no `db.commit()`    |
| Related files | `src/ai_qa/secrets/service.py`, `src/ai_qa/db/session.py`, `frontend/src/App.tsx`, `frontend/e2e/epic-11.spec.ts` |

## Conclusion

**Confidence:** High — Confirmed root cause, deterministic reproduction (fresh user).

The MCP key submitted through Bob's form is added to the session but never committed/flushed; under `autoflush=False`, the immediately-following precondition `SELECT` cannot see it, so Bob reports "conditions not met" and never advances to the chat step the E2E waits on.

## Recommended Next Steps

### Fix direction

Add `db.commit()` immediately after `set_user_secret` in `bob.py` (mirror `secrets.py:143-144` / `alice.py:443-446`). One line; trivial.

## Reproduction Plan

Setup: fresh standard user, project with `confluence_base_url`, On-Premises provider configured via Alice (so provider/model preconditions pass). Trigger: navigate to Bob, enter MCP key, click Start. Expected (post-fix): Bob initialises and the "Type a message" chat input renders; pre-fix: Bob shows the MCP blocker.

## Side Findings

- [Confirmed] Bob's inline MCP form is the *only* persistence path for the MCP secret in this flow — it does not call the `/api/secrets` endpoint; it rides `inputData.mcp_pat` through the WS `start` message (`App.tsx:926-936`). So the commit must live in `handle_start`.

## Follow-up: 2026-06-12

### New Evidence

After the `db.commit()` fix, Bob stopped reporting "conditions not met" and instead showed:
"Could not find a page ID or space key in the URL — point to a specific Confluence page." A 5-agent
workflow (parallel backend/frontend/DB readers + adversarial verifier; **High** confidence, verifier agreed)
located two compounding **test-only** defects.

### Additional Findings

- **Finding 5 [Confirmed].** Real projects store the FULL page URL in `confluence_base_url`, not a host.
  Live Postgres query (`ai_qa_automation.projects`): "PTP Personal Travel Plan" →
  `https://confluence.svc.corp.ch/spaces/EXPERTGROUP/pages/1238866187/PTP+-+Personal+Travel+Plan` (the
  exact page Test 1 targets); "PT Tool" → `.../pages/690323464/...`. The field name "base URL" is a misnomer.
- **Finding 6 [Confirmed].** The test created the project via `baseUrl()` (`epic-11.spec.ts:38-41`), which
  strips to scheme+host → `https://confluence.svc.corp.ch`. `App.tsx:931` forwards that verbatim as
  `confluence_url`; `_validate_confluence_url` finds no page id/space key and returns the on-screen error
  ([bob.py:191-197](src/ai_qa/agents/bob.py)). The host-only URL still passes `is_valid_confluence_url`
  (host matches `confluence[./]`), so it reaches the page-id check rather than the format-hint branch.
- **Finding 7 [Confirmed].** A full server-style page URL (no `/wiki/`) is rescued by the numeric fallback
  `_NUMERIC_ID_RE = /(\d+)(?:/|$)/` ([confluence_reader.py:28,110](src/ai_qa/pipelines/confluence_reader.py))
  → `page_id=1238866187`; host-mismatch check compares netloc only, so it passes.
- **Finding 8 [Confirmed].** No `/Type a message/i` chat composer and no `Send` button exist for Bob anywhere
  in `frontend/src` (grep: zero matches). The backend never turns chat text into `confluence_url`
  (websocket dispatch: start→handle_start, approve→handle_approve, reject→handle_reject). The test's
  `sendUrlAndWaitForResponse` was both impossible (locator never matches) and redundant (URL already on the
  start payload). The only post-start text input is the parent-confirmation card (`App.tsx:1620-1658`,
  placeholder "Enter the correct page URL...", gated by `status==="review_request" && bobState.isConfirmParent`),
  followed by the `SplitPanel` review (`App.tsx:1660-1677`).

### Updated Conclusion

Root cause = **test only**. Backend validation is correct and matches production data; no backend/App.tsx change
warranted. Fix applied to `frontend/e2e/epic-11.spec.ts`: (1) store the FULL page URL in `confluenceBaseUrl`
(drop `baseUrl()`); (2) replace `sendUrlAndWaitForResponse` with `confirmParentAndAwaitReview`, which drives the
real parent-confirmation card → OK → `SplitPanel` review. Confidence **High**.

### Backlog Changes

- **Open — Test 2 Jira leg.** `TEST_PROJECT2_JIRA_URL` is a RapidBoard *board* URL; `_validate_jira_ref`
  ([bob.py:201-241](src/ai_qa/agents/bob.py)) requires an issue key (`PROJ-123`) and would block the whole
  start if filled into the Jira field. Test 2 now exercises Confluence only; the Jira leg needs a real ticket
  URL. Decision pending from Thuong.
- **Latent — separate ticket.** Admin UI placeholder `https://confluence.company.com`
  ([AdminDashboard.tsx:534,743](frontend/src/components/admin/AdminDashboard.tsx)) implies host-only entry,
  contradicting the full-page-URL semantics the backend requires. Worth a placeholder/helper-text fix so real
  admins don't repeat this mistake.
- **Caveat.** The corrected Test 1 now hits the LIVE internal MCP against `confluence.svc.corp.ch` (connect →
  find/get_children/read_page). Requires network + EXPERTGROUP read grant (user confirmed both). If unavailable,
  it times out at the confirm/review wait rather than at URL validation.
