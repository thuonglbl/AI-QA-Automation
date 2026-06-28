# Investigation: Copying an SSO test-login session on UAT (and the "Loading sessions…" hang)

> **NOTE 2026-06-25:** valid as history, but its "Recommended option 1 — client-capture → upload blob" is now **PROHIBITED** by Group Security (session capture is flagged as cookie-stealing). Target-app auth moves to dedicated test-account auto-login — see **Epic 25** / `sprint-change-proposal-2026-06-25-no-session-capture.md`. Thread A (the sync-`invoke` event-loop hang) is unaffected and still valid.

## Hand-off Brief

1. **What happened.** Two intertwined symptoms: (A) the "Test-login sessions" dialog hangs on
   *"Loading sessions…"* while Sarah is generating scripts; (B) the user cannot capture an SSO
   session on UAT the way they can locally. Root of (A) Confirmed: Sarah's per-script LLM call is
   the **synchronous** `LLMClient.invoke()` on the event loop, freezing every concurrent request
   (incl. `GET /sessions`). Root of (B) Confirmed: session capture is a **backend-initiated CDP
   pull** to `localhost:9222`, but on UAT the backend is a remote container and the user's Chrome
   is on their laptop — different machines, no route.
2. **Where the case stands.** Both root causes Confirmed (High). The user's premise — "open UAT and
   the test site in the same Chrome profile and the session can be copied" — is **Refuted**: capture
   never reads the user's own browser; it pulls a `storageState` over CDP from a debug browser the
   backend can reach. No "upload-a-blob" capture path exists today.
3. **What's needed next.** Decide the UAT capture strategy. The robust fix is a new
   **client-captures → uploads blob** endpoint (topology-independent). Short-term workarounds (DB-row
   transfer, reverse CDP tunnel) each have hard caveats documented below. Separately, fixing Sarah's
   sync `invoke` → `ainvoke` removes the "Loading sessions…" hang.

## Case Info

| Field            | Value                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                                            |
| Date opened      | 2026-06-22                                                                                                     |
| Status           | Active                                                                                                         |
| System           | Local dev (localhost:5173 / single-worker uvicorn) + UAT (`https://ai-qa.ai-uat.corpdev.local`, containerized backend); target app = internal SSO `int-progresstalkapplication.corpnet.local` |
| Evidence sources | Screenshot (Sarah step, "Loading sessions…" mid script-gen); frontend + backend source; design doc; project-context.md; project memory |

## Problem Statement

User report (verbatim, VI): "dù đã generate test script nhưng session không load được. Tạm thời có
thể copy session ở local. Nhưng bạn hãy điều tra làm sao để copy session trên uat cho trường hợp
login SSO, mình mở cả môi trường uat và trang web để test ở Chrome cùng 1 profile, tuy nhiên mình
không rõ có copy session được không?"

Two questions: (A) why does the session list not load (it hangs while scripts generate); (B) how can
an SSO session be captured/copied on UAT, given the user opens both the UAT app and the
app-under-test in one Chrome profile — is copying even possible?

## Evidence Inventory

| Source                                                  | Status    | Notes                                                                                  |
| ------------------------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| Screenshot (Sarah — Scripts, "Loading sessions…")       | Available | Dialog stuck on "Loading sessions…" while header shows "Processing" + "Generating script 1 of 7…" |
| `frontend/src/components/sessions/SessionMatrixPanel.tsx` | Available | Dialog: `listSessions` on open; editable CDP-URL field (default `http://localhost:9222`) |
| `src/ai_qa/api/sessions.py`                             | Available | 4 routes only (GET matrix, POST capture-over-CDP, POST auto-capture, DELETE). No blob upload |
| `src/ai_qa/browser/session_capture.py`                  | Available | `capture_storage_state_over_cdp(cdp_url)` — backend `connect_over_cdp` to the debug browser |
| `src/ai_qa/browser/password_login.py`                   | Available | PASSWORD auto-capture launches Chrome **on the backend host** via subprocess           |
| `src/ai_qa/sessions/service.py` + `db/types.py` + `models.py` | Available | Blob Fernet-encrypted (`UserSecretEncryptedText`, env key) keyed `(user_id, project_id, env, role)` |
| `src/ai_qa/pipelines/script_generator.py`               | Available | Sync `llm_client.invoke()` at `:413/:494/:575`, awaited from async `_call_llm*`        |
| `scripts/build-docker-images.ps1` + `.env.example:99`   | Available | Backend shipped as a Docker image; UAT base URL `ai-qa.ai-uat.corpdev.local` (remote)  |
| Design doc `design-test-login-credentials-and-sessions-2026-06-20.md` | Available | §0 proves storageState reuse is portable across machines; capture validated locally only |
| UAT runtime topology (where the container runs vs laptop) | Partial   | Inferred remote-host container from build/deploy + base URL; exact host/network unconfirmed |
| Backend logs / Network tab during the hang             | Missing   | Would directly confirm a *pending* (not failed) `GET /sessions` during script-gen      |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Confirm `GET /sessions` is *pending* (not 500) during script-gen via Network tab | Medium | Open | Closes the last gap on Thread A (event-loop block vs request error) |
| 2 | Decide UAT capture strategy (upload-blob endpoint vs DB transfer vs tunnel) | High | Open | The user's actual ask; needs a product/security call |
| 3 | Confirm UAT backend network path to a laptop CDP port (almost certainly blocked) | Low | Open | Only matters if the tunnel workaround is considered |
| 4 | Whether local & UAT share `USER_SECRETS_ENCRYPTION_KEY` | Medium | Open | Determines if a DB-row transfer can even decrypt on UAT |

