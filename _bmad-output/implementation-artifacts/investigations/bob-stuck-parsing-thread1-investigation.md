# Investigation: Bob stuck on "Parsing 'Progress Talk Period page'…" (thread #1) — worker restart orphaned the run

## Hand-off Brief

1. **What happened.** Bob (Step 2, project "PT Tool", thread #1) froze at "Parsing 'Progress Talk Period page'…" because the `uvicorn --reload` **app worker restarted at 08:28:19 UTC** while that page's LLM conversion was mid-flight on the slow `on-premises` provider — process death killed the in-flight asyncio task. (Confirmed)
2. **Where the case stands.** Root cause Confirmed: the killed task never hit its `except` (process termination ≠ exception), so no error message and no DB status update were emitted, and there is **no startup recovery** for threads left at `status="processing"` — the thread is permanently orphaned and the UI spins forever. The browser's auto-reconnect created a third `agent_run` (08:31:24) that did no work.
3. **What's needed next.** Unblock now by resetting thread #1 out of `processing`; then prevent recurrence (don't run real pipelines under `--reload`, add startup reconciliation of stuck threads, add a client watchdog, and bound each convert LLM call).

## Case Info

| Field            | Value                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                               |
| Date opened      | 2026-06-22                                                                                        |
| Status           | Concluded (root cause Confirmed)                                                                   |
| System           | Windows 11, local dev. Backend `uvicorn ai_qa.api:app --host 0.0.0.0 --port 8000 --reload`. PostgreSQL `ai_qa_automation`. Provider `on-premises` (LiteLLM proxy `ai.svc.corp.ch`). |
| Evidence sources | Live PostgreSQL (threads/messages/agent_runs), OS process table + start times, `netstat`, source code, user screenshot |

## Problem Statement

User (Thuong Lam Ba Le), thread #1: "stuck for 10 minutes". Screenshot shows Bob — Requirements, "Step 2 of 5 · Testing connection…", last line "Parsing 'Progress Talk Period page'…" with no follow-up.

## Evidence Inventory

| Source                       | Status    | Notes                                                                                   |
| ---------------------------- | --------- | --------------------------------------------------------------------------------------- |
| PostgreSQL (live)            | Available | Thread, messages, agent_runs read directly via SQLAlchemy.                               |
| OS process table + uptimes   | Available | Identified worker PID 21728 and its start time (the smoking gun).                        |
| `netstat` outbound sockets   | Available | Worker has NO connection to the on-prem proxy → no in-flight LLM call.                   |
| Source code                  | Available | bob.py, requirement_formatter.py, client.py, websocket.py, routes.py, app.py.            |
| Backend console log          | Missing   | Backend logs to stdout only — no log file. Cannot read the exact reload/crash line.      |

## Timeline of Events (UTC; local = +7 Asia/Saigon)

| Time (UTC)        | Event                                                                                     | Source                          | Confidence |
| ----------------- | ----------------------------------------------------------------------------------------- | ------------------------------- | ---------- |
| 07:22:30          | uvicorn `--reload` supervisor (PID 34928) + reloader started.                              | process start time              | Confirmed  |
| 08:09:30          | Thread #1 created (project "PT Tool", provider `on-premises`).                             | `threads.created_at`            | Confirmed  |
| 08:12:21–08:22:40 | Bob Phase 2 parse/convert loop: ~17 pages converted, per-page **2s–140s** (on-prem LLM).   | `messages`                      | Confirmed  |
| 08:22:40          | "Parsing 'Progress Talk Period page'…" — LAST message; root-page LLM conversion begins.    | `messages` (08:22:40.892782)    | Confirmed  |
| **08:28:19**      | **App worker (PID 21728) restarts** — in-flight asyncio task killed by process death.      | process start time (21728)      | Confirmed  |
| 08:31:24          | `agent_run` #3 created (browser reconnect → "start") — produced NO messages.               | `agent_runs.created_at`         | Confirmed  |
| 08:34–08:39       | Investigation: worker uptime 11.4 min; no on-prem socket; thread still `processing`.       | netstat / process / DB          | Confirmed  |

Per-page conversion durations (gap between each "Parsing X" and "✓ Converted X"): 'DL - PT form page' **140s**, 'Attribution page.' **119s**, 'DLee - PT form page' 69s, 'My Dlees Page' 48s, 'User Guide…' 46s — confirms an LLM-backed step whose latency scales with page size. The root page would be the longest.

## Confirmed Findings

### Finding 1: Thread #1 is frozen at `status="processing"`

`threads` row `4f77a34d-72c9-4119-a5e8-6d582de96bc8`: `current_step=2`, `status='processing'`, `current_agent='Bob'`, `provider='on-premises'`. The last message is "Parsing 'Progress Talk Period page'…" at 08:22:40 UTC; no "✓ Converted" or "⚠ Failed to convert" for that page.

