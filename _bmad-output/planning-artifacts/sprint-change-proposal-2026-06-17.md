# Sprint Change Proposal — Provider Selection Reorder + Claude SSO Login

- **Date:** 2026-06-17
- **Author:** Thuong (with Claude Code, Correct Course workflow)
- **Trigger:** Change request on the Alice "AI Provider Configuration" screen (Step 1 of 5)
- **Scope classification:** **Major** (new browser-based OAuth/SSO authentication subsystem) + Minor (reorder, admin dashboard sync)

---

## Section 1 — Issue Summary

### Problem statement

On the Alice provider-selection screen ([ProviderSelector.tsx](frontend/src/components/ProviderSelector.tsx), driven by `PROVIDER_OPTIONS` in [alice.py:52](src/ai_qa/agents/alice.py)), three changes are requested:

1. **Reorder** — move **On-Premises** to the top of the provider list.
2. **Split Claude into two options:**
   - A **new "Claude SSO" login option** in 2nd position. This is a *new feature*: clicking "Login SSO" opens a browser tab to an identity-provider (IdP) login page where the user enters their company email + password; on successful browser authentication the tool itself becomes authenticated (OAuth Authorization-Code flow).
   - The **existing "Claude (API key)" option is kept**, remaining directly after Browser Use Cloud.
3. **Update the Admin Dashboard** ([AdminDashboard.tsx:44](frontend/src/components/admin/AdminDashboard.tsx)) provider enable/disable list to match (new `claude-sso` entry + reordering).

### How it was discovered / context

User-initiated UX + capability request. The UX spec already anticipated this: Claude was always documented as *"API key (limited accounts), **SSO enterprise login (TBD)**"* ([ux-design-specification.md:108](_bmad-output/planning-artifacts/ux-design-specification.md), [:503](_bmad-output/planning-artifacts/ux-design-specification.md)), and the design test catalog lists *"TC-004: Login with SSO — verify SAML redirect and successful authentication"* ([ux-design-directions.html:421](_bmad-output/planning-artifacts/ux-design-directions.html)). This proposal turns that "TBD" into an implemented feature.

### Evidence — current state (verified in code)

- Provider order is backend-owned: `get_provider_options()` returns `PROVIDER_OPTIONS` in array order; the frontend renders that order verbatim ([ProviderSelector.tsx:159](frontend/src/components/ProviderSelector.tsx)). **Current order:** `browser-use-cloud` → `claude` → `gemini` → `openai` → `on-premises`.
- Claude today authenticates with an `api_key` stored as encrypted per-user secret type `claude` ([secrets/\_\_init\_\_.py:13](src/ai_qa/secrets/__init__.py)); runtime builds `ChatAnthropic` with `x-api-key` ([client.py:62](src/ai_qa/ai_connection/client.py)).
- The company uses **Claude Team plan** under tenant "Information Technology Vietnam" (confirmed by the user from the Claude desktop app). Anthropic supports **OAuth 2.1 + PKCE (S256)** browser login (the same mechanism `ant auth login` / Claude Code uses); the resulting token authenticates the API via `Authorization: Bearer <token>` + `anthropic-beta: oauth-2025-04-20` (grounded via the `claude-api` reference). For a Team/Enterprise tenant, that browser login federates to the company IdP (Microsoft / Azure Entra) where the user types email + password.
- E2E seed values for the new flow: **`TEST_CLAUDE_SSO_EMAIL`** + **`TEST_CLAUDE_SSO_PASSWORD`** (new). `TEST_CLAUDE_KEY` remains the **personal API key** for the API-key option and is **unrelated** to SSO.

---

## Section 2 — Impact Analysis

### Epic impact

- This affects **Epic 9** (per-user secrets + dynamic provider setup) and the Alice step — both `done`. No in-flight epic is blocked. The change is best tracked as a **new follow-up story set under a "Provider Auth Enhancements" epic** (proposed Epic 14-A or appended to the Epic 9 area), because it introduces a genuinely new subsystem (OAuth/SSO), not just a tweak.
- No downstream epic (Bob/Mary/Sarah/Jack) changes behavior — they consume whatever provider Alice configured. They only benefit transparently once `claude-sso` resolves to a working Claude client at runtime.