## Timeline of Events

| Time | Event | Source | Confidence |
| ---- | ----- | ------ | ---------- |
| 18:48–18:51 (screenshot) | Sarah saves 7 test cases, begins "Generating script 1 of 7…" | Screenshot | Confirmed |
| during 18:51+ | User opens "Test-login sessions" → dialog stuck "Loading sessions…" | Screenshot | Confirmed |

## Confirmed Findings

### Finding 1: SSO capture is a backend-initiated CDP *pull*, not a read of the user's browser

**Evidence:** `src/ai_qa/browser/session_capture.py:24-53` (`connect_over_cdp(cdp_url)` →
`contexts[0].storage_state()`); `src/ai_qa/api/sessions.py:173-203` (`capture_session` calls it with
the request's `cdp_url`); `SessionMatrixPanel.tsx:294-307` (editable "Debug-browser CDP URL" field,
default `http://localhost:9222`).

**Detail:** Capture works by the **backend** connecting to a Chrome/Edge started with
`--remote-debugging-port=9222` and exporting its `storageState`. The browser the user normally uses
to view the app is irrelevant; only a CDP endpoint the *backend process* can reach matters.

### Finding 2: On UAT the backend and the user's Chrome are on different machines

**Evidence:** `.env.example:99` (`BASE_URL=https://ai-qa.ai-uat.corpdev.local` — remote host);
`scripts/build-docker-images.ps1:106` (`docker build --file Dockerfile.backend …` → image pushed to
Artifactory and deployed on UAT); project memory (UAT backend = Debian-slim container, air-gapped).

**Detail:** `localhost:9222` evaluated *inside the UAT backend container* points at the container
itself, never at the tester's laptop. The UAT backend has no inbound route to a port on the laptop.
Local dev works only because the uvicorn process, the user's Chrome, and the DB are all co-located on
the same Windows machine (this is the "tạm thời copy được ở local").

### Finding 3: No "upload a captured blob" path exists — capture is CDP-pull or backend-launch only

**Evidence:** `src/ai_qa/api/sessions.py` exposes exactly four routes: `GET /{id}/sessions`,
`POST …/capture` (CDP pull), `POST …/auto-capture` (backend launches Chrome via
`password_login.login_and_capture_storage_state`, `password_login.py:340-422`), `DELETE …`. None
accepts a client-provided `storageState` blob.

**Detail:** Both capture paths require the *backend* to drive/reach a browser. There is no endpoint
where the client captures the blob itself and POSTs it — which is exactly the path that would be
topology-independent and work on UAT.

### Finding 4: The session blob is portable, but stored per-env-key and per-UUID

**Evidence:** Design doc §0.3 (storageState injected into a clean browser loaded `…/dashboard` fully
authenticated — portable across browser instances); `service.py:63-115` (keyed
`(user_id, project_id, environment, role)`); `models.py:171` + `db/types.py:31`
(`UserSecretEncryptedText` → Fernet with `settings.user_secrets_encryption_key`); `.env.example:32`
(`USER_SECRETS_ENCRYPTION_KEY` is per-`.env`).

**Detail:** The blob itself can be reused on any machine that runs the test against the same target
host (cookies are domain-scoped to `int-progresstalkapplication.corpnet.local`). But the *stored row*
is encrypted with an environment-specific key and bound to local DB UUIDs for user+project — so a raw
`captured_sessions` row copied local→UAT will (a) fail to decrypt if the keys differ and (b) not match
the UAT user/project UUIDs even if it does.

### Finding 5: "Loading sessions…" hangs because Sarah's `invoke()` blocks the event loop

