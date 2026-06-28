# SSO-First Authentication — Feasibility Spike & Design Note (Epic 23)

- Date: 2026-06-25
- Author: Dev (BMAD dev-story, Story 23.1)
- Status: Decision note — informs production stories 23.2 … 23.6
- Constraint (Thuong): a single "Sign in with SSO" button; roles from Azure App Roles; **both local AND air-gapped UAT must complete SSO**; drop local password auth.

> This is the spike deliverable for Story 23.1. It is a **written decision**, not merged code. A throwaway local proof-of-concept is described in §7; no secret, real token, or PoC `.env` is committed.

## 0. TL;DR verdict

- **Topology: A (app-level OIDC, confidential client) is the recommended default**, implemented backend-side with the already-locked `msal` confidential client for the code→token exchange and `python-jose` for ID-token validation against the tenant JWKS. Thuong already holds tenant id / client id / client secret + 3 app roles, so the confidential client is available today.
- **Air-gapped UAT is the load-bearing risk.** Topology A needs backend egress to `login.microsoftonline.com` (token exchange + JWKS) and `graph.microsoft.com` (avatar). The UAT host has no internet and no proxy. Mitigation, in priority order: **(1) IT opens an egress proxy** (`HTTP(S)_PROXY` + `NO_PROXY`; `trust_env` is already on — no rebuild) — the cleanest path that keeps topology A on UAT; **(2) bundle/cache the tenant JWKS** in config so the backend validates ID tokens with zero outbound calls (this is the topology-B fallback and is implemented as an option from day one); **(3) reverse-proxy header SSO** if IT prefers to stand up Entra Application Proxy / IIS.
- **The production code supports both modes with one validation path** so the local↔UAT difference is config only, not a rewrite: real Entra exchange (A) on egress-capable hosts; bundled-JWKS validation (B) when egress is blocked; and a **built-in mock IdP** (mirroring `claude_sso.py`) so the whole flow is testable in CI/E2E with no Microsoft dependency.
- **Stable join key = Entra `oid`** (persisted as `User.azure_oid`), email as fallback.
- **Avatar = best-effort** Graph `GET /me/photo/$value`, persisted on login, served from our backend; **initials fallback** whenever the photo is unavailable (so air-gapped UAT degrades cleanly).

## 1. Prior-art recovery & evaluation (AC 1)

Commit `73980bf` ("Azure Entra ID SSO Authentication Foundation", later reverted) is the starting point. `git show --stat 73980bf` shows it touched 26 files; the load-bearing ones:

- `src/ai_qa/api/auth/azure.py` (235 lines) — an **httpx-based** OAuth2 auth-code **+ PKCE** flow: `GET /auth/login` builds the Entra authorize URL with an S256 PKCE challenge + `state`, stores `oauth_state`/`code_verifier` in the Starlette `SessionMiddleware` session, and `GET /auth/callback` verifies state, exchanges the code at `…/oauth2/v2.0/token` via `httpx`, then validates the ID token. **Notes / gaps for our reuse:**
  - It is **httpx-based, not `msal`** — fine, but the story asks topology A to use the locked `msal` confidential client. We rewrite the exchange with `msal` (which also validates the ID token and respects `HTTP(S)_PROXY` via its `requests` transport — useful for the UAT proxy path).
  - It has an **unsafe fallback** (`pyjwt.decode(..., verify_signature=False)` "for development") — **must NOT be carried over.** Production validates the signature against JWKS; dev uses the mock IdP (app-signed token), never an unverified decode.
  - It put the router at `/auth/login` + `/auth/callback`. Our user-login OIDC router lives at `/auth/sso/*` so it never collides with the (temporarily coexisting) local `/auth/login` and the existing `/auth/callback` allowlist entry.
  - It imported `jwt` (PyJWT) which is **not** our locked lib — we use `python-jose` (`from jose import jwt`).
- `frontend/src/components/auth/MicrosoftLoginButton.tsx` (35 lines) — a clean Microsoft-branded button. **Reusable as-is** for the single-button login screen (23.2), though Thuong's wording is "Sign in with SSO" — we keep the Microsoft logo + relabel.
- `src/ai_qa/config.py` Azure block + `.env.example` — fields `azure_tenant_id` / `azure_client_id` / `azure_client_secret` / `azure_redirect_uri` / `azure_scopes`. We rename to the `azure_sso_*` namespace (23.2 AC1) to sit beside the `claude_sso_*` block and avoid any confusion with the provider-auth `claude_sso`.

Dependencies: `msal>=1.28` + `python-jose[cryptography]>=3.3` are still locked in `pyproject.toml` and cover topology A and B. **No additional dependency is needed.** (`httpx` is already a dependency for the JWKS fetch / mock paths.)

## 2. Topology analysis & recommendation (AC 1, 2)

