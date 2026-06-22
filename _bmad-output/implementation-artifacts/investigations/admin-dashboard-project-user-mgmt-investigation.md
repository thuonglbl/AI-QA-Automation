# Investigation: Admin Dashboard — create-project failure + project/user management improvements

## Hand-off Brief

1. **What happened.** "Create project" fails with a generic "Something went wrong. Please try again." — **Confirmed root cause:** the live PostgreSQL column `projects.confluence_base_url` is `NOT NULL`, but the simplified admin create-flow (name + description only) inserts `NULL`, raising an `IntegrityError` that the endpoint mislabels and the frontend collapses to the generic message.
2. **Where the case stands.** Root cause for the bug (item 2) is Confirmed and deterministic. The other four items are scoped feature changes (UI copy removal, project-admin project picker + 1:1 constraints, user-list sorting, user Edit/Delete) — code areas mapped, backend gaps identified.
3. **What's needed next.** One Alembic migration to make `confluence_base_url` nullable fixes the bug immediately; items 1/3/4/5 are a coherent slice of the in-flight project-admin RBAC epic → recommend folding them in via `bmad-correct-course` (or `bmad-quick-dev` for the migration + UI copy now).

## Case Info

| Field            | Value                                                                                  |
| ---------------- | -------------------------------------------------------------------------------------- |
| Ticket           | N/A                                                                                    |
| Date opened      | 2026-06-21                                                                             |
| Status           | Active                                                                                 |
| System           | Windows 11; backend FastAPI + SQLAlchemy on **PostgreSQL** (alembic head `c5b1e9a4d762`); React 19 frontend |
| Evidence sources | Live DB introspection, source code, alembic migrations, two UI screenshots            |

## Problem Statement

Five requested fixes/improvements on the Admin Dashboard (`AdminDashboard.tsx`):

1. Remove the helper sentences "Confluence/Jira links, providers, environments, app roles and members are configured by the project admin after creation." and "Project membership is managed by the project admin."
2. **Create project fails.** Project name must be required, description optional — fix create/edit/delete project.
3. When creating a user, if **Project Admin** is chosen there must be a project picker. One account = project_admin of exactly one project; one project = exactly one project_admin. **Standard** users may belong to many projects.
4. Sort Users Management by Role (Admin → Project Admin → Standard; for Project Admin also show the project name), then status (Active → Inactive), then timezone (alphabetical), then display name.
5. Add Edit / Delete to Users Management.

## Evidence Inventory

| Source                           | Status    | Notes                                                                                              |
| -------------------------------- | --------- | -------------------------------------------------------------------------------------------------- |
| Live PostgreSQL `projects` table | Available | Introspected via SQLAlchemy `inspect` — `confluence_base_url` is `nullable=False` (NOT NULL).      |
| `alembic current` / `heads`      | Available | DB at `c5b1e9a4d762 (head)`; migration `f3a9c8b21d47` (sets confluence NOT NULL) is in the lineage. |
| Backend admin API                | Available | `src/ai_qa/api/admin.py` — project + user CRUD.                                                    |
| ORM model                        | Available | `src/ai_qa/db/models.py:56-99` — `Project`, `confluence_base_url` `nullable=True` (drift).         |
| Frontend dashboard + API client  | Available | `frontend/src/components/admin/AdminDashboard.tsx`, `frontend/src/lib/api.ts`, `lib/projects.ts`.  |
| Server logs / response body      | Missing   | Exact HTTP status of the failing create not captured live; deduced as 409 (see Deduction 1).       |

## Investigation Backlog

| # | Path to Explore | Priority | Status | Notes |
| - | --------------- | -------- | ------ | ----- |
| 1 | Confirm failing create returns HTTP 409 (not 500) by capturing the live response | Medium | Open | Strengthens Deduction 1 from High-Deduced to Confirmed-observed; not blocking the fix. |
| 2 | Verify `User`→`ProjectMembership` FK has `ondelete=CASCADE` so user Delete (item 5) doesn't `IntegrityError` | Medium | Open | `delete_user` (admin.py:323) does a raw delete; orphan memberships may block it. |
| 3 | Read `design-projectadmin-rbac-redesign-2026-06-21.md` for the intended project_admin↔project model before implementing item 3 | High | Open | Avoids contradicting the awaiting-sign-off RBAC design. |

## Confirmed Findings

### Finding 1: Live DB `projects.confluence_base_url` is NOT NULL

**Evidence:** SQLAlchemy introspection of the running PostgreSQL DB returned `confluence_base_url nullable=False`. Migration `alembic/versions/f3a9c8b21d47_enforce_unique_project_name_and_required_confluence.py:41-46` alters the column to `nullable=False`; it is the last migration touching that column's nullability (grep over `alembic/versions` shows only `02eee99fe6ae`, `a3f7d2e9b1c8`, `f3a9c8b21d47` touch it; the latest sets NOT NULL). DB is at head `c5b1e9a4d762`, and `f3a9c8b21d47`'s child is `b7d2f1a9c4e5`, so it is in the applied lineage.

