# Sprint Retrospective — Provider Auth Enhancements

**Date:** 2026-06-17
**Sprint:** Provider Auth Enhancements (PA-1 to PA-5)
**Participants:** Thuong (Project Lead), Amelia (Facilitator/Dev), Alice (Product Owner), Charlie (Senior Dev), Dana (QA Engineer)
**Sprint type:** Correct-Course / Sprint Change (triggered by UX change request on Alice provider screen)

---

## Executive Summary

The Provider Auth Enhancements sprint delivered a complete OAuth/SSO authentication subsystem for Claude alongside a provider list reorder. All 5 stories were completed in a single day, with all quality gates green (backend 1432 passed, frontend 272 passed, mypy/ruff/eslint/typecheck/build clean).

The sprint was technically successful. The most significant outcome was a **post-implementation discovery** that Anthropic's subscription SSO token cannot be used to authenticate the Messages API — a fundamental separation between product subscription and API access. This was documented thoroughly in the sprint-change-proposal and confirmed by Thuong testing `[IP_ADDRESS]` directly. IT has been contacted about an alternative path (Console API key).

---

## Sprint Delivery

| Story | Title | Status |
|-------|-------|--------|
| PA-1 | Provider list reorder + `claude-sso` registry entry | ✅ done |
| PA-2 | Claude SSO secret type + OAuth token storage (adapter + runtime) | ✅ done |
| PA-3 | OAuth/SSO login router + mock IdP (`claude_sso.py`) | ✅ done |
| PA-4 | ProviderSelector "Login SSO" UI + AdminDashboard sync | ✅ done |
| PA-5 | E2E spec (mock IdP path) + env vars + unit test coverage | ✅ done |

**Files changed:** 21 modified, 3 new (untracked at retro time, committed immediately after)
**Net change:** 720+ insertions, 45 deletions

**New provider order (final):**
1. On-Premises ← moved to top
2. Claude SSO ← new
3. Browser Use Cloud
4. Claude (API key)
5. Gemini
6. OpenAI

---

## What Went Well

### 1. Spec quality was exceptional
The sprint-change-proposal-2026-06-17.md was one of the clearest planning documents in the project. It covered: problem statement with evidence from current code, impact analysis with provider-id allowlist touch points, detailed change proposals per layer, recommended approach with justification for rejected alternatives, and implementation handoff with success criteria. Thuong identified this as the top highlight of the sprint.

### 2. Debug quality was high
The implementation proceeded with minimal rework. The team proactively fixed an adjacent issue in `openai_compatible.py` (+15 lines) discovered during implementation rather than deferring it.

### 3. Mock IdP design — testable today, upgrades to real SSO by env var
The configurable authorization server pattern (`CLAUDE_SSO_AUTHORIZE_URL` empty → self-hosted mock IdP) allowed complete E2E automation without dependency on external IdP, MFA, or CAPTCHA. The mock-to-real upgrade path is a pure config change.

### 4. Post-implementation discovery was documented honestly and thoroughly
Section 6 of the sprint-change-proposal documents a significant API access finding (see below) with three independent grounds, adversarial verification (4-stream research + 3 skeptics all REFUTED), and ranked compliant alternatives. This transparency is the correct response to an unexpected discovery.

### 5. Fast delivery with clean suite
A major new authentication subsystem (OAuth router, PKCE state, token storage, adapter, mock IdP, E2E spec, unit tests) was delivered in one session with all quality gates green.

---

## Challenges & Growth Areas

### 1. Subscription SSO ≠ API access — found post-implementation
The most important learning of this sprint: an Anthropic Team-plan SSO login cannot authenticate the Messages API. Three independent grounds (documented in sprint-change-proposal Section 6):
- Anthropic explicitly states subscription does not include API access
- Messages API requires a Console `x-api-key`
- Subscription OAuth tokens are explicitly prohibited in third-party apps by Anthropic ToS (banned since ~Apr 2026)

