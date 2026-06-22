# Re-Architecture: `project_admin`, Dashboard Split, Project Accounts, Role-Aware Pipeline

**Status:** For Thuong's sign-off BEFORE coding. Produced 2026-06-21 from a multi-agent codebase analysis; key claims verified against current (uncommitted) `main`.

---

## 1. Scope & shape

A **multi-epic re-architecture**, not a feature tweak. It revises work shipped 2026-06-20 (project config editors in the Admin dashboard; the per-user `CapturedSession` table) and adds a new authorization tier, a new dashboard, a new credential model, and a role dimension threading through Mary → Sarah → Jack.

- **WS-A — RBAC:** add role `project_admin`; restrict who an admin can create; link `project_admin` ↔ project.
- **WS-B — Dashboard split:** strip project config + membership out of the Admin dashboard; build a Project Admin dashboard.
- **WS-C — Project accounts + login-type:** new `ProjectAccount` model + `Project.login_type`; reconcile with `CapturedSession`.
- **WS-D — Mary role-awareness:** ask role in clarify loop; per-role artifact sub-folders.
- **WS-E — Sarah role propagation:** carry role onto scripts; role-grouped handoff to Jack.
- **WS-F — Jack run plan:** role selection + multi-browser (Jack is **not built** — Epic 14).

WS-A/B/C are tightly coupled (one logical group). WS-D/E are independent and shippable early. WS-F depends on Jack existing.

---

## 2. RBAC model

Three platform roles on `User.role` (`String(50)`, default `"standard"`):

| Role | Scope | Powers |
| ---- | ----- | ------ |
| `admin` (platform) | global | create/sync users, Run E2E, Model Benchmark, create/edit projects (**NAME + DESCRIPTION only**) |
| `project_admin` | per-project (only their own) | Jira/Confluence, environments, app_roles, accounts, membership — for projects they administer |
| `standard` | per-project member | run the pipeline; capture own sessions |

Distinct from **app-under-test roles** (`Project.app_roles`, e.g. Admin/User/Guest) which label *which login a test runs as* — a data dimension, never an authorization role.

- Add `PROJECT_ADMIN_ROLE = "project_admin"` in `auth/service.py`, re-export from `rbac.py`. No column migration (free string) — guard at the API.
- **Can't-create-admin (Directive 1):** `AdminUserRole` (`admin.py:41`) → `Literal["project_admin","standard"]` (drop `"admin"`); add server-side check rejecting `role == ADMIN_ROLE` with 403. Platform admin only via `bootstrap_admin`.
- **Linkage (recommend, no new table):** reuse `ProjectMembership.role` — add `"project_admin"` to `ProjectMembershipRole` (`admin.py:40`). User is a platform `project_admin` (`User.role`) AND administers specific projects via `ProjectMembership(role="project_admin")` rows → supports many-admins-per-project and one-person-many-projects. New dep `require_project_admin_for_project(project_id)`: allow if `User.role == ADMIN_ROLE` (platform backdoor) OR (`User.role == PROJECT_ADMIN_ROLE` AND a matching `project_admin` membership exists).

---

## 3. Dashboard split

| Feature | Today | After |
| ------- | ----- | ----- |
| Create/sync users | Admin | **Admin** (role limited to project_admin/standard) |
| Run E2E / Model Benchmark | Admin | **Admin** |
| Project name + description | Admin | **Admin (trimmed)** |
| environments / app_roles editors | Admin | **MOVE → Project Admin** |
| Confluence / Jira URLs | Admin | **MOVE → Project Admin** |
| `enabled_providers` | Admin | **MOVE → Project Admin** |
| Membership assign/remove | Admin (`admin.py:445-516`) | **MOVE → Project Admin** |
| Accounts matrix + `login_type` | — | **NEW → Project Admin** |

