# Investigation: Cross-thread conversation bleed + stray Alice messages on reload

## Hand-off Brief

1. **What happened.** Switching between conversations in two different projects shows the previous
   conversation's chat in the new one, and switching back surfaces stray raw-text "Finished model
   assignment reasoning." / "Connected successfully to On-Premises…" bubbles.
2. **Where the case stands.** Both root causes Confirmed by code read — neither is a backend data bug.
   Bug 1 = client never clears `messages`/`aliceState` on thread switch (display bleed). Bug 2 = the
   thread-load path drops each message's `metadata`, so the chat filter can no longer hide the
   UI-carrier (thinking_trace / model_assignments) messages.
3. **What's needed next.** Frontend-only fix in two files (`usePipelineState.ts`, `App.tsx`). The "extra"
   messages are not deleted from the DB — they are correctly stored carriers that must stay hidden;
   restore their metadata on load so the existing filter suppresses them again.

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A                                                                        |
| Date opened      | 2026-06-18                                                                 |
| Status           | Active                                                                     |
| System           | Local dev (Win11), React 19 frontend, FastAPI backend; user [EMAIL_ADDRESS], 2 projects (PT, PTP) |
| Evidence sources | Frontend source code, two user screenshots, alice.py message emitters      |

## Problem Statement

User (logged in as [EMAIL_ADDRESS], 2 projects) was chatting in **conversation #2 of project PTP**,
had **not** pressed OK on Alice's config, then switched to **conversation #1 of project PT**.

- **Bug 1:** Conversation #1 displayed the entire chat from conversation #2, even though they are
  different threads in different projects.
- **Bug 2:** Switching back to conversation #2, extra/redundant ("thừa") messages appeared:
  `Finished model assignment reasoning.` and `Connected successfully to On-Premises. ## AI Provider
  Configuration Review **Provider Endpoint:** https://[IP_ADDRESS] ###…`. User wants these removed.

## Evidence Inventory

| Source   | Status     | Notes     |
| -------- | ---------- | --------- |
| `frontend/src/hooks/usePipelineState.ts` | Available | Load/save effects + thread vs project load branches |
| `frontend/src/hooks/useWebSocket.ts` | Available | Clears `messageQueue` on thread/project change (l.91-96); filters cross-thread msgs |
| `frontend/src/App.tsx` | Available | Thread-switch reset effect, message-list filter, Alice state handling |
| `src/ai_qa/agents/alice.py` | Available | Emits the two "extra" messages with `thinking_trace` / `model_assignments` metadata |
| User screenshots (PTP conv2, PT conv1) | Available | Confirm rich panel bleeds into other project; raw-text bubbles on reload |
| Live runtime / network trace | Missing | Not captured; not required — root causes confirmed statically |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Clear `messages` + `aliceState` on `threadId` change | High | Done | Confirmed not cleared today |
| 2 | Preserve `metadata` in thread-load branch | High | Done | Confirmed dropped today |
| 3 | history-sync effect keyed on project id not thread id | Medium | Open | Latent same-project two-thread bug (not this scenario) |
| 4 | Possible DB corruption (T2 messages saved into T1) | Low | Refuted | `isLoaded` guard neutralizes the save race |

## Timeline of Events

| Time | Event | Source | Confidence |
| ---- | ----- | ------ | ---------- |
| t0 | In PTP conv #2: Alice emits provider config → thinking_trace ("Finished…") + model_assignments ("Connected successfully…") messages, rendered as rich panels | alice.py:1114,1205,1590 + App.tsx:1640,1675,1677 | Confirmed |
| t1 | User switches to PT conv #1 (threadId changes) | user report | Confirmed |
| t2 | `usePipelineState` load effect sets `isLoaded=false`, fetches `/threads/T1`, but does NOT clear `state.messages`; App's thread-switch effect does NOT reset `aliceState` | usePipelineState.ts:202-272, App.tsx:655-664 | Confirmed |
| t3 | PT conv #1 renders PTP conv #2's messages + the persisted ModelAssignmentReview panel (Bug 1) | App.tsx:1640,1653 | Deduced |
| t4 | User switches back to PTP conv #2; `/threads/T2` reload returns messages with `metadata` stripped → filter can't hide carriers → raw-text bubbles (Bug 2) | usePipelineState.ts:59-66 vs App.tsx:1673-1677 | Confirmed |

## Confirmed Findings

### Finding 1: Thread-load branch drops message `metadata` (and forces `messageType:"text"`)

**Evidence:** `frontend/src/hooks/usePipelineState.ts:59-66` (thread branch) vs `:96-105` (project branch).