### Finding 2: The app worker restarted at 08:28:19 UTC, mid-extraction

Process tree: launcher `uvicorn.exe` (52304) → reloader (40244) → reload-supervisor (34928, holds the `:8000` listen socket, up 77 min) → **app worker (21728, `multiprocessing-fork`, up 11.4 min, started 08:28:19 UTC)**. A worker restart under uvicorn `--reload` = a reload cycle. The restart fell 5.5 min after Bob's last action and 3 min before run #3.

### Finding 3: No in-flight LLM call — the stuck task is gone, not waiting on the network

`ai.svc.corp.ch` resolves to `10.10.9.50` / `192.168.200.40`. The worker (21728) has outbound connections ONLY to PostgreSQL (`::1:5432` pool) and a local socketpair — **no `:443` to the on-prem proxy**. The one ESTABLISHED socket to `10.10.9.50:443` belongs to `msedge.exe` (the browser), not the backend. So the LLM HTTP request is gone; nothing is computing.

### Finding 4: The convert LLM calls are unbounded and bypass the typed client

`RequirementFormatter._format_story` (`requirement_formatter.py:311`) and `invoke_vision` (`client.py:249`) call `self._llm._chat_model.ainvoke(...)` directly — bypassing `LLMClient.ainvoke`/`_ainvoke_with_retry` and **with no `asyncio.wait_for`**, unlike Bob's clarify loop which wraps `ainvoke` in `asyncio.wait_for(timeout=_CLARIFY_LLM_TIMEOUT)` (`bob.py:1582/1690/1803`). The only bound is the httpx read timeout baked into the chat model (`config.timeout=600s`, `client.py:81`). `convert_markdown` also makes one `invoke_vision` per embedded image, so an image-heavy root page is N sequential unbounded calls.

### Finding 5: WS pipeline state is in-memory and there is no recovery

