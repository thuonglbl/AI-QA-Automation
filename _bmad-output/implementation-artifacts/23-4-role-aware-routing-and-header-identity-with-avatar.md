---
baseline_commit: 0e05262e4d3e53e8bb60cd014effb430f91ad773
---
# Story 23.4: Role-Aware Navigation and Header Identity with Azure Avatar

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Frontend-heavy (+ a small backend avatar fetch). Today `App.tsx` picks ONE screen from the single `User.role`: `admin` → `AdminDashboard`, `project_admin` → `ProjectAdminDashboard`, else workspace ([App.tsx:1702-1711](frontend/src/App.tsx:1702)). Thuong wants **multi-role users to land on the user workspace by default**, with **header links** into the Project Admin Dashboard and/or Admin Dashboard for the roles they hold, and the header to show **name, role(s), and an avatar synced from Azure**. This story consumes the multi-role set from `UserSession.roles` (23.3) and adds role-aware in-app navigation + identity header + avatar. **Two DECISION GATES:** in-app navigation mechanism (state-based vs add a router) and avatar storage.

## Story

As a multi-role user,
I want to land on the user workspace by default with header links to the Project Admin Dashboard and/or Admin Dashboard for the roles I hold, and to see my name, role(s), and Azure-synced avatar in the header,
so that I can move between the surfaces I'm entitled to.

## Acceptance Criteria

1. **Multi-role set reaches the frontend.** Given `UserSession` now carries `roles: list[str]` (23.3) and `/auth/me` + `/auth/status` return the session user, when the FE loads the auth state, then the `AuthUser` type ([frontend/src/lib/auth.ts:3-14](frontend/src/lib/auth.ts:3)) gains `roles?: string[]`, `normalizeUser()` ([:42-58](frontend/src/lib/auth.ts:42)) populates it from the backend payload (falling back to `[role]` when only the single role is present, for back-compat), and the `/auth/me` + `/auth/status` responses include `roles`. The single `role` (derived primary) is still present and unchanged.

2. **Default landing = user workspace for multi-role users.** Given a user holding multiple roles (e.g. `{admin, standard}` or `{project_admin, standard}`), when they log in, then `App.tsx` renders the **standard user workspace by default** (NOT the dashboard), replacing today's "single role picks the screen" branch ([App.tsx:1702-1711](frontend/src/App.tsx:1702)). A user whose ONLY role is `admin` or `project_admin` (no `standard`) still reaches their dashboard sensibly (default to the workspace is fine since they can navigate via the header link; pick the least-surprising default and document it).

3. **DECISION GATE — in-app navigation (default: lightweight state-based view switch).** Given there is **no router** today (no `react-router` dep — confirmed) and all view selection is conditional rendering in `App.tsx`, when this story adds navigation between workspace / Project Admin Dashboard / Admin Dashboard, then the **default approach** is a top-level `activeView` state (`"workspace" | "project_admin" | "admin"`) toggled by header links, keeping the existing no-router architecture. **Alternative (gate):** introduce `react-router` with real `/`, `/project-admin`, `/admin` paths. **Default = state-based** (smaller change, matches current architecture, no new dep, no deep-link requirement stated); choose the router only if Thuong wants real URLs / deep links. Document the choice.

4. **Header links gated by entitlement.** Given the user's `roles` set, when the workspace header renders ([App.tsx:1792-1840](frontend/src/App.tsx:1792)), then it shows an "Admin Dashboard" link **iff** `roles` includes `admin`, and a "Project Admin Dashboard" link **iff** `roles` includes `project_admin` **or** `admin` (admin implicitly has project-admin authority everywhere — 23.5). A standard-only user sees neither link. Clicking a link switches `activeView` (AC3) to that dashboard; each dashboard offers a "Back to workspace" affordance. Links are English (App-UI-English-only).

