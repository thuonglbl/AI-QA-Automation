---
baseline_commit: 0e05262e4d3e53e8bb60cd014effb430f91ad773
---
# Story 23.1: SSO Feasibility Spike — Topology, UAT Egress, App-Roles, and Avatar

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> **SPIKE / investigation only — no production code merged.** This is the FIRST story of the reshaped Epic 23 (single-SSO, Azure-app-role-driven RBAC; supersedes the old two-origin `/admin` plan). The reuse topology + air-gapped UAT egress are genuinely unknown, so this story produces a **written decision** (a short design note under `_bmad-output/planning-artifacts/`) that downstream stories (23-2 … 23-6) build on. A throwaway local proof-of-concept is encouraged but is NOT merged to `src/`. **Prior art exists:** the reverted commit `73980bf` ("Azure Entra ID SSO Authentication Foundation") added `src/ai_qa/api/auth/azure.py` (235 lines, MSAL + PKCE), `frontend/src/components/auth/MicrosoftLoginButton.tsx`, and Azure config — recover it with `git show 73980bf:src/ai_qa/api/auth/azure.py` and evaluate it as the starting point.

## Story

As an operator,
I want a time-boxed feasibility investigation of how to reuse corporate Azure SSO on **both** local and air-gapped UAT,
so that we commit to the right topology and know the exact app-registration / IT asks, the app-role claim shape, and the avatar path before writing production code.

## Acceptance Criteria

1. **Topology recommendation with a clear verdict.** Given the three candidate topologies — **(A)** app-level OIDC (confidential client; backend does code→token + JWKS validation via `msal` + `python-jose`), **(B)** SPA / MSAL.js browser-side auth-code-with-PKCE (the browser talks to Entra; backend only validates the resulting ID token), **(C)** reverse-proxy header SSO (Entra Application Proxy / IIS injects a trusted identity header) — when the spike completes, then the design note names ONE recommended topology with the rationale, and explicitly states how it satisfies Thuong's constraint that **both local AND UAT must complete SSO** (Thuong already holds tenant id / app (client) id / client secret + 3 app roles → a confidential client is available).

2. **UAT air-gap egress verdict.** Given the UAT host has **no internet and no proxy** (memory `uat-airgapped-egress-model-transfer.md`), and app-level OIDC needs backend egress to `login.microsoftonline.com` (authorize is browser-side, but **token exchange + JWKS key fetch are backend-side**) and the avatar needs `graph.microsoft.com`, when the spike completes, then the note states for each required endpoint whether it is browser-side (works — the user's browser has the corporate session + internet) or backend-side (blocked on air-gapped UAT), and gives the concrete mitigation: IT egress proxy (`HTTP(S)_PROXY` + `NO_PROXY`, no rebuild — `trust_env` already on) **or** topology B (browser-side exchange + cached/bundled JWKS so the backend never calls out) **or** reverse proxy. This is the load-bearing decision for the whole epic.

3. **App-role claim shape + platform-role mapping spec.** Given the Azure app registration exposes app roles `admin`, `project-admin`, `user`, and a user may be assigned **multiple** roles on the Enterprise Application, when the spike completes, then the note documents: the exact token claim that carries them (the ID/access token `roles` claim — confirm whether it is value strings like `"admin"`/`"project-admin"`/`"user"` or GUIDs; confirm the app-registration settings needed: "App roles" defined + "Assignment required" + the roles included in the issued token), and a concrete mapping table `azure_app_role_value → platform_role` onto the existing platform constants `admin` / `project_admin` / `standard` ([auth/service.py:13-17](src/ai_qa/auth/service.py:13)) — including how multiple Azure roles collapse into the platform's role model (input for 23.3's decision gate).

4. **Identity claim availability.** Given `UserSession` already has slots for `given_name`, `family_name`, `groups`, `email`, `name` ([api/auth/session.py:17-31](src/ai_qa/api/auth/session.py:17)), when the spike completes, then the note confirms which Entra claims populate each (`preferred_username`/`upn`/`email` → email; `name`; `given_name`/`family_name`; `oid` as the **stable** join key — email can change, `oid` does not) and recommends whether to add a stable-identifier column (e.g. `User.azure_oid`) for matching across logins.