`websocket.py` keeps `_inflight_action_tasks`, `_agent_action_locks`, `active_connections`, and the registered agent instances (with Bob's `self.pages`) in the **worker process memory**. A "start" is dispatched via `asyncio.create_task` (`websocket.py:191`). The FastAPI `lifespan` (`app.py:48`) only initializes the SeaweedFS bucket — there is no startup reconciliation of threads left at `status="processing"`, and `ThreadService` (`service.py`) has no "reset stuck threads" path.

## Deduced Conclusions

### Deduction 1: The worker restart killed the task without triggering any error handling

**Based on:** Findings 1–3, 5.

**Reasoning:** Bob's convert loop ran on the pre-08:28:19 worker. When that process was replaced, the asyncio task running the `ainvoke` was terminated by process death — not by a Python exception. The `except Exception` handlers at `bob.py:1184` (per-page) and `websocket.py:305` (`_dispatch_action`) only fire on exceptions, so neither ran. Therefore no "⚠ Failed to convert" message, no `agent_run`/`thread` status update.

**Conclusion:** The thread is orphaned at `status="processing"` with no terminal signal. With no startup reconciliation (Finding 5), it stays that way indefinitely and the UI keeps the "Step 2 of 5 · Testing connection…" spinner.

### Deduction 2: agent_run #3 (08:31:24) is the browser auto-reconnect doing nothing useful

**Based on:** `agent_runs` timing + `_build_pipeline_context(create_run=True)` (`routes.py:246/269`) + absence of any message after 08:22:40.

**Reasoning:** After the restart the browser's WebSocket reconnected to the fresh worker and re-sent a "start", which always creates a `status="running"` agent_run. No "Extracting/Parsing" messages followed, so the re-run produced no work (re-entry guard on an already-`processing` thread and/or missing Confluence input on the reconnect). All three agent_runs sit at `running` because this code path never flips them to a terminal status.

## Hypothesized Paths

### Hypothesis 1: The reload was triggered by a watched-file change vs. a worker crash

**Status:** Open (does not change the root cause).

**Theory:** Either a file uvicorn watches changed at ~08:28:19 (driving a normal `--reload` cycle) or the worker crashed and was respawned.

**Supporting indicators:** Supervisor alive + fresh worker ⇒ reload cycle (uvicorn's reloader replaces the subprocess). No tracked `.py`/config file in the repo changed in 08:25–08:31 UTC (find returned empty), which argues against a routine code edit.

**Would confirm:** The backend console output around 08:28:19 ("Detected file change in '…', reloading" vs. a traceback / "process died").

**Would refute:** —

**Resolution:** Unresolved — backend logs to stdout only (no file). Recommend re-running with logs captured to a file. Immaterial to the fix: any worker restart mid-run reproduces the bug.

## Missing Evidence

| Gap                                   | Impact                                                       | How to Obtain                                                            |
| ------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- |
| Backend console log at ~08:28:19 UTC  | Distinguishes file-reload vs. crash (Hypothesis 1)          | Restart backend redirecting stdout/stderr to a file; or add file logging |
| Raw size/image count of the root page | Confirms whether the root page would exceed the 600s budget | Inspect the persisted `raw_html` artifact for "Progress Talk Period page" |

## Source Code Trace

| Element       | Detail                                                                                                          |
| ------------- | ------------------------------------------------------------------------------------------------------------- |
| Error origin  | `agents/bob.py:1118-1199` convert loop; LLM call `pipelines/requirement_formatter.py:311` (`_format_story`).   |
| Trigger       | `uvicorn --reload` worker restart while the loop awaited the root-page LLM conversion on the on-prem provider.  |
| Condition     | In-flight `asyncio` task killed by process death (not an exception) ⇒ no `except`, no status update.            |
| Related files | `api/websocket.py` (in-memory tasks/locks, `create_task` dispatch), `api/routes.py:246/269` (run creation), `ai_connection/client.py:67-139,249` (chat-model timeout, vision), `api/app.py:48` (lifespan; no recovery), `threads/service.py:129` (only status path). |

## Conclusion

**Confidence:** High.

Confirmed root cause: the local backend runs `uvicorn --reload`; its app worker restarted at **08:28:19 UTC** while Bob's Step-2 extraction was converting the large root page "Progress Talk Period page" on the slow `on-premises` provider (conversion started 08:22:40). Process death killed the in-flight asyncio task without raising a Python exception, so no failure message and no DB status update were produced. Because all pipeline state is in-memory and nothing reconciles threads left at `status="processing"` on startup, thread #1 is permanently orphaned and the UI shows an endless spinner. The browser's reconnect created a no-op third agent_run.

Contributing factors: (a) slow on-prem per-page LLM latency (2–140s; the root page is the longest) widened the restart-collision window; (b) `convert_markdown`'s LLM calls are unbounded (no `asyncio.wait_for`) and bypass the typed `LLMClient`; (c) no startup reconciliation of stuck threads; (d) no client-side watchdog to surface a silent backend.

Open (immaterial to the fix): whether the restart was a watched-file reload or a crash — unrecoverable without captured backend logs.

## Recommended Next Steps

### Fix direction

- **Immediate unblock (data):** reset thread #1 out of `processing` so the user can retry (set `threads.status` back to a re-runnable value and mark the three `running` agent_runs as `failed`/`interrupted`). Bob saves each requirement page as it converts (`adapter.save_requirement_page`), so already-converted pages are persisted; a fresh start re-does the rest.
- **Don't run real pipelines under `--reload`** (process-level): run the backend without `--reload` for actual extraction runs, or add `--reload-exclude` for output/artifact dirs so a stray file write can't restart the worker mid-run.
- **Startup reconciliation** (recovery): in the `lifespan` startup (`app.py:48`), mark any thread still at `status="processing"` and any `agent_run` still `running` as `interrupted`/`failed`, so a restart surfaces a clear "run was interrupted — retry" instead of an infinite spinner.
- **Bound each convert LLM call** (defense-in-depth): wrap `_format_story`/`invoke_vision` in `asyncio.wait_for` and route through `LLMClient.ainvoke` for typed `LLMTimeoutError` mapping — matching Bob's clarify loop.
- **Client watchdog** (UX): if no agent message arrives for N seconds while a step is "processing", show "connection lost / run interrupted — retry" rather than spinning forever.

### Diagnostic

- Capture backend stdout/stderr to a file and reproduce to confirm reload-vs-crash (Hypothesis 1).
- Inspect the persisted raw page for "Progress Talk Period page" to gauge size/image count vs. the 600s budget.

## Reproduction Plan

1. Start an `on-premises` Bob extraction over a multi-page Confluence space with at least one large root page.
2. While a page is mid-conversion (a "Parsing X…" with no "✓ Converted X" yet), restart the `uvicorn --reload` worker (touch a watched file or `kill` the worker subprocess).
3. Observe: no "Failed to convert" message; thread stays `status="processing"`; UI spinner never resolves; a reconnect creates a new no-op `agent_run`. Matches the reported symptom.

## Side Findings

- All `agent_run` rows for thread #1 are stuck at `status="running"` (`_build_pipeline_context` creates them but this path never flips them to terminal) — independent of this incident, this makes "running" runs an unreliable signal and should be reconciled too. (Confirmed)
- `config.timeout` (600s) is applied as an httpx read timeout; with a non-streaming on-prem completion this bounds time-to-first-byte, but it is the ONLY bound on the convert calls. (Confirmed via `client.py:81-139`)
