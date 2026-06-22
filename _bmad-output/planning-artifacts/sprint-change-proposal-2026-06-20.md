# Sprint Change Proposal — Message Timestamps (hh:mm:ss) for All Chat Messages

- **Date:** 2026-06-20
- **Author:** Thuong (with Developer agent)
- **Scope classification:** Minor (frontend-only, direct implementation)
- **Status:** Implemented + verified (UNCOMMITTED on `main`)

## Section 1 — Issue Summary

**Trigger:** Every chat message — from any agent (Alice, Bob, Mary, Sarah, Jack) **or** the user — should display an `hh:mm:ss` timestamp next to the sender name, localized to the logged-in user's timezone, where that timezone is read from the `users` table.

**Context:** The feature was already ~95% built across the prior commit `c9eac59` ("add time to message") plus the current uncommitted working tree (`MessageTime.tsx`, `timezone.ts`, `AuthContext` export, and many `App.tsx` render sites). This course-correction was opened to (a) confirm the timezone genuinely flows from the `users` table, and (b) guarantee **complete** coverage across every message bubble.

**Evidence found during analysis:**

- The timezone foundation is complete and correct end-to-end (DB column → API serialization → frontend type → `MessageTime` component).
- The message data layer **guarantees** a `timestamp` on every real message (backend `Message.timestamp` is a required timezone-aware field; the WebSocket client only accepts a payload as a message when `data.timestamp` is present; optimistic user messages stamp their own time; history load preserves the server timestamp).
- **One real bug (G1):** the `ProviderSelector` "Alice" label looked up the wrong metadata key (`"provider_selection"` — the user's *selection* marker) instead of `"provider_options"` (Alice's *prompt* message), so its time silently never rendered.
- **Two transient UI bubbles (G2, G3)** are rendered without any server-backed message, so they had no timestamp source.

## Section 2 — Impact Analysis

- **Epic Impact:** None. This is a UI-polish increment on the existing chat surface; no epic scope changes.
- **Story Impact:** None new. Touches the cross-cutting chat rendering only.
- **Artifact Conflicts:** None. PRD / Architecture / UX specs unaffected (no data-model or contract change — `users.timezone` and `Message.timestamp` already exist with migration `c98f775f0b00`).
- **Technical Impact:** Frontend only. 3 files changed (`MessageTime.tsx`, `App.tsx`, 1 new test). No backend, schema, or API change. No new migration.

### Coverage map (post-change)

| Message / bubble | Timestamp source | Status |
| ---------------- | ---------------- | ------ |
| Bob / Mary / Sarah / generic (incl. Jack), You | `msg.timestamp` (real message) | ✅ already covered |
| Alice ThinkingBubble, Bob thinking trace | `msg.timestamp` / located message | ✅ already covered |
| Saved-config prompt, ModelAssignmentReview, confirm_parent, select_id, test_case_review, sarah_inputs_request, test_case_selection, script_review | located message metadata | ✅ verified keys map to real metadata |
| ProviderSelector "Alice" prompt | `provider_options` message | 🐞→✅ **fixed (G1)** |
| Alice loading / error / no-access info | client time, frozen at mount | ➕ **added (G2)** |
| Bob "enter MCP key" fallback | client time, frozen at mount | ➕ **added (G3)** |

## Section 3 — Recommended Approach

**Direct Adjustment** — small, contained edits within the existing plan. No rollback, no MVP re-scope.

- **Effort:** ~30 min. **Risk:** Low (UI-only, no contract change). **Timeline impact:** None.
- **Decision (confirmed by Thuong):** the two transient bubbles (G2/G3) that have no backing message show a **client-side current time, frozen at first render**, so that literally every visible bubble carries an `hh:mm:ss` — with the caveat that this time is the client clock at render, not a server message instant.

## Section 4 — Detailed Change Proposals

### Change 1 (G1) — fix wrong metadata key on the ProviderSelector time

`frontend/src/App.tsx` — the `messageTime` / `messageTimeTitle` props passed to `<ProviderSelector>`.

```diff
- messages.find((m) => m.metadata?.type === "provider_selection")?.timestamp
+ messages.find((m) => m.metadata?.type === "provider_options")?.timestamp
```

Rationale: the backend emits Alice's provider prompt with `metadata.type == "provider_options"` (`alice.py:1109/1210/1318`). `"provider_selection"` is the *user's* selection marker (`App.tsx:793/1345/1926`) and must stay untouched.

### Change 2 (G2/G3) — `NowMessageTime` for transient bubbles

`frontend/src/components/MessageTime.tsx` — new sibling export:

```tsx
/** Like MessageTime but stamps + freezes the moment it first mounts — for transient
 * UI bubbles (loading / error / fallback prompts) that have no server-backed message. */
export function NowMessageTime() {
  const [iso] = useState(() => new Date().toISOString());
  return <MessageTime timestamp={iso} />;
}
```

`frontend/src/App.tsx` — render `<NowMessageTime />` beside the "Alice" label of the loading/error/no-access bubble and the "Bob" label of the MCP-key fallback bubble; import updated to `{ MessageTime, NowMessageTime }`.

Rationale: freezing at mount (via lazy `useState`) keeps the time stable across re-renders; reusing `MessageTime` keeps the same timezone resolution (`users.timezone` via `AuthContext`) and styling.

### Change 3 — test coverage

`frontend/src/components/__tests__/MessageTime.test.tsx` (new): asserts `hh:mm:ss` rendering in a fixed zone (UTC and Asia/Ho_Chi_Minh +7), empty render for missing/invalid timestamp, and that `NowMessageTime` produces a valid `hh:mm:ss`.