- **Routing** (`App.tsx:1503`, currently `role === "admin"`): three-way → `admin` → trimmed `AdminDashboard`; `project_admin` → new `ProjectAdminDashboard` (scoped to administered projects via `GET /project-admin/projects`, project picker if several); `standard` → workspace.
- **Backend:** strip config fields from admin `ProjectCreate/Update`; new `/project-admin` router guarded by `require_project_admin_for_project` (list projects, PUT config, accounts CRUD, members add/remove). `sessions.py` env/role validation unchanged (lists still live on `Project`; only the editor changes).

---

## 4. Dynamic env × role × account model + login-type

- **`Project.login_type`** — new `String(20)` `Literal["SSO","PASSWORD"]`, default `"SSO"`.
- **New table `project_accounts`** (project-level identity catalog, project_admin-owned):
  - `id`, `project_id` (FK CASCADE), `environment String(64)`, `role String(64)`, `login_identifier String(320)` (email/username, always), `encrypted_password` (NULL for SSO; set for PASSWORD), `label`, `UNIQUE(project_id, environment, role)`.
  - SSO → identifier only, no password. PASSWORD → identifier + encrypted password.
  - "Dynamic in env/role/account" = project_admin adds rows; env/role validated against `Project.environments`/`Project.app_roles`.
- **Encryption:** `ProjectAccount.encrypted_password` is **project-shared**, so it must NOT use the per-user `UserSecretEncryptedText`/`USER_SECRETS_ENCRYPTION_KEY`. Add a project/instance-keyed encrypted type (keyed off `db_encryption_key`). → **Q3**.

### Reconciliation with `CapturedSession` (central decision) — two layers that COMPOSE

- **`ProjectAccount` = identity + strategy (WHO logs in, HOW).** Project-level, project_admin-owned.
- **`CapturedSession` = proof-of-auth (storageState blob).** Per-user, per-user-key encrypted, keyed `(user, project, environment, role)`. Each tester owns theirs.