### Story impact (proposed new stories)

| Story | Title | Layer | Risk |
| ------ | ------ | ------ | ------ |
| SSO-1 | Provider list reorder + `claude-sso` registry entry | Backend + FE types/icons | Low |
| SSO-2 | Claude SSO secret type + OAuth token storage | Backend (secrets) | Low |
| SSO-3 | OAuth/SSO login subsystem (authorize → callback → token exchange) | Backend (new router) | **High** |
| SSO-4 | `ProviderSelector` "Login SSO" button + popup + status polling | Frontend | Medium |
| SSO-5 | Runtime: `claude-sso` → `ChatAnthropic` via Bearer + beta header | Backend (client.py) | Medium |
| SSO-6 | Admin Dashboard provider list update | Frontend | Low |
| SSO-7 | E2E + unit coverage (mock IdP path) | Tests | Medium |

### Artifact conflict analysis

- **PRD** — no conflict; aligns with the existing FR around provider configuration. The "SSO enterprise login (TBD)" note in the UX spec is fulfilled.
- **Architecture** — **new component**: an OAuth/SSO authentication flow (authorize endpoint, callback handler, PKCE state store, token storage). This is the only architecturally significant addition. The provider-adapter seam ([providers/\_\_init\_\_.py](src/ai_qa/ai_connection/providers/__init__.py)) and secret store extend cleanly.
- **UI/UX** — `ProviderSelector` gains a credential-less "Login SSO" affordance (button + popup + post-login state) distinct from the api_key text input. Admin Dashboard provider list changes.
- **Security (NFR)** — OAuth tokens are short-lived secrets: store encrypted (per-user secret store), never return to the frontend, never log. Reuses the established encrypted-secret pattern.
- **CI/Infra** — `.env.example` gains `TEST_CLAUDE_SSO_EMAIL` / `TEST_CLAUDE_SSO_PASSWORD`; E2E config gains the mock-IdP-driven login path.

### Provider-id allowlist touch points (every place that must learn `claude-sso`)

Backend: [secrets/\_\_init\_\_.py](src/ai_qa/secrets/__init__.py) (`SECRET_TYPE_CLAUDE_SSO`, `CANONICAL_SECRET_TYPES`, `PROVIDER_SECRET_TYPE_MAP`); [alice.py:52](src/ai_qa/agents/alice.py) (`PROVIDER_OPTIONS`); [providers/\_\_init\_\_.py:34](src/ai_qa/ai_connection/providers/__init__.py) (`_PROVIDER_ADAPTERS`, `_PROVIDER_BASE_URL_SETTINGS`); [config.py](src/ai_qa/config.py) (new SSO settings); [client.py:50](src/ai_qa/ai_connection/client.py) (`_build_chat_model`); new OAuth router under `src/ai_qa/api/`.
Frontend: [provider.ts:4](frontend/src/types/provider.ts) (`ProviderId`); [ProviderSelector.tsx:53](frontend/src/components/ProviderSelector.tsx) (`PROVIDER_LOGOS` + SSO render branch); [AdminDashboard.tsx:44](frontend/src/components/admin/AdminDashboard.tsx) (`PROVIDER_OPTIONS` + `PROVIDER_ICON_FILES`).
E2E: provider lists in `frontend/e2e/story-9-*.spec.ts` + a new SSO login spec.

---

## Section 3 — Recommended Approach

**Selected path: Option 1 — Direct Adjustment (Hybrid: Minor reorder + Major new feature).** No rollback, no MVP reduction. Add the new option and subsystem alongside the existing Claude API-key path; nothing is removed.

### Target provider order (final)

1. **On-Premises** (`on-premises`) — moved to top
2. **Claude SSO** (`claude-sso`) — **new**
3. **Browser Use Cloud** (`browser-use-cloud`)
4. **Claude (API key)** (`claude`) — kept, stays right after Browser Use
5. **Google / Gemini** (`gemini`)
6. **OpenAI / ChatGPT** (`openai`)

> Note: `quality_rank` drives the *badge label only* (display order = array order). `claude-sso` gets `quality_rank: 2`, `security_level: "enterprise"` (same "Second quality / Strong secure" as Claude).

