---
baseline_commit: d97e58533b04901b688a1c04f24032cfc8dc0e53
---
# Story 16.9: Multilingual Agent Conversation with English Specifications

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend + frontend. Add a per-user `conversation_language` (Admin Dashboard, **mirror the existing `timezone` precedent end-to-end**). Agents chat in that language and understand replies in it, but ALL persisted specs/artifacts (requirements, test cases, scripts, reports) and the static UI stay **English** ([[app-ui-english-only]]).

## Story

As a QA user who prefers a non-English language,
I want each agent to converse with me in my configured language while all generated specifications stay in English,
so that I can collaborate naturally without changing the language of the artifacts the team relies on.

## Acceptance Criteria

1. **Admin sets per-user language.** Given an administrator opens the Admin Dashboard user management, when they create or edit a user, then they can set that user's preferred conversation language, which is persisted on the user record.

2. **Agents speak the user's language.** Given a user has a preferred conversation language configured, when Alice, Bob, Mary, Sarah, or Jack send conversational (chat-facing) messages to that user, then the agent's chat-facing prose is written in the user's preferred language.

3. **Agents understand replies in that language.** Given the user replies in their preferred language, when the agent processes the reply (feedback, clarifications, approvals), then the agent understands the input regardless of its language and continues the workflow correctly.

4. **Persisted artifacts stay English.** Given the workflow produces persisted specifications (requirements, test cases, scripts, execution reports, and any other saved artifacts), when those artifacts are generated and saved, then their content remains in English regardless of the user's conversation language.

5. **Static UI stays English.** Given the existing App-UI-English-only convention, when static UI chrome (labels, buttons, placeholders, menus) is rendered, then it stays in English; only dynamic agent conversation content is localized.

## Tasks / Subtasks

- [ ] **Task 1 — Persist `conversation_language` on the user (AC: 1) [mirror timezone]**
  - [ ] Add `conversation_language: Mapped[str]` (NOT NULL, default `"en"`) to `User`, right after `timezone` ([src/ai_qa/db/models.py:43](src/ai_qa/db/models.py:43)).
  - [ ] New Alembic migration mirroring `c98f775f0b00_add_timezone_to_user.py` (server_default `"en"` to backfill existing rows). Thuong runs `alembic upgrade head` himself ([[git-commit-and-branch-preferences]]).
  - [ ] Add the field + a validator that restricts to the **supported language set** (allow-list, NOT a free `^[a-z]{2}$`) to `AdminUserCreateRequest` and `AdminUserUpdateRequest`; add it to `AdminUserResponse`; write it in `create_user`/`update_user`; return it in `_to_admin_user_response` ([src/ai_qa/api/admin.py](src/ai_qa/api/admin.py)). Mirror the timezone validator pattern (validate-against-known-set), default `"en"`.

- [ ] **Task 2 — Admin Dashboard language picker (AC: 1, 5)**
  - [ ] Add a `LANGUAGE_OPTIONS` list with the **DECIDED supported set** (Thuong 2026-06-22, model by language): English `en`, French `fr`, Italian `it`, Spanish `es`, German `de`, Vietnamese `vi`. (Derived from the target countries: Switzerland→German+French, Mauritius→English+French, UK/US→English.) New `frontend/src/lib/language.ts` (or alongside `lib/timezone.ts`). The BE allow-list (Task 1) MUST match this exact set.
  - [ ] Add create + edit language `<select>` to `AdminDashboard.tsx`, mirroring the timezone select (state vars, request bodies, sort key) ([frontend/src/components/admin/AdminDashboard.tsx](frontend/src/components/admin/AdminDashboard.tsx)).
  - [ ] Update the `AdminUser` TS type + the admin client request types to carry `preferred_language` ([frontend/src/types/project.ts](frontend/src/types/project.ts), `frontend/src/lib/projects.ts`). All labels English-only (AC5).

- [ ] **Task 3 — Make the language available at agent runtime (AC: 2, 3)**
  - [ ] Expose the user's language to agents via `PipelineContext` ([src/ai_qa/pipelines/context.py](src/ai_qa/pipelines/context.py)) — either an eager `user_language` field set when context is built, or a lazy lookup. Prefer eager (resolved once where the context is constructed, alongside `user_email`).
  - [ ] Confirm the resolution point (where `PipelineContext` is created with the authorized user) loads the user's `conversation_language`.

- [ ] **Task 4 — Inject the language instruction into conversational LLM prompts ONLY (AC: 2, 3, 4) [CORE + SEAM TO LOCATE]**
  - [ ] Locate the system-prompt construction seam for agent chat prose vs artifact-generation prompts. Conversational prose flows through `BaseAgent.send_message` ([src/ai_qa/agents/base.py](src/ai_qa/agents/base.py)) and agent LLM calls; artifact content is generated by the extraction/generation prompts (`src/ai_qa/prompts/*` — e.g. `test_extraction.py`, requirement formatter, script generation).
  - [ ] Add a "respond to the user in {language}; understand user input in any language" instruction to the **conversational** LLM calls only.
  - [ ] Add/confirm an explicit "**always produce this artifact content in English**" instruction in the **artifact-generation** prompts (requirements, test cases, scripts, reports) so AC4 holds even when the conversation language is non-English. The English boundary is the critical invariant.
  - [ ] Do not change `AgentMessage` shape or storage; language is ambient via context, not a message field.

