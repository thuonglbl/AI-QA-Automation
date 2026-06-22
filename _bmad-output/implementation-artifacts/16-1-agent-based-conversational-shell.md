---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.1: Agent-Based Conversational Shell

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **Foundational story for Epic 16.** Stories 16-2 … 16-7 layer onto the shell this story confirms. Much of the conversational shell already exists (Epics 2, 6, 7, 10) — this story is an **audit-and-close-gaps** pass, not a greenfield build. Do NOT rebuild working components; verify each AC against the live code and fill only the proven gaps.

## Story

As a QA user,
I want the application to present the pipeline as a named-agent conversation,
so that I can understand which agent is guiding each step.

## Acceptance Criteria

1. **Chat shell with identity + timestamps.** Given the user opens a project thread, when the conversational UI loads, then messages are displayed in a chat interface with agent names, avatars, timestamps, and role-appropriate message styling (agent vs user vs system).

2. **Agents frame their step in role.** Given the workflow reaches Alice, Bob, Mary, Sarah, or Jack, when the agent becomes active, then the agent introduces or frames the current task in its expected role, and the UI preserves conversation history for the active thread (across resume/reload).

3. **Identity stays distinguishable across the thread.** Given multiple agents contribute to a thread, when the user reviews prior messages, then agent identity (name + avatar + color) remains clear and distinguishable for each message, including pure-metadata carrier messages.

## Tasks / Subtasks

- [ ] **Task 1 — Audit the existing chat shell against AC1 (AC: 1)**
  - [ ] Confirm `ChatMessage` renders agent/user/system styling, agent name, and timestamp for the three sender types ([frontend/src/components/ChatMessage.tsx](frontend/src/components/ChatMessage.tsx)). Verify the timestamp path uses the timezone-aware `MessageTime` ([frontend/src/components/MessageTime.tsx](frontend/src/components/MessageTime.tsx)) — see [[message-timestamps-feature]] for the empty-content carrier gotcha.
  - [ ] Confirm `AgentTopBar` renders the active agent avatar + color + display name from the `AGENTS` registry ([frontend/src/components/AgentTopBar.tsx](frontend/src/components/AgentTopBar.tsx)).
  - [ ] Confirm `ChatArea` keeps history and auto-scroll behavior ([frontend/src/components/ChatArea.tsx](frontend/src/components/ChatArea.tsx)).
  - [ ] Record any AC1 gap as a subtask here; if none, mark AC1 verified-only in Completion Notes.

