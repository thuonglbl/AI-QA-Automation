# Story 2.4: AgentTopBar and StepDots Components

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a manual QA tester (Linh),
I want to see which AI agent is active, what step I'm on, and the current status,
so that I always know where I am in the pipeline.

## Acceptance Criteria

1. **Given** the chat UI is open  
   **When** an agent is active  
   **Then** AgentTopBar shows agent avatar (initial letter with color), agent name, step title, and step counter "Step X of 5" (UX-DR2)

2. **And** status badge displays correct state with colors: Start (grey), Processing (amber pulsing), Review Request (blue), Done (green + checkmark) (UX-DR8)

3. **And** StepDots show 5 dots: completed (green), active (blue), pending (grey) (UX-DR6)

4. **And** status badge uses color + text + icon (colorblind-safe) (UX-DR8)

5. **And** AgentTopBar has `role="banner"` and status changes announced via `aria-live="polite"` (UX-DR15)

## Tasks / Subtasks

- [x] Task 1: Create AgentTopBar component (AC: 1, 2, 4, 5)
  - [x] 1.1 Create `frontend/src/components/AgentTopBar.tsx`
  - [x] 1.2 Implement agent avatar with initial letter and color
  - [x] 1.3 Display agent name, step title, and step counter "Step X of 5"
  - [x] 1.4 Implement StatusBadge sub-component with all 4 states
  - [x] 1.5 Add accessibility attributes (`role="banner"`, `aria-live="polite"`)

- [x] Task 2: Create StepDots component (AC: 3)
  - [x] 2.1 Create `frontend/src/components/StepDots.tsx`
  - [x] 2.2 Implement 5-dot progress indicator with 8px dot size
  - [x] 2.3 Color states: completed (green-500), active (blue-500), pending (slate-300)
  - [x] 2.4 Add accessibility attributes (`role="progressbar"`, `aria-valuenow`, `aria-valuemax`)

- [x] Task 3: Wire components to pipeline state (AC: 1, 2, 3)
  - [x] 3.1 Update `usePipelineState` hook to expose current agent and step info
  - [x] 3.2 Integrate AgentTopBar into main App layout
  - [x] 3.3 Integrate StepDots below AgentTopBar
  - [x] 3.4 Connect WebSocket status updates to component re-renders

- [x] Task 4: Implement state transition animations (AC: 2)
  - [x] 4.1 Add badge fade animation (150ms) for status changes
  - [x] 4.2 Add pulsing animation for Processing state
  - [x] 4.3 Use Tailwind transitions for smooth state changes

- [x] Task 5: Write component tests (AC: 1, 2, 3, 4, 5)
  - [x] 5.1 Create `frontend/src/components/__tests__/AgentTopBar.test.tsx`
  - [x] 5.2 Test all status badge states render correctly
  - [x] 5.3 Test agent identity displays (name, avatar, colors)
  - [x] 5.4 Test accessibility attributes are present
  - [x] 5.5 Create `frontend/src/components/__tests__/StepDots.test.tsx`
  - [x] 5.6 Test dot colors match step states

- [x] Task 6: Validation
  - [x] 6.1 `npm run lint` passes with no errors
  - [x] 6.2 `npm run type-check` passes with no TypeScript errors
  - [x] 6.3 `npm run test` — all component tests pass
  - [x] 6.4 Manual verification: Start dev server, verify AgentTopBar and StepDots render correctly

## Dev Notes

### Component Design Pattern

AgentTopBar and StepDots are **presentational components** that receive all data via props. They do NOT connect directly to WebSocket — the parent component (App.tsx) passes agent state down.

**Props Interface:**

```typescript
// AgentTopBar.tsx
interface AgentTopBarProps {
  agent: {
    name: string;        // "Alice", "Bob", "Mary", "Sarah", "Jack"
    color: string;       // Hex color (e.g., "#EC4899")
    stepNumber: number;  // 1-5
    stepTitle: string;   // e.g., "AI Provider Configuration"
  };
  status: AgentStatus;  // 'start' | 'processing' | 'review_request' | 'done' | 'completed'
}

// StepDots.tsx
interface StepDotsProps {
  currentStep: number;   // 1-5 (active step)
  completedSteps: number; // How many steps are done
}
```

