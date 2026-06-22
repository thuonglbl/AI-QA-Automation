---
title: 'Fix cross-thread/cross-project conversation bleed + stray Alice messages on reload'
type: 'bugfix'
created: '2026-06-18'
status: 'done'
baseline_commit: '84c454a5aa52ac1eb44ed0bd1f936cde9274b916'
context: ['{project-root}/_bmad-output/implementation-artifacts/investigations/cross-thread-conversation-bleed-investigation.md']
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Switching between conversations across two projects shows the previous conversation's
chat and Alice config panel in the newly-opened one (Bug 1); switching back surfaces stray raw-text
"Finished model assignment reasoning." / "Connected successfully to On-Premises… Configuration Review"
bubbles that should stay hidden (Bug 2). Conversations must be fully isolated, especially across
different projects.

**Approach:** Frontend-only. (1) Correct the thread-load message mapping so it reads the real backend
fields including `message_metadata` — the chat filter already hides metadata-tagged carrier messages,
so restoring metadata removes the stray bubbles. (2) On thread switch, clear stale messages and reset
every agent panel state + the processed-id dedup set so no prior conversation bleeds in, and re-key
the history-restore effect to a per-thread "loaded" signal so each thread restores exactly once.

## Boundaries & Constraints

**Always:** Keep changes frontend-only. Preserve existing behavior for the project-conversation
(non-thread) branch and for live WebSocket message handling. Conversations isolated per thread; fully
isolated across projects. Code must pass `npm run typecheck` and `npm run build`.

**Ask First:** Any change to backend models, endpoints, schemas, or DB (none expected). Any change to
the WebSocket layer (`useWebSocket.ts`).

**Never:** No backend/Alembic changes (backend already persists & returns `message_metadata`). No
documentation updates (this is a bug fix). Do not delete message rows from the database — the carrier
messages are correctly stored and must remain, only hidden in the UI.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Load thread w/ carrier msgs | `GET /threads/{id}` returns messages with `message_metadata.type` = `thinking_trace` / `model_assignments` | Carriers mapped WITH metadata → hidden by existing filter; rich panel restored | N/A |
| Load thread w/ user msg | message has `sender: "user"` | Mapped as `sender: "user"` (not "agent") | N/A |
| Switch project A→B | active thread changes to another project's thread | New conversation shows ONLY its own messages + panels; prior Alice/Bob/Mary/Sarah panels cleared | N/A |
| Switch back A→B→A | return to a thread already visited this session | Thread A's panels re-restore from its history (dedup set cleared so replay isn't skipped) | N/A |
| Message missing metadata | `message_metadata` null | `metadata: undefined`; renders as normal text bubble | N/A |

</frozen-after-approval>

## Code Map

- `frontend/src/hooks/usePipelineState.ts` -- thread-load branch reads wrong keys (`m.role`, hardcoded
  `"text"`, no metadata) at l.59-66; load effect (l.202-272) never clears stale messages; no per-thread
  loaded signal. Primary fix site.
- `frontend/src/App.tsx` -- thread-switch reset effect (l.655-664) omits agent-panel + `processedMsgIds`
  resets; history-restore effect (l.951-969) keyed on `selectedProject?.id` via `syncedProjectIdRef`.
- `frontend/src/hooks/usePipelineState.test.tsx` -- existing tests for the hook; update for new mapping
  + `loadedThreadId`.
- `src/ai_qa/threads/schemas.py:38-61` -- `MessageResponse` (read-only ref): `sender`, `agent_name`,
  `content`, `message_type`, `message_metadata`, `created_at`. No change.
- `frontend/src/App.tsx:1659-1677` -- the metadata-driven render filter that hides carriers (read-only
  ref; the fix re-arms it).

## Tasks & Acceptance

**Execution:**
- [x] `frontend/src/hooks/usePipelineState.ts` -- In the `if (threadId)` branch of
  `loadConversationFromAPI`, map each message from real `MessageResponse` fields:
  `sender` = `m.sender` normalized to `"user"|"system"|"agent"`; `agentName` = non-user ?
  `m.agent_name ?? currentAgent` : undefined; `content` = `m.content`; `timestamp` =
  `m.created_at || new Date().toISOString()`; `messageType` = `m.message_type || "text"`;
  `metadata` = `m.message_metadata ?? undefined`. -- restores metadata so carriers stay hidden + fixes
  user-message mislabeling.