**Evidence:** `script_generator.py:375` (`async def _call_llm`) calls **synchronous**
`llm_client.invoke(messages, timeout=timeout)` at `:413` (also `:494`, `:575`) — not `ainvoke`, not
`asyncio.to_thread`; awaited from `sarah.py:402` `_generate_scripts` → `:448`
`script_generator.generate(...)`. `SessionMatrixPanel.tsx:59-69` shows the dialog stays on "Loading
sessions…" only while the `listSessions` promise is *pending* (a rejection would set `loadError` and
clear `loading` in `finally`). project-context.md:172 documents this exact anti-pattern; project
memory `uat-model-selection-grc-and-freeze-rootcause` independently found "Sarah sync `invoke` blocks
the loop".

**Detail:** On a single-worker uvicorn, a synchronous `invoke()` on a slow on-prem model holds the
event loop for tens-to-hundreds of seconds per script. During that window FastAPI cannot serve the
concurrent `GET /projects/{id}/sessions` the dialog fires, so it spins forever. The screenshot's
"Generating script 1 of 7…" places the hang squarely inside that blocked window.

## Deduced Conclusions

### Deduction 1: The in-app "Capture" button cannot capture an SSO session on UAT

**Based on:** Findings 1 + 2.

**Reasoning:** Capture needs the backend to reach a CDP endpoint; on UAT the backend is a remote
container and the only browser logged into SSO is on the laptop, unreachable from the container.

**Conclusion:** With the current design, clicking Capture on UAT cannot reach the tester's
SSO-authenticated browser → SSO capture is not possible there as it is locally.

### Deduction 2: A raw DB-row transfer local→UAT is fragile, not a clean copy

**Based on:** Finding 4.

**Reasoning:** Decryption needs the same `USER_SECRETS_ENCRYPTION_KEY`; the row's `user_id`/`project_id`
must match UAT's UUIDs. Both are environment-specific.

**Conclusion:** Copying the `captured_sessions` row works only if the key is shared AND the UUIDs are
re-mapped — otherwise the UAT backend reads a corrupt/absent session. There is no tooling for this
(no `model_transfer`-style exporter for sessions).

### Deduction 3: The hang is a pending request, not a failed one

**Based on:** Finding 5 + `SessionMatrixPanel.tsx:59-69`.

**Reasoning:** A failed `listSessions` would surface the red "Could not load sessions…" text and clear
the spinner; the persistent "Loading sessions…" means the request never resolved.

**Conclusion:** The dialog is blocked on the server, consistent with the event-loop block during
script generation — not a frontend or 4xx/5xx error.

## Hypothesized Paths

### Hypothesis 1: Same Chrome profile for UAT + the test site lets the session be copied (user's premise)

**Status:** Refuted

**Theory:** Because the tester is logged into the SSO app in the same Chrome profile they use for the
UAT app, the app can copy that session.

**Supporting indicators:** Intuitive — "the cookies are right there in my browser".

**Would confirm:** A capture path that reads the user's *own* running browser session.

**Would refute:** Capture connects over CDP to a debug browser the *backend* reaches
(`session_capture.py:24-53`); it never reads the user's normal browser, and on UAT the backend can't
reach the laptop at all (Findings 1-2).

**Resolution:** Refuted. The shared-profile detail does not affect the capture mechanism; the blocker
is backend↔browser network topology, not which profile is logged in.

### Hypothesis 2: A reverse CDP tunnel (laptop → UAT backend) could enable capture

**Status:** Open

**Theory:** Launch Chrome `--remote-debugging-port=9222` on the laptop, expose it to the UAT backend
via a reverse tunnel, and set the dialog's CDP-URL field to the tunneled address.

**Supporting indicators:** The CDP-URL field IS editable (`SessionMatrixPanel.tsx:294-301`) and the
backend honors it (`api/sessions.py:190`).

**Would confirm:** The UAT backend successfully `connect_over_cdp`s to the tunneled endpoint and
exports a non-empty storageState.

**Would refute:** Corporate firewall blocks inbound from the air-gapped UAT host to the laptop; CDP
refuses non-localhost origins without `--remote-debugging-address`/host-header handling.