### Critical: Use Existing AGENTS Constant

The frontend already has agent identities defined in `frontend/src/types/pipeline.ts` from Story 2.2:

```typescript
// frontend/src/types/pipeline.ts (EXISTING — DO NOT MODIFY)
export const AGENTS = {
  Alice: { color: "#EC4899", stepNumber: 1, stepTitle: "AI Provider Configuration" },
  Bob:   { color: "#3B82F6", stepNumber: 2, stepTitle: "Requirements Extraction" },
  Mary:  { color: "#22C55E", stepNumber: 3, stepTitle: "Test Case Generation" },
  Sarah: { color: "#A855F7", stepNumber: 4, stepTitle: "Test Script Generation" },
  Jack:  { color: "#F97316", stepNumber: 5, stepTitle: "Test Execution" },
} as const;
```

**MUST use this constant** — do not redefine agent identities. Import from `types/pipeline.ts`.

### Status Badge Color Mapping

Per UX-DR8 and UX-DR9 (Professional Calm color system):

| Status | Badge Style | Background | Text | Icon |
|--------|-------------|------------|------|------|
| `start` | Grey outline | white | slate-600 | — |
| `processing` | Amber pulsing | amber-100 | amber-700 | Loader2 (animate-spin) |
| `review_request` | Blue solid | blue-500 | white | Eye |
| `done` | Green solid | green-500 | white | Check |
| `completed` | Green solid | green-500 | white | Check (Step 5 only) |

### StepDots Color Mapping

Per UX-DR6 and UX-DR9:

| State | Color | Tailwind Class |
|-------|-------|----------------|
| Completed | Green | `bg-green-500` |
| Active | Blue | `bg-blue-500` |
| Pending | Grey | `bg-slate-300` |

### Architecture Compliance

All code must follow patterns from `architecture.md`:

| Rule | Implementation |
|------|---------------|
| TypeScript strict mode | All props fully typed, no `any` |
| Component composition | Small, focused components |
| Accessibility | WCAG 2.1 AA — focus rings, aria attributes, 44px click targets |
| Styling | Tailwind CSS only — no inline styles except dynamic colors |
| Testing | React Testing Library + Jest (via Vitest) |

### Shadcn/ui Components to Use

Install if not already present:

```bash
cd frontend
npx shadcn add badge avatar
```

- **Badge**: Status badge base styling
- **Avatar**: Agent avatar with fallback (initial letter)

### File Structure for This Story

```
frontend/src/
├── components/
│   ├── AgentTopBar.tsx              # NEW
│   ├── StepDots.tsx                 # NEW
│   └── __tests__/
│       ├── AgentTopBar.test.tsx     # NEW
│       └── StepDots.test.tsx        # NEW
├── hooks/
│   └── usePipelineState.ts          # MODIFY: add agent/step selectors
├── types/
│   └── pipeline.ts                  # EXISTING: import AGENTS constant
└── App.tsx                          # MODIFY: integrate components
```

**DO NOT create:** No new backend files — this is frontend-only story.

### Testing Strategy

Use Vitest + React Testing Library (already configured from Story 2.2):

```typescript
// Example test pattern
import { render, screen } from "@testing-library/react";
import { AgentTopBar } from "../AgentTopBar";

test("renders agent name and step title", () => {
  render(<AgentTopBar agent={AGENTS.Alice} status="start" />);
  expect(screen.getByText("Alice")).toBeInTheDocument();
  expect(screen.getByText("AI Provider Configuration")).toBeInTheDocument();
});
```

**Key tests to write:**
1. `test_renders_agent_identity` — name, avatar initial, color
2. `test_renders_step_counter` — "Step 1 of 5", "Step 2 of 5", etc.
3. `test_status_badge_start` — grey outline style
4. `test_status_badge_processing` — amber pulsing with spinner icon
5. `test_status_badge_review` — blue solid with eye icon
6. `test_status_badge_done` — green solid with checkmark icon
7. `test_accessibility_banner_role` — `role="banner"` present
8. `test_stepdots_completed_count` — correct number of green dots
9. `test_stepdots_active_highlight` — current step is blue
10. `test_stepdots_pending_grey` — future steps are grey

