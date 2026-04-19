# Story 2.6: ChatInputArea Component (State-Dependent Actions)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a manual QA tester (Linh),
I want the input area to show the right buttons based on what's happening,
so that I always know what action to take next.

## Acceptance Criteria

1. **Given** the pipeline is in Start state
   **When** the UI renders
   **Then** input area shows input field(s) + Start button (UX-DR4)

2. **Given** the pipeline is in Processing state
   **When** the state changes
   **Then** input area shows disabled area with "Agent is working..." text (UX-DR4)

3. **Given** the pipeline is in Review state
   **When** the state changes
   **Then** input area shows Approve (green solid) + Reject (red outline) buttons (UX-DR4, UX-DR11)

4. **Given** the pipeline is in Reject-feedback state
   **When** Reject is clicked
   **Then** input area shows textarea + Submit button (UX-DR4)

5. **Given** the pipeline is in Done state
   **When** the state changes
   **Then** input area shows Continue button (blue solid) (UX-DR4)

6. **Given** any state transition
   **When** buttons are rendered
   **Then** max 2 buttons visible at a time, primary action on the right (UX-DR11)

7. **Given** the Start button is disabled
   **When** user hovers over it
   **Then** tooltip explains why (e.g., "Enter Confluence URL to start") (UX-DR11)

8. **Given** user clicks Reject
   **When** the action triggers
   **Then** no confirmation dialog — Reject opens feedback inline (UX-DR11)

9. **Given** state transition occurs
   **When** new state renders
   **Then** focus automatically moves to primary action (UX-DR15)

10. **Given** state transitions
    **When** animating
    **Then** badge fades 150ms, input slides up 200ms, messages fade-in 150ms (UX-DR13)

## Tasks / Subtasks

- [x] Task 1: Create ChatInputArea component structure (AC: 1, 6, 9, 10)
  - [x] 1.1 Create `frontend/src/components/ChatInputArea.tsx`
  - [x] 1.2 Define TypeScript props interface accepting `state`, `onStart`, `onApprove`, `onReject`, `onSubmitFeedback`, `onContinue`, `disabledReason`
  - [x] 1.3 Implement state-based conditional rendering for all 5 states
  - [x] 1.4 Add focus management with `useEffect` to focus primary action on state change
  - [x] 1.5 Implement transition animations using Tailwind transition utilities

- [x] Task 2: Implement Start state UI (AC: 1, 7)
  - [x] 2.1 Render dynamic input fields based on current step requirements
  - [x] 2.2 Add Start button (primary/solid blue)
  - [x] 2.3 Implement disabled state with tooltip using Shadcn Tooltip component
  - [x] 2.4 Add validation feedback for required fields

- [x] Task 3: Implement Processing state UI (AC: 2)
  - [x] 3.1 Render disabled overlay with "Agent is working..." message
  - [x] 3.2 Ensure inputs are disabled and visually indicate non-interactivity
  - [x] 3.3 Show ProcessingIndicator component (from Story 2.7) or placeholder

- [x] Task 4: Implement Review state UI (AC: 3, 6, 8)
  - [x] 4.1 Render Approve button (green solid, primary/right)
  - [x] 4.2 Render Reject button (red outline, secondary/left)
  - [x] 4.3 Implement inline feedback textarea expansion on Reject click (no modal)
  - [x] 4.4 Ensure button hierarchy follows UX-DR11 (max 2 buttons, primary right)

- [x] Task 5: Implement Reject-feedback state UI (AC: 4)
  - [x] 5.1 Render textarea for rejection feedback input
  - [x] 5.2 Render Submit button (primary/solid)
  - [x] 5.3 Add character count and placeholder text guidance
  - [x] 5.4 Ensure textarea auto-focuses when state activates

- [x] Task 6: Implement Done state UI (AC: 5)
  - [x] 6.1 Render Continue button (blue solid, primary)
  - [x] 6.2 Handle final step (Step 5) showing "Completed" button instead
  - [x] 6.3 Ensure button triggers transition to next agent/step