- [ ] **Task 5 — Tests (all ACs)**
  - [ ] Backend: extend `tests/api/test_admin_users_api.py` with create/update language (valid + invalid code rejected, default `"en"`), mirroring the timezone tests; add a User-model default test.
  - [ ] Backend: a test that an agent's conversational LLM call receives the language instruction when context has a non-`en` language, and that artifact-generation prompts always carry the English instruction (assert at the prompt/seam, mock the LLM).
  - [ ] Backend: an artifact-boundary test — generated requirement/test-case/script content stays English regardless of `conversation_language` (assert the English instruction is present; full behavioral verification is integration/live).
  - [ ] Frontend: AdminDashboard language picker create/edit fires the request with `preferred_language`.
  - [ ] `uv run alembic upgrade head` → `uv run pytest`; `npm run typecheck` + `npm test`.

## Dev Notes

### Precedent to mirror end-to-end: `timezone` (added 2026-06-20)

`timezone` is the exact blueprint — model column ([models.py:43](src/ai_qa/db/models.py:43)), migration `c98f775f0b00`, admin request/response schemas + validator, create/update wiring, `_to_admin_user_response`, the FE `TIMEZONE_OPTIONS` + create/edit selects in `AdminDashboard.tsx`, and the `AdminUser` TS type. Follow it field-for-field, swapping IANA validation for an **allow-list of the supported language codes** (`{en, fr, it, es, de, vi}` — DECIDED, model-by-language) and default `"en"`. Reject any code outside the set with 422 (mirrors timezone's invalid-IANA → 422).

### The English boundary (AC4 — the critical invariant)

Localize ONLY agent chat prose. Everything persisted stays English:

- Bob → `requirements`/`markdown` artifacts (fed to Mary).
- Mary → `testcase` markdown (`TestCase.to_markdown`, fed to Sarah).
- Sarah → `playwright_script` (Python/selectors).
- Jack → `report` (test names, status).

The generation prompts (`src/ai_qa/prompts/*`) must explicitly instruct English output. The conversational instruction must NOT leak into these. There is **no existing i18n framework** in FE or BE (confirmed) — and none is needed; this is prompt-level localization of prose only.

### Seam to locate (Task 4)

The research could not pin the exact line where each agent's chat-prose system prompt is assembled vs the artifact-generation prompt. The dev must locate it: check `BaseAgent` LLM-call helpers, the `LLMClient` invocation path, and the per-agent `process()`/`handle_*` methods that compose user-facing text. Inject language at the conversational seam; assert the English instruction at the artifact seam. Keep generation prompts lean (slow on-prem models — [[project-context]] LLM-latency rule).

### Source tree components to touch

- `src/ai_qa/db/models.py` — **UPDATE** (`User.conversation_language`).
- `alembic/versions/` — **NEW** migration (mirror `c98f775f0b00`).
- `src/ai_qa/api/admin.py` — **UPDATE** (create/update request + validator, response, create_user/update_user, `_to_admin_user_response`).
- `src/ai_qa/pipelines/context.py` — **UPDATE** (`user_language`).
- `src/ai_qa/agents/base.py` + per-agent prose seam + `src/ai_qa/prompts/*` — **UPDATE** (conversational language instruction; English artifact instruction).
- `frontend/src/lib/language.ts` (**NEW**) + `lib/timezone.ts` pattern, `components/admin/AdminDashboard.tsx`, `types/project.ts`, `lib/projects.ts` — **UPDATE**.
- Tests: `tests/api/test_admin_users_api.py`, a user-model test, an agent-prompt/seam test, FE `AdminDashboard.test.tsx` — **UPDATE/ADD**.

### Current behavior to PRESERVE (regression guardrails)

- App-UI-English-only — every static label/button/placeholder stays English; only agent prose localizes ([[app-ui-english-only]]).
- Persisted artifacts stay English (AC4) — do not localize any generation prompt's output.
- Secrets resolved at runtime only; nothing about language touches secret handling.
- Deterministic model selection unaffected ([[alice-model-selection]]).
- Don't add a language field to `AgentMessage` or the WS payload — keep it ambient via context.

### Testing standards summary

- Backend pytest; copy the canonical admin auth-context fixture; mirror timezone validation tests (valid `vi`/`fr`, invalid `Vietnamese`/`xx` → 422, default `en`).
- For prompt assertions, mock the LLM at the client seam and assert the instruction strings; don't depend on a live model.
- No bare `pytest.raises(Exception)`; specific type + `match=`.

### Project Structure Notes

- Full-stack: BE model+migration+API+context+prompts, FE admin picker. One migration. No new dependencies, no i18n framework.

### References

- Epic + ACs: [epics.md#Story-16.9](_bmad-output/planning-artifacts/epics.md:1872)
- Timezone precedent: [models.py:43](src/ai_qa/db/models.py:43), `alembic/versions/c98f775f0b00_add_timezone_to_user.py`, [admin.py](src/ai_qa/api/admin.py)
- Coding/testing rules: [project-context.md](project-context.md)
- Related: [[app-ui-english-only]], [[message-timestamps-feature]] (timezone end-to-end pattern), [[project-environments-feature]] (admin user-list precedent)

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