| Topology | Where code→token happens | Backend egress required | What IT must provide | Security posture | Air-gapped UAT |
| --- | --- | --- | --- | --- | --- |
| **A. App-level OIDC (confidential client)** | Backend (`msal` + client secret) | `login.microsoftonline.com` (token + JWKS); `graph.microsoft.com` (avatar) | Redirect URI(s); admin consent for `User.Read`; **egress proxy** for UAT | Strong: secret held server-side, never in browser | Blocked unless IT opens a proxy **or** JWKS is bundled (→ becomes B for validation) |
| **B. SPA / MSAL.js (PKCE, public client)** | Browser (MSAL.js) | None for token exchange; JWKS bundled/cached so backend validates with zero egress | Redirect URI(s); SPA registration (public client) | Good: no server secret, but a larger FE and key-freshness management | Works — all egress is browser-side |
| **C. Reverse-proxy header SSO** | Reverse proxy (Entra App Proxy / IIS) | None (app reads a trusted header) | IT stands up the proxy + a hard trust boundary | Depends entirely on the proxy trust boundary being airtight | Works — no backend egress |

### Verdict

Recommend **Topology A** as the default, because Thuong already has a confidential client (secret + tenant + client id) and it keeps the frontend to a single button + redirect (no MSAL.js, no SPA registration, no public-client key management). It works on **local** out of the box (local has internet) and on **UAT** once IT opens an egress proxy — the same `HTTP(S)_PROXY`/`NO_PROXY` mitigation already used for the model-sync 504s (`uat-airgapped-egress-model-transfer.md`; `trust_env` is already on, so this is config-only, no rebuild).

If IT cannot open a UAT egress proxy, fall back to **validating with a bundled JWKS** (config `azure_sso_jwks`): the backend then makes **zero** outbound calls to validate an ID token. This is the topology-B validation mechanism and is implemented from day one as a config option, so switching UAT to it is a config change, not new code. (Full topology B — browser-side token acquisition via MSAL.js — is only needed if the **token exchange** itself cannot be done backend-side even through a proxy; we do not build the MSAL.js path now, but the validation half is ready.)

Topology C (reverse proxy) is the last resort if IT prefers to own auth entirely at the edge; the app already mints its own session cookie from a `UserSession`, so a header-reading shim would be small — but it is not recommended unless IT pushes for it, because the trust boundary is easy to get wrong.

### How the production code embodies the verdict (one code path, three modes)