**Detail:** No migration reverts the column to nullable. The DB still enforces NOT NULL on `confluence_base_url`.

### Finding 2: Model/DB schema drift — model declares the column nullable

**Evidence:** `src/ai_qa/db/models.py:63-65` — `confluence_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)`.

**Detail:** The model was changed to optional (the project-admin RBAC redesign moved Confluence/Jira config out of project creation), but no accompanying migration relaxed the DB constraint. Model and DB disagree.

### Finding 3: The admin create-flow inserts `confluence_base_url = None`

**Evidence:** Frontend `AdminDashboard.tsx:364-390` (`handleCreateProject`) calls `createAdminProject({ name, description })` — no Confluence URL. `lib/projects.ts:37-44` POSTs to `/admin/projects`. Backend `admin.py:341-371` (`create_project`) inserts `confluence_base_url=request.confluence_base_url`; for a name+description-only request the model-validator `normalize_links` (`admin.py:162-170`) normalizes the absent value to `None`.

**Detail:** Every admin-created project now sends `NULL` into a NOT-NULL column.

### Finding 4: The frontend collapses HTTP 409 to the generic "Something went wrong"

**Evidence:** `api.ts:62-68` (`kindForStatus`) maps 401→auth, 403→forbidden, 404→not_found, 422/400→validation, and **everything else (incl. 409) → "server"**. `api.ts:45-60` (`safeMessage`) returns "Something went wrong. Please try again." for `server`. `apiFetch` builds `ApiError.message` from `safeMessage(kind)` only — it never surfaces the server `detail` (the detail is stored in `details`, not shown).

**Detail:** A 409 *and* a 500 both render as the identical generic message, so the visible message cannot, by itself, distinguish the two.

## Deduced Conclusions

### Deduction 1: Create-project fails with a 409 caused by the NOT-NULL violation, shown as the generic error

**Based on:** Findings 1, 2, 3, 4.

**Reasoning:** `create_project` inserts `confluence_base_url=NULL` (F3) into a NOT-NULL column (F1/F2). PostgreSQL raises a NOT-NULL `IntegrityError`. The endpoint's `except IntegrityError` (`admin.py:367-369`) re-raises it as **HTTP 409 "Project name already exists"** — a misleading reuse of the duplicate-name handler. The frontend maps 409 → "server" → "Something went wrong. Please try again." (F4), which is exactly the banner in the screenshot.

**Conclusion:** The bug is a model/DB schema drift, not a frontend or validation bug. The frontend already validates name-required correctly (`AdminDashboard.tsx:366-370`) and the backend already validates it (`ProjectCreateRequest.name_must_not_be_blank`, `admin.py:105-112`) and treats description as optional. The only defect blocking creation is the DB constraint.

## Hypothesized Paths

### Hypothesis 1: Failure is a 500 from a missing column rather than a 409

**Status:** Refuted.

**Theory:** If migrations were unapplied, `environments`/`app_roles`/`login_type` columns would be missing and the insert would 500.

**Supporting indicators:** Project memory noted `alembic upgrade head` as a pending follow-up.

**Would refute:** All columns present in the live DB and DB at head.

**Resolution:** Introspection shows `environments`, `app_roles`, `login_type` all present (`nullable=False`); `alembic current` = head `c5b1e9a4d762`. The project list also renders (a `select(Project)` would otherwise fail). Only `confluence_base_url` NOT NULL remains as the live constraint. Refuted in favor of Deduction 1.

## Missing Evidence

| Gap                                  | Impact                                                  | How to Obtain                                                              |
| ------------------------------------ | ------------------------------------------------------- | -------------------------------------------------------------------------- |
| Exact HTTP status of failing create  | Upgrades Deduction 1 to directly observed               | Reproduce create in the running app; read Network tab / backend log.       |
| `User`→membership FK cascade behavior | Determines whether user Delete (item 5) needs extra work | Inspect FK on `project_memberships.user_id`; test delete of a member user. |
| Intended project_admin↔project model | Prevents item 3 contradicting the RBAC design           | Read `design-projectadmin-rbac-redesign-2026-06-21.md`.                    |

## Source Code Trace

### Item 2 — Create project failure (the bug)

| Element       | Detail                                                                                              |
| ------------- | --------------------------------------------------------------------------------------------------- |
| Error origin  | `src/ai_qa/api/admin.py:354-369` (`create_project`) — INSERT with `confluence_base_url=None`.       |
| Trigger       | Admin submits the Create Project form (name + optional description) — `AdminDashboard.tsx:364-390`. |
| Condition     | Live `projects.confluence_base_url` is NOT NULL (`models.py:63-65` says nullable; DB disagrees).    |
| Related files | `frontend/src/lib/api.ts:45-68` (409→generic message), `alembic/versions/f3a9c8b21d47_*.py`.        |

### Items 1, 3, 4, 5 — feature changes (mapped, not defects)