## Section 5 — Implementation Handoff

- **Scope:** Minor → implemented directly by the Developer agent (this session).
- **Verification (all green):**
  - `npm run typecheck` — clean.
  - `npx vitest run` on `timezone.test.ts`, `App.test.tsx`, `App.wsRoundTrip.test.tsx`, `AdminDashboard.test.tsx` — 39 passed.
  - `npx vitest run` on new `MessageTime.test.tsx` — 5 passed.
  - `npx eslint` on changed files — clean.
- **Success criteria:** every message bubble (agent or user) shows `hh:mm:ss` in the logged-in user's `users.timezone`; ProviderSelector prompt now shows its time; transient bubbles show a frozen client time.
- **Remaining for Thuong:** commit + (no migration needed) per the solo-`main` workflow.

### Optional follow-up (not required, deferred)

- Converge `ProviderSelector` / `ModelAssignmentReview` from the pre-formatted `messageTime`/`messageTimeTitle` props onto the self-sufficient `<MessageTime timestamp={…}/>` component, removing duplicated `formatMessageTime(..., user?.timezone)` call sites in `App.tsx`. Pure consistency cleanup; behavior already correct after G1.

---

## Revision 2 (2026-06-20) — "chỗ có chỗ không": consistency defect found in live testing

Live testing showed timestamps appearing on some bubbles but not others — the G1 key fix alone was not enough. A verified, exhaustive audit (23 render branches + the full message data-flow) localized the real, structural root cause.

### Root cause (structural)

A bubble that back-references its time via `messages.find(PRED)?.timestamp` only shows a time if a message matching `PRED` is actually **retained** in `messages[]`. The live WebSocket gate (`useWebSocket.ts:159`) required `data.sender && data.content && data.timestamp` — so **empty-content carriers were dropped on the live socket** and never reached `messages[]`. History reload has no such gate, so the same carrier *could* re-appear after a refresh. That live-vs-reload asymmetry is exactly the "chỗ có chỗ không" the user saw.

- **Empty-content carriers (`content=""`):** `provider_options` (`alice.py:1206` et al.) → its `messages.find` returned undefined live → time blank.
- **Non-empty carriers** (`thinking_trace`, `model_assignments`, `saved_config_prompt`, `confirm_parent`, `is_select_id`, Mary/Sarah panel requests): survive the gate → always show a real time. (This is why most bubbles looked fine.)
- **ProviderSelector "You" card** (`ProviderSelector.tsx`): a hard-coded omission — the read-only submitted-selection header had **no `MessageTime` markup at all**, even though the `provider_selection` user marker carries a real stamp.

### Fix (coherent set)

1. **`MessageTime` made resilient** — new opt-in `fallbackToNow` prop: when the backing timestamp is missing/invalid it shows a client time **frozen at first mount** (lazy `useState`) instead of rendering nothing. `NowMessageTime` is now a thin wrapper over it. Real server time always wins when present; the fallback only fills genuine gaps.
2. **Converged the two pre-formatted-string consumers** (`ProviderSelector`, `ModelAssignmentReview`) onto internal `<MessageTime timestamp={rawISO} fallbackToNow/>`. Pre-formatted strings could never fall back (a pre-empty string stays empty). Props changed: `messageTime`/`messageTimeTitle`/`selectionTime`/`selectionTimeTitle` → raw-ISO `messageTimestamp` / `selectionTimestamp`. App passes raw timestamps; the now-unused `formatMessageTime`/`formatMessageDateTime` import was removed from `App.tsx`.
3. **Added the missing `MessageTime`** to the ProviderSelector "You" header, wired to the `provider_selection` marker timestamp + `fallbackToNow`.
4. **Hardened all `find()`-backed `MessageTime` calls** in `App.tsx` (saved_config_prompt, confirm_parent, select_id, Mary review/done, all three Sarah panels) with `fallbackToNow` and `ThinkingBubble` likewise — uniform, so the whole bug class can't recur.
5. **Source-level reinforcement (authored concurrently by Thuong):** `useWebSocket.ts:159` gate relaxed to keep empty-content carriers that have a `metadata.type` (`data.sender && data.timestamp && (data.content || data.metadata?.type)`), so `provider_options` now reaches `messages[]` with its **real** server timestamp (the empty-content chat-render filter in `App.tsx` still hides the bubble itself). Complements #1–#3: "Alice" now shows real server time, with `fallbackToNow` as the safety net.

### Verification (all green)

- `npm run typecheck` — clean.
- Full `npx vitest run` — **28 files, 306 tests passed** (incl. rewritten `ProviderSelector.test.tsx` for the new ISO props + always-on time, and `MessageTime.test.tsx`).
- `npx eslint` on changed files — clean.

### Audit deliverable

Per-bubble verdicts across 23 render branches: **19 already showed a time**, **2 real defects** (ProviderSelector "Alice" + "You" — now fixed), **2 by-design** (Bob/Mary clarify-answer *input* panels — the matching question bubble and the submitted "You" answer bubble both carry times; the input affordance intentionally does not).

### Files changed (frontend only, no backend logic / no migration)

`MessageTime.tsx`, `ProviderSelector.tsx`, `ModelAssignmentReview.tsx`, `ThinkingBubble.tsx`, `App.tsx`, `useWebSocket.ts` (gate, Thuong), `__tests__/MessageTime.test.tsx` (new), `__tests__/ProviderSelector.test.tsx` (updated). Still UNCOMMITTED on `main`.
