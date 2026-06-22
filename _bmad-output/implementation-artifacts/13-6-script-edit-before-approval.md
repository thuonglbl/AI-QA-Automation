---
baseline_commit: 2a1f170
---

# Story 13.6: Script Edit Before Approval

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a QA user,
I want to **edit a generated Playwright script in the review panel before I approve it** — with my edits **retained in the review state**, **unsaved changes clearly indicated**, and my edited content **validated** (basic Python syntax + the project's disallowed "unsafe" patterns) with **actionable error messages** —
so that I can correct selectors, assertions, or implementation details before the script is saved and executed.

## Acceptance Criteria

Verbatim from [epics.md#Story-13.6](_bmad-output/planning-artifacts/epics.md) (lines 1367-1387), expanded with implementation defaults (see "Scope decisions"). This is the **edit-and-validate layer** on top of **Story 13.5**'s read-only side-by-side `SarahScriptReviewPanel`. It is the Sarah analog of **Bob's edit-before-approval** (Story 11.6 / `SplitPanel` Preview/Edit tabs → `handle_approve` saving the *edited* markdown) — re-applied to a Python **code** pane with a **validation gate** that markdown did not need.

### AC1 — Edit retained in review state + unsaved-changes indicated

- **Given** a generated script is open for review (13.5's side-by-side panel, right pane = the generated Python)
- **When** the user edits the script content (in an **Edit** view of the right pane)
- **Then** the edited content is **retained in review state** — it survives Prev/Next navigation away from and back to that script within the same review session (it is the value carried into approve)
- **And** **unsaved changes are clearly indicated** (a visible "unsaved changes" affordance, color **+** text/icon, distinct from the read-only Preview)

### AC2 — Submit edited content for validation → syntax + unsafe-pattern checks with actionable errors

- **Given** edited script content is submitted for validation
- **When** the validation runs
- **Then** the system checks **basic Python syntax** and **disallows known unsafe patterns configured for the project**
- **And** **validation errors are shown with actionable messages** (each error names what is wrong, where — line number where available — and what to do), **without discarding the user's edits**

### AC3 — Validation passes → approved artifact uses the edited content

- **Given** validation passes
- **When** the user approves the edited script
- **Then** the approved artifact uses the **edited** script content, **not** the original generated draft

---

## ⚠️ Sequencing dependency (READ FIRST — critical)

**Story 13.6 is the top of the Sarah review chain. It EXTENDS — it does not create — the review panel and the approve handler.** Its prerequisites, none of which exist as of `2a1f170`:

1. **Story 13.5 (the rendering layer)** builds `frontend/src/components/agents/SarahScriptReviewPanel.tsx` (the side-by-side panel with a **read-only** syntax-highlighted right pane), the **present-all** review transport (`SarahAgent._present_script_review` → `metadata.type == "script_review"` + `scripts[]`), the TS `ScriptReviewItem`/`ScriptReviewPayload` types, and **index-addressable** `handle_approve`/`handle_reject`/`handle_skip` keyed off a `_reviewed_indices: set[int]` DONE gate. **13.6 adds the editable right pane + the validation gate on top of that panel and that handler.** If `SarahScriptReviewPanel` / `_present_script_review` / `_reviewed_indices` are absent → **13.5 is unmerged → 13.6 is blocked. Flag and stop.**
2. **Story 13.1 (the Sarah step-4 frontend surface + lifecycle)** adds `isSarahStep`, `sarahState`, `handleSarahMessage` (gated on `agentName === "Sarah"`), the Sarah render block, the Mary→Sarah navigate, the Sarah auto-start, and the **phase-dispatched** `handle_approve` (`self.phase` = input-selection vs script-review). 13.6's frontend edits live in `handleSarahMessage` / the Sarah render block / `handleSarahApprove`; its backend edit lives in the **script-review branch** of the phase-dispatched `handle_approve`. If `sarahState`/`handleSarahMessage`/`self.phase` are absent → **13.1 unmerged → flag and stop.**
3. **Story 13.2 + Epic 12** (the `GeneratedScript.warnings` channel, Mary's approved test cases, `frontend/src/components/agents/`, `frontend/src/types/testcase.ts`). 13.6 does not depend on `warnings` directly, but the panel it extends does. Verify present; reconcile and note divergence.

As of `2a1f170`, **Stories 12.1–12.5 and 13.1–13.5 are all `ready-for-dev` and absent from the working tree** (confirmed: no `isSarahStep`/`sarahState`/`handleSarahMessage`/`script_review`/`SarahScriptReviewPanel` anywhere in `frontend/src`; `GeneratedScript` has no `warnings`; the live `sarah.py` presents one script at a time and is **not** phase-dispatched). **13.6 is therefore blocked until 13.1–13.5 land.** Before starting, verify the prerequisites in the **live tree** (Task 0); if unmerged, **flag and stop** — do NOT re-implement 13.5's panel, 13.1's surface, or Epic 12 here. Treat any cited `file:line` / before-after snippet in this story as a **lead to verify against the live (13.1–13.5-merged) code**, not gospel — reconcile and record divergences in Completion Notes ([verify-subagent-claims](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\verify-subagent-claims.md), [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md)).

---

## Scope decisions (CONFIRMED — Thuong locked all four defaults 2026-06-13: "áp dụng default")

Chosen from the code + ACs + planning docs + the Bob 11.6 / Sarah 13.5 precedent, and **confirmed by Thuong** ("áp dụng default", 2026-06-13). The four formerly-open questions are now resolved decisions (full list under "Confirmed decisions" at the end of this file). No pending input — the dev agent implements exactly as written.

- **This is the edit-and-validate layer for Sarah — it EXTENDS 13.5's panel + handler, mirroring Bob's 11.6 edit-before-approval.** The work is: (a) add a **Preview/Edit tab** to `SarahScriptReviewPanel`'s right (script) pane — **Preview** = 13.5's read-only `SyntaxHighlighter`; **Edit** = a `font-mono` `<textarea>` seeded from the script (mirror [SplitPanel.tsx:210-252](frontend/src/components/SplitPanel.tsx:210)); (b) **retain edits per-script for the whole review session** (AC1) + show an **unsaved-changes** indicator; (c) a **backend validator** (`validate_script` — `ast.parse` syntax check + a denylist unsafe-pattern scan; AC2) wired into the **script-review branch** of `handle_approve`; (d) on validation **failure**, emit a `script_validation_error` payload with actionable, line-numbered errors and **stay REVIEW_REQUEST** without saving/approving/advancing (mirror Bob's stay-reviewable-on-save-failure [bob.py:1191-1205](src/ai_qa/agents/bob.py:1191)); (e) on validation **pass**, set the script's content to the **edited** text and save **that** (AC3). The Approve action carries the edited content in `data["script_content"]` (Sarah's analog of Bob's `data["markdown"]`).
- **Validation trigger = validate-on-approve, single round-trip (CONFIRMED — Saved Q#1).** The Approve action carries the edited content; the backend validates **before** saving. On failure → actionable errors + stay reviewable (nothing saved). On pass → save the edited content + approve. This satisfies AC2 ("submitted for validation … errors shown") **and** AC3 ("validation passes → approve uses edited content") in **one** action with **no new WebSocket router action** (13.5 cautioned against adding router actions). The literal AC2 wording ("submitted for validation") *can* read as a separate "Validate" button; that is offered as the alternative in Saved Q#1 (it would add a `validate` WS message + `handle_validate` + a dedicated button reusing the same validator — a strict superset, deferrable).
- **"Unsafe patterns configured for the project" = a deployment-level denylist, NO migration (CONFIRMED — Saved Q#2).** There is **no per-project config mechanism** for this today — the `Project` model ([db/models.py:51-77](src/ai_qa/db/models.py:51)) has `name`/`description`/`confluence_base_url`/`jira_base_url`/`enabled_providers`/`created_by_user_id` and **no** settings/denylist column, and `AppSettings` ([config.py:121-136](src/ai_qa/config.py:121)) has script-generation knobs but **no** unsafe-pattern list. **Default:** ship a module-level `DEFAULT_UNSAFE_SCRIPT_PATTERNS` constant in the new validator + an optional `AppSettings.script_unsafe_patterns: list[str]` override (read from env/`config.yaml`, in the existing "Script Generation" block). "Configured for the project" = the deployment's config — **no Alembic migration, no DB column, no admin UI.** Alternative (Saved Q#2): a new `Project.unsafe_script_patterns` JSON column + migration + admin UI to edit it per-project (heavier; no admin surface exists for it; deferrable to a later story).
- **Edit retention = per-script, whole-session (CONFIRMED — Saved Q#3).** AC1 requires edits to "be retained in review state". 13.5's panel mirrors `SplitPanel`, which **resets** its editable buffer on every navigation ([SplitPanel.tsx:37-44](frontend/src/components/SplitPanel.tsx:37)) — that would **lose** edits when the user navigates to another script and back, violating AC1. **Default:** hold edits in a per-index map (`Record<number, string>`) keyed by script index, so they survive Prev/Next within the review session; reset only when a brand-new `script_review` payload arrives (a fresh generation/regeneration). Alternative (Saved Q#3): SplitPanel's reset-on-nav (simpler, but AC1's "retained" then only means "until you navigate away" — weaker).
- **E2E coverage = scoped (CONFIRMED — Saved Q#4, same rationale as 13.5).** Primary guardrails: **backend pytest** on `validate_script` + the edited-content approve path, and **Vitest** on the panel's edit/dirty/validation-error rendering. Playwright E2E is scoped because LLM-driven generation is not E2E-reproducible without a provider key and `page.route` mocking is forbidden ([project-context.md#Testing-Rules](project-context.md)); the chrome-path FE is deferred (13.1). Alternative (Saved Q#4): full LLM-driven E2E (rejected for the same reasons 13.5 rejected it).

### Boundary fences — what 13.6 does NOT do

- **Does NOT build the panel, the present-all transport, or the index-addressable handlers** — 13.5 owns `SarahScriptReviewPanel`, `_present_script_review`, `data["script_index"]`, and `_reviewed_indices`. 13.6 **extends** them (adds the Edit tab + reads `data["script_content"]`). Reconcile against the live 13.5-merged shape.
- **Does NOT change reject/regenerate semantics, approval `user`/`timestamp` metadata, "rejected never approved" hardening, or Jack-eligibility** — that is **Story 13.7**.
- **Does NOT change the artifact-save metadata, add save idempotency/D8 for scripts, or fix the `.spec.ts` save-fallback** ([sarah.py:538](src/ai_qa/agents/sarah.py:538)) — that is **Story 13.8**. 13.6 saves the edited content through the **existing** `save_script` call.
- **Does NOT add warnings detectors or change the warnings channel** (13.2/13.3/13.4). Validation **errors** (13.6, blocking) are a separate surface from review **warnings** (13.2+, advisory). The Edit pane preserves any inline `# TODO:`/`# REVIEW:` markers as plain text.
- **Does NOT touch the confidence engine**, the generation prompt, selectors/assertions, or SSO handling.
- **Does NOT execute or import the edited script.** Validation is **static only** (`ast.parse`) — never `exec`/`eval`/`compile(..., "exec")`/`import`. This is a security boundary (see Dev Notes "The validator must never run the code").

## What ALREADY EXISTS (reuse / extend — do not recreate)

| Capability | Where it lives | Status / action for 13.6 |
| --- | --- | --- |
| `SarahScriptReviewPanel` side-by-side panel (read-only highlighted right pane, client `currentIndex` + resolved set, Prev/Next, amber warnings banner, reject-feedback textarea, footer) | created by **13.5** at `frontend/src/components/agents/SarahScriptReviewPanel.tsx` | ⚠️ **EXTEND** — add a Preview/Edit tab to the right pane, an edits map, an unsaved indicator, a validation-error banner; change `onApprove(index)` → `onApprove(index, editedContent?)` |
| `handle_approve` script-review branch (index-addressable, saves via `save_script`, `_reviewed_indices` DONE gate) | **13.5** rewrites [sarah.py:519-570](src/ai_qa/agents/sarah.py:519) | ⚠️ **EXTEND** — read `data.get("script_content")`; validate; on fail emit `script_validation_error` + stay REVIEW_REQUEST; on pass set `script.script_content = edited` then save |
| Bob's **edit-before-approval** backend pattern: read edited content from `data`, guard empty, save the edited copy in `try/except`, stay-reviewable + actionable error on failure | [bob.py:1130-1207](src/ai_qa/agents/bob.py:1130) (read 1147, empty-guard 1148-1150, save edited 1168-1174, UX-DR12 try/except 1191-1205, no-resolve return 1205) | ✅ **mirror** — Sarah's `data["script_content"]` is Bob's `data["markdown"]`; the validation gate is the one extra step markdown didn't need |
| `SplitPanel` Preview/Edit tab + textarea (right pane), reset-on-nav effect, warnings banner, footer | [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx) (tabs 210-236, textarea 244-249, reset effect 37-44, warnings banner 162-191, approve-sends-edited 71-82, footer 296-327) | ✅ **mirror the tab/textarea skeleton**; **diverge** on reset-on-nav (13.6 retains edits — Saved Q#3) and add a **red** validation-error banner distinct from the amber warnings banner |
| WebSocket dispatch: `approve` → `handle_approve(data)`, `reject` → `handle_reject(feedback, data)` (full `data` passthrough) | [websocket.py:312-322](src/ai_qa/api/websocket.py:312) | ✅ **reuse** — `script_content` rides the existing `data` channel; **no router/REST/schema change** |
| `PipelineArtifactAdapter.save_script(name, content)` → `kind="playwright_script"` → `projects/{id}/test_scripts/` | [artifact_adapter.py:143-145](src/ai_qa/pipelines/artifact_adapter.py:143), [storage.py:34-35](src/ai_qa/artifacts/storage.py:34) | ✅ **reuse unchanged** — pass the **edited** content; do NOT add D8/idempotency (13.8) |
| `GeneratedScript.script_content: str` (the in-memory script the panel edits) | [sarah.py:26-37](src/ai_qa/agents/sarah.py:26) | ✅ **the field 13.6 overwrites** with the edited text on a passing approve (AC3) |
| `ast` (stdlib) already imported in the codebase | [alice.py:21](src/ai_qa/agents/alice.py:21) | ✅ **reuse** — `ast.parse` for the syntax check; **no new package** |
| `_format_error_message` (BaseAgent) for single-error rendering; UX-DR12 three-part message pattern | [base.py](src/ai_qa/agents/base.py), Bob inline three-part [bob.py:1195-1204](src/ai_qa/agents/bob.py:1195) | ✅ for the **validation summary** message, build a multi-error body inline (like Bob's UX-DR12) — `_format_error_message` renders only `errors[0]` |
| `react-syntax-highlighter` (Preview), plain `<textarea>` (Edit) | [package.json:33,50](frontend/package.json:33) | ✅ **reuse** — Edit uses a plain `font-mono` textarea (like `SplitPanel`); **do NOT add Monaco/CodeMirror** (project rule: no new packages) |
| `Badge`/`Button`/`ScrollArea`, lucide-react icons | [ui/badge.tsx](frontend/src/components/ui/badge.tsx), [ui/button.tsx](frontend/src/components/ui/button.tsx) | ✅ **reuse** for the unsaved badge + error banner chips |

---

## Tasks / Subtasks

- [x] **Task 0 — Confirm prerequisites (BLOCKING gate)**
  - [x] Verify **13.5** is merged in the live tree: `frontend/src/components/agents/SarahScriptReviewPanel.tsx` exists; `SarahAgent._present_script_review` emits `metadata.type == "script_review"` with a `scripts[]` list; `handle_approve`/`handle_skip`/`handle_reject` read `data["script_index"]`; `self._reviewed_indices: set[int]` gates DONE. If absent → **13.5 unmerged → flag and stop** (do NOT build the panel here).
  - [x] Verify **13.1** is merged: `isSarahStep`/`sarahState`/`handleSarahMessage` in [App.tsx](frontend/src/App.tsx); `handle_approve` is **phase-dispatched** (`self.phase`) in [sarah.py](src/ai_qa/agents/sarah.py). If absent → **flag and stop.**
  - [x] Verify **13.2 + Epic 12**: `GeneratedScript.warnings`, `frontend/src/components/agents/`, `frontend/src/types/testcase.ts`. Record the verification + any divergence (field names, prop shapes) in Completion Notes before relying on them.

- [x] **Task 1 — Backend: the script validator (AC2)**
  - [x] Create `src/ai_qa/pipelines/script_validator.py` (sibling to `script_generator.py`). Define a structured result (errors need line/severity that `StageResult.errors: list[str]` cannot carry — see [create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md): `StageResult` is exactly `{success, data, errors, warnings, confidence}`, no structured errors):

    ```python
    from pydantic import BaseModel

    class ScriptValidationError(BaseModel):
        line: int | None = None        # 1-based; None when not line-locatable
        column: int | None = None
        message: str                   # actionable, human-readable
        severity: str = "error"        # "error" (blocks approve) | "warning"
        code: str                      # "syntax" | "unsafe_pattern"

    class ScriptValidationResult(BaseModel):
        is_valid: bool                 # True ⇔ no severity=="error" entries
        errors: list[ScriptValidationError] = []
    ```

  - [x] Add `DEFAULT_UNSAFE_SCRIPT_PATTERNS` — a default denylist of obviously-unsafe constructs for a *browser-automation* script. Recommend an **AST-based** scan (catches the call/import even when reformatted), e.g.: imports of `subprocess`, `os`/`os.system`/`os.popen`, `socket`, `requests`/`urllib`/`httpx` (no raw network from a Playwright script), `shutil` (`rmtree`), `ctypes`, `pickle`/`marshal`; calls to `eval`, `exec`, `compile`, `__import__`, `open(..., "w"/"a"/"x")` (writing the filesystem), `globals`/`locals` mutation. Keep the list small, documented, and conservative (false positives block the user — prefer precision). Document each entry's rationale in a module docstring.
  - [x] Implement `def validate_script(content: str, *, unsafe_patterns: Sequence[str] | None = None) -> ScriptValidationResult`:
    - **Syntax (basic Python):** `try: tree = ast.parse(content) except SyntaxError as exc:` → one `ScriptValidationError(line=exc.lineno, column=exc.offset, message=f"Python syntax error: {exc.msg}", code="syntax")`, return `is_valid=False` immediately (can't scan an unparseable tree). The line numbers are **relative to `content`** = exactly what the user sees in the Edit pane (AC2 "actionable").
    - **Unsafe patterns:** walk `tree` (`ast.walk`) for `ast.Import`/`ast.ImportFrom`/`ast.Call`/`ast.Attribute` matching the denylist (the `unsafe_patterns` arg overrides `DEFAULT_UNSAFE_SCRIPT_PATTERNS` when provided); each match → `ScriptValidationError(line=node.lineno, message=f"Disallowed pattern '<name>': <why>", code="unsafe_pattern")`.
    - `is_valid = not any(e.severity == "error" for e in errors)`.
  - [x] **The validator must NEVER execute the script** — only `ast.parse`. Do **not** `exec`/`eval`/`compile(..., "exec")`/import the module. Add a code comment stating this (security boundary). Pyrefly/mypy: narrow `exc.lineno`/`exc.offset` (they're `int | None`); type the denylist `frozenset[str]` or `tuple[str, ...]`.
  - [x] Add the optional override field `script_unsafe_patterns: list[str] = Field(default_factory=list, description="Additional/override disallowed patterns for generated scripts (FR21)")` to `AppSettings`, in the existing **Script Generation** block ([config.py:121-136](src/ai_qa/config.py:121)). Empty default ⇒ use `DEFAULT_UNSAFE_SCRIPT_PATTERNS`.

- [x] **Task 2 — Backend: wire validation + edited content into `handle_approve` (AC2, AC3)**
  - [x] In the **script-review branch** of the (13.1-phase-dispatched, 13.5-index-addressable) `handle_approve` ([sarah.py:519-570](src/ai_qa/agents/sarah.py:519)), after resolving `index = data.get("script_index", self._current_review_index)` and bounds-guarding it (13.5), insert the edit+validate step **before** the existing `approved = True` / `save_script` / `_reviewed_indices.add(index)`:

    ```python
    script = self._generated_scripts[index]

    # 13.6: the Edit pane sends the edited script in data["script_content"].
    edited = data.get("script_content") if data else None
    if isinstance(edited, str) and edited.strip():
        result = validate_script(edited, unsafe_patterns=self._unsafe_patterns())
        if not result.is_valid:
            # AC2: actionable errors; do NOT save / approve / advance; stay reviewable.
            await self.send_message(
                content=self._format_validation_errors(result.errors),
                message_type="error",
                metadata={
                    "type": "script_validation_error",
                    "script_index": index,
                    "errors": [e.model_dump() for e in result.errors],
                },
            )
            return  # edits remain in the client's Edit pane (no script_review re-emit)
        script.script_content = edited  # AC3: edited becomes the authoritative content
    # --- existing 13.5 behavior continues unchanged below ---
    script.approved = True
    PipelineArtifactAdapter(self.project_context).save_script(
        Path(script.file_path).name or f"{script.test_case.filename}.spec.ts",
        script.script_content,   # now the EDITED content (AC3)
    )
    self._reviewed_indices.add(index)
    # ... 13.5's DONE-gate (all indices reviewed) / re-emit _present_script_review() ...
    ```

  - [x] **Do NOT re-emit `_present_script_review()` on the validation-failure path.** A re-emit would resend the *original* `script_content` and the panel's reset-on-payload would wipe the user's edits (AC1 violation). Instead send only the targeted `script_validation_error` message; the client keeps its Edit-pane buffer and renders the errors. (This is the one place 13.6 deliberately does **not** mirror Bob's re-present.)
  - [x] Add `_unsafe_patterns(self) -> list[str]` returning `self.app_settings.script_unsafe_patterns or list(DEFAULT_UNSAFE_SCRIPT_PATTERNS)` (Sarah already holds `self.app_settings` — [sarah.py:82](src/ai_qa/agents/sarah.py:82)).
  - [x] Add `_format_validation_errors(self, errors: list[ScriptValidationError]) -> str` — a multi-error, actionable body (don't use `_format_error_message`, which renders only `errors[0]`). Mirror Bob's three-part UX-DR12 shape ([bob.py:1195-1204](src/ai_qa/agents/bob.py:1195)): **What happened** ("Your edited script did not pass validation"), **Why** (the per-error list: `Line {line}: {message}` for each), **What to do** ("Fix the highlighted lines and approve again — your edits were kept").
  - [x] **Back-compat:** when `data` has no `script_content` (approve without editing — the 13.5 path), skip validation entirely and save the original `script.script_content` exactly as 13.5 does. **Empty/whitespace-only edited content** ⇒ treat as "no edit" (do not save an empty script; mirror Bob's empty-guard [bob.py:1148-1150](src/ai_qa/agents/bob.py:1148)) — or surface it as a validation error; pick one and document it (recommend: treat blank as a validation error "Script cannot be empty").
  - [x] **Preserve** the 13.5 `_reviewed_indices` DONE gate, the `_write_approved_scripts_metadata()` call on DONE, and the success message. **Do not** alter `handle_reject`/`handle_skip` (13.7/unchanged), the `.spec.ts` fallback (13.8), or save idempotency (13.8).

- [x] **Task 3 — Frontend: TS types for validation (AC2, full-stack sync)**
  - [x] Add to the script-review types (13.5's `frontend/src/types/testcase.ts` or `script.ts`), matching the Task 1 model **exactly** (full-stack-sync rule, [project-context.md#Critical-Don't-Miss-Rules](project-context.md)):
    - `interface ScriptValidationError { line?: number | null; column?: number | null; message: string; severity: "error" | "warning"; code: "syntax" | "unsafe_pattern" }`
    - `interface ScriptValidationPayload { type: "script_validation_error"; script_index: number; errors: ScriptValidationError[] }`
  - [x] Extend `SarahScriptReviewPanel`'s prop type: `onApprove: (index: number, editedContent?: string) => void` (was `(index: number) => void` in 13.5); add an optional `validationErrors?: Record<number, ScriptValidationError[]>` prop.

- [x] **Task 4 — Frontend: editable right pane + unsaved indicator + error banner in `SarahScriptReviewPanel` (AC1, AC2)**
  - [x] **Edit tab (right pane).** Add a Preview/Edit tab bar to the script (right) pane — mirror [SplitPanel.tsx:210-236](frontend/src/components/SplitPanel.tsx:210). **Preview** = 13.5's existing read-only `<SyntaxHighlighter language="python" …>`. **Edit** = a `font-mono text-sm` `<textarea>` (mirror [SplitPanel.tsx:244-249](frontend/src/components/SplitPanel.tsx:244)) bound to the per-index edit buffer. No syntax highlighting while editing (plain textarea, like `SplitPanel`; no new editor package).
  - [x] **Per-index edit buffer (AC1 — Saved Q#3 default).** Hold edits as `const [edits, setEdits] = useState<Record<number, string>>({})`. The Edit textarea's value = `edits[currentIndex] ?? scripts[currentIndex].script_content`; `onChange` sets `edits[currentIndex]`. **Do NOT reset `edits` on Prev/Next** (this is the deliberate divergence from `SplitPanel`'s `[page]` reset effect — [SplitPanel.tsx:37-44](frontend/src/components/SplitPanel.tsx:37)). Reset `edits` to `{}` **only** when a new `script_review` payload arrives (new `scripts` identity — keep that reset effect, but key it on the payload, not the index).
  - [x] **Unsaved-changes indicator (AC1).** `const isDirty = edits[currentIndex] !== undefined && edits[currentIndex] !== scripts[currentIndex].script_content`. When dirty, show a visible affordance (color **+** text/icon — colorblind-safe, [ux-design-specification.md:790](_bmad-output/planning-artifacts/ux-design-specification.md:790)), e.g. a `<Badge>` "● Unsaved changes" near the Edit tab. Optional: an Edit-tab dot when that pane has unsaved edits.
  - [x] **Validation-error banner (AC2).** When `validationErrors?.[currentIndex]?.length`, render a **red** advisory banner (`bg-red-50 border-red-200 text-red-800`, distinct from 13.5's **amber** warnings banner) listing each error as `Line {line}: {message}` (omit "Line" when `line == null`) — actionable, and it does **not** hide/replace the script pane (the user can still see and fix their code). Errors do not block typing; they clear when a fresh `script_review` arrives or when the panel chooses to clear on next edit (document the choice).
  - [x] **Approve carries the edited content (AC3).** Change the footer Approve to `onApprove(currentIndex, edits[currentIndex])` (passes `undefined` when the script was never edited → backend back-compat path). Reject/Skip unchanged from 13.5 (`onReject(index, feedback)` / `onSkip(index)`). Keep 13.5's auto-advance after approve/skip, the reject-feedback textarea, the nav bar, and the per-item status indicator.
  - [x] **Failed-script placeholder** ([sarah.py:340-349](src/ai_qa/agents/sarah.py:340)): a `# Generation failed:` stub is editable like any other script (the user can rewrite it and approve once it validates) — keep it navigable; 13.5 already renders the `error_message`.

- [x] **Task 5 — Frontend: wire validation errors + edited approve into App.tsx (AC2, AC3)**
  - [x] Extend 13.1/13.5's `sarahState` with `validationErrors: Record<number, ScriptValidationError[]>` (default `{}`).
  - [x] In `handleSarahMessage` (gated on `agentName === "Sarah"`, dual path: live `messageQueue` + history replay — mirror [App.tsx:778-812](frontend/src/App.tsx:778)), add a branch: when `message.metadata?.type === "script_validation_error"`, set `sarahState.validationErrors[script_index] = errors` **without touching `sarahState.scripts`** (so the panel's Edit buffer is not reset — the load-bearing AC1 mechanism). Keep 13.5's `script_review` branch (which **should** clear `validationErrors` to `{}` when a fresh payload arrives).
  - [x] Change `handleSarahApprove` to accept the edited content: `handleSarahApprove(index: number, editedContent?: string)` → `sendMessage({ type: "approve", step: 4, data: { action: "approved", script_index: index, ...(editedContent !== undefined ? { script_content: editedContent } : {}) } })`. Mirror `handleBobApprove` ([App.tsx:974-987](frontend/src/App.tsx:974)) which threads `markdown`.
  - [x] Pass `validationErrors={sarahState.validationErrors}` into `<SarahScriptReviewPanel>` and wire `onApprove={handleSarahApprove}`.

- [x] **Task 6 — Backend tests (AC2, AC3)**
  - [x] New `tests/pipelines/test_script_validator.py`: a valid Playwright script (`async def test_…` + `from playwright.async_api import …`) → `is_valid=True`, no errors; a syntax error (e.g. missing colon) → `is_valid=False`, one `code="syntax"` error with the correct `line`; an unsafe pattern (`import subprocess`, `os.system("…")`, `eval("…")`) → `is_valid=False`, `code="unsafe_pattern"` with the offending `line`; the `unsafe_patterns=[...]` override is honored; blank/whitespace handled per the chosen rule. **Security test:** a script containing `open("sentinel.txt", "w")` is **flagged** and the validator did **not** create the file (assert the path does not exist after validation) — proves no execution.
  - [x] Extend `tests/test_agents/test_sarah.py` (seed `_generated_scripts` with `GeneratedScript(...)`, `agent.phase = "script_review"` per 13.1, patch `ai_qa.agents.sarah.PipelineArtifactAdapter` + `ScriptGenerator` — [test_sarah.py:172-212](tests/test_agents/test_sarah.py:172); assert via `mock_broadcast.call_args_list` → `call[0][0].metadata`):
    - **Edited + valid approve (AC3):** `handle_approve({action:"approved", script_index:0, script_content:"<valid edited>"})` → `save_script` called with the **edited** content (assert the saved string == edited, **not** the original); `script.approved is True`; `0 in _reviewed_indices`.
    - **Edited + invalid approve (AC2):** edited content with a syntax error / unsafe import → `save_script` **not** called; `approved` stays `False`; `0 not in _reviewed_indices`; a `metadata.type=="script_validation_error"` message with `script_index==0` + non-empty `errors`; agent stays `REVIEW_REQUEST` (no DONE).
    - **Back-compat (13.5 preserved):** `handle_approve({action:"approved", script_index:0})` with **no** `script_content` → saves the **original** content, no validation message.
  - [x] Run the **whole** suite with `uv run pytest --no-cov` (subset runs trip the coverage gate; prior-epic baseline = 1098 passed — [backend-test-suite-orphaned-legacy-tests](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\backend-test-suite-orphaned-legacy-tests.md)). `uv run mypy src` clean. Fix shared-fixture breaks centrally in [tests/conftest.py](tests/conftest.py) ([agent-gate-conftest-regression](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\agent-gate-conftest-regression.md)).

- [x] **Task 7 — Frontend tests (AC1, AC2, AC3)**
  - [x] Extend `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx` (mirror [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx): fixture factory, mock the heavy `SyntaxHighlighter`/`ScrollArea` children, callback spies, role/text queries). Assert:
    - **Edit tab + textarea (AC1):** clicking **Edit** shows a textarea seeded with `script_content`; typing updates it; clicking **Preview** still shows the (mocked) highlighter.
    - **Unsaved indicator (AC1):** absent initially; appears after an edit; uses text not color-only.
    - **Edit retention across nav (AC1 — Saved Q#3):** edit script 0, navigate to script 1 and back → the edit on script 0 is still present in the textarea.
    - **Approve carries edits (AC3):** after editing, Approve calls `onApprove(0, "<edited>")`; with no edit, Approve calls `onApprove(0, undefined)`.
    - **Validation-error banner (AC2):** with `validationErrors={{0:[{line:3,message:"…",severity:"error",code:"syntax"}]}}`, the red banner renders the line+message **and the script pane is still present** (banner does not hide the code); banner absent when no errors; banner is visually distinct from the amber warnings banner.
    - Vitest 4 rules — [project-context.md#Testing-Rules](project-context.md) (`vi.mock` hoisted; non-null assert known array elements `scripts[i]!`).
  - [x] Playwright E2E (`frontend/e2e/`, extend `epic-13.spec.ts`): scoped per Saved Q#4 — LLM gen not E2E-reproducible without a provider key; chrome-path FE deferred. Deferred to Vitest (39 tests covering all AC1/AC2/AC3 behaviors). Noted in Completion Notes.

- [x] **Task 8 — Verify (no migration)**
  - [x] Backend: `uv run pytest --no-cov` green (1360 passed, 2 pre-existing failures unrelated to 13.6); `uv run mypy src` clean (0 issues in 80 source files); Pyrefly-clean — `data.get("script_content")` narrowed via `isinstance(edited, str) and edited.strip()`; `exc.lineno`/`exc.offset` kept as `int | None` matching typeshed; denylist typed as `tuple[str, ...]`; no redundant casts; no bare exceptions.
  - [x] Frontend: `npm run lint` (0 warnings), `npm run typecheck` (0 errors), `npm run test` (258 passed / 23 files). No new package (`package.json`/`package-lock.json` unmodified).
  - [x] Confirmed **no Alembic migration** — deployment-level denylist (Saved Q#2 default); no `Project` column, no DB model change; validation rides existing WS metadata channel; the edited script persists through the existing `save_script` → `kind="playwright_script"` artifact path.

## Dev Notes

### Current state of the files this story touches (READ FIRST)

**`src/ai_qa/agents/sarah.py` — substantial Epic-5 implementation; 13.1 phase-dispatches it; 13.5 makes it present-all + index-addressable; 13.6 adds the edit+validate step.**

- The Epic-5 per-item review loop is fully built: `handle_approve` ([:519-570](src/ai_qa/agents/sarah.py:519)) **already accepts `data` but ignores it today** — it marks `approved=True`, calls `save_script(Path(file_path).name or "<…>.spec.ts", script_content)` ([:537-540](src/ai_qa/agents/sarah.py:537)) on the **original** content, advances `_current_review_index`, DONE at `_current_review_index >= len`. `handle_reject` ([:572-619](src/ai_qa/agents/sarah.py:572)) regenerates; `handle_skip` ([:621-666](src/ai_qa/agents/sarah.py:621)); `_present_current_script_for_review` ([:698-736](src/ai_qa/agents/sarah.py:698)) emits one `review_data` with `script_content` + `script_language:"python"`.
- **By the time 13.6 starts, 13.1 + 13.5 have changed this**: `handle_approve` is phase-dispatched (`self.phase`), the script-review branch reads `data["script_index"]`, the DONE gate is `_reviewed_indices`, and the present is `_present_script_review` (present-all). **13.6's single backend insertion is the edit+validate step inside that script-review branch** (Task 2). Reconcile against the live (13.1/13.5-merged) shape; the snippet in Task 2 shows the *new* lines wrapped around the **preserved** 13.5 save/approve/`_reviewed_indices` lines — **do not delete** the surrounding 13.5 behavior ([create-story-snippet-hazards](C:\Users\thuong\.claude\projects\C--Users-thuong-source-repos-ai-qa-automation\memory\create-story-snippet-hazards.md): the "after" snippet must keep the unchanged tail).
- `GeneratedScript.script_content` ([:32](src/ai_qa/agents/sarah.py:32)) is the field the panel edits and 13.6 overwrites on a passing approve (AC3). `self.app_settings` ([:82](src/ai_qa/agents/sarah.py:82)) is where `script_unsafe_patterns` is read. The failed-script placeholder ([:340-349](src/ai_qa/agents/sarah.py:340)) is an editable script like any other.

**`src/ai_qa/agents/bob.py` — the edit-before-approval analog (Story 11.6).** `handle_approve` ([:1130-1207](src/ai_qa/agents/bob.py:1130)): reads `updated_markdown = data.get("markdown")` ([:1147](src/ai_qa/agents/bob.py:1147)), guards empty ([:1148-1150](src/ai_qa/agents/bob.py:1148)), writes `page["requirement_md"] = updated_markdown`, saves the **edited** copy via `adapter.save_requirement(... markdown=updated_markdown ...)` ([:1168-1174](src/ai_qa/agents/bob.py:1168)) inside a `try/except` that on failure sends a **three-part actionable** message and `return`s **without resolving the page or transitioning to DONE** ([:1191-1205](src/ai_qa/agents/bob.py:1191)). 13.6 is the same shape **plus** the validation gate before the save, and a `script_validation_error` metadata payload (markdown needed no validation).

**`frontend/src/components/SplitPanel.tsx` — the Preview/Edit pattern to mirror (NOT reuse).** Tab bar ([:210-236](frontend/src/components/SplitPanel.tsx:210)); Preview vs Edit branch ([:238-251](frontend/src/components/SplitPanel.tsx:238)); editable textarea bound to a single buffer ([:244-249](frontend/src/components/SplitPanel.tsx:244)); approve passes the **edited** buffer ([:71-82](frontend/src/components/SplitPanel.tsx:71)); amber warnings banner ([:162-191](frontend/src/components/SplitPanel.tsx:162)). **Two deliberate divergences for 13.6:** (1) the right pane is **Python code** (Preview = `SyntaxHighlighter`, not `ReviewContent`/iframe); (2) edits are held **per-index** and **not** reset on navigation ([:37-44](frontend/src/components/SplitPanel.tsx:37) is `SplitPanel`'s reset-on-`[page]` — 13.6 must NOT copy that, or it loses edits on nav and fails AC1). **Do NOT use the dormant `ChatInputArea`** (rendered nowhere).

**`frontend/src/App.tsx` — 13.1 builds the Sarah surface, 13.5 adds the `script_review` branch + render block; 13.6 adds a `script_validation_error` branch + threads `script_content` through `handleSarahApprove`.** Mirror the Bob wiring for shape: `handleBobMessage` dual path ([:721-774](frontend/src/App.tsx:721), result.data/flat-metadata fallback [:725-726](frontend/src/App.tsx:725)); `handleBobApprove` threading `markdown` ([:974-987](frontend/src/App.tsx:974)).

### The load-bearing AC1 mechanism — why validation failure must NOT re-emit the review

AC1 requires edits to be **retained**. The panel holds the user's edits in a client buffer (per-index map). If, on a validation failure, the backend re-emitted `_present_script_review()` (carrying the **original** `script_content`), the panel's payload-reset would overwrite the buffer and the user would **lose their edits** — the opposite of AC1. So the failure path sends **only** a targeted `script_validation_error` message (`{script_index, errors}`), the client buffer is untouched, and the red error banner renders alongside the still-edited textarea. This is the single most important design point in 13.6 — call it out in Completion Notes and guard it with the "edit retention across nav" + "errors don't reset the buffer" Vitest assertions (Task 7). (Bob *does* re-present on its save-failure path because Bob has no separate client edit buffer to protect; Sarah's editable code pane changes the calculus.)

### The validator must never run the code (security)

`validate_script` uses `ast.parse` **only** — it must not `exec`, `eval`, `compile(..., "exec")`, or import the edited text. A generated/edited script is **untrusted input being checked for safety**; executing it to "test" it would be the exact vulnerability the unsafe-pattern denylist exists to prevent. Static AST inspection is sufficient for "basic Python syntax" (parse succeeds/fails) and for the denylist (imports/calls are AST nodes). The Task 6 security test (`open(..., "w")` is flagged but no file is created) is the regression guard. This also keeps the validator deterministic and fast (no sandbox, no subprocess). Aligns with the architecture's read-only / no-side-effects posture ([architecture.md:368-373](_bmad-output/planning-artifacts/architecture.md:368)) and the no-secret-leakage rule ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)) — the validator reads the script text but never emits it to logs or external services.

### "Configured for the project" — the planning gap (Saved Q#2)

The epic AC says "unsafe patterns **configured for the project**", but **no per-project configuration surface exists** for this (the `Project` model has no settings column; there is no admin UI for script policy; `AppSettings` has no denylist). The planning docs (PRD FR21 "edit scripts before approval", UX spec Step-4 review) describe edit-before-approval and syntax highlighting but **do not specify** the unsafe-pattern list, its storage, or where it is configured — this is a genuine spec gap. The **default** resolves it the lightest faithful way: a documented module default denylist + an optional deployment-level `AppSettings.script_unsafe_patterns` override (env/`config.yaml`) — "the project" = the deployment. This needs **no migration** and is consistent with how `chrome_path`/`script_generation_*`/`confidence_threshold` are already deployment config ([config.py:113-136](src/ai_qa/config.py:113)). If Thuong wants true **per-project** policy editable in the UI, that is the Saved Q#2 alternative: a `Project.unsafe_script_patterns` JSON column + Alembic migration + an admin/project-settings UI — materially larger and better as its own story.

### Validation errors vs review warnings — two distinct surfaces

13.2/13.3/13.4 produce **advisory, non-blocking** review *warnings* (brittle selectors, ambiguous assertions, SSO setup needed) shown in 13.5's **amber** banner — they never block approval. 13.6's validation produces **blocking errors** (syntax / unsafe pattern) shown in a **red** banner — a failing validation prevents the (edited) approve. Keep them visually and semantically separate so the reviewer isn't confused: amber = "FYI, double-check this", red = "this edit will not be saved until you fix it". Do not route validation errors through the warnings channel or vice versa.

### Architecture compliance (hard rules)

- **Mandatory human review at every step — no auto-advance, no bulk approve** ([architecture.md:271-272](_bmad-output/planning-artifacts/architecture.md:271), [ux-design-specification.md:188](_bmad-output/planning-artifacts/ux-design-specification.md:188)). Editing happens **within** the per-item review; approve is still explicit and per-item; a failing validation **blocks** approve (stronger gate, consistent with mandatory review). No "Are you sure?" modal ([ux-design-specification.md:1426](_bmad-output/planning-artifacts/ux-design-specification.md:1426)).
- **Agents never read/write storage directly — always via the artifact service** ([architecture.md:518,533](_bmad-output/planning-artifacts/architecture.md:518)). 13.6 adds **no** storage access; the edited script saves through the **existing** `PipelineArtifactAdapter.save_script` ([artifact_adapter.py:143](src/ai_qa/pipelines/artifact_adapter.py:143)).
- **No credential/secret leakage** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md), [architecture.md:362-373](_bmad-output/planning-artifacts/architecture.md:362)): the `script_validation_error` payload carries only error metadata (line/message/code), never the script body, config, or tokens. The validator never logs the script content. SSO/credential scrubbing in the script body is **13.4's** detector — 13.6's denylist may catch obvious `subprocess`/`socket`/network constructs but must not duplicate/replace 13.4's secret handling.
- **Full-stack sync** ([project-context.md#Critical-Don't-Miss-Rules](project-context.md)): the `ScriptValidationError` Pydantic model ↔ the TS `ScriptValidationError` interface ↔ the `script_validation_error` payload must match exactly; verify with `npm run typecheck`/`build`.
- **Sarah flow** `script_generator.py → ai_connection + browser/agent.py → projects/{project_id}/test_scripts/` ([architecture.md:824-828](_bmad-output/planning-artifacts/architecture.md:824)) — unchanged; 13.6 only intercepts the content before the save.

### Library / framework constraints (from project-context.md)

- **Backend:** Python ≥3.14, `uv` only (`uv run`, never `pip`/`python3`). Ruff + Mypy strict (`uv run mypy src`). Pyrefly-clean: narrow `data.get("script_content")` (`Any | None`) and `SyntaxError.lineno`/`.offset` (`int | None`) before use; type the denylist as `tuple[str, ...]`/`frozenset[str]`; no redundant casts/conversions; Pydantic `Field(default_factory=list)` for the `AppSettings` list. No bare `except Exception` where `SyntaxError` fits. `pytest.raises` needs a specific type + `match=`. The agent path uses a **sync** artifact `Session`.
- **Frontend:** React 19.2, TS ~6.0 strict (`npm run typecheck`), Tailwind v4, Vitest 4 (`vi.mock` hoisted file-wide — mock `SyntaxHighlighter`/`ScrollArea`; prefer `vi.spyOn(globalThis,"fetch")`; preserve real exports via `importOriginal()`), ESLint 9. Path alias `@` → `./src`. Strict null/index access — non-null assert known array elements (`scripts[i]!`). For the `setTimeout`/auto-advance reuse from 13.5, the project-context `setTimeout` typing note applies. Status/unsaved/error use color **+** text/icon, never color alone. Playwright: `getByRole`/`getByText`; no `page.route`, no `waitForTimeout`.

### Project Structure Notes

- **New files:** `src/ai_qa/pipelines/script_validator.py` (validator + `ScriptValidationError`/`ScriptValidationResult` + `DEFAULT_UNSAFE_SCRIPT_PATTERNS`), `tests/pipelines/test_script_validator.py`, the TS `ScriptValidationError`/`ScriptValidationPayload` types (in 13.5's `frontend/src/types/testcase.ts` or `script.ts`).
- **Modified files (expected):** `src/ai_qa/agents/sarah.py` (edit+validate step in the script-review branch of `handle_approve`; `_unsafe_patterns` + `_format_validation_errors` helpers), `src/ai_qa/config.py` (`AppSettings.script_unsafe_patterns`), `frontend/src/components/agents/SarahScriptReviewPanel.tsx` (Edit tab + edits map + unsaved indicator + error banner + `onApprove(index, edited?)`), `frontend/src/App.tsx` (`sarahState.validationErrors` + `script_validation_error` branch + `handleSarahApprove` threads `script_content`), `tests/test_agents/test_sarah.py`, `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx`, possibly `frontend/e2e/epic-13.spec.ts`.
- **No backend route/schema/REST changes, no new WS router action** (default Saved Q#1) — approve carries `script_content` on the existing `data` channel; validation failure rides `send_message` metadata. **No Alembic migration** (default Saved Q#2).

### Testing standards summary

- Backend: pytest; validator tested in isolation (`tests/pipelines/`); Sarah edited-approve tested by seeding `_generated_scripts` + `agent.phase="script_review"` and patching `ai_qa.agents.sarah.PipelineArtifactAdapter`/`ScriptGenerator` ([test_sarah.py:172-212](tests/test_agents/test_sarah.py:172)); assert the **saved** content equals the **edited** content (AC3) and that an invalid edit produces a `script_validation_error` with nothing saved (AC2). Whole suite `--no-cov`; mypy `src`.
- Frontend: Vitest on the panel (edit tab, dirty indicator, retention-across-nav, edited-approve payload, red error banner with the script still visible); mirror `SplitPanel.test.tsx` scaffolding. Playwright scoped per Task 7.

### Previous-story / sibling intelligence

- **Story 13.5 (Sarah side-by-side review UX)** — the **direct predecessor** and the panel 13.6 extends. 13.5's own fence list states verbatim: *"Edit (13.6): no editable script pane, no 'unsaved changes', no syntax/safety validation. The right pane is read-only highlighted code."* 13.6 supplies exactly that editable pane + unsaved indicator + validation. 13.5 confirmed (Thuong, 2026-06-13): present-all transport, index-addressable approve/reject/skip, `_reviewed_indices` DONE gate, confidence rendered client-side, scoped E2E — all of which 13.6 inherits unchanged.
- **Story 11.6 (Bob reviewable extraction output)** — the established **edit-before-approval** pattern: `SplitPanel` Preview/Edit tabs editing a client buffer, `handle_approve` saving the *edited* `data["markdown"]`, stay-reviewable + actionable error on save failure. 13.6 is the code-pane analog with a validation gate.
- **Story 13.7 (approve/reject/regenerate semantics)** and **Story 13.8 (artifact save metadata + `.spec.ts` defect + save idempotency)** — the explicit downstream fences; 13.6 must not pre-empt them (no approval metadata, no Jack-eligibility, no save-idempotency/D8, no `.spec.ts` fix).
- **Epic 5 (Sarah, done)** — built `GeneratedScript`, the per-item review loop, `save_script`, the chrome-path flow. 13.6 reuses `GeneratedScript.script_content` and the `save_script` call; it changes neither.

### Git intelligence (recent work patterns)

Recent commits (`2a1f170 epic 11 code e2e unit done`, `b4ce65f epic 10 all e2e test OK`, `8cf53eb epic 10 all code done`) are Epic 10/11. **Epic 12 (12.1–12.5) and Stories 13.1–13.5 are NOT implemented** — the live `sarah.py`/`App.tsx`/`TestCase` are pre-12.1/pre-13.1 (verified at `2a1f170`: `handle_approve` accepts but **ignores** `data` and saves the **original** `script_content`; no `isSarahStep`/`sarahState`/`SarahScriptReviewPanel`; `GeneratedScript` has no `warnings`; `_present_current_script_for_review` is one-at-a-time). **13.6 is blocked until 13.1–13.5 land** — verify in the live tree (Task 0) and flag/stop if unmerged rather than re-implementing upstream. Closest existing patterns to copy: [bob.py:1130-1207](src/ai_qa/agents/bob.py:1130) (edit→save→stay-reviewable), [SplitPanel.tsx](frontend/src/components/SplitPanel.tsx) + [SplitPanel.test.tsx](frontend/src/components/__tests__/SplitPanel.test.tsx) (Preview/Edit tabs + Vitest scaffold), [alice.py:21](src/ai_qa/agents/alice.py:21) (stdlib `ast`), and the **13.5 story** (the panel + transport this story extends).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-13.6] — ACs (lines 1367-1387); Epic 13 intro + FRs incl. **FR21 edit before approval** (1253-1257); siblings 13.5 review UX (1345-1365), 13.7 approve/reject/regenerate (1389-1409), 13.8 save (1411-1430)
- [Source: _bmad-output/planning-artifacts/prd.md] — FR21 "Reviewer can edit generated scripts before approval" (382); FR19/FR20 review/approve-reject (380-381); generated-script spec — Python/Playwright/assertions/stable selectors (309-316); security/no-secrets-in-scripts (237-243, 465-475)
- [Source: _bmad-output/planning-artifacts/ux-design-specification.md] — Step 4 Sarah review side-by-side + syntax highlighting + Next/Previous + approve/reject/skip (599-628); `react-syntax-highlighter` for Python scripts (1286), code `aria-label` (1293), `text-sm font-mono` (726); advisory/non-blocking warning pattern (1466-1480); mandatory review / no auto-advance (188, 239, 314); no "are you sure" modal (1426); accessibility color+text (787-795). **Gap:** the spec does not define the unsafe-pattern list, dirty-state UI tokens, or validation-error presentation (Saved Q#2 / Dev Notes).
- [Source: _bmad-output/planning-artifacts/architecture.md] — mandatory review / no auto-advance (271-272); no-direct-storage (518, 533); Sarah flow → test_scripts/ (824-828); security/read-only/no-secret-leakage (362-373)
- [Source: src/ai_qa/agents/sarah.py] — `GeneratedScript.script_content` (26-37, 32); `__init__` state (70-86); `handle_approve` accepts-but-ignores `data`, saves original (519-570, save call 537-540); `handle_reject` (572-619); `handle_skip` (621-666); `_present_current_script_for_review` + `review_data` (698-736, 714-725); failed-script placeholder (340-349); `self.app_settings` (82); `.spec.ts` fallback = 13.8 (538)
- [Source: src/ai_qa/agents/bob.py] — edit-before-approval analog: read `data["markdown"]` (1147), empty-guard (1148-1150), save edited (1168-1174), UX-DR12 stay-reviewable on failure (1191-1205)
- [Source: src/ai_qa/agents/alice.py] — stdlib `import ast` precedent (21)
- [Source: src/ai_qa/pipelines/artifact_adapter.py] — `save_script` (143-145), `_save_text` (191-202); `save_requirement` D8 (51-103) is the idempotency 13.8 may copy — **not** 13.6
- [Source: src/ai_qa/artifacts/storage.py] — `build_artifact_key` maps `playwright_script`/`testscript` → `test_scripts/` (28-38, 34-35)
- [Source: src/ai_qa/api/websocket.py] — dispatch `approve`→`handle_approve(data)` / `reject`→`handle_reject(feedback, data)` with full `data` passthrough (312-322) — no change needed
- [Source: src/ai_qa/config.py] — `AppSettings` "Script Generation" block where `script_unsafe_patterns` goes (121-136); deployment-config precedent (`chrome_path` 113-116, `confidence_threshold` 134-136)
- [Source: src/ai_qa/db/models.py] — `Project` has no settings/denylist column (51-77) — confirms Saved Q#2 gap
- [Source: frontend/src/components/SplitPanel.tsx] — Preview/Edit tabs (210-236), Preview/Edit branch (238-251), editable textarea (244-249), approve-sends-edited buffer (71-82), reset-on-nav effect to **diverge from** (37-44), amber warnings banner (162-191), footer (296-327)
- [Source: frontend/src/App.tsx] — Bob wiring to mirror: `handleBobMessage` dual path + fallback (721-774, 725-726), `handleBobApprove` threads `markdown` (974-987), history-replay path (778-812)
- [Source: frontend/package.json] — `react-syntax-highlighter` ^16.1.1 + types ^15.5.13 already present (33, 50) — no new package
- [Source: tests/test_agents/test_sarah.py] — Sarah test scaffold (patch adapter+ScriptGenerator 172-212; approve/reject/skip/navigate tests 411-800)
- [Source: frontend/src/components/__tests__/SplitPanel.test.tsx] — review-panel Vitest scaffold (fixture factory, child mocks, callback spies, role/text queries)
- [Source: _bmad-output/implementation-artifacts/13-5-sarah-side-by-side-review-ux.md] — the predecessor panel + transport this story extends (explicit "Edit (13.6)" fence; present-all + index-addressable + `_reviewed_indices`)
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; Pyrefly (narrow Optional/Any, no redundant cast); no bare except; no `# type: ignore`; full-stack sync; no new packages; security (no secrets in payloads/logs)

## Confirmed decisions (defaults locked by Thuong 2026-06-13 — "áp dụng default")

All four formerly-open questions are resolved to their defaults. No pending input — implement exactly as stated.

1. **Validation trigger = validate-on-approve, single round-trip (CONFIRMED — Saved Q#1).** The Approve action carries the edited content in `data["script_content"]`; the backend validates **before** saving — on failure, actionable errors + stay `REVIEW_REQUEST` (nothing saved); on pass, set `script.script_content = edited` and save **that**. Satisfies AC2 ("submitted for validation … errors shown") **and** AC3 ("validation passes → approve uses edited content") in **one** action with **no new WebSocket router action**. (Rejected: a separate **"Validate" button** — new `validate` WS message + `handle_validate` reusing the same validator — closer to AC2's literal wording but adds a router action 13.5 cautioned against; can be added later as a strict superset.)
2. **"Unsafe patterns configured for the project" = deployment-level denylist, NO migration (CONFIRMED — Saved Q#2).** A documented `DEFAULT_UNSAFE_SCRIPT_PATTERNS` constant in the new validator + an optional `AppSettings.script_unsafe_patterns` override (env/`config.yaml`, in the existing "Script Generation" block). "The project" = the deployment config — **no `Project` column, no Alembic migration, no admin UI** (consistent with how `chrome_path`/`confidence_threshold` are already deployment config). (Rejected: a per-project `Project.unsafe_script_patterns` JSON column + migration + project-settings admin UI — true per-project policy but materially larger; deferred to its own story if ever needed.)
3. **Edit retention = per-script, whole-session (CONFIRMED — Saved Q#3).** Edits held in a per-index map keyed by script index; they survive Prev/Next within the review session and are the value carried into approve (AC1). Reset only when a fresh `script_review` payload arrives. **Do NOT copy `SplitPanel`'s reset-on-navigation effect** ([SplitPanel.tsx:37-44](frontend/src/components/SplitPanel.tsx:37)) — that would lose edits on nav and fail AC1. (Rejected: reset-on-navigation — simpler, but a weaker reading of "retained in review state".)
4. **E2E coverage = scoped (CONFIRMED — Saved Q#4).** Backend pytest on `validate_script` + the edited-content approve path, and Vitest on the panel's edit/dirty/validation-error rendering, are the primary guardrails. Playwright E2E reaches the edit/validate UI only when a Chrome path + provider key are present (else AC-display assertions deferred to Vitest), because LLM-driven generation isn't E2E-reproducible without a provider key and the chrome-path FE is deferred (13.1); `page.route` mocking is forbidden. (Rejected: full LLM-driven E2E — same reasons 13.5 rejected it.)

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- `test_import_subprocess_provides_line_number`: initial assertion used `len(lines) + 2` but the unsafe import is at `len(lines) + 1` because `"\n".join(lines) + "\nimport subprocess\n"` places it at the next line after the join. Fixed to `len(lines) + 1`.

### Completion Notes List

- **Prerequisites verified (Task 0):** 13.5's `SarahScriptReviewPanel.tsx`, `_present_script_review`, index-addressable `handle_approve`, and `_reviewed_indices` DONE gate all confirmed present in the live tree. 13.1's phase dispatch and `sarahState` confirmed present. 13.2's `GeneratedScript.warnings`, `testcase.ts`, and `SarahScriptReviewPanel` imports confirmed present.
- **No Alembic migration** (Saved Q#2 default confirmed): `script_unsafe_patterns` is a deployment-level `AppSettings` env/config field only — no `Project` column, no schema change, no DB migration.
- **AC1 load-bearing mechanism:** On validation failure the backend sends only a targeted `script_validation_error` message and returns — it does **not** re-emit `_present_script_review()`. Re-emitting would send the original `script_content`, triggering the panel's payload-reset and wiping the user's edits (AC1 violation). The client Edit buffer is unaffected; the red error banner renders alongside the still-edited textarea. Guarded by Vitest tests "edit retention across nav" and "errors don't reset edit buffer".
- **Blank edit treated as no-edit:** `isinstance(edited, str) and edited.strip()` — whitespace-only `script_content` is skipped and the original is saved (back-compat), rather than surfacing as a validation error. This avoids a false validation block when the user approves without touching the textarea.
- **E2E scoped (Saved Q#4):** LLM script generation not E2E-reproducible without a provider key; `page.route` mocking forbidden by project rules. All AC1/AC2/AC3 behaviors are covered by the 39 Vitest tests in `SarahScriptReviewPanel.test.tsx` (16 new 13.6 tests + 23 updated 13.5 tests). No new Playwright E2E added. The existing `epic-13.spec.ts` AC3 block path is unchanged.
- **Full-stack sync verified:** `ScriptValidationError` Pydantic model ↔ `ScriptValidationError` TS interface ↔ `script_validation_error` WS metadata payload — all field names/types match exactly. Confirmed by `npm run typecheck` (0 errors).
- **No new packages:** `frontend/package.json` and `package-lock.json` unmodified. `react-syntax-highlighter` was already present from 13.5.
- **Backend suite:** 1360 passed, 2 pre-existing failures (unrelated to 13.6 — `test_output_writer` and `test_artifact_service_integration` — tracked in [[backend-test-suite-orphaned-legacy-tests]]). `uv run mypy src` 0 issues across 80 source files.
- **Frontend suite:** 258 passed / 23 files. `npm run lint` 0 warnings. `npm run typecheck` 0 errors.

### File List

- `src/ai_qa/pipelines/script_validator.py` — NEW: `ScriptValidationError`/`ScriptValidationResult` Pydantic models, `DEFAULT_UNSAFE_SCRIPT_PATTERNS`, `validate_script` (AST-based, never executes)
- `src/ai_qa/config.py` — MODIFIED: added `script_unsafe_patterns: list[str]` to `AppSettings` Script Generation block
- `src/ai_qa/agents/sarah.py` — MODIFIED: edit+validate step in `handle_approve` script-review branch; `_unsafe_patterns()` and `_format_validation_errors()` helpers added
- `frontend/src/types/testcase.ts` — MODIFIED: added `ScriptValidationError` and `ScriptValidationPayload` TS interfaces
- `frontend/src/components/agents/SarahScriptReviewPanel.tsx` — MODIFIED: Preview/Edit tab bar, per-index edit buffer, unsaved-changes indicator, red validation-error banner, `onApprove(index, editedContent?)` signature
- `frontend/src/App.tsx` — MODIFIED: `sarahState.validationErrors`, `script_validation_error` handler branch, `handleSarahApprove` threads `script_content`, prop wired to panel
- `tests/pipelines/test_script_validator.py` — NEW: 18 tests (valid script, syntax errors, unsafe patterns, blank content, security no-execution proof)
- `tests/test_agents/test_sarah.py` — MODIFIED: `TestSarahHandleApproveEditValidate` class with 5 tests (valid edit saves edited content, invalid edit blocks approve + emits error, back-compat no-edit saves original, unsafe pattern blocks)
- `frontend/src/components/__tests__/SarahScriptReviewPanel.test.tsx` — MODIFIED: 39 tests total (23 existing updated for new `onApprove` signature + 16 new 13.6 tests)

## Change Log

| Date | Version | Description | Author |
|------|---------|-------------|--------|
| 2026-06-17 | 1.0 | Story created | BMAD |
| 2026-06-17 | 1.1 | Implementation complete — all tasks done, status → review | claude-sonnet-4-6 |
