---
baseline_commit: 9d878c5
---

# Story 11.6: Bob Reviewable Extraction Output

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to review Bob's extracted Confluence/Jira output before it is saved,
so that I can verify source requirements were captured correctly.

## Acceptance Criteria

### AC1 â€” Review state shows source links, rendered Markdown, and warnings

**Given** Bob completes extraction and parsing
**When** the review state is presented
**Then** the UI shows source reference links and **rendered** extracted Markdown content (not just a raw text box)
**And** extraction warnings are visible **inside the review content** (per item).

### AC2 â€” Multi-item navigation with clear batch scope

**Given** multiple pages or tickets are extracted
**When** the user reviews output
**Then** the user can navigate between extracted items with **Next/Previous** controls
**And** approval applies to the **current item**, with the batch scope (which item, how many resolved) clearly shown by the UI.

### AC3 â€” Reject an item with feedback â†’ Bob reprocesses and re-presents

**Given** the user rejects an extracted item with feedback
**When** feedback is submitted
**Then** Bob reprocesses that item where possible (re-runs the requirement conversion with the feedback as guidance)
**And** Bob acknowledges the feedback conversationally **before** retrying
**And** the reprocessed item is presented again in the same review UI.

---

## âš ï¸ CRITICAL: This is the capstone REVIEW-UX story. It wires the half-built pagination, renders the warnings 11.5 already produces, and turns the dead `handle_reject` stub into a real reprocess loop

By the time control reaches this story, the backend already **assembles `self.pages`** (Confluence from 11.3, the Jira supplement from 11.4) and **attaches `quality_issues`** to each page (11.5). The frontend already **receives that payload** and renders a `SplitPanel`. Three things are broken / missing, one per AC:

1. **AC1 â€” warnings are produced but never shown, and Markdown is shown raw.** 11.5 attaches `quality_issues` to every page and 11.3 attaches `warnings`, but the `SplitPanel` renders neither, and the right pane is a **raw editable `<textarea>`** (no rendered preview). This story renders both: a per-item warnings banner + a **Preview/Edit tab** using the existing `ReviewContent` markdown renderer.
2. **AC2 â€” pagination is half-wired and non-functional.** `SplitPanel` is rendered with **`currentIndex={0}` hardcoded** ([App.tsx:1627](frontend/src/App.tsx)) and has **no Next/Previous controls**, so today only page 0 is ever reviewable. The backend advances a `current_page_index` counter that the frontend never reads. This story makes the `SplitPanel` own a real `currentIndex` (local state + Prev/Next) and switches the backend's DONE-trigger from a fragile counter to a **resolved-page-id set**.
3. **AC3 â€” there is no reject affordance, and `process(feedback)` is a do-nothing stub.** The `SplitPanel` only has "Approved" / "Not requirement"; there is **no Reject button**. `BobAgent.process(feedback)` returns the page **unchanged** ([bob.py:139-153](src/ai_qa/agents/bob.py)), and `handle_reject` re-emits a payload shape (`is_paginated`/`result`) the frontend **does not consume**. This story adds the reject-with-feedback UI, makes `process(feedback)` **actually re-run the LLM formatter with the feedback**, targets the rejected page by `page_id`, and re-emits the **same `is_review_ready` payload** so the panel re-renders.

### Confirmed scope decisions (Thuong, 2026-06-11) â€” implement exactly these

- **AC3 reprocess depth = full LLM re-run.** `process(feedback)` re-runs `RequirementFormatter` on the page's stored `raw_html` with the feedback woven into the prompt, regenerating `requirement_md`. "Where possible" = when `raw_html` is present and the LLM call succeeds; when there is **no** `raw_html` (e.g. a Jira item from 11.4, `raw_html=""`) or the LLM errors, fall back to **re-presenting the item unchanged for manual edit** with a clear info message â€” never crash the reject loop.
- **AC1 rendered Markdown = Preview/Edit tabs.** The right pane of the `SplitPanel` gets two tabs: **Preview** (default, rendered via `ReviewContent`) and **Edit** (the existing `<textarea>`). Approve still sends the (possibly edited) Markdown. Edit-before-approve is preserved.

### In scope

- Frontend: rewrite `SplitPanel` to add (a) a per-item warnings banner (AC1), (b) Preview/Edit tabs (AC1), (c) Next/Previous navigation + batch progress (AC2), (d) a Reject-with-feedback affordance (AC3). Wire a new `handleBobReject` in `App.tsx` and extend the page/quality TypeScript types.
- Backend: switch Bob's DONE-trigger to a resolved-page-id set (AC2); make `process(feedback)` a real reprocess via the formatter (AC3); target the rejected page by `page_id`; re-emit the `is_review_ready` payload after reprocess; thread an optional `data` arg through `handle_reject` (base + all four overrides, ignored by the others); accept `feedback` in `RequirementFormatter`.

### Out of scope (do NOT build)