- [x] `frontend/src/hooks/usePipelineState.ts` -- In the load effect, clear `state.messages` (and reset
  `loadedThreadId` to null) at the start of every load before the await; add `loadedThreadId` state set
  to the loaded `threadId` in every completion path (after messages are placed in state, incl. the
  no-project/no-thread and `denied`/null paths → null); add `loadedThreadId` to
  `PipelineStateSelectors` and the returned object. -- gives App a stale-free per-thread load signal.
- [x] `frontend/src/App.tsx` -- In the thread-switch effect (deps `[threadId]`), additionally call
  `resetAliceConfiguration()`, reset `bobState`/`maryState`/`sarahState` to their initial-state objects,
  and `processedMsgIds.current.clear()`. -- prevents prior conversation's panels/dedup from bleeding in.
- [x] `frontend/src/App.tsx` -- Replace `syncedProjectIdRef` with `syncedThreadIdRef`; consume
  `loadedThreadId` from `usePipelineState`; gate the history-restore effect as: return if
  `loadedThreadId === null`, return if `syncedThreadIdRef.current === loadedThreadId`, else set the ref
  and replay messages into the four `handle*Message` handlers (keep the `processedMsgIds` skip). Deps:
  `[loadedThreadId, messages, handleAliceMessage, handleBobMessage, handleMaryMessage, handleSarahMessage]`.
  -- restores panels exactly once per loaded thread, same-project switches included, no stale read.
- [x] `frontend/src/hooks/usePipelineState.test.tsx` -- Update/extend tests: thread-load now carries
  metadata + correct sender/type; `loadedThreadId` exposed and reflects the loaded thread.

**Acceptance Criteria:**
- Given a thread whose history includes Alice `thinking_trace` and `model_assignments` carrier messages,
  when the thread is loaded, then those messages do NOT appear as raw text bubbles and the rich Alice
  panel is shown.
- Given an active conversation in project A, when the user switches to a conversation in project B
  without approving, then project B's view shows only its own messages and no Alice/Bob/Mary/Sarah panel
  from A.
- Given the user switches A→B→A within one session, when returning to A, then A's panels re-render from
  its persisted history (not blank).
- Given two conversations in the SAME project, when switching between them, then each shows only its own
  history and panels.
- Given a persisted user message, when its thread is reloaded, then it renders on the user side.

## Design Notes

Root of Bug 2: the thread branch read `m.role`/`m.created_at` and dropped metadata; the backend
actually returns `MessageResponse` (`m.sender`, `m.message_metadata`, …). Without metadata the filter at
`App.tsx:1673-1677` can't recognize carriers. Root of Bug 1: neither `messages` nor `aliceState` is
cleared on switch, and the restore effect keyed on project id + a never-cleared `processedMsgIds` make
restoration unreliable. `loadedThreadId` must flip only AFTER the matching thread's messages are in
state — this avoids the stale-`isLoaded` read where the switch render still holds the old thread's
messages with `isLoaded === true`.

## Verification

**Commands:**
- `cd frontend && npm run typecheck` -- expected: no errors
- `cd frontend && npm run build` -- expected: build succeeds
- `cd frontend && npx vitest run src/hooks/usePipelineState.test.tsx` -- expected: pass
- `cd frontend && npx vitest run` -- expected: no new failures vs. baseline (153 passing)

**Manual checks (if no CLI):**
- Reproduce the case-file steps (project A conv ↔ project B conv) and confirm both bugs are gone.

## Suggested Review Order

**Bug 2 — stray "extra" messages (start here)**

- Entry point: thread-load now keeps `message_metadata`, so the chat filter hides carrier messages.
  [`usePipelineState.ts:83`](../../frontend/src/hooks/usePipelineState.ts#L83)

**Bug 1 — conversation isolation on switch**

- Reset every agent panel + the dedup set when the active thread changes.
  [`App.tsx:666`](../../frontend/src/App.tsx#L666)
- Clear stale messages at the start of each load so the prior thread can't linger.
  [`usePipelineState.ts:231`](../../frontend/src/hooks/usePipelineState.ts#L231)

**Race-free per-thread restore**

- New `loadedThreadId` signal flips only after the matching thread's messages are in state.
  [`usePipelineState.ts:292`](../../frontend/src/hooks/usePipelineState.ts#L292)
- History-restore re-keyed to `loadedThreadId` (trailing ref avoids the stale-read race).
  [`App.tsx:979`](../../frontend/src/App.tsx#L979)
- Replayed ids are now marked processed, keeping dedup symmetric with the live queue.
  [`App.tsx:984`](../../frontend/src/App.tsx#L984)

**Supporting**

- New tests: metadata preservation, sender/type mapping, `loadedThreadId` exposure.
  [`usePipelineState.test.tsx:99`](../../frontend/src/hooks/usePipelineState.test.tsx#L99)