**Resolution:** Open — technically plausible but likely policy-blocked on an air-gapped UAT; needs a
network test (Backlog #3).

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Pending vs failed `GET /sessions` during the hang | Confirms Thread A is the event-loop block (vs a 5xx) | Open DevTools → Network while Sarah generates; watch the `/sessions` request state |
| Whether local & UAT share `USER_SECRETS_ENCRYPTION_KEY` | Decides if a DB-row transfer can decrypt on UAT | Compare the two `.env` values (do not print the key) |
| UAT host ↔ laptop network reachability for CDP | Decides feasibility of the tunnel workaround | Attempt a tunnel from the UAT host to the laptop's :9222 |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Capture mechanism | `browser/session_capture.py:37` `pw.chromium.connect_over_cdp(cdp_url)` → `:45` `storage_state()` |
| Capture entry (API) | `api/sessions.py:173-203` `capture_session` (uses request `cdp_url`); `:206-237` `auto_capture` (backend launches Chrome) |
| Topology boundary | UAT backend = remote container (`build-docker-images.ps1:106`, `.env.example:99`); user Chrome = laptop |
| Storage / encryption | `sessions/service.py:63-115`; `db/models.py:171`; `db/types.py:22-32,118-126` (env-keyed Fernet) |
| Hang origin (Thread A) | `pipelines/script_generator.py:413` sync `invoke()` on the loop, awaited via `sarah.py:402,448`; dialog spinner `SessionMatrixPanel.tsx:178` |

## Conclusion

**Confidence:** High

- **Thread B (the main ask) — "can the SSO session be copied on UAT?"**: **Not via the current in-app
  Capture flow.** Capture is a backend→browser CDP pull; on UAT the backend is a remote container that
  cannot reach the tester's laptop browser, and there is no endpoint to upload a client-captured blob.
  The "same Chrome profile" premise is refuted — capture never reads the user's own browser. The blob
  *is* portable, so the right fix is to change *how the blob reaches the backend*, not the blob itself.
- **Thread A — "session won't load"**: the "Loading sessions…" hang is the documented event-loop block:
  Sarah's per-script generation uses the synchronous `LLMClient.invoke()` on the loop, so the concurrent
  `GET /sessions` request cannot be served until generation yields.

## Recommended Next Steps

### Fix direction

**Thread B — pick one (in preference order):**

1. **(Recommended, design change) Add a "client-capture → upload blob" path.** New endpoint
   `POST /projects/{id}/sessions/import` accepting a `storageState` JSON. The tester captures locally
   (the already-validated Node Playwright `connectOverCDP().storageState()` flow, or a small helper),
   then uploads the blob over the normal authenticated HTTPS request. Works identically on local and
   UAT because nothing is pulled over CDP from the backend. Decouples capture from network topology.
   → tracked work, suits `bmad-create-story` / `bmad-correct-course`.
2. **(Short-term) Scripted DB-row transfer local→UAT.** Only viable if both environments share
   `USER_SECRETS_ENCRYPTION_KEY` and the export re-maps `user_id`/`project_id` to the UAT UUIDs.
   No tooling exists; would need a small export/import script. Fragile; document the caveats.
3. **(Last resort) Reverse CDP tunnel laptop → UAT backend.** Set the editable CDP-URL field to the
   tunneled endpoint. Almost certainly blocked by air-gapped UAT policy; validate the network path first.

**Thread A — fix the hang:** change Sarah's generation to `await llm_client.ainvoke(...)` (or wrap the
sync `invoke` in `asyncio.to_thread`) at `script_generator.py:413/494/575`, per project-context.md:172.
This is the same class of fix already flagged in memory `uat-model-selection-grc-and-freeze-rootcause`.

### Diagnostic

- Confirm Thread A: DevTools → Network during script-gen; the `/sessions` request should sit *pending*.
- Confirm Thread B option 2 feasibility: compare `USER_SECRETS_ENCRYPTION_KEY` across `.env` files.

## Reproduction Plan

- **Thread A:** Open a project, run Sarah to generate ≥1 script on a slow on-prem model; while
  "Generating script N…" shows, open "Test-login sessions" → it stays on "Loading sessions…" until
  generation yields.
- **Thread B:** On UAT, open Test-login sessions for an SSO project; launch Chrome on the laptop with
  `--remote-debugging-port=9222`, log into the SSO app, click Capture → the backend cannot reach
  `localhost:9222` (the container's own localhost) → capture fails / no session.

## Side Findings

- `except json.JSONDecodeError, ValueError:` (`service.py:45,158`) and `except OSError, IndexError:`
  (`password_login.py:299`) look like Python-2 syntax but are **valid Python 3.14** (PEP 758,
  unparenthesized `except`) — verified via `ast.parse`: parsed as a tuple, `handler.name = None`, so
  both exception types are caught. Not a bug. (Confirmed.)
- PASSWORD-project auto-capture launches Chrome **on the backend host** (`password_login.py:340-422`),
  so it has the same topology constraint on UAT as SSO capture — it would need a browser binary the
  UAT container can launch and a route to the target app. (Confirmed.)