- **Mode = real (A):** `azure_sso_tenant_id` + `client_id` + `client_secret` set → `GET /auth/sso/login` redirects to Entra; `GET /auth/sso/callback` does the `msal` code→token exchange, then validates the ID token via `python-jose` against JWKS (fetched from Entra **or** the bundled `azure_sso_jwks`).
- **Mode = bundled-JWKS (B-validation):** same as A but `azure_sso_jwks` is populated → the JWKS fetch never calls out. (Token exchange still needs egress; pair with the proxy, or move exchange browser-side later if ever required.)
- **Mode = mock IdP (dev/CI/E2E):** real Azure config absent → `GET /auth/sso/login` redirects to a built-in `/auth/sso/authorize` login form that mints an **app-signed HS256** token (validated with the app's own secret). No Microsoft, no network. Mirrors `claude_sso.py`.

The **token-validation contract is identical** across modes (issuer / audience / expiry / signature), satisfying the story's "keep validation identical either way".

## 3. App-role claim shape & platform-role mapping (AC 3)

### Claim shape (to confirm against a real token in §7)

- Azure App Roles are emitted in the **`roles`** claim of the ID token (and access token) as an **array of the app-role *value* strings** — i.e. the "Value" field configured on each app role in the App Registration → "App roles" blade — **not** GUIDs. So with roles defined as `admin`, `project-admin`, `user`, the claim is e.g. `"roles": ["project-admin", "user"]`.
- App-registration prerequisites to surface `roles`:
  - Define the three app roles (Value = `admin` / `project-admin` / `user`) on the App Registration, "Allowed member types" = Users/Groups.
  - On the Enterprise Application, set **"Assignment required" = Yes** and **assign each user (or group) to one or more app roles**. Only assigned roles appear in the token.
  - No special "Token configuration" optional claim is needed for `roles` (app-role membership is included automatically once assigned); `oid` is a core claim and is always present.
- **Multiple roles**: a user assigned to several app roles gets all of them in the array — this is the multi-role case the epic depends on.

### Mapping table (`azure_app_role_value → platform_role`)

| Azure app-role value | Platform role constant (`auth/service.py:13-17`) |
| --- | --- |
| `admin` | `ADMIN_ROLE` (`"admin"`) |
| `project-admin` | `PROJECT_ADMIN_ROLE` (`"project_admin"`) |
| `user` | `STANDARD_ROLE` (`"standard"`) |
| (unknown / empty) | `{STANDARD_ROLE}` (never crash, never empty) |

### Multi-role collapse rule (feeds 23.3)

- Keep the **full set** in `UserSession.roles: list[str]` (new field, 23.3) for the FE to offer every entitled dashboard.
- Persist a single **derived primary** to `User.role` for the large existing single-role surface (`rbac.py`, `admin.py`, `projects.py`, `App.tsx`): priority **`admin > project_admin > standard`**.
- The effective role set at login = `map_app_roles(token roles)` **∪** `{project_admin}` **if** the user holds ≥1 `ProjectMembership(role="project_admin")` — so an in-app project-admin assignment (23.5) confers the role even with no Azure `project-admin` grant, and works **before the user's first login**. The platform **`admin`** role comes **only** from Azure.

## 4. Identity claim availability (AC 4)

`UserSession` (`api/auth/session.py:17-31`) already has `email` / `name` / `given_name` / `family_name` / `groups`. Mapping from Entra ID-token claims:

| `UserSession` field | Entra claim source |
| --- | --- |
| `email` | `preferred_username` → `upn` → `email` (first present, normalized lower-case) |
| `name` | `name` |
| `given_name` | `given_name` |
| `family_name` | `family_name` |
| `groups` | `groups` (if group claims are enabled; not required for this epic — roles drive RBAC, not groups) |
| `roles` (new, 23.3) | `roles` (the app-role values, §3) |
| stable join key | `oid` (object id) — **does not change**; `email`/`upn` can |

**Recommendation:** add a nullable, unique-indexed `User.azure_oid: str | None` column (23.3) and match on it first, email as fallback for pre-existing rows. `oid` is a stable GUID per user per tenant.

## 5. Avatar retrieval plan + air-gap fallback (AC 5)

- **Source:** Microsoft Graph `GET https://graph.microsoft.com/v1.0/me/photo/$value` using the access token obtained in the callback. This is a **backend-side egress** to `graph.microsoft.com` → blocked on air-gapped UAT (same class as the token/JWKS egress).
- **Storage options for 23.4** (decision gate there): (a) persist the bytes as a small per-user blob/data-URI exposed via `avatar_url` in the auth payload — **recommended** (FE never needs a Graph token; air-gap simply has no photo); (b) a dedicated `GET /auth/me/avatar` streaming route; (c) store a Graph URL — **rejected** (FE would need a token to fetch it).
- **Mandatory fallback:** when the photo is unavailable for any reason (egress blocked, no photo set, Graph error, oversized blob) → render an **initials avatar** (derived from name/email). The avatar fetch is **best-effort**: a failure NEVER blocks login and NEVER returns a 500. This makes the header behave identically on local and UAT.

## 6. IT asks — verbatim list for Thuong to forward (AC 6)

1. **Register redirect URI(s)** on the App Registration for **both** environments:
   - Local: `http://localhost:8000/api/auth/sso/callback`
   - UAT: `https://<uat-host>/api/auth/sso/callback` (please confirm the exact UAT scheme + host).
2. **Confirm the issued ID/access token includes the `roles` claim** with the app-role **Value** strings `admin`, `project-admin`, `user` (not GUIDs), and that **"Assignment required" = Yes** with users assigned to one or more of those roles on the Enterprise Application.
3. **Grant admin consent** for the delegated Microsoft Graph scope **`User.Read`** (needed for the profile + `/me/photo/$value` avatar). Confirm whether reading `/me/photo` requires any additional consent in our tenant.
4. **Air-gapped UAT egress** — choose ONE:
   - (preferred) Open an **outbound proxy** from the UAT backend host to `login.microsoftonline.com` and `graph.microsoft.com`, and give us the proxy URL so we can set `HTTPS_PROXY` / `HTTP_PROXY` + `NO_PROXY` (no rebuild required); **or**
   - Provide the **tenant signing keys (JWKS)** out-of-band so we can bundle them for offline ID-token validation (note: the **code→token exchange still needs egress** — this only removes the JWKS fetch); **or**
   - Stand up a **reverse proxy** (Entra Application Proxy / IIS) in front of the UAT app that authenticates and injects a trusted identity header.
5. **Provide / confirm the client secret rotation policy** and the secret value for each environment (stored server-side only, never in the repo or returned to the FE).
6. Confirm the **tenant id** and **application (client) id** are the same across local and UAT (or provide per-environment values).

## 7. Local proof-of-concept (throwaway) (AC 7)

- **Status: not executed against the live tenant from the spike environment** — this development environment has no access to Thuong's real client secret and (for the egress verdict) deliberately does not call out to Microsoft. Running the live round-trip requires Thuong's local machine with the real `azure_sso_*` values set.
- **Reproducible PoC procedure** (throwaway; do NOT commit secrets or merge into `src/`):
  1. On a local machine with internet, set env: `AZURE_SSO_TENANT_ID`, `AZURE_SSO_CLIENT_ID`, `AZURE_SSO_CLIENT_SECRET`, `AZURE_SSO_REDIRECT_URI=http://localhost:8000/api/auth/sso/callback`, `AZURE_SSO_ENABLED=true`.
  2. Run the backend + frontend; click "Sign in with SSO" → complete the Entra login.
  3. In the callback (temporarily), log only **structural** evidence (claim **names** present, the `roles` **values**, whether `oid`/`preferred_username` exist, and whether the `msal` exchange + `jose` JWKS validation succeeded). **Never log the raw token or secret.**
- **What to record (redacted):** `roles` claim values seen (expect `["admin"]` / `["project-admin","user"]` / etc.), presence of `oid` + `preferred_username`, and a boolean for "exchange OK" / "JWKS validation OK". Paste the redacted structural result back into this note's appendix when run.
- **Why this is acceptable for the epic to proceed:** the production code (23.2) ships a **built-in mock IdP** that exercises the *exact* same `_complete_login` path (match → provision → role-map → cookie) with an app-signed token, so the whole flow is proven in CI/E2E without Microsoft. The live round-trip is a **deploy-time validation** (consistent with the project's standing pattern that UAT/live validation is a follow-up), and the only thing it confirms that the mock cannot is the real `roles`/`oid` claim shape (§3/§4) and the egress verdict (§2) — both of which are also confirmable from the Azure Portal "Token configuration" / a manual token decode.

## 8. Story-by-story impact + open decision gates (AC 8)

### Impact on 23.2 … 23.6

- **23.2 (login foundation):** add `azure_sso_*` config; new `src/ai_qa/api/auth/sso.py` with `GET /auth/sso/login` + `GET /auth/sso/callback` (+ mock `/authorize`); register in `app.py`; allowlist the SSO paths in middleware; single "Sign in with SSO" button in `LoginPage.tsx` (reuse `MicrosoftLoginButton`); **existing-user match only**, no-match → 403 placeholder. Token exchange = `msal` (A); validation = `jose` JWKS (bundled-capable). Mock-IdP mode mandatory for tests.
- **23.3 (provision + role map):** `map_app_roles()` + `primary_role()` (§3); `UserSession.roles`; `User.azure_oid` column + nullable `password_hash` (one migration off head `d5e8c1b9f3a2`); turn the 23.2 403 into auto-provision (config-gated); re-sync identity + roles every login; effective set ∪ membership-derived `project_admin`; Azure `admin` = admin bootstrap.
- **23.4 (nav + avatar):** `roles` on the FE `AuthUser` + `/auth/me`/`/auth/status`/`_profile_response`; `App.tsx` `activeView` state-based nav (default workspace) + entitlement-gated header links; header identity (name + role-set + avatar); backend best-effort Graph photo fetch persisted as `avatar_url`; initials fallback.
- **23.5 (admin global PA + assignment):** audit the admin backdoor on every project-admin-gated route + a proving test; generalize single `project_id` → `project_ids` set with reconciliation; FE multi-select picker for any project_admin user (closes deferred 16-13). Membership confers `project_admin`; admin can create+assign before first login.
- **23.6 (drop passwords):** drop `users.password_hash` (only credential column left after `c7e3a9f04b21`); remove `/auth/login` + `authenticate_user`/`register_user` + password bootstrap; de-password `admin.py` + FE create/edit form + CI `test.yml`; migrate the canonical test fixture to a session-cookie/mock-IdP helper; remove `pwdlib` if unused. **No break-glass** (Azure `admin` app-role is recovery).

### Open decision gates (defaults chosen; Thuong can flip)

1. **Multi-role persistence (23.3):** default = **no persisted role-set column** — derive each login, keep single derived `User.role` primary + full set in `UserSession.roles`. (Flip to a `User.roles` JSON column only if server-side role-set queries are needed.)
2. **Avatar storage (23.4):** default = **persist bytes on login + serve from our backend** via `avatar_url`; initials fallback.
3. **In-app navigation (23.4):** default = **state-based `activeView`** (no `react-router`); real URLs only if deep-linking is wanted.
4. **Break-glass (23.6):** default = **none** (Azure `admin` app-role is the recovery); add an env-validated emergency token only if a non-SSO recovery hatch is required.

All four are baked into the production stories as defaults; this note records them so they are explicit going into dev.

## Appendix — live PoC evidence (fill after running §7)

- Date run: _pending_
- `roles` claim values observed (redacted): _pending_
- `oid` present: _pending_ · `preferred_username` present: _pending_
- `msal` code→token exchange: _pending_ · `jose` JWKS validation: _pending_
- Notes: _pending_