### SSO authentication design (the load-bearing decision)

The "Login SSO" flow is an **OAuth 2.0 Authorization-Code + PKCE** flow with a **configurable authorization server**, so the same code serves both production and test:

```
[Login SSO] click
   → FE: POST /api/auth/claude-sso/start  → { authorize_url, state }
   → FE: window.open(authorize_url)            (new browser tab)
   → IdP login page: user enters email + password, authenticates
   → IdP redirects to backend callback with ?code&state
   → BE: POST/GET /api/auth/claude-sso/callback → exchange code for token (PKCE verifier)
   → BE: store token as encrypted per-user secret `claude_sso`; mark state authenticated
   → tab shows "Login successful — you can close this tab"
   → FE: polls GET /api/auth/claude-sso/status?state=...  → authenticated:true
   → FE: proceeds exactly like a normal provider "Start" (connection test + model assignment)
Runtime: claude-sso → ChatAnthropic(base_url, auth via Bearer + anthropic-beta: oauth-2025-04-20)
```

**Configurable authorization server** via new settings in [config.py](src/ai_qa/config.py):

- `CLAUDE_SSO_AUTHORIZE_URL` — empty ⇒ use the **built-in self-hosted mock IdP page** (`GET /api/auth/claude-sso/authorize`) for dev/E2E (Playwright fills `TEST_CLAUDE_SSO_EMAIL`/`TEST_CLAUDE_SSO_PASSWORD`); set ⇒ redirect to the **real Anthropic OAuth** endpoint, which federates to IdP for the Team plan.
- `CLAUDE_SSO_TOKEN_URL`, `CLAUDE_SSO_CLIENT_ID`, `CLAUDE_SSO_REDIRECT_URI` — real-OAuth params (unused in mock mode).

This satisfies the user's exact UX ("open a tab, type email+password, tool gets logged in"), is **fully E2E-testable today** via the mock IdP (no dependency on a live external IdP, MFA, or captcha), and upgrades to real Anthropic Team-plan SSO by setting env vars — no code change.

### Why not the alternatives

- **Real Anthropic OAuth only** — not automatable in E2E (cross-origin popup → Microsoft login, MFA), needs a registered OAuth client; blocks delivery on external setup.
- **Azure Entra app-SSO** — explicitly deferred in [epics.md:132](_bmad-output/planning-artifacts/epics.md); out of scope and unnecessary for the provider-login use case.
- **Email-as-credential (no browser)** — rejected by the user; they specifically want a browser login tab.

### Effort / risk

- Reorder + registry + admin (SSO-1, SSO-6): **Low effort, Low risk.**
- Secret type + OAuth subsystem + runtime (SSO-2/3/5): **Medium–High effort, Medium–High risk** (new auth surface, must pass strict mypy/Pyrefly/ESLint gates + E2E).
- Timeline: deliverable as one feature branch; recommend sequencing SSO-1/6 first (immediately verifiable), then the OAuth subsystem.

---

## Section 4 — Detailed Change Proposals

### 4.1 Backend — `PROVIDER_OPTIONS` ([alice.py:52](src/ai_qa/agents/alice.py))

Reorder to On-Premises → **Claude SSO (new)** → Browser Use → Claude → Gemini → OpenAI. New entry:

```python
{
    "id": "claude-sso",
    "name": "Anthropic / Claude (SSO)",
    "description": "Cloud · Enterprise SSO login",
    "quality_rank": 2,
    "security_level": "enterprise",
    "credential_fields": [],          # no manual credential — uses the SSO login flow
    "auth_method": "sso",             # new discriminator the FE keys off to render the button
    "endpoint_setting": "claude_api_base_url",
    "env_key": "",                    # token comes from the OAuth flow, not an env key
},
```

The existing `claude` (API key) entry is unchanged except for its position.

### 4.2 Backend — secrets ([secrets/\_\_init\_\_.py](src/ai_qa/secrets/__init__.py))

Add `SECRET_TYPE_CLAUDE_SSO = "claude_sso"`, append to `CANONICAL_SECRET_TYPES`, and map `"claude-sso" → SECRET_TYPE_CLAUDE_SSO` in `PROVIDER_SECRET_TYPE_MAP`. Stores the OAuth token (write-only; never returned). No DB migration (secret_type is a string column value).