**Detail:** When loading a conversation by `threadId`, each message is mapped to
`{id, sender, agentName, content, timestamp, messageType:"text"}` — **no `metadata`** field. The
project-conversation branch, by contrast, maps `metadata: m.metadata`. The code even flags this:
"frontend-specific metadata might be lost if not stored in the new Message model" (`:57`).

### Finding 2: The chat message-list filter hides UI-carrier messages by `metadata.type`

**Evidence:** `frontend/src/App.tsx:1673-1677`.

**Detail:** The render filter skips `metadata.type === "provider_options"` (l.1673),
`metadata.type === "thinking_trace"` (l.1675), and `metadata.model_assignments` (l.1677). These
messages are instead rendered via the `ThinkingBubble` / `ModelAssignmentReview` components. With
metadata stripped (Finding 1), `msg.metadata?.type` is `undefined`, so the filter returns `true`
and the message renders as a raw text bubble.

### Finding 3: The two "extra" messages are exactly the carriers the filter normally hides

**Evidence:** `src/ai_qa/agents/alice.py:1114, 1185, 1205` ("Finished model assignment reasoning."
emitted with `metadata={"type":"thinking_trace", …}`); `alice.py:1589-1616` builds the
"Connected successfully to {provider}. ## AI Provider Configuration Review …" string, sent with
`model_assignments` in metadata (consumed at `App.tsx:770-786`).

**Detail:** "Finished model assignment reasoning." → `thinking_trace` carrier (hidden by l.1675).
"Connected successfully…/Configuration Review" → `model_assignments` carrier (hidden by l.1677).
Both lose their metadata on thread reload and leak through as the "thừa" bubbles the user saw.

### Finding 4: On thread switch, neither `messages` nor `aliceState` is cleared

**Evidence:** `usePipelineState.ts:202-272` (load effect sets `setIsLoaded(false)` but never resets
`state.messages` before the async fetch); `App.tsx:655-664` (thread-switch effect resets
`hasSentStartRef`, `marySelectedId`, scroll refs — but NOT `aliceState`); `resetAliceConfiguration`
is only called on *new* conversation (`App.tsx:582`) and WS auth failure (`:985`), never on plain
thread switch.

**Detail:** The `ModelAssignmentReview` panel renders whenever `aliceState.modelAssignments` is set
(`App.tsx:1640`). Switching threads leaves that state populated, so the previous thread's rich panel
persists. Combined with stale `messages` during the async load, the new conversation shows the old
one's content (Bug 1). Screenshot 2 confirms PT conv #1 showing PTP conv #2's model-assignment panel.

## Deduced Conclusions

### Deduction 1: Bug 1 is a client-side display bleed, not backend data leakage

**Based on:** Findings 4; `useWebSocket.ts:91-96` (queue cleared on thread change) and `:143-156`
(incoming messages filtered by project/thread id).

**Reasoning:** The WebSocket layer already isolates messages per thread/project, and the thread-load
endpoint is correctly scoped (`/threads/{threadId}`). The only reason conv #1 shows conv #2's content
is that the client retains the prior thread's `messages` (until overwritten by the async load) and
never resets `aliceState` (which drives the rich panels independently of `messages`).

**Conclusion:** Fix is to clear `messages` and reset `aliceState` synchronously on `threadId` change.

## Hypothesized Paths

### Hypothesis 1: The save effect persists conv #2's messages into conv #1 (DB corruption)

**Status:** Refuted

**Theory:** When `threadId` flips T2→T1, the debounced save effect (`usePipelineState.ts:275-283`)
could fire with the new `threadId` but the old `state.messages`, writing T2's chat into T1.

**Supporting indicators:** The save effect depends on `[state, isLoaded, projectId, threadId]`; on the
switch render, `state` still holds T2's messages.

**Would confirm:** A network POST to `/threads/T1/conversation` carrying T2's message contents.

**Would refute:** The `isLoaded` guard cancelling the debounced save before its 500ms timer fires.

**Resolution:** Refuted by control-flow analysis. The load effect runs `setIsLoaded(false)` on the
switch; that state update triggers a re-render in which the save effect's cleanup clears the pending
500ms timer and its body early-returns on `!isLoaded` (`:276`). The re-render occurs well within the
500ms debounce, so the stale save never reaches the network. Bug 1 is therefore display-only.

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| Network trace of `/threads/*/conversation` GET/POST during the switch | Would empirically confirm Bug 1 is display-only and the carriers persist correctly | DevTools Network tab while reproducing |
| Whether `/threads/{id}/conversation` POST persists `metadata` server-side | Determines if fix can rely on reading metadata back, or must reconstruct it | Inspect thread conversation save/load endpoint + Message model |