- [ ] **Task 2 — Verify agent identity model is complete and consistent (AC: 2, 3)**
  - [ ] Confirm the `AGENTS` registry has name/displayName/avatar/color/stepNumber/stepTitle for all five agents (Alice/Bob/Mary/Sarah/Jack) in `frontend/src/types/pipeline.ts` (the `AGENTS` record).
  - [ ] Confirm `agentName` is stamped on each agent message at send time and survives a thread reload via `loadConversationFromAPI` (it maps backend `agent_name` → `AgentMessage.agentName`) in [frontend/src/hooks/usePipelineState.ts](frontend/src/hooks/usePipelineState.ts).
  - [ ] Confirm pure-metadata carrier messages (content="" but `metadata.type` present, e.g. Alice's `provider_options`) still carry agent identity and are not dropped by the WS gate in [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts).

- [ ] **Task 3 — Verify each agent frames its step in role on activation (AC: 2)**
  - [ ] For each agent (`agents/alice.py`, `bob.py`, `mary.py`, `sarah.py`, `jack.py`), confirm the first message sent on `handle_start`/activation introduces the step in-role (uses `BaseAgent.send_message`). Note any agent that activates silently as a gap.
  - [ ] Confirm history preservation on resume: `loadConversationFromAPI` rehydrates the thread's messages, step, status, and agent (do not regress the Alice start-state filtering that drops failed-attempt bubbles).

- [ ] **Task 4 — Close proven gaps only (AC: 1, 2, 3)**
  - [ ] If the registry, identity stamping, or in-role framing has a concrete gap found in Tasks 1–3, fix it minimally. Otherwise add no new behavior.
  - [ ] Strengthen the metadata typing only if it blocks an AC (see Dev Notes "Known partials"); otherwise defer to 16-3/16-5 where it bites.

- [ ] **Task 5 — Tests (AC: 1, 2, 3)**
  - [ ] Add/extend Vitest tests asserting: agent-name + timestamp render for an agent message; user vs agent vs system styling differs; identity survives a simulated reload; a pure-metadata carrier keeps its `agentName`.
  - [ ] Reuse the established patterns in `frontend/src/components/__tests__/ChatMessage.test.tsx`, `ChatArea.test.tsx`, and `frontend/src/hooks/__tests__/useWebSocket.test.tsx`.
  - [ ] `npm run typecheck` + `npm run lint` + `npm test` green in `frontend/`.

## Dev Notes

### What already exists (do not rebuild)

The conversational shell is largely delivered. The research map (against live code) found:

- **`ChatMessage`** — sender-based styling (agent/user/system), agent name, timestamp, and message-type routing (`text`/`code`/`error`/`processing`). Renders `ReviewContent` for rich agent content; plain text for user.
- **`ChatArea`** — scroll container with auto-scroll-to-bottom unless the user scrolled up, plus a floating "New message" pill.
- **`AgentTopBar`** — avatar + color + display name + step indicator + status badge; Alice gets a personalized "Hello, {userName}!" greeting.
- **`StepDots`** — 5-step progress dots (completed/current/pending).
- **`AGENTS` registry** (`frontend/src/types/pipeline.ts`) — per-agent name/displayName/avatar/color/stepNumber/stepTitle. Colors: Alice pink `#EC4899`, Bob blue `#3B82F6`, Mary green `#22C55E`, Sarah purple `#A855F7`, Jack orange `#F97316`.
- **`useWebSocket`** — connection lifecycle, project/thread filtering, an AgentMessage gate that intentionally accepts pure-metadata carriers, exponential-backoff reconnect, and a raw-event channel for non-AgentMessage events (e.g. `artifact_change`).
- **`usePipelineState`** — loads/saves thread conversation, maps backend `MessageResponse` → `AgentMessage`, derives current step/agent from `agentName`.

### Known partials (candidate gaps — confirm before acting)

- `ProcessingIndicator` hardcodes the label "Alice" (`frontend/src/components/ProcessingIndicator.tsx`) — this is the **flexible agent-name gap**; it is owned by **story 16-3**, not here. Do not fix it in 16-1 unless it blocks AC2's "frames in role" for non-Alice agents during processing; if it does, note it and coordinate with 16-3.
- `AgentMessage.metadata` is typed `Record<string, unknown>` (no discriminated union). Tightening it is optional here and lands more naturally in 16-3/16-5. Only touch if an AC requires it.

### Source tree components to touch

- `frontend/src/components/ChatMessage.tsx` — **READ / VERIFY**; change only on a proven AC1 gap.
- `frontend/src/components/AgentTopBar.tsx` — **READ / VERIFY** (identity rendering).
- `frontend/src/components/ChatArea.tsx` — **READ / VERIFY** (history + scroll).
- `frontend/src/types/pipeline.ts` — **READ / VERIFY** the `AGENTS` registry + `AgentMessage` interface.
- `frontend/src/hooks/usePipelineState.ts` — **READ / VERIFY** load/save + agent derivation.
- `frontend/src/hooks/useWebSocket.ts` — **READ / VERIFY** the AgentMessage gate (carrier acceptance).
- `src/ai_qa/agents/{alice,bob,mary,sarah,jack}.py` — **READ / VERIFY** in-role framing on activation; minimal edit only if an agent activates without framing.
- `frontend/src/components/__tests__/*.tsx` — **UPDATE** (add the AC assertions).

### Current behavior to PRESERVE (regression guardrails)

- The WS gate's acceptance of pure-metadata carriers (content="" + `metadata.type`) — these drive Alice's provider UI; do not tighten the gate ([[message-timestamps-feature]]).
- Alice start-state message filtering on reload (keeps the final `provider_options`, drops failed-attempt bubbles) — do not regress.
- `data-testid="thread-{id}"` and the frozen `getByText` artifact-label contract in `ProjectSidebar` (10-7/10-8) — do not rename.
- App-UI-English-only: every static label/string stays English ([[app-ui-english-only]]). (Per-user conversation language is story 16-9; do not pre-empt it here.)

### Testing standards summary

- Vitest 4 + React Testing Library, happy-dom env, `setupFiles: src/test-setup.ts`. `vi.mock` hoists file-wide — prefer `vi.spyOn(globalThis, "fetch")` and `importOriginal()` (see [[project-context]] Frontend rules).
- Prefer `getByRole` / `getByText` over `data-testid`. Assert ARIA where it exists.
- `noUncheckedIndexedAccess` is on — write `arr[0]!` / chained `mock.calls[0]![0]` in tests.

### Project Structure Notes

- All FE changes stay under `frontend/src/`; backend verification is read-only unless an agent's in-role framing is missing. No schema/migration. No new dependencies.

### References

- Epic + ACs: [epics.md#Story-16.1](_bmad-output/planning-artifacts/epics.md:1706)
- Component map source: the conversational-shell research conducted for this epic (see Dev Notes "What already exists").
- Coding/testing rules (authoritative): [project-context.md](project-context.md)
- Related memories: [[message-timestamps-feature]], [[app-ui-english-only]]

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
