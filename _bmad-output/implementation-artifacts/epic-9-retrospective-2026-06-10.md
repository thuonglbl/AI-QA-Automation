# Epic 9 Retrospective

## Epic Title

Epic 9 - Per-User Secret Management and Dynamic AI Provider Setup

## Date

2026-06-10

## Participants

- Amelia (Senior Software Engineer) - facilitator
- John (Product Manager) - product / scope perspective
- Winston (System Architect) - architecture / security perspective
- Murat (Test Architect) - quality / testing perspective
- Thuong (Project Lead)

## Summary

Epic 9 replaced static provider-to-model assumptions with a runtime, per-user, validated AI provider configuration system. The 7-story chain delivered: encrypted per-user secret storage (9.1), a secret status/replacement API (9.2), a provider adapter interface with connection validation (9.3), dynamic model discovery (9.4), an agent model-assignment review with reject flow (9.5), runtime secret resolution for agent runs (9.6), and saved per-(user, project) configuration with rotation-applies-to-future-runs semantics (9.7). All 7 stories are `done` (100%).

## Delivery Metrics

| Metric | Value |
| ------ | ----- |
| Stories completed | 7/7 (9.1 -> 9.7) |
| Backend test growth | 663 -> 724 -> 769 -> 809; coverage held >= 80% gate (~82%) every story |
| New DB tables | 2 (`user_secrets`, `ai_provider_configs`) + Alembic migrations |
| Code review | Every story passed adversarial 3-layer review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) |
| Production incidents | 0 (R&D, pre-deployment) |
| Notable mid-course corrections | Browser Use Cloud API v2 fix (caught by live test); 9.5 wrong-feature build; on-prem key leak fixed in 9.7 |

## What Went Well

- **Secret hygiene as a non-negotiable gate.** Every story carried leak-canary assertions (the sentinel `sk-secret-LEAK-CANARY-123` must never appear in any output). 9.6 systematized this into 7 explicit output channels (WebSocket, persisted messages, artifact metadata, artifact content, audit logs, agent-run metadata, error responses). Rare consistency.
- **Scope discipline with clean extension points.** The `NotImplementedError("list_models is implemented in Story 9.4")` stub pattern in 9.3 is textbook - each story refused to implement the next story's slice and left a documented seam.
- **Reuse over reinvent.** 9.2 reused `set_user_secret` (no parallel upsert path); 9.4 reused 9.3's `_probe` / `_candidate_endpoints` / `_build_headers` helpers instead of re-deriving them.
- **Live-provider testing caught a real bug.** The `@pytest.mark.live_provider` integration test in 9.4 discovered Browser Use Cloud was actually on API v2 with the `X-Browser-Use-API-Key` header and `/billing/account` validation - not v3 as originally assumed. Real-stack proof beat assumptions.
- **Architecture-driven boundaries respected.** `ai_connection` never imports `agents`; adapters never read secrets directly (credentials are passed in). The "three concerns kept separate" model in 9.7 (encrypted secret / remembered non-secret config / immutable per-thread snapshot) is a clean mental model.
- **Strong continuity.** Each story's "Previous Story Intelligence" section carried forward concrete learnings (strip asymmetry, leak gate, the `>= 8` format floor).

## What Could Be Improved

- **Story 9.5 initially built the WRONG feature.** It shipped provider enable/disable instead of the spec'd reject-flow + rationale + discovered-model summary (residue: `story-9-5-provider-enable-disable.spec.ts`). Review had to rule "Accept + file a new story" to redo the actual spec. Root cause (confirmed by Project Lead): **the dev context drifted at dev time even though the story spec was sound** - the in-scope portion was misread, not the out-of-scope portion.
- **Schema changes without migrations.** The 9.5 review found `role->sender` rename, `conversation_data` removal, and `enabled_providers` / `jira_base_url` additions made with no Alembic migration. The `conversation_data` removal means existing threads lose conversation history (deferred). Silent data-integrity debt.
- **Story 9.4 scope creep.** Intended as just `list_models`, it absorbed the `gemini-chatgpt` -> `openai` + `gemini` split (backend + frontend), native Gemini discovery, benchmark UI, an `LLMClient` per-provider routing fix, and rate-limit error surfacing - five changelog iterations (0.1 -> 0.5). Useful bundling, but a large blast radius for one review pass.
- **Pre-existing leaks found late.** The on-prem `api_key` leak to the frontend (decrypted key returned into WebSocket metadata, pre-filled by `ProviderSelector`) violated FR57 and survived 9.1 -> 9.6, fixed only in 9.7 Task 10. The corrupt-ciphertext-as-plaintext issue was flagged in 9.1, deferred three times, and hardened in 9.7.
- **Story 9.7 shipped fragile initially.** 13 review patches, including 1 Critical (on-prem blank-key: `_test_connection` ran before the stored secret was resolved, breaking "leave blank to reuse" entirely) and 4 High (`use_saved_config` hardening: empty `_model_reasoning`, missing `project_id` guard, empty provider, dropped downstream agents). Caught in review (good), but the happy path shipped fragile.

## Key Lessons