5. **Header identity: name + role(s) + avatar.** Given the header today shows only `user.name` ([App.tsx:1821](frontend/src/App.tsx:1821)) with no avatar, when this story is implemented, then the workspace header AND both dashboard headers ([AdminDashboard.tsx:622-660](frontend/src/components/admin/AdminDashboard.tsx:622), [ProjectAdminDashboard.tsx:203-236](frontend/src/components/admin/ProjectAdminDashboard.tsx:203)) display: the user's name/`display_name`, their role(s) (render the set, e.g. "Admin · Project Admin"), and an **avatar** (image when available, initials fallback otherwise). Reuse the Radix Avatar component already used by `AgentTopBar` ([frontend/src/components/AgentTopBar.tsx](frontend/src/components/AgentTopBar.tsx)) for consistency.

6. **Avatar synced from Azure (best-effort) + DECISION GATE on storage.** Given Thuong wants the avatar synced from Azure, when a user logs in via SSO, then the backend best-effort fetches the Microsoft Graph photo (`GET /me/photo/$value`) using the access token from 23.2 and makes it available to the FE. **DECISION GATE (storage):** default = persist the photo bytes as a small per-user blob/data-URI exposed via a backend endpoint or the `/auth/me` payload (`avatar_url` field); alternatives = store a Graph URL (requires token to fetch, bad) or a dedicated `GET /auth/me/avatar` streaming endpoint. **Default = persist on login + serve from our backend** so the FE never needs a Graph token and air-gapped UAT (no `graph.microsoft.com` egress) simply has no photo. The fetch is **best-effort**: failure/egress-block → no avatar → initials fallback, never an error.

7. **Air-gap + missing-photo fallback.** Given the avatar fetch is backend egress to `graph.microsoft.com` (blocked on air-gapped UAT — 23.1), when the photo is unavailable for any reason, then the FE renders the initials avatar (derived from name/email) with no error and no broken-image icon; the rest of the header is unaffected. This guarantees the header works identically on local and UAT.

8. **No regression to existing dashboards.** Given `AdminDashboard` and `ProjectAdminDashboard` are reached today purely by the single-role branch, when navigation becomes role-aware, then both dashboards still render and function (Users Management, project-admin assignment, members, etc.) — they are now reached via header link + `activeView` instead of the role branch, and a standard-only user can never reach them (defense-in-depth: the backend RBAC already enforces this — [rbac.py:47-80](src/ai_qa/api/auth/rbac.py:47) — so the FE gate is UX, not the security boundary).

## Tasks / Subtasks

- [x] **Task 1 — `roles` on the FE auth type + payload (AC: 1)**
  - [x] Added `roles?: string[]` + `avatarUrl?: string | null` to `AuthUser` ([frontend/src/lib/auth.ts](frontend/src/lib/auth.ts)); `normalizeUser()` populates `roles` (prefers `data.roles`, falls back to `[role]`) + `avatarUrl`. Backend: `UserProfileResponse` + shared `_profile_response()` gained `roles` + `avatar_url` (so `/me` + `/login` stay consistent); `/auth/status` inline dict updated separately (roles from the session, avatar_url via a cheap PK lookup). Single `role` unchanged.

- [x] **Task 2 — Role-aware view switching (AC: 2, 3, 4, 8)**
  - [x] Replaced the single-role screen branch in `App.tsx` with an `activeView` state (`"workspace" | "project_admin" | "admin" | null`). **Chosen path = state-based view switch (no `react-router`)**, per AC3 default. `currentView = activeView ?? defaultView`; `defaultView` = workspace when the role set includes `standard`, else the highest entitled dashboard (so a pure-admin still lands on the dashboard — preserves the existing Story-8.1 AC5 test and is least-surprising).
  - [x] Header links (AC4) gated by the role set: `Project Admin Dashboard` iff `admin || project_admin`; `Admin Dashboard` iff `admin`. Each dashboard renders with `onBackToWorkspace` → a "Back to workspace" button.
  - [x] `effectiveRoles(user)` helper exported from `UserBadge.tsx`.