This discovery came *after* implementation, not during planning. A pre-implementation adversarial research pass on "can subscription SSO authenticate the Anthropic API?" would have caught this and potentially changed the design. The mock IdP path remains valid and useful for E2E; production use of `claude-sso` requires an IT-provisioned Console key.

### 2. No individual story spec files
Unlike previous epics (where each story has a dedicated `.md` file in `_bmad-output/implementation-artifacts/`), this sprint had no per-story spec files — PA-1 through PA-5 exist only as keys in `sprint-status.yaml`. The sprint-change-proposal served as the combined spec. This works for a fast-moving sprint change but reduces traceability for future readers.

### 3. Production flow has no E2E coverage
The real Anthropic OAuth flow (real IdP → real token → real API call) is explicitly not E2E-automated. This is a documented limitation, but it means the production path has never been end-to-end tested and cannot be without a real Console key + registered OAuth client.

---

## Key Insights

1. **Pre-flight research on external auth systems pays off.** For any feature that depends on a third-party auth mechanism, run adversarial research on "can this actually work?" before implementation — not after. A one-hour research pass can save a full sprint of misdirection.

2. **"Theatrical" features need explicit labelling.** The `claude-sso` browser login is currently UX theatre (the browser password does not authenticate the API — a server-side key does). This is documented, but needs to be surfaced clearly in the UI when IT key is absent so users are not confused.

3. **The gateway option should be verified early.** The sprint-change-proposal listed `[IP_ADDRESS]` as the best compliant option. Thuong verified directly that it does not serve Claude models, eliminating that option. This verification should happen during planning.

4. **Correct-Course workflow works well for rapid pivots.** The sprint-change-proposal → sprint-status → dev → retro cycle handled a major new subsystem cleanly without disrupting the main epic sequence.

---

## Previous Epic Action Items Follow-Through

**From Epic 12-13 Retrospective (2026-06-17):**

| Action Item | Status | Notes |
|-------------|--------|-------|
| Fix all 50 CR findings | ⏳ Pending | Not addressed in this sprint; Thuong noted these may no longer be valid given upcoming changes |
| Fix TypeScript typecheck config | ⏳ Pending | Deferred |
| Implement robust idempotency | ⏳ Pending | Deferred |
| Enforce E2E UI coverage | ⏳ Pending | Deferred |
| Centralize frontend state | ⏳ Pending | Deferred |

**Decision:** Epic 12-13 action items are being dropped. Priority has shifted to change requests and bug fixes. Epic 14+ is not currently a priority. The action items may no longer be valid given upcoming large changes to the codebase.

---

## Readiness Assessment

| Dimension | Status |
|-----------|--------|
| Code committed | ✅ Yes (committed after retro discussion) |
| Suite green | ✅ Yes (1432 BE + 272 FE, all gates) |
| `claude-sso` mock path E2E | ✅ Covered by `claude-sso-login.spec.ts` |
| `claude-sso` production path | ⚠️ Requires IT-provisioned Console API key |
| IT contacted | ✅ Yes (Thuong) — awaiting response |
| `[IP_ADDRESS]` Claude availability | ❌ Confirmed not available |

---

## Action Items

| # | Action | Owner | Status |
|---|--------|-------|--------|
| 1 | Commit working tree (PA-1–PA-5 + 3 new files) | Thuong | ✅ Done (committed before retro closed) |
| 2 | Await IT response on Console API key for `claude-sso` | Thuong | ⏳ Waiting |
| 3 | Once IT responds: decide code direction (keep SSO UX + IT key vs. fold into API-key path) | Thuong | 🔲 Pending IT answer |

---

## Next Steps

The team is focused on **change requests and bug fixes** as the immediate next priority, not Epic 14. Epic 14 (Audit Logging & Leadership Metrics) and later epics remain in backlog until priorities shift.

When IT responds about the Console API key:
- If yes → wire `claude-sso` to use the key server-side; the SSO UX stays as-is
- If no → evaluate folding `claude-sso` into the existing `claude` API-key path or keeping as a planned-but-deferred feature

---

*Retrospective facilitated by Amelia (Developer). Document language: English per project config.*