- [x] Task 7: Write component tests
  - [x] 7.1 Test state-based conditional rendering for all 5 states
  - [x] 7.2 Test button hierarchy and positioning (max 2, primary right)
  - [x] 7.3 Test tooltip behavior on disabled Start button
  - [x] 7.4 Test focus management on state transitions
  - [x] 7.5 Test inline Reject feedback flow (no modal confirmation)
  - [x] 7.6 Test callback handlers are invoked correctly

- [x] Task 8: Integration and validation
  - [x] 8.1 Integrate with `ChatArea` component from Story 2.5
  - [x] 8.2 Run `npm run lint`, `npm run typecheck`, `npm run test`
  - [x] 8.3 Manual validation of all 5 state transitions

## Dev Notes

### State Machine Reference

The ChatInputArea component implements the UI layer of the universal state transition machine (UX-DR13):

```
Start → Processing → ReviewRequest → Done
   ↑         ↓           ↓
   └─────────┴────── RejectFeedback (with feedback → back to Processing)
```

**State Definitions:**

| State | UI Elements | Primary Action | Secondary Action |
|-------|-------------|----------------|------------------|
| `start` | Input field(s) + Start | Start (blue solid, right) | — |
| `processing` | Disabled overlay + status | — (disabled) | — |
| `review` | Approve/Reject buttons | Approve (green solid, right) | Reject (red outline, left) |
| `reject_feedback` | Textarea + Submit | Submit (blue solid, right) | — |
| `done` | Continue button | Continue (blue solid, right) | — |

### Component Props Interface

```typescript
// frontend/src/types/pipeline.ts
export interface ChatInputAreaProps {
  state: 'start' | 'processing' | 'review' | 'reject_feedback' | 'done';
  stepNumber: number; // 1-5, for determining "Continue" vs "Completed"
  isLastStep: boolean; // true for Step 5
  inputConfig?: {
    fields: Array<{
      name: string;
      label: string;
      type: 'text' | 'url' | 'password' | 'textarea';
      placeholder?: string;
      required?: boolean;
      validation?: (value: string) => string | null; // returns error message or null
    }>;
  };
  disabledReason?: string; // Tooltip text when Start is disabled
  isLoading?: boolean;
  onStart: (values: Record<string, string>) => void;
  onApprove: () => void;
  onReject: () => void;
  onSubmitFeedback: (feedback: string) => void;
  onContinue: () => void;
}
```

### Animation Implementation

Use Tailwind CSS transition utilities:

```typescript
// For state transitions (UX-DR13)
<div className="transition-all duration-150 ease-in-out">
  {/* Content fades 150ms */}
</div>

<div className="animate-slide-up duration-200">
  {/* Input slides up 200ms */}
</div>
```

Custom keyframe for slide-up (add to `tailwind.config.js` if not present):

```javascript
// tailwind.config.js
module.exports = {
  theme: {
    extend: {
      keyframes: {
        'slide-up': {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
      animation: {
        'slide-up': 'slide-up 200ms ease-out',
      },
    },
  },
}
```

### Button Hierarchy & Styling

Per UX-DR11 and UX-DR9 (Professional Calm color system):

| Button | Variant | Color | Position |
|--------|---------|-------|----------|
| Start | `default` (solid) | `bg-blue-500` | Right (primary) |
| Approve | `default` (solid) | `bg-green-500` | Right (primary) |
| Reject | `outline` | `border-red-500 text-red-500` | Left (secondary) |
| Submit | `default` (solid) | `bg-blue-500` | Right (primary) |
| Continue | `default` (solid) | `bg-blue-500` | Right (primary) |
| Completed | `default` (solid) | `bg-green-500` | Right (primary) |

### Focus Management

Use `useEffect` with `useRef` to manage focus:

```typescript
const primaryButtonRef = useRef<HTMLButtonElement>(null);

useEffect(() => {
  // Focus primary action when state changes
  primaryButtonRef.current?.focus();
}, [state]);
```