### 4.3 Backend — new OAuth router `src/ai_qa/api/claude_sso.py`

Endpoints: `POST /start` (build authorize URL + PKCE challenge, persist verifier+state), `GET /authorize` (mock IdP login form, dev/E2E only), `POST /callback` (validate state, exchange code → token, store `claude_sso` secret, mark authenticated), `GET /status` (poll). PKCE state held in a short-TTL in-memory/DB store keyed by `state`. Mock mode validates the posted email/password and issues a placeholder token mapped to a server-side enterprise key for actual model calls.

### 4.4 Backend — adapter + runtime

- `providers/__init__.py`: register `"claude-sso": ClaudeSSOAdapter()` + base-url setting. The adapter `validate_connection` probes Claude `/v1/models` using the obtained token (Bearer) — mirrors `AnthropicAdapter` but with Bearer + the OAuth beta header.
- `client.py` `_build_chat_model`: add a `claude-sso` branch building `ChatAnthropic` with `default_headers={"anthropic-beta": "oauth-2025-04-20"}` and Bearer auth when the secret is an OAuth token (mock mode: fall back to the configured enterprise key with `x-api-key`).

### 4.5 Frontend

- `provider.ts`: add `"claude-sso"` to `ProviderId`; add optional `authMethod?: "sso" | "api_key"` to `ProviderOption`.
- `ProviderSelector.tsx`: add the `claude-sso` logo; when `authMethod === "sso"`, render a **"Login SSO"** button (instead of the credential text input) that calls `/start`, opens the tab, and polls `/status`; on success, invoke `onSelect("claude-sso", {})`.
- `AdminDashboard.tsx`: add `{ id: "claude-sso", label: "Claude (SSO)" }` to `PROVIDER_OPTIONS` (reordered to match Alice) and an icon entry in `PROVIDER_ICON_FILES`.

### 4.6 Config + env

- `config.py`: `claude_sso_authorize_url`, `claude_sso_token_url`, `claude_sso_client_id`, `claude_sso_redirect_uri`, `claude_sso_enterprise_api_key` (server-side key used for real model calls in mock/demo mode).
- `.env` / `.env.example`: add `TEST_CLAUDE_SSO_EMAIL`, `TEST_CLAUDE_SSO_PASSWORD`; keep `TEST_CLAUDE_KEY` as the personal API-key value.

### 4.7 Tests

- Backend unit: adapter Bearer/beta header, OAuth callback token exchange, secret mapping.
- Frontend Vitest: `ProviderSelector` renders the Login-SSO button for `authMethod:"sso"` and the api_key input otherwise.
- E2E: new spec drives the mock IdP login with `TEST_CLAUDE_SSO_EMAIL`/`PASSWORD`; assert the provider proceeds. (Real-Anthropic OAuth is **not** E2E-automated — documented limitation; provider-key-dependent specs skip as today.)

---

## Section 5 — Implementation Handoff

- **Scope: Major** (new auth subsystem) → primary owner **Developer agent**, with **Architect** sign-off on the OAuth/SSO component (state store, token lifecycle, mock-vs-real switch).
- **Sequencing:** SSO-1 (reorder + registry) and SSO-6 (admin) first — small, immediately verifiable. Then SSO-2 → SSO-3 → SSO-5 (the OAuth subsystem + runtime). SSO-4 (FE login UX) pairs with SSO-3. SSO-7 (tests) throughout.
- **Success criteria:** Alice shows the 6 options in the target order; "Login SSO" opens a tab, accepts email+password (mock IdP in dev/E2E), and the tool proceeds to model assignment; `claude-sso` makes a real Claude call at runtime; Admin Dashboard lists and gates `claude-sso`; backend `uv run pytest` green, `npm run typecheck`/`build`/`lint` green, E2E mock-IdP login spec green.
- **Deferred / external:** wiring the *real* Anthropic Team-plan OAuth (client registration, IdP federation, redirect URI allow-listing) is config-only and validated against a live tenant outside automated tests.

---

## Section 6 — Post-implementation finding: subscription SSO ≠ API access (researched 2026-06-17)

