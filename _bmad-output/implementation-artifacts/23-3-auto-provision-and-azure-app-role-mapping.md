---
baseline_commit: 0e05262e4d3e53e8bb60cd014effb430f91ad773
---
# Story 23.3: Auto-Provision on First Login and Azure App-Role → Platform-Role Mapping

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

> Backend. Turns the 23.2 "account not provisioned" 403 into **auto-provisioning** and makes the user's **platform role(s) come from Azure App Roles** instead of an admin-set DB value. The Azure app registration exposes app roles `admin` / `project-admin` / `user`, and a user may be assigned **multiple** at once. This story: (1) auto-creates a `User` on first SSO login, (2) parses the token `roles` claim → platform roles `{admin, project_admin, standard}`, (3) supports **multiple roles per user**, (4) re-syncs identity + roles on every login, and (5) makes the first user bearing the Azure `admin` role the platform-admin bootstrap (replacing the password bootstrap that 23.6 removes). **Contains a DECISION GATE** on how to persist multiple roles — a default is baked in below; Thuong can flip it.

## Story

As a first-time or returning SSO user,
I want the platform to auto-create my User record on first login and derive my platform role(s) from my Azure App Roles (supporting multiple roles),
so that I can use the platform immediately without an admin adding me, and an Azure `admin` app-role bootstraps platform-admin access.

## Acceptance Criteria

1. **App-role claim → platform-role mapping.** Given the validated ID/access token from 23.2 carries a `roles` claim with the values confirmed in 23.1 (e.g. `"admin"`, `"project-admin"`, `"user"`), when a user logs in, then a pure mapping function (e.g. `map_app_roles(roles_claim: list[str]) -> set[str]`) translates them to the platform constants `ADMIN_ROLE` / `PROJECT_ADMIN_ROLE` / `STANDARD_ROLE` ([auth/service.py:13-17](src/ai_qa/auth/service.py:13)). Unknown/empty claim → `{STANDARD_ROLE}` (never crash, never empty). The mapping is config/constant-driven (an Azure-value → platform-role dict) so renamed Azure roles are a one-line change, and it is unit-tested in isolation. (The login callback then **UNIONs** this token-derived set with a membership-derived `project_admin` — see AC4 — so `map_app_roles` itself stays token-only and testable in isolation.)

2. **DECISION GATE — multi-role persistence (default: derive-each-login + keep a single derived `User.role` primary).** Given `User.role` is today a **single** `String(50)` ([db/models.py:38](src/ai_qa/db/models.py:38)) and the whole codebase reads it as one value ([rbac.py:51,68](src/ai_qa/api/auth/rbac.py:51), [admin.py](src/ai_qa/api/admin.py), [projects.py:95](src/ai_qa/api/projects.py:95), [App.tsx:1706-1711](frontend/src/App.tsx:1706)), when this story is implemented, then the **default approach** is: keep `User.role` as the **derived primary** (highest-privilege of the mapped set: `admin > project_admin > standard`) for backward compatibility, AND carry the **full role set** in the `UserSession` (a new `roles: list[str]` field on the dataclass + `to_dict`/`from_dict`) so the FE/header (23.4) can offer every entitled dashboard. **Alternative (gate):** add a persisted `User.roles` JSON column (`list[str]`, migration) as the source of truth and compute `role` from it. **Default = no new column** (session-derived set + derived primary) because Azure is the source of truth re-read every login and a stale persisted set risks drift; flip to the column only if a role set must be queryable server-side without a live token. Document the chosen path in Completion Notes.

3. **Auto-provision on first login.** Given the 23.2 callback validates a token for a user with **no** matching `User` row, when auto-provisioning is enabled, then a new `User` is created with `email` (from `preferred_username`/`upn`/`email`), `display_name` (from `name`), `is_active=True`, `timezone` default, the derived primary `role` (AC2), and the stable Azure id persisted for future matching (see AC6). No `password_hash` is set for SSO-provisioned users (it is nullable/absent after 23.6; until then, set a non-usable sentinel or make the column nullable — see Dev Notes). The user is then logged in in the same request (cookie set), so first login is seamless.