### Tooltip Implementation

Use Shadcn/ui Tooltip component for disabled Start button:

```typescript
<TooltipProvider>
  <Tooltip>
    <TooltipTrigger asChild>
      <Button disabled={!canStart}>Start</Button>
    </TooltipTrigger>
    <TooltipContent>
      <p>{disabledReason || "Enter required information to start"}</p>
    </TooltipContent>
  </Tooltip>
</TooltipProvider>
```

### Inline Reject Feedback Pattern

No confirmation dialog — expand inline:

```typescript
// When state === 'reject_feedback'
<div className="space-y-4">
  <Textarea
    placeholder="Please explain what needs to be corrected..."
    value={feedback}
    onChange={(e) => setFeedback(e.target.value)}
    autoFocus
  />
  <div className="flex justify-end">
    <Button onClick={() => onSubmitFeedback(feedback)}>Submit</Button>
  </div>
</div>
```

### Project Structure Notes

- Component location: `frontend/src/components/ChatInputArea.tsx`
- Types location: `frontend/src/types/pipeline.ts` (ensure `ChatInputAreaProps` is defined)
- Tests location: `frontend/src/components/__tests__/ChatInputArea.test.tsx`
- Use existing Shadcn components: `Button`, `Input`, `Textarea`, `Tooltip`, `Badge`

### Dependencies

Ensure these are installed (from previous stories):

```bash
# Should already be present from Story 2.2
npm install @radix-ui/react-tooltip
```

### Integration with Pipeline State

The `ChatInputArea` receives its state from parent component (likely `App.tsx` or a pipeline state manager). Ensure the state machine transitions are handled upstream:

```typescript
// Parent component pattern
const [pipelineState, setPipelineState] = useState<PipelineState>('start');

<ChatInputArea
  state={pipelineState}
  onStart={(values) => {
    setPipelineState('processing');
    // Trigger agent processing
  }}
  onApprove={() => setPipelineState('done')}
  onReject={() => setPipelineState('reject_feedback')}
  onSubmitFeedback={(feedback) => {
    setPipelineState('processing');
    // Trigger re-processing with feedback
  }}
  onContinue={() => {
    // Advance to next step or agent
  }}
/>
```

### Accessibility Requirements (UX-DR15)

- All buttons must have descriptive `aria-label` when icon-only or context-dependent
- Tooltip must be keyboard accessible (standard Shadcn Tooltip behavior)
- Focus indicator: `ring-2 ring-blue-500 ring-offset-2` on all interactive elements
- Form inputs must have associated `<Label>` elements
- Minimum 44px click targets for all buttons
- Status changes announced via `aria-live="polite"` on parent container

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.6]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR4 (ChatInputArea)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR11 (Button Hierarchy)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR13 (State Transitions)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR15 (Accessibility)]
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md#Core Interaction Flow]
- [Source: _bmad-output/planning-artifacts/architecture.md#Frontend & API Layer]
- [Source: 2-5-chatmessage-component-with-rich-content.md#Dev Notes (ChatArea integration)]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4

### Debug Log References

<!-- To be filled by dev agent -->

### Completion Notes List

- Implemented ChatInputArea component with all 5 state transitions
- Added shadcn/ui components: Button, Input, Textarea, Tooltip, Label
- Updated tailwind.config.js with slide-up animation
- Added ChatInputAreaProps and InputFieldConfig types to pipeline.ts
- Created comprehensive test suite with 26 tests covering all acceptance criteria
- All 47 frontend tests passing
- TypeScript type-check and ESLint validation passing

### File List

<!-- To be filled by dev agent -->
- `[NEW] frontend/src/components/ChatInputArea.tsx`
- `[NEW] frontend/src/components/__tests__/ChatInputArea.test.tsx`
- `[MODIFY] frontend/src/types/pipeline.ts` (add ChatInputAreaProps if not exists)