After implementation, a viability question surfaced: the user holds **only** a corporate SSO username/password for the Claude **Team plan** (org "Information Technology Vietnam") and **no Anthropic API key** (IT manages keys). Question: can that login power the tool's Claude calls in local/UAT? A 4-stream + 3-skeptic adversarial research pass (all three skeptics **REFUTED**, high confidence) concluded:

**No — a Team-plan SSO login alone cannot give a custom app Claude Messages API access, in any environment.** Three independent grounds:

1. **Subscription ≠ API.** Anthropic states a paid subscription (Pro/Max/**Team**/**Enterprise**) *"doesn't include access to the Claude API or Console"* — separate products, separate billing, separate credentials. The seat fee includes **no** API/token allowance. ([support.claude.com/9876003](https://support.claude.com/en/articles/9876003-i-have-a-paid-claude-subscription-pro-max-team-or-enterprise-plans-why-do-i-have-to-pay-separately-to-use-the-claude-api-and-console))
2. **Messages API requires a Console `x-api-key`.** SSO login never provisions one; only an org admin/IT creates keys in the Console.
3. **The subscription OAuth token (`sk-ant-oat01…`, via `claude setup-token`) does not bridge the gap.** It is scoped to Claude Code / native apps; the public Messages API rejects it (*"OAuth authentication is currently not supported"*, [claude-code#37205 — "not planned"](https://github.com/anthropics/claude-code/issues/37205)); and using subscription OAuth tokens in any third-party product (incl. the Agent SDK) is **explicitly prohibited** by Anthropic's Feb-2026 Authentication & Credential Use policy, **enforced** (bans without notice, ~Apr 2026). ([code.claude.com/legal-and-compliance](https://code.claude.com/docs/en/legal-and-compliance), [The Register](https://www.theregister.com/2026/02/20/anthropic_clarifies_ban_third_party_claude_access/))

The SSO login *does* grant: claude.ai web, Claude Desktop, mobile, and Claude Code — none of which is a programmatic Messages API surface. **browser-use SSO-session reuse** (Epics 5/13) drives a real Chrome with the user's web session for the *apps under test*; it cannot supply LLM inference to Alice/Bob/Mary/Sarah.

### Impact on the implemented `claude-sso` feature

The shipped flow works **as a UX**, but its real model calls run on the server-side `CLAUDE_SSO_ENTERPRISE_API_KEY` — which **must be a real Console org key from IT**, not the user's password. The mock-IdP password is login *theatre*; it does not, and cannot, authenticate the Anthropic API. This is a documented limitation, not a bug.

### Compliant options for local + UAT (ranked)

1. **Enterprise gateway (best — infra already exists).** Route Claude through the company AI gateway already in `.env` (`ON_PREMISES_API_BASE_URL`, with `TEST_ON_PREMISES_KEY`). The gateway holds the org Claude key server-side and authenticates the developer by SSO/identity; the app just points `base_url` at it + sends a per-user token. Fully compliant (billed to a real org key). If that gateway serves Claude models, **this is the legitimate "Claude via SSO" path** and largely overlaps the existing **On-Premises** provider. ([Anthropic LLM gateway docs](https://code.claude.com/docs/en/llm-gateway))
2. **IT-provisioned Console API key**, workspace-scoped, for local/UAT. The officially supported path for building on the API; blocker is organizational (IT controls keys).
3. **Do NOT** wire a subscription OAuth/`setup-token` into the app — ToS-banned and server-side blocked.

### Decision (2026-06-17)

Thuong's call: **do not change code yet** — record this finding and confirm with IT first (a) whether the Anthropic LLM gateway serves Claude models and supports per-user SSO auth, and (b) whether IT will issue a scoped Console key for local/UAT. The future code direction (point `claude-sso` at the gateway vs. keep the SSO UX behind an IT key vs. fold into the API-key/On-Premises path) is deferred to that answer. The implemented `claude-sso` code stays as-is (green suite) pending that decision.

## Sprint-status note

Recommend adding a new epic/story group ("Provider Auth Enhancements — Claude SSO", stories SSO-1…SSO-7) to [sprint-status.yaml](_bmad-output/implementation-artifacts/sprint-status.yaml) with status `backlog` (or `in-progress` once batch implementation starts).