4. **Identity + roles re-sync on every login; membership confers `project_admin` (Thuong 2026-06-25).** Given an existing matched user logs in again, when the callback completes, then their `display_name`, `given_name`/`family_name` (in session), and **derived role(s)** are refreshed. **The effective role set = `map_app_roles(token roles claim)` ∪ {`PROJECT_ADMIN_ROLE` if the user holds ≥1 `ProjectMembership(role="project_admin")`}** — i.e. an in-app project-admin assignment (23.5) **confers** the role; the Azure `project-admin` app role is honored additively but is **NOT required**. So a project-admin whom an admin **pre-created + assigned a project to, before they ever logged in**, gets `project_admin` on first login **from the membership alone**, and `require_project_admin_for_project` ([rbac.py:70-79](src/ai_qa/api/auth/rbac.py:70) — needs `User.role==project_admin` **AND** the membership) passes. Re-sync **MUST NEVER downgrade a user who holds a `project_admin` membership** to standard. The platform **`admin`** role still comes **ONLY from Azure** (AC5). Re-sync MUST NOT clobber platform-managed state that is NOT owned by Azure: project memberships (`ProjectMembership` rows), per-user secrets, and `timezone` are preserved. Only identity + role-source fields are updated.

5. **Admin bootstrap via the Azure `admin` app-role.** Given local password bootstrap (`bootstrap_admin`, `AI_QA_BOOTSTRAP_ADMIN_PASSWORD`) is being retired in 23.6, when the first user bearing the Azure `admin` app-role logs in, then they are provisioned/updated as a platform `admin` with no manual step — so a fresh deployment gets its first admin purely through SSO. This is the replacement bootstrap path (no DB password needed).

6. **Stable matching key.** Given email/UPN can change but the Entra `oid` does not (23.1), when this story is implemented, then matching prefers the stable id: add a nullable, unique-indexed `User.azure_oid: str | None` column (small migration) populated on first provision and used as the primary match in the 23.2 callback, with email as the fallback for users created before this column existed. (If 23.1 concludes `oid` is unnecessary, record that and match by normalized email — but `oid` is the recommended default.)

7. **Provisioning is config-gated and safe.** Given auto-provisioning changes who can get an account, when `azure_sso_enabled` is false (or an `azure_sso_auto_provision` flag is off), then no user is auto-created and login falls back to the 23.2 "not provisioned" 403. Domain restriction (reuse the `*_allowed_email_domain` pattern) is honored if configured. Provisioning failures are logged (safe fields only) and surfaced as an actionable login error — never a 500, never a partial half-created user committed.

## Tasks / Subtasks

- [x] **Task 1 — Role mapping function (AC: 1)**
  - [x] Added `map_app_roles(roles_claim) -> set[str]` + `primary_role(roles) -> str` + `AZURE_APP_ROLE_TO_PLATFORM` to [auth/service.py](src/ai_qa/auth/service.py) (next to the role constants). `{"admin": ADMIN_ROLE, "project-admin": PROJECT_ADMIN_ROLE, "project_admin": …, "user": STANDARD_ROLE}`, lower-cased lookup; empty/unknown → `{STANDARD_ROLE}`; priority `admin > project_admin > standard`.
  - [x] Unit-tested exhaustively in `tests/unit/test_role_mapping.py` (single/multi/unknown/empty/case/underscore/non-string).

- [x] **Task 2 — `UserSession.roles` (AC: 2)**
  - [x] Added `roles: list[str] = field(default_factory=list)` to `UserSession` + `to_dict`/`from_dict`/`create_session` ([api/auth/session.py](src/ai_qa/api/auth/session.py)). Default empty for back-compat. **Chosen path = no persisted role-set column** (session-derived set + derived single `User.role` primary), per the AC2 default.

