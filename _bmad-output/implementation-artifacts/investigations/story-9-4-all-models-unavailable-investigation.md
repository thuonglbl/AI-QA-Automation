# Investigation: Story 9.4 — All Models Unavailable: Assignments Still Shown + Test Failures

## Hand-off Brief

1. **What happened.** When all discovered models are unavailable (quota exceeded / unsupported), Alice's backend sends `fallback_assignments` with those unavailable models and a `SILENT_ABORT` — but the frontend App.tsx reads `trace.assignments` and populates `modelAssignments`, causing a disabled review table to render instead of halting; the ThinkingBubble never shows "Available Models (N)" because `available_models` is `[]`, so the test locator is never found.
2. **Where the case stands.** Root cause is Confirmed: the frontend unconditionally maps `trace.assignments` → `modelAssignments` even in the error path, and the `ThinkingBubble` only renders the "Available Models" heading when `available_models.length > 0`.
3. **What's needed next.** The frontend must NOT populate `modelAssignments` when `available_models` is empty (error path); the "OK" button must remain disabled (already is) and Alice must only show the error trace. This is a frontend-only fix in `App.tsx`.

---

## Case Info

| Field            | Value |
| ---------------- | ----- |
| Ticket           | N/A |
| Date opened      | 2026-06-08 |
| Status           | Concluded |
| System           | Windows / Chromium (Playwright 1.60.0), React 18 + TypeScript, FastAPI backend |
| Evidence sources | `_bmad-output/test-artifacts/results.xml`, `frontend/test-results/*/error-context.md`, `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts`, `frontend/src/App.tsx`, `frontend/src/components/ThinkingBubble.tsx`, `src/ai_qa/agents/alice.py` |

---

## Problem Statement

User ran the full E2E suite; 3 of 6 tests in `story-9-4-dynamic-model-discovery.spec.ts` failed (Anthropic/Claude, Google/Gemini, OpenAI/ChatGPT).  
User's stated intent: *"Khi toàn bộ model unavailable thì Alice chỉ báo lỗi chứ không assign model."*  
(When all models are unavailable, Alice should only report an error — not assign models.)

---

## Evidence Inventory

| Source | Status | Notes |
| ------ | ------ | ----- |
| `_bmad-output/test-artifacts/results.xml` | Available | 36 tests, 3 failures, all in `story-9-4-dynamic-model-discovery.spec.ts` |
| `frontend/test-results/story-9-4-dynamic-model-di-4407b-.../error-context.md` | Available | Full DOM snapshot at failure point (Anthropic) |
| `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts` | Available | Full test spec |
| `frontend/src/App.tsx` (lines 495–533) | Available | WebSocket message handler |
| `frontend/src/components/ThinkingBubble.tsx` | Available | Renders "Available Models (N)" heading |
| `src/ai_qa/agents/alice.py` (lines 777–870) | Available | Backend error paths |
| Playwright trace `.zip` / video `.webm` | Partial | Files exist but binary; DOM snapshot sufficient |

---

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | App.tsx: trace.assignments → modelAssignments branch | High | Done | Root cause found |
| 2 | ThinkingBubble.tsx: `available_models.length > 0` guard | High | Done | Confirms symptom |
| 3 | alice.py: error path emits `assignments` + `SILENT_ABORT` | High | Done | Confirmed |
| 4 | `_assign_fallback_models` output shape | Medium | Done | Returns unavailable-model ids, shown in disabled dropdowns |

---

## Timeline of Events

| Time | Event | Source | Confidence |
| ---- | ----- | ------ | ---------- |
| Test run 2026-06-08T12:31:28Z | Test for Claude, Gemini, OpenAI started | results.xml | Confirmed |
| ~T+30s | API key accepted; connection succeeds | DOM snapshot: "Connected successfully to" | Confirmed |
| ~T+30s | All discovered models have `quota_status=exceeded` or are unsupported | alice.py:765-776 | Confirmed |
| ~T+30s | Backend emits `thinking_trace` with `available_models=[]`, `unavailable_models=[...]`, `assignments=[fallback]` | alice.py:781-797 | Confirmed |
| ~T+30s | App.tsx WebSocket handler sets `thinkingTrace` and maps `trace.assignments` → `modelAssignments` | App.tsx:519-528 | Confirmed |
| ~T+30s | `ModelAssignmentReview` renders with disabled dropdowns; OK button disabled | DOM snapshot: all combos `[disabled]`, `button "OK" [disabled]` | Confirmed |
| ~T+30s | `ThinkingBubble` collapses (isCompleted=? or isOpen=false) | ThinkingBubble.tsx:16 | Confirmed |
| ~T+35s | Test looks for `Available Models (\d+)` — not found (available_models=[]) | spec:245-251 | Confirmed |
| ~T+35s | Test tries to click "Alice's thought" to expand — still not found | spec:250-251 | Confirmed |
| ~T+35s | Test fails with `expect(locator).toBeVisible() failed` | results.xml | Confirmed |