- A written scope-boundary section is not enough; the dev must **actively confirm** scope/ACs at dev start. 9.5 had an explicit "do NOT implement 9.6/9.7" note yet still built the wrong in-scope feature.
- Adversarial 3-layer review reliably catches logic and security defects, but it is a late gate. Fragile happy paths (9.7 Critical/High) would surface earlier with a targeted integration test before review.
- Live-provider tests are worth keeping as a debug gate when integrating any new provider - they caught the Browser Use Cloud v2 reality.
- Schema evolution must travel with a migration, every time - the 9.5 miss is a recurring class of risk.
- Secret hygiene rigor (leak canaries across all output channels) is a reusable asset; carry it into Epic 10's artifact content/metadata.

## Previous Retrospective (Epic 8) Follow-Through

| Epic 8 action item | Status in Epic 9 |
| ------------------ | ---------------- |
| (1) Automate `sprint-status.yaml` updates when stories created | Improved - Epic 9 fully tracked (9-1...9-7 all present); no recurrence of the Epic 8 gap |
| (2) Visual streaming/polling for admin E2E execution (deferred from 8.6) | Not addressed - outside Epic 9 domain |
| (3) Sync fetch timeout on long E2E runs (deferred from 8.6) | Not addressed - outside Epic 9 domain |
| (4) Document Argon2 serial-execution requirement in README | No evidence addressed |
| (5) Resolve "plan dependent stories together" tension | Mixed - 9.5 wrong-feature + 9.4 scope creep show story-boundary coupling is still weak at plan time |

## Next Epic Preview - Epic 10: Project Artifact Collaboration and Realtime Sync

Project members share/browse/edit/delete and receive realtime updates for project-level artifacts on SeaweedFS + PostgreSQL. 8 stories. **10.7 (realtime refresh UX) and 10.8 (open-artifact notice) are already `done`, ahead of the 10.1 storage foundation.**

Dependency on Epic 9 is low - no Epic 9 assumption invalidates the Epic 10 plan. The relevant carry-forward is story 10.5 (agents write artifacts): generated scripts must contain no secrets, and the 9.6 leak tests already cover the artifact channels.

## Epic Update Required?

**NO.** No discovery from Epic 9 fundamentally changes the Epic 10 plan. No re-plan session needed - only the critical-path prep below.

## Action Items

### Process

1. **Scope-confirmation gate at dev-story start** - dev states aloud: what the story does / what is intentionally OUT of scope / how ACs are measured, before writing code. Owner: Amelia (dev process). From lesson 9.5(b).
2. **Migration in Definition-of-Done** - any story changing schema must include an Alembic migration + a plan for existing data. Owner: Winston + dev. From the 9.5 schema-without-migration miss.
3. **Lock story boundaries at PLAN time**, especially for dependent stories; split oversized stories (like 9.4) into independently reviewable sub-stories. Owner: John (PM). Upgrades the still-open Epic 8 action (5).

### Technical / Quality

1. **Integration test for fragile happy paths BEFORE review** - e.g. "leave blank to reuse key", the `use_saved_config` path. Owner: Murat. From the 9.7 Critical/High findings.
2. **Make live-provider testing a habit** - run `-m live_provider` as a debug gate when integrating any new provider. Owner: Murat.
3. **Sweep deferred-work for open key-related security items** (e.g. Fernet cache / real encryption-key rotation, intentionally out of 9.7 scope) into a deliberate backlog. Owner: Winston.

## Epic 10 Preparation Tasks (Critical Path)

- **[CRITICAL]** Reconcile 10.7 / 10.8 (already done) against 10.1 (storage foundation) - confirm the done frontend stories fit the upcoming backend, not the reverse. Owner: Amelia + Winston. (Selected by Project Lead as the #1 blocker.)
- Carry the 7-channel leak tests into artifact content for 10.5. Owner: Murat.
- Apply "migration in DoD" immediately to 10.1 / 10.4. Owner: Winston.
- Confirm SeaweedFS/S3 is dev-ready and seedable. Owner: Amelia.

## Readiness Assessment - Is Epic 9 really done?

| Item | Status |
| ---- | ------ |
| Stories | 7/7 `done` |
| Backend tests | Green (~809 tests, ~82% coverage, >= 80% gate held) |
| Frontend tests | 12 failures in `AdminDashboard.test.tsx` - PRE-EXISTING, unrelated to Epic 9 (flagged) |
| Git | Story 9.7 changes are UNCOMMITTED (working tree still modified + new untracked files) |
| 9.7 E2E live run (Task 11) | NOT RUN - needs a live Claude key + 3-terminal stack (spec created, typecheck clean) |
| Epic / retro flags | `epic-9: in-progress` (kept); `epic-9-retrospective: optional -> done` |
| Deploy / stakeholder acceptance | N/A (R&D) |

### Recommended critical path before flipping `epic-9 -> done` (pending Project Lead confirmation)

1. Commit the Story 9.7 working-tree changes (capstone risk - do not leave uncommitted).
2. Run `story-9-7-saved-config.spec.ts` on the live stack to prove the saved-config path end-to-end.
3. Then flip `epic-9: in-progress -> done`.
4. Accept the 12 `AdminDashboard.test.tsx` failures as separate pre-existing debt (handle in a dedicated story) - not an Epic 10 blocker.

## Commitments

- Action items: 6 (3 process, 3 technical/quality)
- Epic 10 preparation tasks: 4 (1 critical)
- Critical-path-to-done items: 3 (commit 9.7, run E2E live, then flip epic flag)

## Status

Epic 9 retrospective: done