- [x] **Task 3 — `User.azure_oid` column + migration (AC: 6)**
  - [x] Added `azure_oid: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True, index=True)` to `User` ([db/models.py](src/ai_qa/db/models.py)). Migration `e1a2c3d4f5b6` (`down_revision="d5e8c1b9f3a2"`, the verified head) — single `batch_alter_table` block (Postgres direct ALTERs + SQLite recreate). **Verified upgrade/downgrade round-trip on SQLite** (`tests/db/test_azure_oid_migration.py`): adds `ix_users_azure_oid` unique index + relaxes `password_hash` nullable; downgrade reverts.
  - [x] Gate path (persisted `roles` column) NOT taken — default no-new-column.

- [x] **Task 4 — Auto-provision + re-sync in the callback (AC: 3, 4, 5, 7)**
  - [x] Extended 23.2's `sso.py` `_complete_login`: match by `azure_oid` then email; no-match + `azure_sso_enabled && azure_sso_auto_provision` + domain-allowed → `_provision_user` (identity-only, `password_hash=None`, derived role) via `flush` then commit (atomic — any failure rolls back, redirects `sso_error=provision_failed`, never 500/half-user).
  - [x] On match: `_resync_identity` refreshes display_name/azure_oid only — never touches memberships/secrets/timezone.
  - [x] `_effective_roles` = `map_app_roles(claim)` ∪ `{project_admin if ≥1 ProjectMembership(role="project_admin")}`; `User.role = primary_role(effective)` (never downgrades a PA-membership holder); `UserSession.roles = sorted(effective)`.
  - [x] Gated on `azure_sso_enabled` + new `azure_sso_auto_provision`; honors `azure_sso_allowed_email_domain`; safe-field logging only.

- [x] **Task 5 — Password-column compatibility until 23.6 (AC: 3)**
  - [x] Chose **(a)**: `User.password_hash` → `Mapped[str | None]` (nullable now; dropped in 23.6). Guarded `authenticate_user` (`if user.password_hash is None or not verify_password(...)`) so a password-less SSO user can never authenticate via the local path.

- [x] **Task 6 — Tests (all ACs)**
  - [x] Mapping unit tests (6). Callback tests in `tests/api/test_sso_api.py`: provision creates identity-only user (derived role + `azure_oid` + null password); Azure `admin` → platform admin bootstrap; multi-role token → `UserSession.roles` full set + `role` = primary; provisioning off → not_provisioned, no user; disallowed domain → rejected, no user; **membership-confers-role + no-downgrade + timezone/membership preserved on re-sync**.
  - [x] Migration round-trip test on SQLite (`tests/db/test_azure_oid_migration.py`) — unique `azure_oid` index asserted + `down_revision` chain locked.
  - [x] `uv run pytest` whole suite → **1864 passed** (coverage 85%); `ruff check --fix` + `ruff format`; `uv run mypy src` → clean.

## Dev Notes

### Why Azure is the role source, re-read every login (default = no persisted role set)

Thuong's direction: roles come from Azure App Roles, a user can hold several, and the Enterprise Application is the source of truth. The cleanest model is therefore to **derive** the platform role set from the token on every login and not maintain a second copy that can drift. `User.role` stays as a single **derived primary** purely so the large existing single-role surface ([rbac.py](src/ai_qa/api/auth/rbac.py), [admin.py](src/ai_qa/api/admin.py), [projects.py](src/ai_qa/api/projects.py), [App.tsx](frontend/src/App.tsx)) keeps working unchanged, and the **full set** rides in the session for the 23.4 header/nav. Persisting a `User.roles` column is the documented alternative if a role set ever needs to be queried without a live token (e.g. an admin listing) — but that is the gate, not the default.

### Multi-role collapse: primary = highest privilege

`admin > project_admin > standard`. An `admin`-role user implicitly has project-admin authority everywhere (already true via the `rbac.py:68-69` backdoor — confirmed in 23.5), so the primary being `admin` is correct. A user with both `project-admin` and `user` roles → primary `project_admin`, set `{project_admin, standard}`, lands on the user workspace by default (23.4) with a Project Admin Dashboard link.

