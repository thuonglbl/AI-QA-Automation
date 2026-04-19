# Story 2.5: ChatMessage Component with Rich Content

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a manual QA tester (Linh),
I want to see agent messages and my own messages in a familiar chat layout,
so that interacting with the AI pipeline feels like chatting with a colleague.

## Acceptance Criteria

1. **Given** the conversational chat UI is rendered
   **When** messages are exchanged
   **Then** agent messages display left-aligned with white background and flat bottom-left radius (UX-DR3)
2. **And** user messages display right-aligned with blue background and flat bottom-right radius (UX-DR3)
3. **And** agent messages show avatar, name, and timestamp
4. **And** rich content within bubbles supports rendered markdown via react-markdown with GFM (UX-DR5)
5. **And** code blocks display with syntax highlighting via react-syntax-highlighter (UX-DR5)
6. **And** content exceeding 400px height shows internal ScrollArea (UX-DR5)
7. **And** chat area auto-scrolls to bottom on new messages, with "↓ New message" indicator when scrolled up (UX-DR18)
8. **And** chat messages have `role="listitem"` within chat area `role="list"` (UX-DR15)

## Tasks / Subtasks

- [x] Task 1: Create ChatMessage component base structure (AC: 1, 2, 3, 8)
  - [x] 1.1 Create `frontend/src/components/ChatMessage.tsx`
  - [x] 1.2 Implement left-aligned layout for agent messages (white bg, flat bottom-left radius)
  - [x] 1.3 Implement right-aligned layout for user messages (blue bg, flat bottom-right radius)
  - [x] 1.4 Render Agent avatar (or generic user icon), sender name, and timestamp within message wrapper
  - [x] 1.5 Add ARIA roles: `role="listitem"` for the message container

- [x] Task 2: Implement rich content rendering (AC: 4, 5, 6)
  - [x] 2.1 Add `react-markdown` with `remark-gfm` plugin to support tables/GFM
  - [x] 2.2 Add `react-syntax-highlighter` to provide source code highlighting
  - [x] 2.3 Integrate existing Shadcn `ScrollArea` for rendering blocks exceeding 400px height
  - [x] 2.4 Refactor this rich rendering concern into `frontend/src/components/ReviewContent.tsx` according to UX-DR5 if required

- [x] Task 3: Handle Chat scroll behavior (AC: 7, 8)
  - [x] 3.1 Create `frontend/src/components/ChatArea.tsx` (the parent list container)
  - [x] 3.2 Implement auto-scroll to bottom upon receiving new messages using refs
  - [x] 3.3 Add scroll boundary tracking to detect when the user scrolls up
  - [x] 3.4 Display "↓ New message" overlay button/badge when scrolled up and new message arrives
  - [x] 3.5 Set `role="list"` on the ChatArea container

- [x] Task 4: Write component tests
  - [x] 4.1 Write UI tests testing `ChatMessage` class layouts based on sender
  - [x] 4.2 Test rich rendering components (markdown rendering, code syntax)
  - [x] 4.3 Test scroll tracking and correct toggle behavior of "New message" indicator
  - [x] 4.4 Verify required accessibility attributes

- [x] Task 5: Validation
  - [x] 5.1 Run `npm run lint`, `npm run type-check`, `npm run test`
  - [x] 5.2 Validate rendering manually by mocking a few agent vs. user messages

## Dev Notes

### Component Design Pattern
`ChatMessage` is purely a presentational rendering component. `ChatArea` coordinates scrolling states and houses the message list. Ensure TypeScript types correctly reflect `AgentMessage` schema:

```typescript
// frontend/src/types/pipeline.ts
export interface ChatMessageData {
  id: string;
  sender: 'agent'|'user';
  agent_name?: string;  // e.g. 'Alice'
  content: string;
  timestamp: string; // ISO 8601
}
```

Tailwind typography plugins or localized prose classes may be mapped for markdown lists, headers, etc. Using `"Professional Calm"` tokens makes agent bubbles `bg-white text-slate-900 border border-slate-200` while user bubbles remain `bg-blue-500 text-white`.

For Markdown and Code highlighting, use compatible styling:
```bash
npm install react-markdown remark-gfm react-syntax-highlighter
npm install -D @types/react-syntax-highlighter
```

The "↓ New message" indicator should be a small `Badge` or rounded `Button` located near the bottom of `ChatArea` via absolute positioning (`absolute bottom-4 left-1/2 -translate-x-1/2`).

### Project Structure Notes
- Maintain standard component layout in `frontend/src/components/`.
- Ensure naming follows the PascalCase patterns established (`ChatMessage.tsx`, `ChatArea.tsx`).
- Tests should live within `frontend/src/components/__tests__/`.

### References
- [Source: _bmad-output/planning-artifacts/epics.md#Story 2.5]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR3 (ChatMessage)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR5 (ReviewContent / Rich Text)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR18 (Chat scroll behavior)]
- [Source: _bmad-output/planning-artifacts/epics.md#UX-DR15 (Accessibility)]
- [Source: frontend/src/types/pipeline.ts#AgentMessage (if already defined)]

## Dev Agent Record

### Agent Model Used
Gemini 3.1 Pro (High)

### Debug Log References
- Had to manually install `@tailwindcss/typography`.
- Configured Radix ScrollArea component to support `viewportRef` and `onScroll` manually because `@radix-ui/react-scroll-area` primitive lacks direct exposure of these on the root.

### Completion Notes List
✅ Implemented `ChatMessage` with avatar, generic timestamp, and specific roles.
✅ Added `ReviewContent` component integrating `react-markdown` and `react-syntax-highlighter`.
✅ Created `ChatArea` that auto-scrolls to the bottom on new message if the user is already at the bottom, and conditionally shows a "New message" arrow badge if they are scrolled up.
✅ Tests created successfully for `ChatMessage.test.tsx`, `ReviewContent.test.tsx`, and `ChatArea.test.tsx`.
✅ Lint and static types verified.
✅ Resolved code review readiness and updated status.

### Code Review Fixes Applied
✅ **System message handling**: Added proper 'system' sender type support with distinct styling.
✅ **Date validation**: Added safe timestamp parsing to prevent crashes on invalid dates.
✅ **Long text overflow**: Added `break-all` fallback for user messages with long contiguous strings.
✅ **Scroll performance**: Implemented debounced scroll handler (~60fps) to prevent stuttering.
✅ **Button type safety**: Added `type="button"` to prevent unintended form submission.
✅ **TypeScript strictness**: Removed all `any` types, added proper interfaces for component props.
✅ **Test pollution fix**: Added proper cleanup/teardown for global mocks and DOM property overrides.
✅ **Scroll detection**: Improved bottom detection with `Math.ceil()` for fractional pixel handling.

### File List
- `[NEW] frontend/src/components/ChatMessage.tsx`
- `[NEW] frontend/src/components/ReviewContent.tsx`
- `[NEW] frontend/src/components/ChatArea.tsx`
- `[NEW] frontend/src/components/ui/scroll-area.tsx`
- `[NEW] frontend/src/components/__tests__/ChatMessage.test.tsx`
- `[NEW] frontend/src/components/__tests__/ReviewContent.test.tsx`
- `[NEW] frontend/src/components/__tests__/ChatArea.test.tsx`
- `[MODIFY] frontend/tailwind.config.js`
- `[MODIFY] _bmad-output/implementation-artifacts/sprint-status.yaml`