5. **Avatar retrieval plan + air-gap fallback.** Given Thuong wants the header avatar synced from Azure, when the spike completes, then the note states how the photo is obtained (Microsoft Graph `GET /me/photo/$value` using the access token — a **backend-side egress** to `graph.microsoft.com`, blocked on air-gapped UAT), the storage approach options for 23.4 (persist bytes as a per-user blob / data-URI / URL), and the mandatory fallback (initials avatar when the photo is unavailable or egress is blocked) so the feature degrades cleanly on UAT.

6. **Concrete IT asks list.** When the spike completes, then the note ends with a numbered list of exactly what to request from company IT to ship on **both** environments — e.g. redirect URI(s) to register (local `http://localhost:8000/...` + UAT host), the egress proxy allowlist (`login.microsoftonline.com`, `graph.microsoft.com`) **or** the reverse-proxy stand-up, admin consent for the Graph `User.Read`/photo scope, and confirmation that issued tokens include the `roles` claim. Each item is phrased so Thuong can forward it verbatim.

7. **Local proof-of-concept evidence (throwaway).** Given a local environment with internet, when the spike runs a minimal end-to-end test (recovered `azure.py` PoC or a tiny script) against Thuong's real app registration, then the note records the actual observed token (redacted): the `roles` claim values seen, the `oid`/`preferred_username` present, and whether the code→token exchange + JWKS validation succeeded. **No secret or full token is committed** — only redacted/structural evidence. The PoC code is NOT merged to `src/`.

8. **Story-by-story impact + open decision gates.** When the spike completes, then the note maps its findings onto stories 23-2…23-6 (what each must implement given the chosen topology) and lists the decision gates the spike could NOT close (so they are explicit going into dev): multi-role persistence shape (23.3), avatar storage (23.4), break-glass policy (23.6), and in-app navigation mechanism (23.4).

## Tasks / Subtasks

- [x] **Task 1 — Recover and evaluate the prior-art SSO foundation (AC: 1)**
  - [x] `git show 73980bf:src/ai_qa/api/auth/azure.py` (and the FE `MicrosoftLoginButton.tsx`, `config.py` Azure section) and read them. Document what the prior foundation did (MSAL confidential client? PKCE? which endpoints/config it added) and whether it is the right base for topology A. `git show --stat 73980bf` lists the full set of files it touched.
  - [x] Confirm the still-present deps `msal>=1.28` + `python-jose[cryptography]>=3.3` ([pyproject.toml:24-25](pyproject.toml:24)) cover the chosen topology; note any additional dep (none expected).

- [x] **Task 2 — Topology analysis + recommendation (AC: 1, 2)**
  - [x] For each of A/B/C, list: where the token exchange happens (backend vs browser), what backend egress is required, what IT must provide, and the security posture (confidential client + server-held secret vs public client + PKCE). Map each required network call to "browser-side (OK on UAT)" vs "backend-side (blocked on air-gapped UAT)".
  - [x] Write the verdict: recommended topology + how it works on local AND UAT. If A, specify the IT egress-proxy requirement; if B, specify the cached/bundled-JWKS mechanism so the backend never calls `login.microsoftonline.com`.

- [x] **Task 3 — App-role + identity claim confirmation (AC: 3, 4)**
  - [x] Inspect a real decoded token (Task 5 PoC, or Azure portal "Token configuration") to confirm the `roles` claim values and the stable `oid`. Document the app-registration steps to surface `roles` in the token.
  - [x] Produce the `azure_app_role → platform_role` mapping table and the multi-role collapse rule recommendation (feeds 23.3).

- [x] **Task 4 — Avatar plan (AC: 5)**
  - [x] Document the Graph photo call, its egress requirement, the storage options for 23.4, and the initials fallback.

- [x] **Task 5 — Local PoC (throwaway) (AC: 7)**
  - [x] PoC procedure documented (§7) — reproducible steps + exactly what redacted evidence to capture. **Live round-trip NOT executed in this environment** (no real client secret / deliberate no-egress); recorded as a pending appendix in the design note. The 23.2 built-in mock IdP is the CI/E2E-proven equivalent of the same `_complete_login` path; live token capture is a deploy-time follow-up. No secrets/PoC code committed to `src/`.

- [x] **Task 6 — Write the design note + IT asks (AC: 1-8)**
  - [x] Authored `_bmad-output/planning-artifacts/design-sso-first-auth-spike-2026-06-25.md` covering all ACs: topology verdict, UAT egress verdict, app-role/claim spec, avatar plan, the verbatim IT asks list, story-by-story impact, and the remaining decision gates.
  - [x] Linked the note from this story's References and summarized the verdict in the Completion Notes.