### Membership confers `project_admin` (Thuong 2026-06-25 decision)

Beyond the Azure claim, the effective role set adds `project_admin` whenever the user holds a `ProjectMembership(role="project_admin")`. This is the decision that lets an admin set up a project-admin **entirely in-app** (create the user + assign a project, before that person ever logs in — 23.5) with **no Azure `project-admin` app-role grant required**; the Azure app role remains an additive alternative. The platform **`admin`** role is the one role that comes **only** from Azure (the admin bootstrap, AC5). Because `require_project_admin_for_project` ([rbac.py:70-79](src/ai_qa/api/auth/rbac.py:70)) gates on `User.role==project_admin` **and** the membership row, deriving the role from the membership is exactly what makes a pre-assigned project-admin work on their first login.

### Current behavior to PRESERVE (regression guardrails)

- **Don't clobber platform-managed state on re-sync.** `ProjectMembership` rows (who administers/belongs to which project), `UserSecret` rows, and `timezone` are NOT owned by Azure — never overwrite them during identity/role re-sync (AC4).
- **Atomic provisioning.** Create-user + commit in one transaction; a failure must leave no half-created user (mirror the careful commit boundaries in [admin.py create_user:397-406](src/ai_qa/api/admin.py:397)).
- **No secret leak / no 500s on the login path.** Safe-field logging only; provisioning/role errors become actionable login messages.
- **Local login still works until 23.6.** This story does not remove password auth; it only stops *requiring* a password for SSO-provisioned users (AC5/Task 5).

### Source tree components to touch

- `src/ai_qa/auth/service.py` (or new `auth/roles.py`) — **ADD** (`map_app_roles`, `primary_role`, mapping constant).
- `src/ai_qa/api/auth/session.py` — **UPDATE** (`UserSession.roles`).
- `src/ai_qa/db/models.py` — **UPDATE** (`User.azure_oid`; make `password_hash` nullable; optional `roles` column on gate path).
- `alembic/versions/` — **ADD** (one migration: `azure_oid` [+ `password_hash` nullable] [+ `roles` on gate path]).
- `src/ai_qa/api/auth/sso.py` — **UPDATE** (provision + re-sync in callback).
- `src/ai_qa/config.py` — **UPDATE** (`azure_sso_auto_provision`, reuse `*_allowed_email_domain`).
- Tests — **ADD** (mapping, provisioning callback, migration).

### Decided scope (defaults — Thuong, correct if needed)

- **No persisted role-set column** (session-derived set + derived single `User.role` primary). Flip to a `User.roles` JSON column only if server-side role-set queries are needed.
- **Match by `azure_oid`** (stable), email fallback.
- **Azure `admin` app-role = platform admin bootstrap** (replaces the password bootstrap removed in 23.6).
- **`password_hash` → nullable now, dropped in 23.6.**
- **Auto-provision gated** by `azure_sso_enabled` + `azure_sso_auto_provision` + optional domain allowlist.

### Testing standards summary

- Pure mapping function unit-tested separately from the callback. Callback tested via the 23.2 mock-IdP + `app.dependency_overrides`. Whole-suite pytest run. Pyrefly-clean: assert optionals before use; bind+assert mock `call_args` before indexing ([project-context.md](project-context.md)).

### Project Structure Notes

- This story owns ONE migration (`azure_oid` [+ nullable `password_hash`]). 23.6 owns the migration that DROPS `password_hash`. Chain `down_revision` carefully if implemented out of order.

### References