## Source Code Trace

| Element | Detail |
| ------- | ------ |
| Error origin (Bug 2) | `frontend/src/hooks/usePipelineState.ts:59-66` — thread-load mapping omits `metadata` |
| Error origin (Bug 1) | `frontend/src/App.tsx:655-664` (no `aliceState`/messages reset) + `usePipelineState.ts:202-211` (no messages clear on load) |
| Trigger | User switches active conversation (`setThreadId`) between two threads, esp. across projects |
| Condition | Prior thread had Alice `thinking_trace` / `model_assignments` messages; reload strips their metadata |
| Related files | `frontend/src/App.tsx:1640-1707` (filter + rich panels), `frontend/src/hooks/useWebSocket.ts:91-96`, `src/ai_qa/agents/alice.py:1114-1208,1589-1616` |

## Conclusion

**Confidence:** High

Two distinct frontend root causes, both Confirmed by code:

1. **Bug 1 (cross-thread display bleed):** On `threadId` change the client neither clears the prior
   thread's `messages` (`usePipelineState.ts` load effect) nor resets `aliceState`
   (`App.tsx` thread-switch effect). The previous conversation's chat and rich Alice panel therefore
   render in the newly opened conversation. No backend leakage; the save-corruption path is Refuted.

2. **Bug 2 (stray "extra" messages):** The thread-load branch (`usePipelineState.ts:59-66`) drops each
   message's `metadata`, so the chat render filter (`App.tsx:1673-1677`) can no longer recognize and
   hide the `thinking_trace` ("Finished model assignment reasoning.") and `model_assignments`
   ("Connected successfully…/Configuration Review") UI-carrier messages — they leak through as
   raw-text bubbles. They are not duplicate DB rows; they are correctly stored carriers that should
   stay hidden.

## Recommended Next Steps

### Fix direction

Frontend-only, two files. Categorized by mechanism:

- **Metadata preservation (fixes Bug 2 — the user's "delete extra messages" ask):** In
  `usePipelineState.ts` thread branch (`:59-66`), carry `metadata: m.metadata` (and derive
  `messageType` from the stored value instead of hardcoding `"text"`), mirroring the project branch
  (`:96-105`). This re-arms the existing `App.tsx:1673-1677` filter so the carriers are hidden again.
  Requires confirming the thread conversation endpoint persists `metadata` (see Missing Evidence);
  if it does not, the backend Message model / save path must store it, or the filter must fall back
  to content/`messageType` heuristics.
- **State reset on thread switch (fixes Bug 1):** (a) In `usePipelineState.ts` load effect, clear
  `state.messages` (reset toward `initialState`) at the start of a load when `threadId`/`projectId`
  changes, so stale messages don't render during the async fetch. (b) In `App.tsx:655-664`
  thread-switch effect, also call `resetAliceConfiguration()` (and clear any other agent panel state)
  so the prior thread's `ModelAssignmentReview`/`ThinkingBubble` panels don't persist.
- **Latent (Backlog #3):** Re-key the history-sync effect (`App.tsx:951-969`) on `threadId` rather
  than `selectedProject?.id` so switching between two threads in the *same* project also re-syncs.

### Diagnostic

- Reproduce with DevTools Network open; confirm the `/threads/{id}/conversation` GET response for the
  reloaded thread either includes or omits `metadata` on its messages — this decides whether the
  Bug 2 fix is purely client-side.

## Reproduction Plan

1. Log in with an account having ≥2 projects, each with a conversation thread.
2. In project PTP conv #2, run Alice through provider config until the model-assignment review panel
   shows (do **not** press OK).
3. Click project PT conv #1 → observe conv #2's chat + model-assignment panel rendered (Bug 1).
4. Click back to PTP conv #2 → observe raw-text "Finished model assignment reasoning." and
   "Connected successfully to On-Premises… Configuration Review" bubbles (Bug 2).

## Side Findings

- `App.tsx:951-969` history-sync effect is guarded by `syncedProjectIdRef` keyed on project id; two
  threads in the same project would not re-sync on switch (latent bug, Backlog #3). Confirmed by code.
- `useWebSocket.ts` already clears `messageQueue` and filters incoming messages by project/thread id
  (`:91-96`, `:143-156`) — the WS layer is correctly isolated; the bleed is purely in the persisted
  pipeline state and Alice panel state. Confirmed.

## Follow-up: 2026-06-18

### New Evidence — backend persists AND returns metadata (Bug 2 is purely frontend)

- `src/ai_qa/threads/models.py:58` — `Message.message_metadata: Mapped[dict | None]` JSON column exists.
- `src/ai_qa/api/threads.py:238` — save endpoint writes `message_metadata=msg.metadata`.
- `src/ai_qa/api/threads.py:185-196` — `GET /threads/{id}/conversation` returns `metadata=m.message_metadata`.
- `src/ai_qa/api/threads.py:108-117` + `src/ai_qa/threads/schemas.py:50-61` — the load actually used by the
  client is `GET /threads/{id}` → `ThreadDetailsResponse.messages: list[MessageResponse]`, and
  `MessageResponse` (schemas.py:38-56) carries `sender`, `agent_name`, `content`, `message_type`,
  `message_metadata`, `created_at`.

**Confirmed:** the backend already provides every field the rich rendering needs. The frontend
thread-load branch (`usePipelineState.ts:59-66`) reads the **wrong keys** — `m.role` (does not exist;
field is `m.sender`), hardcodes `messageType:"text"` (ignores `m.message_type`), and **omits
`m.message_metadata`**. So persisted user messages reload mislabeled as "agent", and the
metadata-driven filter can't hide UI-carrier messages. No backend change required.

### Updated Hypotheses

- Hypothesis 1 (DB corruption) remains **Refuted**.
- New side effect confirmed: `m.role === "user"` is always false ⇒ persisted user messages reload as
  "agent". Latent correctness bug fixed by the same mapping correction.

### Backlog Changes

- #2 marked Done (metadata available end-to-end; only client mapping wrong).
- #3 (history-restore keyed on project id, not thread) promoted to High — needed so two threads in the
  *same* project also re-restore on switch. Re-key restoration to a per-load thread signal to avoid
  the stale-`isLoaded` read race.

### Updated Conclusion

Root cause set is final and **100% frontend**, two files:

- `frontend/src/hooks/usePipelineState.ts`: correct the thread-load field mapping (read `m.sender`,
  `m.agent_name`, `m.message_type`, `m.message_metadata`); clear `messages` at load start; expose a
  `loadedThreadId` signal that flips only when the matching thread's messages are in state.
- `frontend/src/App.tsx`: on `threadId` change, reset `aliceState`/`bobState`/`maryState`/`sarahState`
  and clear `processedMsgIds`; drive the history-restore effect off `loadedThreadId` (per-thread)
  instead of `selectedProject?.id`.

Proceeding to implement via `bmad-quick-dev` (bug fix, no documentation update per user).

## Follow-up #2: 2026-06-18 — submitted-input state not rebuilt on restore

### New Evidence

After the first fix shipped, switching away from and back to a Bob-step conversation showed: the
chosen provider ("On-Premises") reverted to the selectable list, and the MCP-key prompt rendered an
editable input again instead of greyed-out; duplicate MCP inputs / "Start requirements extraction"
bubbles also appeared.

- `frontend/src/App.tsx` — `aliceState.submittedSelection` is set ONLY in the live click handler
  `handleProviderSelect` (~l.1204) and `bobState.submittedMcp` only in `handleBobStart` (~l.1240).
  Neither is persisted nor rebuilt during the history-restore replay.
- The first fix correctly **resets** these on thread switch (isolation), so on return they were lost
  and the UI re-prompted. `ProviderSelector` shows the list when `submittedSelection` is null
  (`App.tsx:1639-1654`); the MCP input is editable when `submittedMcp` is false (`App.tsx` Bob render).
- Duplication root: because `submittedMcp` wasn't restored, the user could click Start again on each
  return → multiple persisted `bob_start` markers accumulated → one MCP input + bubble per marker.

### Updated Conclusion

Same root theme as Bug 1/2: ephemeral per-conversation UI state must be **reconstructed from the
persisted history** on restore, not just reset. Fix (frontend-only):

- `handleProviderSelect` persists a **secret-free** `provider_selection` marker (providerId +
  providerName, NO credentials).
- `handleAliceMessage` rebuilds `submittedSelection` from that marker on replay (in timeline order, so
  a later `provider_options` re-prompt still clears it); `handleBobMessage` rebuilds `submittedMcp`
  from the existing `bob_start` marker.
- The chat filter hides the `provider_selection` marker and collapses duplicate `bob_start` markers to
  the first, so the MCP input / start bubble render exactly once.

Verified: typecheck clean, 276 frontend tests pass (new App test asserts the marker is recorded
without credentials), build succeeds. Restoring `submittedMcp` also prevents new duplicate `bob_start`
markers going forward.