---

## Confirmed Findings

### Finding 1: "Available Models (N)" is gated on `available_models.length > 0`

**Evidence:** `frontend/src/components/ThinkingBubble.tsx:70`
```tsx
{available_models && available_models.length > 0 && (
  <div>
    <h4 ...>Available Models ({available_models.length})</h4>
```
**Detail:** When the backend sends `available_models: []` (all quota-exceeded), this JSX branch is skipped entirely. The heading never renders, so the test locator `getByText(/Available Models \(\d+\)/)` finds nothing.

### Finding 2: Backend sends `assignments` in the error path

**Evidence:** `src/ai_qa/agents/alice.py:779`, `alice.py:849`  
Both the "no available models" branch (line 779) and the "LLM rate limit" branch (line 849) call `_assign_fallback_models(unavailable_models)` and place the result in `error_trace["assignments"]` / `trace_payload["assignments"]`.

### Finding 3: App.tsx unconditionally maps `trace.assignments` → `modelAssignments`

**Evidence:** `frontend/src/App.tsx:519-528`
```ts
...(trace?.assignments && trace.assignments.length > 0
  ? { 
      modelAssignments: trace.assignments.map(a => ({
        agent: a.agent.charAt(0).toUpperCase() + a.agent.slice(1),
        model: a.model,
        purpose: a.rationale || "Agent task"
      })) 
    }
  : {}),
```
**Detail:** There is no guard for the error path. Even when `available_models` is empty and the backend intends to abort, this code fires because `trace.assignments.length > 0` is true (fallback assignments were created). This renders the `ModelAssignmentReview` table with disabled dropdowns and a disabled OK button — the "error-but-looks-like-review" state seen in the DOM snapshot.

### Finding 4: DOM snapshot confirms the symptom precisely

**Evidence:** `frontend/test-results/story-9-4-dynamic-model-di-4407b-.../error-context.md` (DOM tree)  
- "Connected successfully to" is visible — connection succeeded.
- All 5 agent combos show `claude-opus-4-8 (Unavailable) [disabled]`.
- `button "OK" [disabled]` — not clickable.
- `ThinkingBubble` collapsed (`button "▶"`) — header clickable but expanding won't show "Available Models (N)" because the list is empty.

---

## Deduced Conclusions

### Deduction 1: The 3 failures (Claude, Gemini, OpenAI) share the same root cause

**Based on:** Findings 1, 2, 3  
**Reasoning:** All three providers' test keys hit quota-exceeded or rate-limit errors during the live run. The backend took the error path in both branches, emitted fallback assignments, and SILENT_ABORT'd. The frontend mapped those assignments to `modelAssignments`, producing the disabled review UI. The test expected "Available Models (N)" in the thinking bubble but that text is structurally absent when `available_models=[]`. Identical error message at `spec:251` for all three confirms they hit the same code path.

**Conclusion:** This is one bug, not three independent ones.

### Deduction 2: "On-Premises" and "Browser Use Cloud" passed because they reached the happy path

**Based on:** results.xml (both green), Finding 3  
**Reasoning:** These two providers either had working keys or took a different code branch. The happy path sends `available_models` with real items, so "Available Models (N)" renders correctly.

---

## Hypothesized Paths

### Hypothesis 1: ThinkingBubble collapsed state caused the failure (not missing heading)

**Status:** Refuted  
**Theory:** The bubble was collapsed and clicking it would have revealed "Available Models (N)".  
**Refutation:** DOM snapshot shows `available_models=[]` in all dropdowns are `(Unavailable)`. `ThinkingBubble.tsx:70` only renders the heading when `available_models.length > 0`. Clicking the header cannot reveal something that is never rendered.  
**Resolution:** Evidence from Finding 1 definitively refutes this.

### Hypothesis 2: The fix requires only a test change (guard for rate-limit outcome)

**Status:** Refuted  
**Theory:** The test should skip or pass when all models are unavailable, since the user's intent is only about the UI behavior.  
**Refutation:** User's stated intent is: Alice should only show an error and NOT assign models when all models are unavailable. The current code DOES assign (disabled) models. The production behavior is incorrect — the fix must be in the frontend, not the test.  
**Resolution:** User-stated requirement directly refutes a test-only fix.

### Hypothesis 3: The fix requires the backend to stop sending `assignments` in the error path

