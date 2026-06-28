# Investigation: Bob parent-page URL — user message disappears after submit

## Hand-off Brief

1. **What happened.** When Bob asks for a parent-page URL (the `confirm_parent` step, between two "Bob's thought" bubbles), the user types a Confluence URL and submits, but their message never appears in the chat — **Confirmed** root cause: the submit handler `handleBobApproveParent` is the only Bob input handler that never calls `addUserMessage`.
2. **Where the case stands.** Concluded. Root cause Confirmed at `frontend/src/App.tsx:1532-1545`; the fix is a one-line addition mirroring the four sibling handlers.
3. **What's needed next.** Add `addUserMessage(trimmed)` (and a "Skip" echo for the blank case) inside `handleBobApproveParent`, then `npm run typecheck`. Trivial fix → `bmad-quick-dev`.

## Case Info

| Field            | Value                                                                      |
| ---------------- | -------------------------------------------------------------------------- |
| Ticket           | N/A                                                                        |
| Date opened      | 2026-06-22                                                                 |
| Status           | Concluded                                                                  |
| System           | Win11; React 19.2 frontend (`frontend/`); FastAPI backend                  |
| Evidence sources | Frontend source (`App.tsx`, `usePipelineState.ts`, `useWebSocket.ts`), user screenshot |

## Problem Statement

> Ở giữa 2 "Bob's thought" mình có nhập đường dẫn Confluence URL, vừa submit (nhấn Start hoặc Enter) xong thì message của mình biến mất. Expect: message của user cần giữ lại trên UI cái link Confluence.

(Between two "Bob's thought" bubbles the user enters a Confluence URL; right after submitting (Start / Enter) the user's message disappears. Expected: the user's message with the Confluence link stays on the UI.)

Screenshot timeline: Bob's thought 20:52:01 "Read Confluence page via MCP: **request_review**" → Bob's thought 20:53:21 "**Fetching children of** 'https://confluence.svc.corp.ch/spaces/CORPHRSOL/pages/777945456/General+knowledge' via MCP: processing" → Bob 20:53:22 "Extracting page '…General+knowledge'…". No "You" bubble for the URL the user typed in between.

## Evidence Inventory

| Source                                   | Status    | Notes                                                                                  |
| ---------------------------------------- | --------- | -------------------------------------------------------------------------------------- |
| `frontend/src/App.tsx`                   | Available | All five Bob submit handlers + the chat render/filter live here                        |
| `frontend/src/hooks/usePipelineState.ts` | Available | `addUserMessage` (the only client-side path that creates a user bubble) + persistence  |
| `frontend/src/hooks/useWebSocket.ts`     | Available | WS receive gate; no backend echo of user input as a chat message                       |
| User screenshot                          | Available | Confirms `confirm_parent` ("Fetching children of '<URL>'") flow, not `select_id`       |
| Backend Bob agent                        | Missing   | Not needed — bug is purely client-side message creation                                |

## Timeline of Events

| Time     | Event                                                                              | Source           | Confidence |
| -------- | ---------------------------------------------------------------------------------- | ---------------- | ---------- |
| 20:52:01 | Bob reads default Confluence page, enters `review_request` → `confirm_parent` panel | Screenshot       | Confirmed  |
| ~20:53   | User types parent-page URL into the panel, presses OK/Enter                         | Screenshot + UX  | Deduced    |
| 20:53:21 | Bob "Fetching children of '<URL>'" — `confirmed_page_name` was received             | Screenshot       | Confirmed  |
| 20:53:21 | `status` leaves `review_request`; `confirm_parent` panel unmounts; no user bubble exists | Code (deduced) | Deduced    |

## Confirmed Findings

### Finding 1: `handleBobApproveParent` never creates a user message

**Evidence:** `frontend/src/App.tsx:1532-1545`

```ts
const handleBobApproveParent = useCallback(
  (suggestedPage: string) => {
    if (!selectedProjectId) return;
    const trimmed = suggestedPage.trim();
    sendMessage({
      type: "approve",
      step: 2,
      data: trimmed ? { confirmed_page_name: trimmed } : { action: "skip" },
    });
  },
  [selectedProjectId, sendMessage],   // <- addUserMessage not even a dependency
);
```

**Detail:** This is the handler bound to the parent-page input's OK button (`App.tsx:2362-2364`) and its Enter key (`App.tsx:2352-2357`). It only calls `sendMessage`. It contains no `addUserMessage(...)` call, and `addUserMessage` is absent from its dependency array.

### Finding 2: Every other Bob submit handler DOES echo the user message

**Evidence:**

- `handleBobStart` → `addUserMessage("Start requirements extraction", "info", { type: "bob_start" })` (`App.tsx:1494`)
- `handleBobSelectId` → `addUserMessage(trimmed)` (`App.tsx:1555`)
- `handleBobClarifyAnswer` → `addUserMessage(action === "skip_file" ? "Skip this file" : trimmed)` (`App.tsx:1575`)
- `handleApprove` → `addUserMessage("✓ OK", "success")` (`App.tsx:1520`)

**Detail:** `handleBobApproveParent` is the lone exception. The inconsistency is the bug.

### Finding 3: A user bubble can only originate client-side via `addUserMessage`

**Evidence:** `frontend/src/hooks/usePipelineState.ts:345-365` (`addUserMessage` pushes a `sender:"user"` entry into `state.messages`); `frontend/src/hooks/useWebSocket.ts:158-171` (the WS receive gate only ingests `data.sender` messages from the server — Bob's own thoughts/processing — there is no server echo of the user's typed input).