- Epic + story: [epics.md#Epic-23](_bmad-output/planning-artifacts/epics.md:2371), [Story 23.3](_bmad-output/planning-artifacts/epics.md:2395)
- Role constants + bootstrap: [auth/service.py:13-124](src/ai_qa/auth/service.py:13), [auth/bootstrap_admin.py](src/ai_qa/auth/bootstrap_admin.py)
- Session + claims: [api/auth/session.py:17-75](src/ai_qa/api/auth/session.py:17)
- User model: [db/models.py:30-53](src/ai_qa/db/models.py:30) (`role` :38, `password_hash` :37)
- Provision/commit precedent: [api/admin.py:364-491](src/ai_qa/api/admin.py:364) (create_user / update_user)
- Add-column migration template: `alembic/versions/c98f775f0b00_add_timezone_to_user.py`; head `d5e8c1b9f3a2`
- Callback to extend: `src/ai_qa/api/auth/sso.py` (from 23.2)
- Coding/testing rules: [project-context.md](project-context.md)
- Related memories: [[epic-23-sso-first-auth]], [[alice-model-selection]] (deterministic-mapping precedent), [[projectadmin-rbac-redesign-plan]], [[epic-15-admin-rbac-sprint-change]]

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (BMAD dev-story)

### Debug Log References

- Migration round-trip verified on in-memory SQLite (upgrade adds `azure_oid` + `ix_users_azure_oid` + nullable `password_hash`; downgrade reverts).
- `uv run pytest` → 1864 passed (85% cov); `uv run mypy src` clean; ruff clean.

### Completion Notes List

- **Default decisions taken (Thuong's bakes):** (1) **no persisted role-set column** — roles derived from the token every login + carried in `UserSession.roles`; `User.role` keeps the single derived primary for the existing single-role surface. (2) Match by **`azure_oid`** (stable), email fallback. (3) Azure **`admin`** app-role = platform-admin bootstrap (replaces the password bootstrap removed in 23.6). (4) **`password_hash` → nullable now** (dropped in 23.6).
- **Membership confers `project_admin`:** the effective set unions `project_admin` whenever the user holds a `ProjectMembership(role="project_admin")`, so an admin can create+assign a project-admin **before that person logs in** (23.5) and it takes effect on first login — `require_project_admin_for_project`'s `User.role==project_admin` check then passes. Re-sync **never downgrades** a PA-membership holder.
- **Re-sync is non-destructive:** only identity (display_name) + `azure_oid` + derived role are refreshed; `ProjectMembership` rows, `UserSecret` rows, and `timezone` are preserved (verified by test).
- **Atomic + safe:** provisioning flushes then commits in one transaction; any failure rolls back (no half-user) and redirects to a safe `sso_error` code — never a 500, never a secret in logs.
- **Provisioning is config-gated** by `azure_sso_enabled` + `azure_sso_auto_provision` (both default False, so the suite + a no-SSO dev run are unaffected and 23.2's existing-user-only tests still pass).
- **Local login still works** until 23.6 (only stopped *requiring* a password for SSO users).

### File List

- `src/ai_qa/auth/service.py` — UPDATED (`AZURE_APP_ROLE_TO_PLATFORM`, `map_app_roles`, `primary_role`; `authenticate_user` nullable-hash guard).
- `src/ai_qa/api/auth/session.py` — UPDATED (`UserSession.roles` + to_dict/from_dict/create_session).
- `src/ai_qa/db/models.py` — UPDATED (`User.azure_oid`; `password_hash` nullable).
- `alembic/versions/e1a2c3d4f5b6_add_azure_oid_and_nullable_password_hash.py` — ADDED (one migration, off head `d5e8c1b9f3a2`).
- `src/ai_qa/config.py` — UPDATED (`azure_sso_auto_provision`).
- `src/ai_qa/api/auth/sso.py` — UPDATED (provision + re-sync + role derivation in `_complete_login`; mock `roles` form param).
- `tests/unit/test_role_mapping.py` — ADDED (6 mapping unit tests).
- `tests/db/test_azure_oid_migration.py` — ADDED (migration round-trip + chain).
- `tests/api/test_sso_api.py` — UPDATED (6 provisioning/role tests).

### Change Log

- 2026-06-25 — Story 23.3: auto-provision on first SSO login + Azure app-role → platform-role mapping. `map_app_roles`/`primary_role`, `UserSession.roles`, `User.azure_oid` + nullable `password_hash` (migration `e1a2c3d4f5b6`), membership-confers-project_admin, Azure-admin bootstrap. Suite 1864 green. Status → review.
