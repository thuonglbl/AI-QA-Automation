# Story 3.5: Bob Agent — Extract Requirements with Paginated Review

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a manual QA tester (Linh),
I want Bob to extract my Confluence pages and let me review each one side-by-side with the original,
So that I can verify the extraction is accurate before proceeding.

## Acceptance Criteria

1. **Given** Bob's step begins after Alice completes
   **When** Bob greets the user
   **Then** Bob introduces himself: "Hi! I'm Bob, and I'll help you extract requirements from Confluence." (UX-DR19, blue avatar)
   **And** guidance text explains MCP PAT setup if first time (UX-DR20)
   **And** user enters Confluence project URL (required) and Jira URL (optional)
2. **Given** user clicks Start
   **When** Bob processes the request
   **Then** Bob connects to MCP, navigates Confluence space, extracts pages
   **And** Processing indicator shows progress per page (e.g., "Reading page 3 of 5...")
3. **Given** extraction completes
   **When** Review Request is presented
   **Then** split panel shows: left = link to open original Confluence page in new tab, right = rendered markdown (not raw) (UX-DR16)
   **And** Next/Previous buttons navigate between pages (UX-DR14)
   **And** Approve applies to current page only, auto-advances to next (UX-DR14)
   **And** Reject opens feedback textarea, Bob re-processes that single page with feedback context
   **And** after all pages approved, status changes to Done with summary: "X files saved to requirements/"
   **And** output saved to `workspace/requirements/` folder
   **And** chat history clears when transitioning to next agent (UX-DR18)

## Technical Requirements

### Core Functionality

Implement `BobAgent` class in `src/ai_qa/agents/bob.py` inheriting from `BaseAgent`:
- Must support Start, Processing, Review, and Done states.
- Uses `src/ai_qa/mcp/` methods to connect to MCP.
- Orchestrate parsing through `ConfluenceReader` and `ContentParser` pipeline stages (implemented in 3.2 and 3.3).
- Utilize the `OutputWriter` pipeline stage (implemented in 3.4) to save outputs to `workspace/requirements/`.
- Handle pagination of pages via WebSocket for incremental review.

### UI Components

- Implement the Split Panel review interface in the frontend UI (`SplitPanel.tsx`).
- Customize `ChatInputArea` based on Bob's specific input requirements (Confluence URL, optional Jira).
- Store/read inputs using `localStorage` for UX-DR20.

## Architecture Compliance

- Follow `BaseAgent` lifecycle (Story 2.3).
- Exchange data through typed, validated Pydantic models (e.g. `StageResult` everywhere, never raw dicts).
- All JSON output uses snake_case keys; datetimes use ISO 8601.
- Continue to avoid raw `Exception` throws or bare `except:`. Must return `StageResult(success=False, errors=[...])`.

## Previous Story Intelligence (Story 3.4)

- Ensure that any new metadata creation adheres to `OutputMetadata` Pydantic models with `model_config = ConfigDict(validate_assignment=True)`.
- Re-use the existing `OutputWriter` class implementation logic for folder storage guarantees and to prevent partial output corruption.

## Tasks/Subtasks

- [ ] Create `BobAgent` class extending `BaseAgent` in `src/ai_qa/agents/bob.py`
  - [ ] Implement `start` lifecycle state
  - [ ] Implement `process` logic integrating ConfluenceReader and ContentParser
  - [ ] Implement `review` state managing pagination
  - [ ] Implement `complete` state writing with OutputWriter
- [ ] Export `BobAgent` in `src/ai_qa/agents/__init__.py`
- [ ] Implement `SplitPanel.tsx` in frontend for side-by-side review
- [ ] Modify `ChatInputArea.tsx` with specific Bob inputs and localStorage for MCP PAT
- [ ] Add unit tests for `BobAgent` lifecycle logic
- [ ] Confirm all code passes tests and linters

## File List
(To be populated)

## Change Log
(To be populated)

## Dev Agent Record

### Agent Model Used

Gemini-3.1-Pro

### Completion Notes

Ultimate context engine analysis completed - comprehensive developer guide created.