- [x] **Task 3 — Header identity + avatar UI (AC: 5, 7)**
  - [x] New shared `UserBadge` component (Radix Avatar `AvatarImage src={avatarUrl}` + initials `AvatarFallback`; name + role-set label) used in the workspace header + both dashboard headers (replacing the bespoke identity blocks + the `{user.name}` span).

- [x] **Task 4 — Backend avatar fetch + storage (AC: 6, 7)**
  - [x] **Chosen storage gate = persist bytes + serve from our backend.** `User.avatar` (nullable Text, data-URI; migration `f2b3c4d5e6a7`). The 23.2 callback best-effort `GET graph.microsoft.com/v1.0/me/photo/$value` with the access token (`_fetch_graph_avatar`, honors `trust_env`/proxy), size-guarded (≤512KB), never logs bytes, never blocks login. Served via `GET /auth/me/avatar` (decodes the data-URI → image bytes; 404 → initials). `avatar_url` in the payload points at that route (chosen over an inline data-URI to avoid bloating the polled `/auth/status`).
  - [x] Size guard + no byte logging in place; any failure/egress block → null avatar → initials fallback.

- [x] **Task 5 — Tests (all ACs)**
  - [x] FE Vitest: `UserBadge.test.tsx` (avatar image when `avatarUrl` set, initials fallback when absent/no broken image, role-set label, `effectiveRoles`/`roleSetLabel`); `App.test.tsx` (multi-role admin+standard → workspace default + both entitled links + click switches to Admin Dashboard + "Back to workspace"; standard-only → no dashboard links). Updated the Story-8.1 login assertion + the 6 E2E-button sentinels for the new header.
  - [x] Backend `tests/api/test_sso_api.py`: `/auth/status` returns `roles` + null `avatar_url` for a no-photo user; `/auth/me/avatar` 404 without a photo; serves the stored PNG bytes + `avatar_url="/auth/me/avatar"` when set. Migration `f2b3c4d5e6a7` is a simple add/drop column.
  - [x] `npm run typecheck` + `npm run lint` clean; `npx vitest run` → **381 passed**. Backend `uv run pytest` + ruff + `mypy src` clean (see Completion Notes for the count).

## Dev Notes

### The routing model changes from "role picks the screen" to "default workspace + entitled links"