| Item | Location | What exists / what's needed |
| ---- | -------- | --------------------------- |
| 1 (remove copy) | `AdminDashboard.tsx:761-764` ("Confluence/Jira links … after creation."), `:826-829` ("Project membership is managed by the project admin."). Near-duplicate at `:647-650` in the edit-project form ("Confluence/Jira, providers, environments, roles and members are managed by the project admin."). | Delete the two named lines; confirm whether the edit-form variant (`:647-650`) should also go. Pure FE, trivial. |
| 3 (project_admin picker + constraints) | FE Create User form has Role `<select>` but no project picker (`AdminDashboard.tsx:882-903`). Backend `AdminUserCreateRequest` (`admin.py:177-184`) has no `project_id`; `create_user` (`admin.py:292-320`) only creates a `User`. project_admin↔project link is a `ProjectMembership(role="project_admin")` (`rbac.py:56-64`, `projects_admin.py`). | FE: show a project `<select>` when role=project_admin. Backend: add optional `project_id` (required iff role=project_admin), create the `project_admin` membership, and enforce **one project_admin per project** + **one project per project_admin**. Standard users unchanged (membership stays project_admin-managed). Needs backend + FE + tests. |
| 4 (sort users) | `AdminDashboard.tsx:791-832` renders `users.map(...)` with no ordering; backend `list_users` (`admin.py:282-289`) orders by email. `AdminUser` type already carries `project_memberships` incl. `project_name` (`types/project.ts:83-94`). | FE sort: role rank (admin→project_admin→standard) → is_active (active first) → timezone (A→Z) → display_name; render the project name for project_admin from `project_memberships` (the one with role `project_admin`). Pure FE. |
| 5 (Edit/Delete users) | Delete endpoint exists: `DELETE /admin/users/{id}` (`admin.py:323-338`). **No update endpoint** (no PUT/PATCH `/admin/users/{id}`). FE list has no Edit/Delete buttons. | Backend: add an update-user endpoint (display_name, role, timezone, is_active, project reassignment for project_admin, optional password reset). FE: Edit form + Delete button. Guard against editing/deleting the platform admin and check membership FK cascade (Backlog #2). |

## Conclusion

**Confidence:** High (for item 2 — the bug).

Item 2's root cause is **Confirmed**: schema drift where `projects.confluence_base_url` remains NOT NULL in the DB while the model and create-flow treat it as optional, so every admin-created project violates the constraint; the resulting 409 is rendered by the frontend as the generic "Something went wrong." Items 1, 3, 4, 5 are well-scoped enhancements with code areas and backend gaps identified — they are not malfunctions of existing code.

## Recommended Next Steps

### Fix direction

- **Item 2 (root-cause fix):** add an Alembic migration that `op.alter_column("projects", "confluence_base_url", nullable=True)` (and matching `downgrade` back to NOT NULL with the existing empty-string backfill). This realigns the DB with `models.py`. Optional hardening: in `create_project`/`update_project`, narrow `except IntegrityError` handling so a non-duplicate violation doesn't masquerade as "Project name already exists"; and consider adding a 409 case to `kindForStatus` so conflicts surface a meaningful message instead of the generic one.
- **Item 1:** delete the two helper lines (and decide on the edit-form near-duplicate).
- **Item 3:** FE conditional project picker + backend `project_id` on user-create with the two uniqueness invariants enforced (one project_admin per project; one project per project_admin).
- **Item 4:** client-side multi-key sort + project-name rendering for project_admin.
- **Item 5:** new update-user endpoint + FE Edit/Delete, with platform-admin guards and FK-cascade verification.

### Diagnostic

- To directly confirm the 409 (Backlog #1): start the backend, attempt a create in the UI, and read the response status in the browser Network tab or the backend log. Deduction 1 predicts `409 "Project name already exists"` despite a unique name.

## Reproduction Plan

1. Backend at head (`alembic current` = `c5b1e9a4d762`), frontend running.
2. As the platform admin, open Admin Dashboard → Create Project, enter a **unique** name (e.g. `test`) and any/empty description, submit.
3. Expected (current/buggy): banner "Something went wrong. Please try again."; backend insert raises NOT-NULL `IntegrityError` on `confluence_base_url`, returned as 409.
4. Expected (after the nullable migration): project is created successfully.

## Side Findings

- `api.ts` never surfaces the server `detail` — all non-(401/403/404/400/422) errors collapse to one generic string (`api.ts:45-68`). This is a broad UX gap: 409 conflicts and 500s look identical to users. Worth a separate small improvement (add 409 handling and/or surface `detail` for `validation`/`server`). [Confirmed]
- `create_project`/`update_project` reuse the duplicate-name 409 for *any* `IntegrityError` (`admin.py:367-369`, `:401-403`), which is why a NOT-NULL violation reports as "Project name already exists". [Confirmed]
- Project memory flagged `alembic upgrade head` as pending; the live DB is in fact at head — that follow-up appears already done. [Confirmed]