### Previous Story Intelligence (from Story 2.2 & 2.3)

**From Story 2.2 (React frontend scaffold):**
- `frontend/src/types/pipeline.ts` exists — defines `AgentStatus` type and `AGENTS` constant
- Shadcn/ui is initialized — Badge, Avatar components available
- Tailwind CSS configured with "Professional Calm" color system
- Vitest + React Testing Library configured

**From Story 2.3 (BaseAgent lifecycle):**
- Backend sends status updates via WebSocket using `AgentMessage` model
- Status values: `'start'`, `'processing'`, `'review_request'`, `'done'`, `'completed'`
- Frontend receives status in `message.metadata.state` from system messages

**Critical learning:** The connection between frontend and backend is through WebSocket messages. `useWebSocket` hook receives status updates. `usePipelineState` should derive current agent from the active step.

### Git Intelligence (Recent Commits)

Recent commit: `b6fdba1 feat: Stories 2.1 & 2.2 - FastAPI server with WebSocket and React frontend scaffold`

The `AgentTopBar.tsx` and `StepDots.tsx` do NOT exist yet — confirm this before writing files. The frontend components directory exists with UI primitives.

### Project Structure Notes

- **Component naming**: PascalCase files (`AgentTopBar.tsx`), kebab-case in stories
- **Test location**: Colocate tests in `__tests__/` subfolder (or use `.test.tsx` suffix alongside components)
- **Hook updates**: `usePipelineState.ts` needs selectors for current agent and step progress
- **Color handling**: Dynamic hex colors from AGENTS constant require inline style: `style={{ backgroundColor: agent.color }}`

### Design Specifications

**AgentTopBar Layout:**
```
┌─────────────────────────────────────────────────────────┐
│ ┌────┐  Alice           AI Provider Configuration    ●  │
│ │ A  │  Step 1 of 5                                   🟡 │
│ └────┘                              [Processing...]      │
└─────────────────────────────────────────────────────────┘
```

**StepDots Layout:**
```
● ── ● ── ● ── ○ ── ○
↑    ↑    ↑    ↑    ↑
1    2    3    4    5
```

**Combined Layout (App.tsx):**
```tsx
<div className="flex flex-col h-screen">
  <AgentTopBar agent={currentAgent} status={currentStatus} />
  <StepDots currentStep={currentStep} completedSteps={completedSteps} />
  <ChatArea messages={messages} />
  <ChatInputArea state={currentStatus} />
</div>
```

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.4]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#UX-DR2 (AgentTopBar)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#UX-DR6 (StepDots)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#UX-DR8 (Status Badge System)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#UX-DR9 (Color System)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#UX-DR15 (Accessibility)]
- [Source: frontend/src/types/pipeline.ts#AgentStatus + AGENTS]

## Dev Agent Record

### Agent Model Used

### Agent Model Used

Gemini 3.1 Pro (Low)

### Debug Log References

None

### Completion Notes List

- Implemented `AgentTopBar` and `StepDots` using existing shadcn UI components.
- Used lucide-react for icons (Loader2, Eye, Check).
- Ensured proper accessibility with `role="banner"` and `role="progressbar"`.
- Wired into App layout. It turns out `usePipelineState` already exposed the correct info!
- All tests passing perfectly.

### File List

- `frontend/src/components/AgentTopBar.tsx` — NEW
- `frontend/src/components/StepDots.tsx` — NEW
- `frontend/src/components/__tests__/AgentTopBar.test.tsx` — NEW
- `frontend/src/components/__tests__/StepDots.test.tsx` — NEW
- `frontend/src/hooks/usePipelineState.ts` — MODIFY
- `frontend/src/App.tsx` — MODIFY (integrate components)

### Review Findings

- [x] [Review][Patch] StatusBadge uses text 'Ready' instead of 'Start' per AC2 [frontend/src/components/AgentTopBar.tsx:38]
- [x] [Review][Patch] StatusBadge has no graceful fallback if status is missing/invalid [frontend/src/components/AgentTopBar.tsx:35]