Today the single `User.role` deterministically routes to one of three screens ([App.tsx:1702-1711](frontend/src/App.tsx:1702)) — there is no way to be admin AND see the workspace. Thuong's model: everyone starts in the workspace; the header offers shortcuts into the dashboards you're entitled to. This needs (a) the multi-role set on the FE (from 23.3's `UserSession.roles`) and (b) a way to switch views without a role change. Keep it state-based (`activeView`) unless Thuong wants real URLs — the app has lived without a router this whole time and nothing here requires deep links.

### Avatar is best-effort and air-gap-safe by design

The Graph photo is a backend egress to `graph.microsoft.com`, which the air-gapped UAT blocks (23.1, memory `uat-airgapped-egress-model-transfer`). Persisting the photo on login (when egress works, e.g. local or UAT-with-proxy) and serving it from our own backend means the FE never needs a Graph token, and the initials fallback makes the missing-photo case a non-event. Never make login depend on the photo.

### Current behavior to PRESERVE (regression guardrails)

- **Backend RBAC is the real boundary.** The FE link-gating is UX only; `require_admin` / `require_project_admin_for_project` ([rbac.py:47-80](src/ai_qa/api/auth/rbac.py:47)) still enforce access server-side. Do not weaken them.
- **Dashboards keep working.** `AdminDashboard` (Users Management, model benchmarks, etc.) and `ProjectAdminDashboard` (project config, members) must render and function exactly as before — only their entry point changes.
- **Single `role` stays.** Don't remove `user.role`; `roles` is additive. Existing code reading `user.role` is untouched.
- **App-UI-English-only.** Every new label/link/aria string is English ([[app-ui-english-only]]).
- **Vitest 4 mock rules** ([project-context.md](project-context.md)): file-wide `vi.mock` hoist; preserve real exports via `importOriginal()`; `noUncheckedIndexedAccess` → `!`/`?.` on indexed access in tests.

### Source tree components to touch

- `frontend/src/lib/auth.ts` — **UPDATE** (`AuthUser.roles`, `normalizeUser`).
- `frontend/src/App.tsx` — **UPDATE** (`activeView`, role-aware links, header avatar/identity).
- `frontend/src/components/admin/AdminDashboard.tsx` — **UPDATE** (header identity/avatar + "Back to workspace").
- `frontend/src/components/admin/ProjectAdminDashboard.tsx` — **UPDATE** (same).
- `frontend/src/components/` — **ADD** (optional shared `Avatar`/identity component).
- `src/ai_qa/api/auth/sso.py` — **UPDATE** (best-effort Graph photo fetch).
- `src/ai_qa/api/auth/local.py` + SSO `/auth/me` builders — **UPDATE** (include `roles` + `avatar_url`).
- `src/ai_qa/db/models.py` + `alembic/versions/` — **UPDATE/ADD** (only if storing avatar as a column — per gate).
- Tests — **ADD** (FE nav/header/avatar; backend avatar fetch + payload).

### Decided scope (defaults — Thuong, correct if needed)

- **State-based `activeView` navigation** (no `react-router`).
- **Persist the Azure photo on login + serve from our backend** (`avatar_url`); initials fallback; best-effort, air-gap-safe.
- **Header links gated by the role set**; admin sees both dashboards (admin ⇒ project-admin everywhere).
- **Default landing = workspace** for everyone.

### Testing standards summary

- FE Vitest 4 + the mock-hoisting/`importOriginal` rules; backend pytest whole-suite; full-stack type sync for payload changes. No `page.route` mocking in e2e.

### Project Structure Notes

- If the avatar is stored as a `User` column, this story adds a small migration; otherwise no schema change. Coordinate with 23.3's migration (`azure_oid`) and 23.6's (drop `password_hash`).

### References

- Epic + story: [epics.md#Epic-23](_bmad-output/planning-artifacts/epics.md:2371), [Story 23.4](_bmad-output/planning-artifacts/epics.md:2401)
- FE routing today: [frontend/src/App.tsx:1702-1840](frontend/src/App.tsx:1702); no router ([frontend/package.json](frontend/package.json))
- Auth type/normalize: [frontend/src/lib/auth.ts:3-58](frontend/src/lib/auth.ts:3); context [frontend/src/contexts/AuthContext.tsx:12-89](frontend/src/contexts/AuthContext.tsx:12)
- Dashboard headers: [AdminDashboard.tsx:622-660](frontend/src/components/admin/AdminDashboard.tsx:622), [ProjectAdminDashboard.tsx:203-236](frontend/src/components/admin/ProjectAdminDashboard.tsx:203)
- Avatar component precedent: [frontend/src/components/AgentTopBar.tsx](frontend/src/components/AgentTopBar.tsx)
- Backend RBAC (the real boundary): [api/auth/rbac.py:47-80](src/ai_qa/api/auth/rbac.py:47); `/auth/me` [api/auth/local.py:124-143](src/ai_qa/api/auth/local.py:124) → shared builder `_profile_response` [api/auth/local.py:58](src/ai_qa/api/auth/local.py:58); `/auth/status` inline dict [api/auth/local.py:145-158](src/ai_qa/api/auth/local.py:145)
- Session roles source: [api/auth/session.py:17-75](src/ai_qa/api/auth/session.py:17) (23.3 adds `roles`)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[epic-23-sso-first-auth]], [[app-ui-english-only]], [[message-timestamps-feature]] (full-stack payload-sync gotcha), [[projectadmin-rbac-redesign-plan]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (BMAD dev-story)

### Debug Log References

- `npm run typecheck` + `npm run lint` clean; `npx vitest run` → 381 passed (37 files).
- `uv run pytest` → 1867 passed (85% cov); `uv run mypy src` clean; ruff clean.

### Completion Notes List

- **Decision gates (defaults taken):** (3) in-app nav = **state-based `activeView`** (no `react-router`); (6) avatar storage = **persist bytes + serve from our backend** via `GET /auth/me/avatar` (the `avatar_url` payload field points at that route, NOT an inline data-URI — keeps the polled `/auth/status` small); default landing = workspace.
- **Landing rule:** `defaultView` = workspace when the role set includes `standard`, else the highest entitled dashboard. This preserves the existing Story-8.1 AC5 test (a pure-admin lands on the Admin Dashboard) and is least-surprising for single-surface users, while multi-role users (with `standard`) land on the workspace with header links (AC2). An explicit header-link/"Back to workspace" click overrides via `activeView`.
- **Header links are entitlement-gated** (`admin` → Admin Dashboard; `admin || project_admin` → Project Admin Dashboard); backend RBAC remains the real boundary (FE gating is UX only).
- **Avatar is air-gap-safe:** best-effort Graph fetch on login (real mode), size-guarded ≤512KB, bytes never logged; any failure/egress block → null → Radix initials fallback. Mock/dev has no access token → no photo → initials.
- **`roles` plumbed full-stack:** `UserSession.roles` (23.3) → `/auth/status` (from session) + `/auth/me`/`_profile_response` (`[role]` fallback) → FE `AuthUser.roles` via `normalizeUser`. Single `role` unchanged (additive).
- **Test fixups (consequences of the header change):** updated the Story-8.1 login assertion to the SSO button, and 6 AdminDashboard E2E-button sentinels from `findByText("Admin")` (now ambiguous with the role label) to the unique `findByRole("heading", {name:/admin dashboard/i})`.

### File List

- `src/ai_qa/db/models.py` — UPDATED (`User.avatar` nullable Text).
- `alembic/versions/f2b3c4d5e6a7_add_user_avatar.py` — ADDED (avatar column; off head `e1a2c3d4f5b6`).
- `src/ai_qa/api/auth/sso.py` — UPDATED (`_fetch_graph_avatar`; access_token wired into `_complete_login`).
- `src/ai_qa/api/auth/local.py` — UPDATED (`roles`+`avatar_url` in `UserProfileResponse`/`_profile_response`; `GET /auth/me/avatar`; `/auth/status` roles+avatar_url).
- `frontend/src/lib/auth.ts` — UPDATED (`AuthUser.roles`/`avatarUrl`; `normalizeUser`).
- `frontend/src/components/auth/UserBadge.tsx` — ADDED (shared avatar+identity; `effectiveRoles`/`roleSetLabel`).
- `frontend/src/App.tsx` — UPDATED (`activeView` nav, entitled header links, `UserBadge`).
- `frontend/src/components/admin/AdminDashboard.tsx` — UPDATED (`onBackToWorkspace` + `UserBadge` header).
- `frontend/src/components/admin/ProjectAdminDashboard.tsx` — UPDATED (same).
- `tests/api/test_sso_api.py` — UPDATED (roles in /status; avatar route 404 + serve).
- `frontend/src/components/auth/UserBadge.test.tsx` — ADDED; `frontend/src/App.test.tsx` — UPDATED (multi-role nav + standard-only + login assertion); `frontend/src/components/admin/AdminDashboard.test.tsx` — UPDATED (sentinels).

### Change Log

- 2026-06-25 — Story 23.4: role-aware in-app nav (state-based `activeView` + entitled header links), shared `UserBadge` identity header (name + role-set + Azure avatar with initials fallback), backend best-effort Graph avatar (`User.avatar`, migration `f2b3c4d5e6a7`, `GET /auth/me/avatar`), `roles`/`avatar_url` on the auth payloads. FE 381 / BE 1867 green. Status → review.