| `login_type` | Session for (env, role) |
| ------------ | ----------------------- |
| **SSO** | account stores identifier only; each tester logs in manually + captures their own `CapturedSession` (existing CDP flow, `auth_method=SSO_MANUAL`). |
| **PASSWORD** | account holds shared password → enables backend **auto-capture** (drive headless login → write each tester's `CapturedSession`, `auth_method=PASSWORD`). → **Q2**. |

`ProjectAccount` does NOT replace `CapturedSession` — it *parameterizes* how each slot's session is produced. No `CapturedSession` schema change; `sessions.py` capture gains a slot-exists check + the PASSWORD auto-capture branch.

---

## 5. Mary role-awareness (WS-D)

`TestCase` has no `role` field; clarify loop never asks role; artifacts saved flat `{base}.md`.

- Add optional `TestCase.role: str | None`; round-trip via a `Role:` line in `to_markdown`/`from_markdown` (consistent with MD-only test-case storage).
- `_plan_test_clarifications`: when the source doesn't specify the app role, add a clarify question ("Which application role should this test run as?", offering `Project.app_roles`). Reuses the existing `test_clarify_request` loop.
- Sub-folder naming: `_persist_test_case` → `name = f"{role}/{base}.md"` when role set (else flat). `sanitize_artifact_name` preserves `/`; `build_artifact_key` yields `.../test_cases/{id}/v{n}/{role}/{base}.md`. Role optional → skipped question = flat name, unchanged.

---

## 6. Sarah role propagation (WS-E)

- Read `TestCase.role`; stamp it on the script metadata sidecar (alongside `source_test_case_id`/env).
- Mirror Mary's layout: save scripts `<role>/<script>.py` (`.../test_scripts/{id}/v{n}/{role}/...`).
- **Role-grouped handoff to Jack:** payload grouped by role (`{ "Admin": [...], "User": [...] }`), each group carrying its `(environment, role)` tag — different roles use different accounts/sessions and cannot run in one authenticated context.

---

## 7. Jack run plan (WS-F)

Jack **does not exist** (only alice/bob/mary/sarah). Jack = **Epic 14** (now top priority; `epics.md:1432-1567`). All of WS-F is greenfield, gated on Epic 14.

- **Role selector:** pick ONE role per run (one role = one account = one session context).
- **Browser multi-select:** Playwright 1.60 offers **Chromium / Chrome / Edge (`msedge`) / Firefox**. **⚠ Safari/WebKit cannot run on Windows** (needs macOS) → on Windows fleet offer Chrome/Chromium/Edge/Firefox; grey out Safari until a macOS runner exists. → **Q4**.
- **Session feed:** for the chosen role, resolve the current user's `CapturedSession` via `resolve_storage_state`, validate freshness (fail loud "re-capture needed" if stale), run each script in the group across selected browsers in isolated contexts.

---

## 8. Conflicts with today's uncommitted work (must MOVE/CHANGE)

1. `Project.environments`/`app_roles` editors MOVE off Admin (`EnvironmentsEditor`/`AppRolesEditor` in `AdminDashboard.tsx`; fields in admin `ProjectCreate/Update`) → Project Admin.
2. Confluence/Jira URLs + `enabled_providers` MOVE off Admin → project_admin config endpoint.
3. Membership assign/remove MOVE off Admin (`admin.py:445-516`) → `/project-admin/.../members`.
4. `AdminUserRole` literal changes (drop `admin`, add `project_admin`) + can't-create-admin guard.
5. `ProjectMembershipRole` literal adds `project_admin`.
6. `CapturedSession` / `sessions/service.py` / `api/sessions.py` / `session_capture.py` NOT replaced — `ProjectAccount` sits above them; only capture validation + PASSWORD branch added.
7. `UserSecretEncryptedText` is the WRONG key for `ProjectAccount.encrypted_password` (per-user vs project-shared) — needs a project-keyed type.
8. `TestCase` MD round-trip changes to carry `role`.
9. E2E specs that bootstrap projects with env/app_roles via the admin path break → repoint to project_admin endpoints (the 2026-06-20 `frontend/e2e` 7-group rebuild touches real PT/PTP projects — re-verify).

---

## 9. Phased plan (ordered; each shippable + testable)

- **Slice 1 — RBAC core (WS-A) [recommended first; backend-only, low risk].** `PROJECT_ADMIN_ROLE`, `require_project_admin_for_project`, role-literal changes, can't-create-admin guard. Tests: role gates, 403 on admin-create.
- **Slice 2 — Dashboard split (WS-B), needs S1.** `/project-admin` router + `ProjectAdminDashboard`; move env/app_roles/jira/confluence/providers/membership; trim Admin; three-way routing; E2E repoint.
- **Slice 3 — Accounts + login_type (WS-C), needs S2.** `Project.login_type`, `ProjectAccount` + project-keyed encryption, account-matrix UI, `sessions.py` slot validation. (3b: PASSWORD auto-capture, deferrable.)
- **Slice 4 — Mary role-awareness (WS-D), independent.** `TestCase.role` + MD round-trip, clarify role question, per-role sub-folders. (Parallel with S1-S3.)
- **Slice 5 — Sarah role propagation (WS-E), needs S4.** Role on script metadata, `<role>/` storage, role-grouped handoff.
- **Slice 6 — Jack run plan (WS-F), needs Epic-14 Jack + S5 + S3.** Build Jack, then role selector + Windows-safe multi-browser + session resolution.

Dependencies: **S1→S2→S3**; **S4→S5**; **S6 needs Jack + S5 + S3.** S4/S5 parallel to S1-S3.

---

## 10. Decisions (signed off by Thuong 2026-06-21)

1. **Linkage:** ✅ reuse `ProjectMembership.role="project_admin"` — no new table.
2. **PASSWORD auto-capture:** ✅ backend auto-drives login with the project account and writes each tester's `CapturedSession` (Slice 3b is IN scope, not deferred).
3. **Shared-password key:** ✅ add a project/instance-level encrypted type keyed off `db_encryption_key` for `ProjectAccount.encrypted_password` (do NOT reuse the per-user key).
4. **Safari:** ✅ offer Chrome/Chromium/Edge/Firefox only; Safari greyed-out/deferred until a macOS runner exists.

**Implementation starts at Slice 1 (RBAC core).**