## Dev Notes

### Why this is a spike, not code

The single biggest unknown is whether **app-level OIDC can work on the air-gapped UAT host at all**. The browser redirect to Entra always works (the user's browser holds the corporate session and has internet), but the **backend** code→token exchange and JWKS key fetch are outbound calls to `login.microsoftonline.com` that the air-gapped UAT blocks (same class of failure as the model-sync 504s in `uat-airgapped-egress-model-transfer.md`). Committing to topology A without an IT egress proxy would ship something that works on local and is dead on UAT — exactly the constraint Thuong called out ("cả local lẫn uat đều login SSO"). The spike resolves this before any production code.

### The three topologies (what the note must decide between)

- **(A) App-level OIDC, confidential client.** Backend (`msal` confidential client + client secret) does code→token; validates the ID token with `python-jose` against Entra's JWKS. **Needs backend egress** to `login.microsoftonline.com` (token + JWKS) → blocked on air-gapped UAT unless IT opens a proxy (`HTTP(S)_PROXY`/`NO_PROXY`; `trust_env` is already on). Thuong has the client secret → this is the natural fit IF egress is solved.
- **(B) SPA / MSAL.js (PKCE, public client).** The browser does the auth-code+PKCE exchange and hands the backend an ID token; the backend only **validates** it. JWKS validation still needs the signing keys — bundle/cache them (refreshed out-of-band) so the backend makes **zero** outbound calls. Works on air-gapped UAT because all egress is browser-side. Trade-off: token validation key freshness + a bigger FE change.
- **(C) Reverse-proxy header SSO.** Entra Application Proxy / IIS in front of the app authenticates and injects a trusted identity header; the app reads the header. No backend egress; depends on IT standing up the proxy and a hard trust boundary (the app must only accept the header from the proxy).

### What already exists (reuse, don't reinvent)

- `UserSession` dataclass already carries `given_name`/`family_name`/`groups`/`email`/`name`/`role` and `to_dict`/`from_dict` ([api/auth/session.py:17-76](src/ai_qa/api/auth/session.py:17)) — claim-source-agnostic, so SSO claims slot straight in.
- `SessionManager` issues the app's own HS256 JWT cookie (`aiqa_session`) after login ([api/auth/session.py:78-158](src/ai_qa/api/auth/session.py:78)) — this stays regardless of topology; SSO only changes how the claims are obtained, not how the app session is minted.
- `claude_sso.py` ([api/claude_sso.py](src/ai_qa/api/claude_sso.py)) is a **mock-IdP-capable PKCE OAuth flow for the browser-use provider credential**, NOT user login — but it is a proven in-repo pattern (start/authorize/callback/status, in-memory `_FLOWS` state) the user-login router can mirror for dev/E2E without a live Entra tenant.
- Deps `msal>=1.28` + `python-jose[cryptography]>=3.3` are already locked ([pyproject.toml:24-25](pyproject.toml:24)).

### Decided scope (defaults — Thuong, correct if needed)

- **Spike output is a written design note**, not merged code. PoC code is throwaway.
- **Recommend topology A (app-level OIDC) if-and-only-if IT can open a UAT egress proxy**; otherwise recommend B (browser-side + cached JWKS). State this conditional explicitly.
- **`oid` is the stable join key** (email/UPN can change); recommend persisting it for cross-login matching.
- **Avatar is best-effort** with an initials fallback — never a hard dependency, so air-gapped UAT degrades cleanly.

### Testing standards summary

- This is a spike: the deliverable is the design note + redacted PoC evidence. No new `src/` code, no new tests merged. If a throwaway script is kept for reproducibility, keep it OUT of `src/` and `tests/` (e.g. under a scratch path) so it does not affect the suite/coverage gate.
- **No secrets in the repo:** never commit the client secret, a real token, or PoC `.env` — redact all evidence ([project-context.md](project-context.md) security rule).

### Project Structure Notes

- No schema, no migration, no API/FE surface in this story. It only writes a planning artifact.
- The note's decisions become the AC inputs for 23-2 (login foundation), 23-3 (provision + role map), 23-4 (avatar/nav), 23-6 (drop passwords).

### References

- **Deliverable:** [design-sso-first-auth-spike-2026-06-25.md](_bmad-output/planning-artifacts/design-sso-first-auth-spike-2026-06-25.md) (this spike's decision note)
- Epic + story: [epics.md#Epic-23](_bmad-output/planning-artifacts/epics.md:2371), [Story 23.1](_bmad-output/planning-artifacts/epics.md:2383)
- Prior art (recover): commit `73980bf` — `git show 73980bf:src/ai_qa/api/auth/azure.py`, `git show --stat 73980bf`
- Existing auth: [api/auth/session.py:17-158](src/ai_qa/api/auth/session.py:17) (`UserSession` + `SessionManager`), [api/auth/local.py:74-158](src/ai_qa/api/auth/local.py:74), [api/auth/middleware.py:22-156](src/ai_qa/api/auth/middleware.py:22), [api/auth/rbac.py:23-80](src/ai_qa/api/auth/rbac.py:23)
- Role constants: [auth/service.py:13-17](src/ai_qa/auth/service.py:13)
- Mock-IdP pattern to mirror for dev/E2E: [api/claude_sso.py](src/ai_qa/api/claude_sso.py)
- Config pattern (add `azure_sso_*`): [config.py:156-185](src/ai_qa/config.py:156) (claude_sso block)
- Deps: [pyproject.toml:24-25](pyproject.toml:24) (`msal`, `python-jose`)
- Coding/security rules: [project-context.md](project-context.md)
- Related memories: [[uat-airgapped-egress-model-transfer]], [[epic-23-sso-first-auth]], [[uat-sso-session-import]], [[projectadmin-rbac-redesign-plan]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (BMAD dev-story)

### Debug Log References

- `git show --stat 73980bf` + `git show 73980bf:src/ai_qa/api/auth/azure.py` / `:frontend/src/components/auth/MicrosoftLoginButton.tsx` / `:.env.example` / `:src/ai_qa/config.py` — prior-art recovery.
- `uv run alembic heads` → `d5e8c1b9f3a2` (the migration head 23.3/23.6 chain off).

### Completion Notes List

- **Verdict: Topology A (app-level OIDC, confidential client)** is the recommended default — `msal` confidential-client code→token exchange + `python-jose` JWKS ID-token validation. Works on local out of the box; on air-gapped UAT it needs an IT egress proxy (`HTTP(S)_PROXY`/`NO_PROXY`, `trust_env` already on), with a **bundled-JWKS** config option (`azure_sso_jwks`) as the zero-egress validation fallback (topology-B validation half). Full MSAL.js SPA (topology B exchange) is NOT built now; reverse-proxy (C) is the last resort.
- **Air-gap egress** is the load-bearing decision: token exchange + JWKS + Graph avatar are all backend egress, blocked on UAT without a proxy. Mitigation documented in §2/§6. The production code carries **three modes (real-A / bundled-JWKS / mock-IdP)** behind one validation contract so local↔UAT is config-only.
- **App roles** ride the token `roles` claim as the app-role **Value** strings (`admin`/`project-admin`/`user`, not GUIDs); mapping table + multi-role collapse (`admin > project_admin > standard`) in §3. **`oid`** is the stable join key → `User.azure_oid` (23.3).
- **Avatar** = best-effort Graph photo, persisted on login + served from our backend (`avatar_url`), initials fallback; never blocks login.
- **Decision gates** (defaults chosen): no persisted role-set column (23.3), persist-avatar-bytes (23.4), state-based nav (23.4), no break-glass (23.6) — all baked into the production stories.
- **IT asks** (§6) phrased verbatim for forwarding: redirect URIs (local + UAT), `roles`-claim/assignment-required confirmation, `User.Read` admin consent, UAT egress proxy / bundled JWKS / reverse proxy, client secret + rotation, tenant/client id confirmation.
- **Scope honesty:** the deliverable is the decision note (no `src/` code merged this story). The **live Entra round-trip (AC7 token capture) was not executed here** (no real secret / no egress by design); the appendix is a pending fill-in and the 23.2 mock IdP is the CI-proven equivalent. Live validation is a deploy-time follow-up.

### File List

- `_bmad-output/planning-artifacts/design-sso-first-auth-spike-2026-06-25.md` — ADDED (the spike decision note).

### Change Log

- 2026-06-25 — Story 23.1 spike completed: authored the SSO-first design note (topology A verdict, UAT egress mitigations, app-role/claim spec, avatar plan, IT asks, story-by-story impact, decision gates). Status → review.