**Detail:** Because the backend never echoes the submitted URL back as a `sender:"user"` message, the optimistic `addUserMessage` call is the *only* way the URL becomes a chat bubble. With that call missing, no bubble is ever created.

## Deduced Conclusions

### Deduction 1: The "message disappears" is the input panel unmounting, with nothing left behind

**Based on:** Findings 1 & 3 + the render guard `isBobStep && status === "review_request" && bobState.isConfirmParent` (`App.tsx:2316-2318`).

**Reasoning:** While in `review_request` the `confirm_parent` panel shows the URL the user typed (bound to `bobState.suggestedPage`, `App.tsx:2345`). On submit, Bob transitions to `processing` (screenshot 20:53:21), so the panel's render condition becomes false and the panel unmounts. Since no `sender:"user"` message was ever added to `state.messages`, there is no surviving bubble — the typed URL vanishes with the panel.

**Conclusion:** Perceived "disappearance" = panel teardown + absent optimistic echo. Matches the user's report exactly.

## Hypothesized Paths

### Hypothesis 1: The URL message is created but filtered out by the chat render filter

**Status:** Refuted

**Theory:** A user message is added but the `is_confirm_parent` skip rule (`App.tsx:2102-2109`) hides it.

**Supporting indicators:** There is a filter rule that drops `metadata.is_confirm_parent` messages and any content containing "contains all requirements, is it correct?".

**Would confirm:** An `addUserMessage` call in the confirm_parent submit path.

**Would refute:** No such call.

**Resolution:** Refuted — `handleBobApproveParent` makes no `addUserMessage` call at all (Finding 1), so there is nothing for the filter to drop. (Corollary for the fix: a plain user bubble carrying the raw URL has no `is_confirm_parent` metadata and does not contain that phrase, so it would pass the filter cleanly.)

## Missing Evidence

| Gap                                  | Impact                                                | How to Obtain                          |
| ------------------------------------ | ----------------------------------------------------- | -------------------------------------- |
| None blocking — root cause Confirmed | n/a                                                   | n/a                                    |

## Source Code Trace

| Element       | Detail                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------- |
| Error origin  | `frontend/src/App.tsx:1532-1545` — `handleBobApproveParent` (missing `addUserMessage`)              |
| Trigger       | User submits the parent-page URL via OK button (`App.tsx:2362`) or Enter (`App.tsx:2352`)           |
| Condition     | Bob is in `review_request` with `bobState.isConfirmParent === true`; submit moves status off `review_request`, unmounting the panel (`App.tsx:2316-2373`) |
| Related files | `frontend/src/hooks/usePipelineState.ts` (`addUserMessage`), `frontend/src/hooks/useWebSocket.ts` (receive gate, no user echo) |

## Conclusion

**Confidence:** High

Confirmed root cause: `handleBobApproveParent` (`frontend/src/App.tsx:1532-1545`) submits the parent-page URL without calling `addUserMessage`, while all four sibling Bob handlers do. Because the user bubble can only be created client-side (no backend echo — Finding 3) and the `confirm_parent` input panel unmounts as soon as Bob leaves `review_request`, the typed Confluence URL is never preserved on screen. Deterministic and reproducible.

## Recommended Next Steps

### Fix direction

In `handleBobApproveParent`, echo the user's action before/alongside `sendMessage`, mirroring `handleBobClarifyAnswer`:

```ts
const handleBobApproveParent = useCallback(
  (suggestedPage: string) => {
    if (!selectedProjectId) return;
    const trimmed = suggestedPage.trim();
    addUserMessage(trimmed ? trimmed : "Skip");   // <- preserve the link (or note the skip)
    sendMessage({
      type: "approve",
      step: 2,
      data: trimmed ? { confirmed_page_name: trimmed } : { action: "skip" },
    });
  },
  [selectedProjectId, sendMessage, addUserMessage],   // <- add addUserMessage
);
```

Notes:
- Echoing the raw URL is safe vs. the render filter (Hypothesis 1 resolution): a plain user bubble has no `is_confirm_parent` metadata and won't match the phrase rule, so it renders.
- Decide whether the blank/skip case should show a "Skip" bubble (consistent with `handleBobClarifyAnswer`'s "Skip this file") or nothing. Recommend "Skip" for symmetry; trivial either way.

### Diagnostic

Confirm in the running app: enter Bob, provide MCP key, reach the "I found the link below…" parent-page prompt, type a Confluence URL, press OK → a blue "You" bubble with the URL should now persist above Bob's "Fetching children…" trace and survive a page reload (it is persisted via the debounced `saveConversationToAPI`, `usePipelineState.ts:304-312`).

## Reproduction Plan

1. Start a Bob run on a project with a `confluence_base_url`.
2. Submit the MCP key (Start). Bob reads the default page and shows the parent-page confirmation panel ("I found the link below…").
3. Type any Confluence page URL into the input, press OK or Enter.
4. **Observed:** the URL disappears; chat jumps straight to Bob's "Fetching children of '<URL>'…".
5. **Expected (post-fix):** a "You" bubble with the URL remains in the chat, in chronological order between the two Bob thoughts.

## Side Findings

- The `confirm_parent` input pre-fills `bobState.suggestedPage` from Bob's suggestion or, when blank/"Requirements", the project's `confluence_base_url` (`App.tsx:963-979`). So the field is often non-empty before the user edits it — but with no echo, even the auto-filled value is lost on submit. The same fix covers this.