**Status:** Refuted  
**Theory:** Remove `assignments` from `error_trace` in alice.py so the frontend never gets them.  
**Refutation:** The backend is also used by the "0 available models" test (last test, which passes), which asserts `[What happened] No available models were found`. Removing `assignments` from the backend is over-reaching. The frontend should gate on `available_models.length > 0` before promoting assignments to `modelAssignments`.  
**Resolution:** The fix is in the frontend conditional at `App.tsx:519`.

---

## Missing Evidence

| Gap | Impact | How to Obtain |
| --- | ------ | ------------- |
| `_assign_fallback_models` implementation | Low — shape of assignments known from DOM (agent+model), irrelevant to fix direction | Read `alice.py` around line 1162 |
| Why `ThinkingBubble` is collapsed at failure point | Low — refuted as root cause | Playwright trace video |

---

## Source Code Trace

| Element | Detail |
| ------- | ------- |
| Error origin | `frontend/src/App.tsx:519` — `trace.assignments` mapped to `modelAssignments` unconditionally |
| Trigger | WebSocket `thinking_trace` message where `available_models=[]` and `assignments=[fallback_items]` |
| Condition | `trace?.assignments && trace.assignments.length > 0` is `true` even in the error path |
| Related files | `frontend/src/components/ThinkingBubble.tsx:70` (rendering gate), `src/ai_qa/agents/alice.py:779,849` (error path emissions), `frontend/e2e/story-9-4-dynamic-model-discovery.spec.ts:245` (test locator) |

---

## Conclusion

**Confidence: High**

Root cause is Confirmed. When all provider models are unavailable (quota exceeded / unsupported), the backend correctly sends `available_models: []` and signals a `SILENT_ABORT`. However, the frontend's WebSocket handler in `App.tsx` does not gate on `available_models` presence before mapping `trace.assignments` → `modelAssignments`. This causes the `ModelAssignmentReview` table to render with disabled dropdowns (unavailable model IDs) — visually misleading and functionally incorrect. The `ThinkingBubble` never renders "Available Models (N)" because its guard at `ThinkingBubble.tsx:70` is `available_models.length > 0`, which is `false` in the error path.

The fix is a **single conditional in `App.tsx`**: only promote `trace.assignments` to `modelAssignments` when `trace.available_models` is non-empty.

---

## Recommended Next Steps

### Fix direction

**File:** `frontend/src/App.tsx`, lines 519–528  
**Mechanism:** Add a guard `trace.available_models && trace.available_models.length > 0` before mapping `trace.assignments` to `modelAssignments`.

**Draft diff:**
```ts
// BEFORE (App.tsx ~line 519)
...(trace?.assignments && trace.assignments.length > 0
  ? { 
      modelAssignments: trace.assignments.map(a => ({...})) 
    }
  : {}),

// AFTER
...(trace?.assignments && trace.assignments.length > 0 
    && trace.available_models && trace.available_models.length > 0
  ? { 
      modelAssignments: trace.assignments.map(a => ({...})) 
    }
  : {}),
```

This ensures: when all models are unavailable, `modelAssignments` stays `null`, `ModelAssignmentReview` is not rendered, and the ThinkingBubble's error chain-of-thought is the only thing shown — matching user intent.

### Diagnostic

Once the fix is applied:
1. The 3 provider tests (Claude, Gemini, OpenAI) will hit the `ratelimit` branch at `spec:236-240` and return early with `expect(["claude", "gemini", "openai"]).toContain(providerCase.id)` — which is the existing correct behavior for quota-exceeded keys.
2. The "0 available models" test should continue to pass.
3. Run: `npx playwright test e2e/story-9-4-dynamic-model-discovery.spec.ts`

---

## Reproduction Plan

1. Ensure `.env` has a valid but quota-exceeded `TEST_CLAUDE_KEY`.
2. Run: `npx playwright test e2e/story-9-4-dynamic-model-discovery.spec.ts --grep "Anthropic"`
3. Observe: disabled dropdowns render, "Available Models (N)" is never visible, test fails at `spec:251`.
4. Apply fix to `App.tsx:519`.
5. Re-run: test now reaches `spec:236` `outcome === "ratelimit"` branch and exits cleanly.

---

## Side Findings

- The "0 available models" test (`[P1]`) passed (results.xml) — it correctly uses `mock-empty-key` via On-Premises, backend emits the error trace, and the test only asserts `[What happened] No available models were found` in the ThinkingBubble's `chain_of_thought`, not the "Available Models" heading. This test will remain unaffected by the fix.
- `button "OK" [disabled]` in the DOM snapshot shows the `ModelAssignmentReview` component already correctly disables the OK button when models are unavailable. The frontend disablement logic is correct; only the `should we render this at all` gate is missing.