- **No new requirement-save semantics.** Approval still saves via the existing `PipelineArtifactAdapter.save_requirement_page` / `save_metadata` path (including 11.5's acknowledgement metadata). The dedicated project-artifact save under `projects/{id}/requirements/` with full metadata is **Story 11.7** â€” do not pull it forward.
- **No DB migration, no new package, no schema change.** Pages already carry every key this story renders.
- **No LLM quality scoring.** Quality detection stays 11.5's deterministic scan; 11.6 only **renders** what 11.5 produces. Model-driven scoring is Epic 12 / Story 12.3.
- **Do not resurrect the dormant `ChatInputArea` review/nav/reject state machine.** It exists ([ChatInputArea.tsx](frontend/src/components/ChatInputArea.tsx)) with a full `review`/`reject_feedback` flow and Prev/Next, but **it is not rendered anywhere in `App.tsx`** â€” Bob's review is the bespoke inline `SplitPanel`. Use `ChatInputArea` only as a **reference pattern**; enhance the `SplitPanel` in place.
- **No change to the confirm-parent flow, the MCP/connect path, secret resolution, or `_extract_descendants`'s extraction logic.** The single-MCP-client + disconnect invariants are untouched (the reject reprocess opens **no** MCPClient â€” it uses only the LLM formatter).

### What ALREADY EXISTS (reuse â€” do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `SplitPanel` review component (source iframe + editable markdown textarea + Approve/Skip) | [frontend/src/components/SplitPanel.tsx](frontend/src/components/SplitPanel.tsx) | âœ… exists â€” **rewrite to add warnings, tabs, nav, reject** |
| `SplitPanel` render site (with `currentIndex={0}` hardcoded) | [frontend/src/App.tsx:1617-1634](frontend/src/App.tsx) | âœ… exists â€” **drop the hardcoded index; pass `onReject`** |
| `is_review_ready` handler â€” sets `bobState.extractedPages` from `metadata.pages` | [frontend/src/App.tsx:753-766](frontend/src/App.tsx) | âœ… done â€” pages already carry `quality_issues`/`warnings`/`source_type`; **no handler change, only types** |
| `handleBobApprove` / `handleBobSkip` â€” send `{type:"approve", step:2, data:{action, page_id, markdown?}}` | [frontend/src/App.tsx:973-999](frontend/src/App.tsx) | âœ… done â€” **add `handleBobReject` alongside** |
| `sendMessage` â€” auto-injects `projectId`/`threadId`; transports any object as JSON | [frontend/src/hooks/useWebSocket.ts:235-262](frontend/src/hooks/useWebSocket.ts) | âœ… done â€” reuse for reject |
| `ReviewContent` â€” renders Markdown via `react-markdown`+`remark-gfm`, mermaid, syntax highlighting, tables | [frontend/src/components/ReviewContent.tsx:30-96](frontend/src/components/ReviewContent.tsx) | âœ… done â€” **use for the Preview tab** (AC1) |
| `Badge` UI primitive; amber warning styling convention (`bg-amber-50 border-amber-200 text-amber-800` + `AlertTriangle`) | [frontend/src/components/ui/badge.tsx](frontend/src/components/ui/badge.tsx), [frontend/src/components/artifacts/ArtifactNotice.tsx:32-39](frontend/src/components/artifacts/ArtifactNotice.tsx) | âœ… done â€” reuse for the warnings banner |
| `ChatInputArea` reject-feedback + Prev/Next pattern (textarea, 1000-char cap, ChevronLeft/Right nav) | [frontend/src/components/ChatInputArea.tsx:276-382](frontend/src/components/ChatInputArea.tsx) | âœ… reference only â€” **mirror, do not wire in** |
| Per-page dict shape: `page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md` (+ `parsed_markdown`/`warnings` from 11.3, `source_type` from 11.4, `quality_issues` from 11.5) | [src/ai_qa/agents/bob.py:461-469](src/ai_qa/agents/bob.py) | âœ… done â€” read defensively |
| `BobAgent.handle_approve` (confirm-parent + markdown-review branches) | [src/ai_qa/agents/bob.py:513-599](src/ai_qa/agents/bob.py) | âœ… exists â€” **switch DONE-trigger to resolved-id set; resolve on skip too** |
| `BobAgent.handle_reject` (conversational ack + re-process + re-present, wrong payload shape) | [src/ai_qa/agents/bob.py:601-643](src/ai_qa/agents/bob.py) | âœ… exists â€” **target by page_id; re-emit `is_review_ready`; keep ack** |
| `BobAgent.process(feedback)` â€” stub returning current page unchanged | [src/ai_qa/agents/bob.py:139-153](src/ai_qa/agents/bob.py) | âœ… exists â€” **replace stub with real formatter re-run** |
| `RequirementFormatter.convert_page` / `_format_story` â€” LLM HTMLâ†’requirement conversion | [src/ai_qa/pipelines/requirement_formatter.py:23-114](src/ai_qa/pipelines/requirement_formatter.py) | âœ… done â€” **add optional `feedback`** |
| WS dispatch: `reject` â†’ `feedback = message.get("feedback","")` â†’ `handle_reject(feedback)` | [src/ai_qa/api/websocket.py:319-321](src/ai_qa/api/websocket.py) | âœ… exists â€” **also pass `data`** |
| `handle_reject(self, feedback)` on base + Alice/Mary/Sarah/Bob | [src/ai_qa/agents/base.py:349](src/ai_qa/agents/base.py), [alice.py:856](src/ai_qa/agents/alice.py), [mary.py:163](src/ai_qa/agents/mary.py), [sarah.py:572](src/ai_qa/agents/sarah.py) | âœ… exists â€” **add optional `data` param to all (others ignore it)** |
| `message_type="warning"` rendering (chat) | [frontend/src/components/ChatMessage.tsx:31-42](frontend/src/components/ChatMessage.tsx) | âœ… renders, but no distinct warning style â€” **optional small amber style** |

---

## Tasks / Subtasks

- [x] **Task 1 â€” Frontend types: extend the page + add `QualityIssue` (AC1)**
  - [x] 1.1 Create a shared type module (or extend an existing one) so `App.tsx` and `SplitPanel.tsx` import the **same** `ExtractedPage` â€” today both declare it locally and they will drift. Add to `frontend/src/types/pipeline.ts` (or a new `frontend/src/types/extraction.ts`):
    - `export interface QualityIssue { category: string; location: string; message: string; impact: string; }` â€” mirrors the backend `QualityIssue` from 11.5 ([src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py)).
    - `export interface ExtractedPage { page_id: string; page_title: string; source_url: string; raw_html: string; requirement_md: string; warnings?: string[]; quality_issues?: QualityIssue[]; source_type?: string; }` â€” the optional `?` keys degrade gracefully if 11.3/11.4/11.5 are not all merged.
  - [x] 1.2 In `App.tsx`, change `BobState.extractedPages` to `ExtractedPage[] | null` (import the shared type) and delete the inline object-literal type ([App.tsx:178-184](frontend/src/App.tsx)). In `SplitPanel.tsx`, delete its local `ExtractedPage` ([SplitPanel.tsx:6-12](frontend/src/components/SplitPanel.tsx)) and import the shared one. (Full-stack-sync rule: backend payload keys â†’ TS interface.)

- [x] **Task 2 â€” Rewrite `SplitPanel` for warnings + tabs + navigation + reject (AC1/AC2/AC3)**
  - [x] 2.1 **Own the current index locally (AC2).** Replace the `currentIndex` prop with `const [currentIndex, setCurrentIndex] = useState(0)`. Clamp on `pages.length` change (`useEffect` â†’ if `currentIndex >= pages.length`, reset). Keep the `[page]`-keyed `useEffect` that resets `markdownContent` so the Edit textarea always reflects the current (or reprocessed) page. Compute `totalPages = pages.length` internally (drop the `totalPages`/`currentIndex` props from `SplitPanelProps`).
  - [x] 2.2 **Track resolved items locally for batch scope (AC2).** Add `const [resolvedIds, setResolvedIds] = useState<Set<string>>(new Set())`. On approve/skip, add the page_id and **auto-advance** to the next unresolved page (if any). Reject does **not** add to `resolvedIds`. Header/nav shows `({currentIndex + 1} of {totalPages}) â€” {resolvedIds.size} resolved` so the batch scope is explicit (AC2 "clear batch scope shown by the UI").
  - [x] 2.3 **Navigation bar (AC2).** Add Previous/Next buttons (mirror [ChatInputArea.tsx:284-313](frontend/src/components/ChatInputArea.tsx): `ChevronLeft`/`ChevronRight`, `variant="outline" size="sm"`, `aria-label="Previous item"`/`"Next item"`, disabled at the ends). Only show the bar when `totalPages > 1`.
  - [x] 2.4 **Source link + source type (AC1).** Keep the "Open Original" link; label it by `page.source_type` (e.g. "Open in Jira" when `source_type === "jira"`, else "Open Original"). Keep `target="_blank" rel="noopener noreferrer"` and the `ExternalLink` icon.
  - [x] 2.5 **Warnings banner (AC1).** Above the split layout, if `(page.quality_issues?.length || page.warnings?.length)`, render an amber banner (`bg-amber-50 border border-amber-200 text-amber-800 rounded-md p-3`, `AlertTriangle` icon â€” matching [ArtifactNotice.tsx:32-39](frontend/src/components/artifacts/ArtifactNotice.tsx)). For each `quality_issue`, show a `<Badge>` with the `category` + the `message`, and a muted line for `impact`. Also fold raw `page.warnings` strings (11.3) that are not already covered by a `quality_issue` of category `unsupported_content`. Keep it compact and scrollable if long.
  - [x] 2.6 **Preview/Edit tabs on the right pane (AC1).** Replace the bare `<textarea>` with two tabs (a lightweight local `useState<"preview"|"edit">("preview")` toggle â€” no new dependency needed; a simple segmented control of two buttons is fine, mirror the project's tab styling). **Preview** renders `<ReviewContent content={markdownContent} />` (rendered Markdown, mermaid, tables). **Edit** renders the existing editable `<textarea bind markdownContent>`. Default to **Preview**. Approve sends `markdownContent` (edited or not), unchanged from today.
  - [x] 2.7 **Reject-with-feedback affordance (AC3).** Add a `Reject` button to the footer (left, outline/red â€” mirror [ChatInputArea.tsx:318-326](frontend/src/components/ChatInputArea.tsx)). Clicking it reveals an inline feedback `<textarea>` (placeholder "Describe what needs to be changedâ€¦", `maxLength={1000}`, char counter) with a **Submit** button. Submit calls a new `onReject(page.page_id, feedback)` prop and hides the textarea. Disable Submit while feedback is empty or `disabled`. Keep the existing "Not requirement" (skip) and "Approved" buttons.
  - [x] 2.8 **Props.** New `SplitPanelProps`: `{ pages: ExtractedPage[]; onApprove: (pageId, markdown) => void; onSkip: (pageId) => void; onReject: (pageId, feedback) => void; disabled?: boolean; className?: string }`. Remove `currentIndex`/`totalPages` (now internal).

- [x] **Task 3 â€” Wire reject + drop the hardcoded index in `App.tsx` (AC2/AC3)**
  - [x] 3.1 Add `handleBobReject` next to `handleBobApprove`/`handleBobSkip` ([App.tsx:973-999](frontend/src/App.tsx)):

    ```tsx
    const handleBobReject = useCallback(
      (pageId: string, feedback: string) => {
        if (!selectedProjectId) return;
        sendMessage({
          type: "reject",
          step: 2,
          feedback,
          data: { page_id: pageId },
        });
      },
      [selectedProjectId, sendMessage],
    );
    ```

    `feedback` is top-level (the WS layer reads `message.get("feedback")` at [websocket.py:320](src/ai_qa/api/websocket.py)); `data.page_id` rides alongside (Task 5 reads it).
  - [x] 3.2 Update the `SplitPanel` render ([App.tsx:1625-1632](frontend/src/App.tsx)): remove `currentIndex={0}` and `totalPages={...}`, add `onReject={handleBobReject}`. Keep the `isBobStep && status === "review_request" && bobState.isPaginating && bobState.extractedPages` guard.
  - [x] 3.3 (Optional, low-risk AC1 bonus) Add amber styling for `message.messageType === "warning"` in [ChatMessage.tsx:31-42](frontend/src/components/ChatMessage.tsx) (`bg-amber-50 text-amber-900 border border-amber-200`) so 11.5's chat-side warning summary is visually distinct. The **in-panel** banner (Task 2.5) is the primary AC1 deliverable; this is a small nicety.

- [x] **Task 4 â€” Backend: resolved-id set drives DONE; resolve on skip too (AC2)**
  - [x] 4.1 In `BobAgent.__init__` ([bob.py:28-40](src/ai_qa/agents/bob.py)) add `self._resolved_page_ids: set[str] = set()` alongside the other attributes.
  - [x] 4.2 Rewrite the markdown-review tail of `handle_approve` ([bob.py:560-599](src/ai_qa/agents/bob.py)) so it (a) handles **both** `action == "approved"` and `action == "not_requirement"`, (b) points `current_page_index` at the acted page (used by the reject path), (c) saves only on approve (preserving 11.5's acknowledgement metadata if 11.5 is merged), (d) resolves the page id for **either** action, and (e) transitions to DONE only when **every** page id is resolved:

    ```python
        # Markdown Review Phase (Split Panel)
        if data and data.get("action") in ("approved", "not_requirement"):
            action = data.get("action")
            page_id = data.get("page_id")
            page = next((p for p in self.pages if p["page_id"] == page_id), None)
            if page is not None:
                # Keep the index pointed at the acted page (the reject path reuses it)
                self.current_page_index = self.pages.index(page)
                if action == "approved":
                    updated_markdown = data.get("markdown")
                    if updated_markdown:
                        page["requirement_md"] = updated_markdown
                        if self.project_context is None:
                            raise ValueError("BobAgent requires an active project context.")
                        adapter = PipelineArtifactAdapter(self.project_context)
                        adapter.save_requirement_page(
                            f"{page['page_id']}/requirement.md", updated_markdown
                        )
                        adapter.save_metadata(
                            f"{page['page_id']}/requirement.metadata.json",
                            {
                                "source_url": page["source_url"],
                                "extracted_at": datetime.now(UTC).isoformat(),
                                # (11.5 acknowledgement fields stay here if 11.5 is merged)
                            },
                        )
                        self.output_files_saved += 1
                if page_id:
                    self._resolved_page_ids.add(page_id)

        # DONE only when every extracted page has been approved or skipped.
        if self.pages and len(self._resolved_page_ids) >= len(self.pages):
            await self.transition_to(AgentState.DONE)
            await self.send_message(
                f"Saved {self.output_files_saved} approved requirements. "
                "I'm handing off to Mary to create test cases.",
                "success",
            )
            return
        # Otherwise the frontend stays on the review payload and navigates locally.
    ```

    > Snippet-fidelity note: this **replaces** the old `if data and data.get("action") == "approved":` block **and** the trailing `self.current_page_index += 1` / `if self.current_page_index >= len(self.pages):` logic ([bob.py:561-599](src/ai_qa/agents/bob.py)). The **confirm-parent branch** above it ([bob.py:515-558](src/ai_qa/agents/bob.py)) is **unchanged** â€” do not touch it. If 11.5 is merged, keep its acknowledgement fields (`quality_warnings_acknowledged`, `acknowledged_quality_issues`, `acknowledged_at`) in the `save_metadata` dict.

- [x] **Task 5 â€” Backend: real reprocess + page-targeted, re-rendering reject (AC3)**
  - [x] 5.1 **Thread an optional `data` arg through `handle_reject`.** Change the signature on the base and **all four** overrides to `async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None`. Alice/Mary/Sarah/base **ignore** `data` (no behavior change â€” keeps mypy-strict override compatibility). Files: [base.py:349](src/ai_qa/agents/base.py), [alice.py:856](src/ai_qa/agents/alice.py), [mary.py:163](src/ai_qa/agents/mary.py), [sarah.py:572](src/ai_qa/agents/sarah.py), [bob.py:601](src/ai_qa/agents/bob.py).
  - [x] 5.2 **Pass `data` from the WS dispatch.** In [websocket.py:319-321](src/ai_qa/api/websocket.py) change the reject branch to also read `data = message.get("data", {})` and call `await agent.handle_reject(feedback, data)`. Leave the REST path [routes.py:461](src/ai_qa/api/routes.py) calling `handle_reject(request.feedback)` as-is (the new param is optional).
  - [x] 5.3 **Rewrite `BobAgent.handle_reject`** ([bob.py:601-643](src/ai_qa/agents/bob.py)) to: target the rejected page by `page_id`, acknowledge **before** retrying, reprocess, and re-emit the **same `is_review_ready` payload** the `SplitPanel` consumes:

    ```python
    async def handle_reject(self, feedback: str, data: dict[str, Any] | None = None) -> None:
        """Reprocess the rejected page with feedback, then re-present it for review."""
        # Target the rejected page (frontend sends data={"page_id": ...}); default to current.
        page_id = data.get("page_id") if data else None
        if page_id:
            idx = next((i for i, p in enumerate(self.pages) if p["page_id"] == page_id), None)
            if idx is not None:
                self.current_page_index = idx

        # AC3: acknowledge conversationally BEFORE retrying.
        await self.send_message(
            content=f'Understood â€” reprocessing this page with your feedback: "{feedback}"',
            message_type="text",
        )
        await self.transition_to(AgentState.PROCESSING)

        try:
            result = await self.process(input_data={}, feedback=feedback)
        except Exception as exc:
            logger.error("BobAgent error during reject: %s", exc, exc_info=True)
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message([str(exc)]), message_type="error"
            )
            return

        if result.success and result.data is not None:
            self.pages[self.current_page_index] = result.data
            self.phase = "review_markdown"
            await self.transition_to(AgentState.REVIEW_REQUEST)
            await self.send_message(
                content="I've updated this page based on your feedback. Please review it again.",
                message_type="text",
                metadata={
                    "is_review_ready": True,
                    "pages": self.pages,
                    # carry 11.5's flag if present so 11.6's banner stays in sync
                    "has_quality_warnings": getattr(self, "_has_quality_warnings", False),
                },
            )
        else:
            await self.transition_to(AgentState.ERROR)
            await self.send_message(
                content=self._format_error_message(result.errors), message_type="error"
            )
    ```

    Re-emitting `is_review_ready`/`pages` (not the old `is_paginated`/`result`) is what makes the panel re-render with the reprocessed page. The `SplitPanel` keeps its local `currentIndex` (same `page_id` â†’ same position), so the user stays on the rejected item; its `[page]` effect refreshes the textarea/preview to the new `requirement_md`.
  - [x] 5.4 **Replace the `process(feedback)` stub with a real reprocess** ([bob.py:139-153](src/ai_qa/agents/bob.py)). When `feedback` is provided, re-run the formatter on the page's stored `raw_html` with the feedback as guidance; fall back gracefully:

    ```python
        if feedback:
            current_page = self.pages[self.current_page_index]
            await self.send_message(
                f"Re-processing '{current_page.get('page_title', 'this page')}' with feedback...",
                "info",
            )
            raw_html = current_page.get("raw_html") or ""
            if not raw_html:
                # "Where possible": no source HTML (e.g. a Jira item) â€” re-present
                # unchanged for manual edit rather than fabricating content.
                await self.send_message(
                    "This item has no source HTML to regenerate from. Please edit the "
                    "requirement directly and approve.",
                    "info",
                )
                return StageResult(
                    success=True, data=current_page, errors=[], warnings=[], confidence=1.0
                )
            try:
                config = self.get_llm_config()
                llm_client = LLMClient(config)
                formatter = RequirementFormatter(llm_client)
                page_model = ConfluencePage(
                    page_id=current_page["page_id"],
                    title=current_page.get("page_title", ""),
                    content=raw_html,
                    space_key=self._space_key or "",
                    url=current_page.get("source_url", ""),
                )
                new_md = await formatter.convert_page(page_model, feedback=feedback)
                current_page["requirement_md"] = new_md
            except Exception as exc:
                # Never crash the reject loop â€” re-present unchanged with a notice.
                logger.error("Bob reprocess failed: %s", exc, exc_info=True)
                await self.send_message(
                    "I couldn't automatically regenerate this page. Please edit it "
                    "directly and approve.",
                    "warning",
                )
            return StageResult(
                success=True, data=current_page, errors=[], warnings=[], confidence=1.0
            )
    ```

    The `ConfluencePage` fields used here are verified against [src/ai_qa/pipelines/models.py:29-33](src/ai_qa/pipelines/models.py): `page_id`, `title`, `content`, `space_key`, `url` (all required `str`). This path opens **no** `MCPClient` (it only builds an `LLMClient`), so the single-MCP-client / disconnect invariants are untouched.
  - [x] 5.5 (Soft, only if 11.5 is merged) After a successful reprocess, refresh the page's quality data so the AC1 banner stays accurate: `if hasattr(self, "_detect_quality_issues"): current_page["quality_issues"] = [qi.model_dump(mode="json") for qi in self._detect_quality_issues(current_page)]`. Guard with `hasattr` so 11.6 does not hard-depend on 11.5 being merged.

- [x] **Task 6 â€” Backend: feedback-aware formatter (AC3)**
  - [x] 6.1 In [requirement_formatter.py](src/ai_qa/pipelines/requirement_formatter.py), add an optional `feedback: str | None = None` to `convert_page` (line 23) and `_format_story` (line 78). Thread it through (`return await self._format_story(page, md, feedback)`).
  - [x] 6.2 In `_format_story`, when `feedback` is truthy, prepend a revision instruction to the prompt, e.g.:

    ```python
    revision = ""
    if feedback:
        revision = (
            "\n\nIMPORTANT â€” a reviewer rejected the previous version with this "
            f"feedback. Revise the requirement to address it:\n{feedback}\n"
        )
    ```

    Insert `{revision}` near the top of the existing prompt (before "Format the output EXACTLY like this"). Keep the rest of the prompt and the `ainvoke` call unchanged. No signature change to `_caption_image`.

- [x] **Task 7 â€” Frontend tests (AC1/AC2/AC3)**
  - [x] 7.1 New `frontend/src/components/__tests__/SplitPanel.test.tsx` (Vitest + `@testing-library/react`, mirror the style of [ArtifactPreview.test.tsx](frontend/src/components/__tests__/ArtifactPreview.test.tsx) and `test-setup.ts`). Build a `pages` array of 2-3 `ExtractedPage`s, one with `quality_issues`.
    - **AC1 â€” source link:** asserts an anchor with the page `source_url`; Jira page (`source_type:"jira"`) shows a Jira-labelled link.
    - **AC1 â€” rendered Markdown:** Preview tab is default; a `## Heading` in `requirement_md` renders as a heading element (not raw `##` text). Switching to Edit shows a `<textarea>` with the raw markdown.
    - **AC1 â€” warnings:** a page with `quality_issues` renders the amber banner containing each issue's `message` and `impact`; a clean page renders no banner.
    - **AC2 â€” navigation:** with `pages.length > 1`, Next advances the displayed item and "(2 of N)"; Previous goes back; buttons disable at the ends.
    - **AC2 â€” batch scope:** approving the current item calls `onApprove(page_id, markdown)` and the "resolved" count/auto-advance updates.
    - **AC3 â€” reject:** clicking Reject reveals the feedback textarea; submitting calls `onReject(page_id, feedbackText)`; empty feedback keeps Submit disabled.
    - Skip still calls `onSkip(page_id)`.
  - [x] 7.2 `npm run typecheck` clean (shared `ExtractedPage`/`QualityIssue` types resolve in both files); `npm run lint` clean (prefix unused args with `_`); `npm run test` green.

- [x] **Task 8 â€” Backend tests (AC2/AC3)**
  - [x] 8.1 Extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py) (reuse the `bob_agent` + `mock_project_context` fixtures; `@pytest.mark.asyncio`, `patch("ai_qa.agents.bob.<symbol>")`, `AsyncMock`/`MagicMock`).
  - [x] 8.2 **Rewrite `test_bob_handle_approve_pagination`** ([test_bob.py:102-122](tests/test_agents/test_bob.py)) for the resolved-id model: the old test calls `handle_approve()` with **no data** and asserts a counter â€” that no longer triggers DONE. New test: set two pages; `await handle_approve({"action":"approved","page_id":"1","markdown":"x"})` (patch `PipelineArtifactAdapter`, `transition_to`, `send_message`) â†’ assert `"1" in bob_agent._resolved_page_ids` and **not** DONE; then approve/skip page "2" â†’ assert DONE (`transition_to` called with `AgentState.DONE`). Add a skip case: `{"action":"not_requirement","page_id":"2"}` resolves without saving (`save_requirement_page` not called for it).
  - [x] 8.3 **Update `test_bob_process_with_feedback`** ([test_bob.py:206-221](tests/test_agents/test_bob.py)): it currently asserts the page is returned **unchanged** â€” that contract is gone. New: give the page a `raw_html`, patch `ai_qa.agents.bob.RequirementFormatter` so `convert_page` (AsyncMock) returns `"revised md"`, patch `LLMClient`/`get_llm_config`, call `process({}, feedback="Fix X")`, assert `result.data["requirement_md"] == "revised md"` and `convert_page` was awaited with `feedback="Fix X"`.
  - [x] 8.4 **New `test_bob_process_feedback_no_raw_html_falls_back`:** page with `raw_html=""` (Jira-style) â†’ `process({}, feedback=...)` returns the page unchanged, **no** `RequirementFormatter` constructed, an info message sent.
  - [x] 8.5 **New `test_bob_process_feedback_llm_error_falls_back`:** `convert_page` raises â†’ `process` returns `success=True` with the page unchanged + a warning message; never raises.
  - [x] 8.6 **New `test_bob_handle_reject_targets_page_and_re_presents`:** set `bob_agent.pages = [p1, p2]`; patch `process` (AsyncMock â†’ returns an updated `p2`), `transition_to`, `send_message`. Call `await bob_agent.handle_reject("feedback", {"page_id": "2"})`. Assert: `current_page_index == 1`; an acknowledgement `send_message` fired **before** PROCESSING; `bob_agent.pages[1]` is the updated page; a final `send_message` carries `metadata["is_review_ready"] is True` and `metadata["pages"] == bob_agent.pages`; state ends `REVIEW_REQUEST`.
  - [x] 8.7 **New `test_bob_handle_reject_defaults_to_current_when_no_page_id`:** `handle_reject("fb", None)` (or `{}`) uses the existing `current_page_index` and still re-presents.
  - [x] 8.8 **Regression (must stay green):** `test_bob_extract_descendants_creates_single_mcp_client`, the disconnect tests, and the confirm-parent tests â€” the reject path opens **no** `MCPClient`, so `mock_mcp_client_class.call_count` assertions are unaffected. Verify no test calls `handle_reject(feedback)` positionally in a way the new optional `data` param breaks (it does not).

- [x] **Task 9 â€” Full gate + DoD**
  - [x] 9.1 Backend: `uv run ruff check .` and `uv run mypy src` clean. (The `handle_reject` override widening with an optional `data` param is LSP-safe; `process`/formatter are fully typed; narrow `result.data is not None` before use per project-context.)
  - [x] 9.2 Backend: `uv run pytest tests/test_agents/test_bob.py -v` all green (new + rewritten + existing).
  - [x] 9.3 Frontend: `npm run lint`, `npm run typecheck`, `npm run test` (Vitest) all green in `/frontend`.
  - [x] 9.4 **No DB migration** â€” `uv run alembic upgrade head` is a no-op (no schema change).
  - [x] 9.5 Update the Dev Agent Record (file list, commands run, outputs).

---

## Dev Notes

### Why the index model changes (AC2) â€” read before touching `handle_approve`

Today the panel is **stuck on page 0**: `SplitPanel` is rendered with `currentIndex={0}` ([App.tsx:1627](frontend/src/App.tsx)) and has no Prev/Next, while the backend blindly does `self.current_page_index += 1` on every approve and calls DONE when the counter reaches `len(self.pages)` ([bob.py:587-596](src/ai_qa/agents/bob.py)). The two never meet â€” multi-page review has never actually worked.

This story makes the **frontend own navigation** (a real local `currentIndex` + Prev/Next) and the **backend identify pages by `page_id`** (approve/skip/reject all carry one). The server stops relying on a positional counter for completion and instead tracks a **resolved-id set**; DONE fires when every page is approved-or-skipped. This removes the desync entirely and is what makes "approval applies to the current item, batch scope shown" (AC2) coherent. The one casualty is `test_bob_handle_approve_pagination`, which asserted the old counter â€” Task 8.2 rewrites it.

### Why reject needs `page_id`, and why the base signature changes (AC3)

With free navigation, the server no longer knows which item the user is looking at, so reject must say so. The WS layer dispatches generically (`agent.handle_reject(feedback)` at [websocket.py:321](src/ai_qa/api/websocket.py)) against the **base** type, so to pass `data` at that call site the **base** `handle_reject` must accept it â€” which is why the optional `data` param lands on the base and all four overrides (Alice/Mary/Sarah ignore it). Adding an **optional** parameter to an override is LSP-safe and accepted by mypy-strict, and the REST call site `handle_reject(request.feedback)` ([routes.py:461](src/ai_qa/api/routes.py)) stays valid. This is a deliberate, contained cross-cutting change â€” not scope creep.

### AC1 â€” rendering, not detecting

11.5 already runs the deterministic quality scan and attaches `quality_issues` (`{category, location, message, impact}`) to each page; 11.3 attaches raw `warnings`. 11.6 is purely the **renderer**: the amber banner reads those keys defensively (`page.quality_issues ?? []`, `page.warnings ?? []`) so it works whether or not 11.3/11.5 are merged (no issues â†’ no banner). The Preview tab reuses `ReviewContent` verbatim ([ReviewContent.tsx:30-96](frontend/src/components/ReviewContent.tsx)) â€” the same renderer the artifact preview uses, so mermaid/tables/code all render consistently. Keep the Edit textarea so edit-before-approve survives.

### AC3 â€” the reprocess loop, end to end

1. User clicks **Reject** on the viewed item â†’ inline feedback textarea â†’ Submit â†’ `handleBobReject(page_id, feedback)` â†’ `sendMessage({type:"reject", step:2, feedback, data:{page_id}})`.
2. WS dispatch passes `feedback` + `data` to `BobAgent.handle_reject`.
3. `handle_reject` sets `current_page_index` from `data.page_id`, **acknowledges before retrying** (AC3), â†’ PROCESSING, calls `process(feedback)`.
4. `process(feedback)` rebuilds a `ConfluencePage` from the page's stored `raw_html` and re-runs `RequirementFormatter.convert_page(page, feedback=...)` (the feedback is woven into the `_format_story` prompt). No raw_html / LLM error â†’ re-present unchanged for manual edit (the "where possible" clause), never crash.
5. `handle_reject` swaps the updated page into `self.pages`, â†’ REVIEW_REQUEST, re-emits **`is_review_ready`/`pages`** (the shape the panel consumes â€” the old `is_paginated`/`result` payload was a dead end), and the `SplitPanel` re-renders on the same item with refreshed content.

### Project-context rules that bite here

- **Full-stack sync:** the backend page dict already grew keys in 11.3/11.4/11.5; this story adds the matching TS interface (`ExtractedPage` + `QualityIssue`) and shares it between `App.tsx` and `SplitPanel.tsx` so they cannot drift. Run `npm run typecheck` (Vite skips strict errors).
- **Narrow Optional before use:** `assert result.data is not None` (or an `is not None` guard) before assigning `self.pages[i] = result.data` and before subscripting it (Pyrefly/mypy). `StageResult.data` is `Any | None`.
- **No bare `except`:** the reprocess `try/except` catches `Exception` to keep the reject loop alive and logs with `exc_info=True`, then falls back â€” it does not re-raise. The detection/render paths raise nothing.
- **Security:** the warnings banner and reject acknowledgement contain only page titles + canned `message`/`impact`/feedback text. Never render or log `raw_html`, MCP tokens, or config. The `raw_html` iframe is already `sandbox=""` ([SplitPanel.tsx:85](frontend/src/components/SplitPanel.tsx)) â€” keep it.
- **JSON/dict access:** `page.get("raw_html") or ""`, `data.get("page_id")`, `page.quality_issues ?? []` â€” the empty-fallback idiom on both sides.
- **TS unused args:** prefix intentionally-unused callback args with `_` (ESLint `argsIgnorePattern: ^_`). **No `# type: ignore` / `@ts-ignore`.**
- **`uv` only**, never `pip`; **never `python3`** â€” use `uv run` / `py -3`. **`npm` only** in `/frontend`.
- **Markdown lint:** lists use `-`; real `####` headings (no bold-as-heading); table separators padded (`| --- | --- |`).

### Do NOT regress these existing behaviors

- The confirm-parent â†’ `_extract_descendants` â†’ review flow still works end-to-end; `_extract_descendants` still constructs exactly **one** `MCPClient` and `disconnect()`s it (pinned by `test_bob_extract_descendants_creates_single_mcp_client` and the disconnect tests). The reject reprocess builds only an `LLMClient` â€” **no** new MCP client.
- Approve still saves the (possibly edited) Markdown via `save_requirement_page` + `save_metadata`, including 11.5's acknowledgement fields if merged.
- The `is_review_ready` payload stays backward-compatible: existing keys unchanged; `quality_issues`/`warnings`/`source_type` already ride inside `pages`; `has_quality_warnings` is additive metadata. The frontend ignores unknown keys at runtime.
- The dormant `ChatInputArea` is left untouched (not wired in) â€” its test [ChatInputArea.test.tsx](frontend/src/components/__tests__/ChatInputArea.test.tsx) stays green.

### Testing approach (match the house style)

- Backend: `@pytest.mark.asyncio`; patch at the `ai_qa.agents.bob.*` boundary; `AsyncMock` for `process`/`convert_page`/`send_message`/`transition_to`; build `self.pages` directly; assert on `send_message.call_args` for ack-ordering and the re-emitted `is_review_ready` metadata.
- Frontend: Vitest + Testing Library (`render`/`screen`/`userEvent`), `happy-dom` env, `src/test-setup.ts` already mocks `TooltipProvider`/`localStorage`. Drive the `SplitPanel` with hand-built `pages`; assert rendered headings (Preview), textarea presence (Edit), banner text, nav state, and the `onApprove`/`onSkip`/`onReject` spies' call args.
- A full Playwright E2E is **not required** for this story: the review state needs live MCP + LLM extraction to reach, the `frontend/support/fixtures.ts` referenced by existing specs is currently missing, and prior Bob stories did not E2E the extraction path. Component-level Vitest + backend pytest are the guardrail tests here. (If an E2E is later wanted, it belongs with 11.7/11.8 once a seam to inject extracted pages exists.)

### Project Structure Notes

**Modified files (backend):**

- `src/ai_qa/agents/bob.py` â€” `__init__` (`_resolved_page_ids`); `handle_approve` (resolved-id DONE + resolve-on-skip); `handle_reject` (page-targeted, re-emits `is_review_ready`, `data` param); `process` (real feedback reprocess). No change to `_extract_descendants` extraction logic, `_resolve_mcp_pat`, or the confirm-parent branch.
- `src/ai_qa/agents/base.py`, `alice.py`, `mary.py`, `sarah.py` â€” add optional `data` param to `handle_reject` (others ignore it).
- `src/ai_qa/api/websocket.py` â€” reject branch passes `data` to `handle_reject`.
- `src/ai_qa/pipelines/requirement_formatter.py` â€” optional `feedback` on `convert_page`/`_format_story`.

**Modified files (frontend):**

- `frontend/src/components/SplitPanel.tsx` â€” warnings banner, Preview/Edit tabs, Prev/Next nav + batch scope, reject-with-feedback; props reshaped.
- `frontend/src/App.tsx` â€” `handleBobReject`; `SplitPanel` render (drop hardcoded index, pass `onReject`); `BobState.extractedPages` typed via shared `ExtractedPage`.
- `frontend/src/types/pipeline.ts` (or new `frontend/src/types/extraction.ts`) â€” shared `ExtractedPage` + `QualityIssue`.
- `frontend/src/components/ChatMessage.tsx` â€” (optional) amber `warning` styling.

**New files:** `frontend/src/components/__tests__/SplitPanel.test.tsx`. **No DB migration. No new packages. No backend schema change.**

### Previous-story intelligence

- **Story 11.3** (`ready-for-dev`) â€” adds `parsed_markdown` + `warnings` per page. 11.6 renders `warnings` in the banner; reads it defensively (`?? []`).
- **Story 11.4** (`ready-for-dev`) â€” appends a Jira item with `source_type="jira"` and `raw_html=""`. 11.6 labels the source link by `source_type` and **falls back to manual-edit** on reject for items with no `raw_html` (the AC3 "where possible" clause). Confirmed 11.4 defaults: single-ticket, deterministic render, `raw_html=""`.
- **Story 11.5** (`ready-for-dev`) â€” the **producer** this story consumes: attaches `quality_issues` ({category, location, message, impact}) per page, sets `has_quality_warnings`, emits a chat warning summary, records acknowledgement on approve. 11.6 is the **renderer** of those `quality_issues` (AC1 banner) and preserves the acknowledgement metadata on approve. 11.6 degrades gracefully if 11.5 is unmerged (banner reads `warnings` only). See [verify-subagent-claims](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/verify-subagent-claims.md).
- **Epic 9** (done) â€” per-user secret resolution; `get_llm_config()` resolves the provider key at run time. The reject reprocess reuses it to build the `LLMClient` (same as `_extract_descendants`), so it inherits the missing-key `PipelineError` UX.
- **Epic 10** (done) â€” `PipelineArtifactAdapter.save_requirement_page`/`save_metadata`; the artifact path is sync. See [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md).
- See [agent-gate-conftest-regression](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/agent-gate-conftest-regression.md): if 11.2's intake gate is merged and a happy-path Bob test now trips it, fix the shared `mock_db`/`mock_project_context` centrally, not per-test.
- See [backend-test-suite-orphaned-legacy-tests](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md): a full `uv run pytest` is red from orphaned legacy tests â€” verify only the 11.6-touched files.
- See [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md): the `handle_approve`/`handle_reject`/`process` snippets above **replace** specific blocks â€” preserve the surrounding confirm-parent branch and the `_extract_descendants` `try/except/finally` verbatim; do not drop unchanged blocks.

### Git intelligence (recent work patterns)

Recent commits center on Epic 10 artifact events (`9d878c5`, `1852886`) and the 3.12â†’3.14 upgrade (`39db313`). None touch Bob's review UI or `handle_reject` â€” no merge-conflict risk. The established pattern: connect MCP once, build `self.pages[]`, emit one `is_review_ready` payload, paginate review, save on approve. 11.6 completes that pattern (real navigation, rendered output, working reject loop) without changing the connect/extract shape.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1074-1095] â€” Story 11.6 ACs (review shows source links + rendered markdown + warnings; Next/Previous + batch scope; reject-with-feedback â†’ reprocess + conversational ack)
- [Source: _bmad-output/planning-artifacts/epics.md:1097-1118] â€” Story 11.7 (requirements artifact save) â€” the explicitly OUT-of-scope save semantics
- [Source: src/ai_qa/agents/bob.py:139-153] â€” `process(feedback)` stub to replace; :461-469 page dict shape; :513-599 `handle_approve`; :601-643 `handle_reject`
- [Source: src/ai_qa/agents/base.py:349] â€” base `handle_reject`; :212-273 `send_message`/`transition_to`; AgentState
- [Source: src/ai_qa/api/websocket.py:319-321] â€” reject dispatch; :316-318 approve dispatch (`data`)
- [Source: src/ai_qa/pipelines/requirement_formatter.py:23-114] â€” `convert_page`/`_format_story` (add `feedback`)
- [Source: src/ai_qa/pipelines/models.py] â€” `ConfluencePage` fields; `QualityIssue` (11.5)
- [Source: frontend/src/components/SplitPanel.tsx] â€” review component to rewrite
- [Source: frontend/src/App.tsx:172-187,753-766,973-999,1617-1634] â€” `BobState`, `is_review_ready` handler, approve/skip handlers, `SplitPanel` render
- [Source: frontend/src/components/ReviewContent.tsx:30-96] â€” markdown renderer for the Preview tab
- [Source: frontend/src/components/ChatInputArea.tsx:276-382] â€” reject-feedback + Prev/Next reference pattern (dormant, not rendered)
- [Source: frontend/src/components/artifacts/ArtifactNotice.tsx:32-39] â€” amber warning styling convention
- [Source: frontend/src/hooks/useWebSocket.ts:235-262] â€” `sendMessage` envelope
- [Source: frontend/src/types/pipeline.ts:148-167] â€” `ChatInputAreaProps` (reference)
- [Source: tests/test_agents/test_bob.py:102-122,206-221] â€” pagination + feedback tests to rewrite
- [Source: tests/conftest.py:51-55] â€” `mock_project_context` fixture
- [Source: project-context.md] â€” `uv`/`npm` only; Ruff + Mypy strict; no `# type: ignore`/`@ts-ignore`; narrow Optional; no bare except; full-stack TS sync; security (no HTML/secret/config logging)

### Definition of Done

- [ ] Shared `ExtractedPage` + `QualityIssue` TS types added and imported by both `App.tsx` and `SplitPanel.tsx` (no duplicate inline types).
- [ ] `SplitPanel` shows source link (labelled by source type), a **rendered** Markdown Preview tab (+ Edit tab preserving edit-before-approve), and a per-item warnings banner from `quality_issues`/`warnings` (AC1).
- [ ] `SplitPanel` has working Next/Previous navigation with batch scope ("(i of N) â€” X resolved"); approval/skip act on the current item and auto-advance (AC2).
- [ ] Backend transitions to DONE only when every page is approved-or-skipped (resolved-id set), not on a positional counter (AC2).
- [ ] Reject affordance (button â†’ feedback textarea â†’ submit) sends `{type:"reject", step:2, feedback, data:{page_id}}`; `handle_reject` targets the page, acknowledges **before** retrying, reprocesses, and re-emits `is_review_ready` so the panel re-renders (AC3).
- [ ] `process(feedback)` re-runs `RequirementFormatter` on `raw_html` with feedback woven into the prompt; falls back to unchanged re-present (no crash) when there's no `raw_html` or the LLM errors (AC3 "where possible").
- [ ] Optional `data` param added to `handle_reject` on base + Alice/Mary/Sarah/Bob (others ignore it); WS reject branch passes `data`.
- [ ] Existing Bob regression tests (single-MCP-client, disconnect on completion/exception, confirm-parent) still pass unchanged; the reject path opens no MCP client.
- [ ] New/updated tests: frontend `SplitPanel.test.tsx` (source link, rendered preview, warnings, nav, reject); backend reject targeting + reprocess + fallbacks + resolved-id DONE.
- [ ] `uv run ruff check .` + `uv run mypy src` clean; `uv run pytest tests/test_agents/test_bob.py -v` green.
- [ ] `npm run lint` + `npm run typecheck` + `npm run test` green in `/frontend`.
- [ ] `uv run alembic upgrade head` is a no-op (no schema change). No new packages.

---

## Resolved Decisions (confirmed by Thuong â€” do NOT revisit)

Confirmed 2026-06-11 during story creation; locked â€” implement exactly as stated.

1. **AC3 reprocess = full LLM re-run.** `process(feedback)` re-runs `RequirementFormatter.convert_page` on the page's stored `raw_html` with the reviewer feedback woven into the `_format_story` prompt, regenerating `requirement_md`. *(Alternative rejected: conversational-ack-only + manual re-edit with no LLM call.)* "Where possible" = when `raw_html` exists and the LLM succeeds; otherwise re-present unchanged for manual edit with a clear message â€” never crash the loop.
2. **AC1 rendered Markdown = Preview/Edit tabs.** The right pane gets a Preview tab (default, rendered via `ReviewContent`) and an Edit tab (the existing textarea). Approve still sends the possibly-edited Markdown. *(Alternative rejected: keep the textarea + a separate read-only preview pane â€” too cramped in the 2-column layout.)*
3. **AC2 navigation/DONE model (default, applied).** The frontend `SplitPanel` owns the current index (local state + Prev/Next); the backend identifies items by `page_id` and transitions to DONE via a resolved-id set, not a positional counter. The half-wired `currentIndex={0}` render and the old `current_page_index += 1` counter are removed.
4. **Save semantics unchanged; 11.7 owns the project-artifact save.** 11.6 keeps the existing `save_requirement_page`/`save_metadata` approve path (and 11.5's acknowledgement metadata); the `projects/{id}/requirements/` artifact save with full metadata stays in Story 11.7.

## Saved Questions

(No open questions â€” the two genuine forks were resolved with Thuong during story creation; see Resolved Decisions 1-2. Defaults 3-4 follow the established Epic 11 pattern and are applied directly. Flag during dev only if the `ConfluencePage` constructor fields differ from the snippet in Task 5.4, or if 11.3/11.4/11.5 are unmerged and the page keys are absent â€” both are handled by the defensive defaults specified above.)

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Resolved-id set model implemented for DONE trigger; removes positional counter and frontend/backend desync.
- handle_reject now emits is_review_ready/pages (matching the panel handler) instead of the dead is_paginated/result shape.
- Optional data param added to handle_reject across base + Alice/Mary/Sarah/Bob; WS dispatch passes data; REST call site untouched.
- process(feedback) fully rewritten: re-runs RequirementFormatter.convert_page on stored raw_html; two fallback paths (no raw_html or LLM error -> re-present unchanged with info/warning message).
- RequirementFormatter.convert_page / _format_story gain optional feedback threaded into the LLM prompt as a revision instruction.
- SplitPanel fully rewritten: owns currentIndex (local state), resolvedIds set, Preview/Edit tab toggle, amber warnings banner, Prev/Next nav, reject-with-feedback affordance.
- Shared frontend/src/types/extraction.ts created with ExtractedPage + QualityIssue; both App.tsx and SplitPanel.tsx import it.
- All gates passed: ruff clean, mypy clean (80 files), alembic no-op, 1172 backend tests passed (2 pre-existing 11.8 fails), 171 frontend tests passed.

### File List

- frontend/src/types/extraction.ts (new)
- frontend/src/components/SplitPanel.tsx (modified - full rewrite)
- frontend/src/components/__tests__/SplitPanel.test.tsx (new - 18 tests)
- frontend/src/App.tsx (modified - handleBobReject, BobState.extractedPages type, SplitPanel props)
- src/ai_qa/agents/bob.py (modified - _resolved_page_ids, handle_approve, handle_reject, process)
- src/ai_qa/agents/base.py (modified - handle_reject optional data param)
- src/ai_qa/agents/alice.py (modified - handle_reject optional data param)
- src/ai_qa/agents/mary.py (modified - handle_reject optional data param)
- src/ai_qa/agents/sarah.py (modified - handle_reject optional data param)
- src/ai_qa/api/websocket.py (modified - reject branch passes data)
- src/ai_qa/pipelines/requirement_formatter.py (modified - feedback param on convert_page / _format_story)
- tests/test_agents/test_bob.py (modified - rewrote pagination test, 6 new tests, 1 new skip)

### Change Log

- 2026-06-12: Implemented Story 11.6 - rewrote SplitPanel (warnings banner, Preview/Edit tabs, Prev/Next nav, reject-with-feedback); switched backend DONE trigger to resolved-id set; implemented real LLM reprocess in process(feedback) via RequirementFormatter; threaded optional data through handle_reject chain; added shared TS types; 18 new frontend tests + 6 new backend tests. All gates green.