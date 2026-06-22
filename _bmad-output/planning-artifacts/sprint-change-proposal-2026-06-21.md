# Sprint Change Proposal — Admin Dashboard: Project-Admin RBAC & User/Project Management

- Date: 2026-06-21
- Author: Thuong (with Dev correct-course)
- Trigger source: investigation `_bmad-output/implementation-artifacts/investigations/admin-dashboard-project-user-mgmt-investigation.md`
- Mode: Batch
- Decisions captured (2026-06-21): (1) project_admin↔project cardinality = **many-to-many** (per design); (2) packaging = **one new epic, all 5 changes as stories**; (3) the platform `admin` account is **immutable** (cannot be edited or deleted; only the platform admin may edit/delete `project_admin` and `standard` users); (4) review mode = Batch; (5) demoting `project_admin`→`standard` **deletes** the project_admin membership; the new epic is **Epic 15**, and former epics 15-21 are renumbered **+1 → 16-22**.

## Section 1 — Issue Summary

Five fixes/improvements were requested on the Admin Dashboard (`frontend/src/components/admin/AdminDashboard.tsx`), one of which is a confirmed production bug:

1. Remove obsolete helper copy that describes config the platform admin no longer owns.
2. **[BUG]** "Create project" fails with a generic "Something went wrong." for every project.
3. When creating a `project_admin` user, require a project picker and link the user to a project.
4. Sort the Users Management list (Role → status → timezone → display name) and show a `project_admin`'s project.
5. Add Edit / Delete to Users Management.

**Bug root cause (Confirmed, High confidence).** The live PostgreSQL column `projects.confluence_base_url` is `NOT NULL` (set by migration `f3a9c8b21d47`, DB at head `c5b1e9a4d762`), but the post-redesign admin create-flow sends only name + description, inserting `confluence_base_url = NULL`. This raises an `IntegrityError`, which `create_project` (`src/ai_qa/api/admin.py:367-369`) re-labels as HTTP 409 "Project name already exists"; the frontend maps 409 → "server" → the generic banner (`frontend/src/lib/api.ts:62-68`). The ORM model already declares the column `nullable=True` (`src/ai_qa/db/models.py:63-65`) — pure model/DB schema drift. Verified directly via SQLAlchemy introspection (`confluence_base_url nullable=False`).

**Context.** The five changes are the Admin Dashboard slice of the signed-off project-admin RBAC re-architecture (`design-projectadmin-rbac-redesign-2026-06-21.md`, Section 10 — 4 decisions approved 2026-06-21). The RBAC backend core has already landed (uncommitted): `PROJECT_ADMIN_ROLE`, `require_project_admin_for_project`, the `/project-admin` router, and the `ProjectAccount`/`login_type` model. The Admin Dashboard frontend changes and the create-user→membership wiring are not yet built.

## Section 2 — Impact Analysis

### Epic impact

- **No dedicated project-admin RBAC epic exists** in `epics.md` or `sprint-status.yaml`. The design lives only as the design doc (sliced WS-A..WS-F / Slice 1-6).
- **Epic 8 "Admin Dashboard and Project Membership Management"** (`epics.md:428-609`, `sprint-status.yaml:122-130`) is **`done` + retro'd** and owns every touched surface (Stories 8.2/8.3/8.5). It cannot be reopened → **all 5 changes require new stories.**
- **Decision:** create a **new epic** that bundles all 5 changes (the Admin Dashboard realization of design Slices 1-2).

### Story impact

| Requested item | New story | Type |
| -------------- | --------- | ---- |
| 2 (create-project bug) | Story: Fix project-create regression (confluence_base_url nullable migration) | Backend (migration) |
| 1 (remove copy) | Story: Trim obsolete Admin Dashboard helper copy | Frontend |
| 3 (project_admin picker) | Story: project_admin project picker + membership on user-create | Backend + Frontend + types |
| 4 (sort users) | Story: Sort Users Management + show project_admin's project(s) | Frontend |
| 5 (Edit/Delete users) | Story: User Edit/Delete + new update-user endpoint + admin-immutability guard | Backend + Frontend + types |

### Artifact conflicts / alignment

- **PRD FR16** (`prd.md:368`): "Admin can CRUD users/projects and assign/remove memberships." → items 2/3/5 fill explicit requirements (the missing update-user endpoint is a spec gap, not scope creep).
- **Architecture** (`architecture.md:320-322,1100-1117`, FR14b): Confluence/provider base URLs are **env/deployment-owned**, not mandatory project-create inputs → architecturally supports `confluence_base_url` nullable (item 2) and removing the "configured after creation" copy (item 1).
- **Architecture** (`architecture.md:371,693`): RBAC checks required on all admin/membership ops → new endpoints must be `require_admin`-guarded.
- **UX spec**: the admin panel UI is **explicitly deferred** (Journey 4, `ux-design-specification.md:1051-1056`) → **no canonical UX guidance exists** for table sorting / role display / edit-delete patterns. These follow the investigation's rules plus the general design system (status = color **+ text + icon**, English-only labels, focus ring `ring-2 ring-blue-500`, 44px targets, destructive = red).
- **RBAC design doc**: items 1/2/4 align cleanly; item 3 uses the design's settled linkage (`ProjectMembership(role="project_admin")`, no new table) and now **adopts the design's many-to-many cardinality** (decision 1); item 5 must respect the can't-create/can't-be `admin` guard (Directive 1).

### Technical impact

- **DB:** one new Alembic migration (item 2). Optional new partial index is **not needed** (many-to-many → no uniqueness to enforce).
- **Backend (`src/ai_qa/api/admin.py`):** add `project_id` to `AdminUserCreateRequest` + membership creation in `create_user`; add a new `PUT/PATCH /admin/users/{id}` endpoint + `AdminUserUpdateRequest`; add admin-immutability guards on update and delete.
- **Frontend:** `AdminDashboard.tsx` (copy removal, project picker, sort, Edit/Delete), `lib/projects.ts` (`updateAdminUser`), `types/project.ts` (`project_id`, `UpdateAdminUserRequest`).
- **FK finding (Confirmed):** `project_memberships.user_id` is `ondelete=CASCADE` → user delete won't `IntegrityError` on memberships. `projects.created_by_user_id` is **also** `ondelete=CASCADE`, but since projects are created by the platform admin (`create_project` sets `created_by_user_id=admin.id`) and the admin is now immutable (decision 3), the cascade-delete-projects hazard is closed for `project_admin`/`standard` deletions.
- **Tests:** backend builds schema from `Base.metadata.create_all` on SQLite (model = `nullable=True`), so the item-2 bug is **invisible to the suite and the migration breaks nothing** (`tests/api/test_admin_projects_api.py::test_create_project_name_only_succeeds` already passes). New/updated tests required for items 3 and 5; frontend `AdminDashboard.test.tsx` needs updates for the project_admin create body and the new Edit/Delete controls.

## Section 3 — Recommended Approach

**Direct Adjustment** — add a new epic and its stories to the backlog; no rollback, no MVP-goal change.

- Create **Epic 15: "Admin Dashboard — Project-Admin RBAC & User/Project Management"** — inserted at slot 15; former epics 15-21 renumbered **+1 → 16-22** across `epics.md` and `sprint-status.yaml` (done in this change). It realizes design-doc Slices 1-2 for the Admin Dashboard. Design Slices 3-6 (accounts/login_type matrix UI, Mary/Sarah/Jack role-awareness) remain future work referenced by, but out of scope of, this epic.
- File all 5 requested changes as the epic's stories (table above).
- **Effort estimate (rough):** items 1, 4 ≈ trivial FE (≈0.5 day each); item 2 ≈ small (migration + a guard-rail test, ≈0.5 day); item 3 ≈ medium (backend + FE + tests, ≈1.5 days); item 5 ≈ medium-high (new endpoint + FE + guards + tests, ≈2 days).
- **Risk:** item 5 is the highest (lockout / role-transition coupling). Mitigated by the admin-immutability rule + self-edit guard.
- **Timeline impact:** none on the broader roadmap; this is an additive epic. Migrations are run by Thuong.

## Section 4 — Detailed Change Proposals

### Story A — Fix project-create regression (item 2)

- **New Alembic migration** under `alembic/versions/`. **Run `uv run alembic heads` first** to confirm the single head for `down_revision` (project memory warns `b2f5c9d81a34`/`a3f8d21c64b9` were hand-edited during the Epic-14 review).
  - `upgrade`: `op.alter_column("projects", "confluence_base_url", existing_type=sa.String(512), nullable=True)`.
  - `downgrade`: backfill `UPDATE projects SET confluence_base_url='' WHERE confluence_base_url IS NULL` then `alter_column(... nullable=False)` (mirror `f3a9c8b21d47:39-46`).
- No model change (`models.py:63-65` already nullable). No endpoint change (`name` already required, `description`/`confluence` already optional).
- **Optional hardening (recommend include):** narrow the `except IntegrityError` in `create_project`/`update_project` (`admin.py:367-369`,`:401-403`) so a non-duplicate violation no longer masquerades as "Project name already exists"; and add a `409` case to `kindForStatus` (`api.ts:62-68`) so conflicts surface a meaningful message instead of the generic banner. (If done, update the two FE tests in `AdminDashboard.test.tsx` that assert the generic message on 409.)
- **Test:** add a metadata/round-trip assertion that the column is nullable; the bug is live-PostgreSQL-only so guard against future regression.

### Story B — Trim Admin Dashboard helper copy (item 1)

- Delete **three** user-facing strings in `AdminDashboard.tsx`:
  - Create-Project helper `:761-764` ("Confluence/Jira links … configured by the project admin after creation.").
  - Edit-Project near-duplicate `:647-650` ("Confluence/Jira, providers, environments, roles and members are managed by the project admin.").
  - Users-Management per-user note `:825-829` — delete the **whole** `{!isAdminUser && (<div>…)}` block, not just the inner text.
- Optional: update the stale internal comment `:239-241` (not user-facing).
- **Test:** optional negative assertion `queryByText(/managed by the project admin/i)` is absent. No existing assertion depends on these strings.

### Story C — project_admin project picker + membership on user-create (item 3, many-to-many)

- **Backend (`admin.py`):**
  - `AdminUserCreateRequest` (`:177-216`): add `project_id: UUID | None = None`; `model_validator` — **require** `project_id` when `role=="project_admin"`, **forbid** it when `role=="standard"` (422 otherwise).
  - `create_user` (`:292-320`): after inserting the `User`, when `role=="project_admin"` also insert `ProjectMembership(project_id=project_id, user_id=user.id, role=PROJECT_ADMIN_ROLE)` in the **same transaction** (roll back the user if membership insert fails). **No uniqueness enforcement** (many-to-many): a project may have multiple project_admins and a user may admin multiple projects (more assigned later via existing membership flows).
- **Frontend (`AdminDashboard.tsx`):** add `createUserProjectId` state + a project `<select>` rendered only when `createUserRole==='project_admin'` (after the Role select `:882-903`); include `project_id` in the `createAdminUser` body (`:398-404`). Projects come from `useProject()` (`:233`). Handle an empty project list gracefully (disable submit + message).
- **Types (`types/project.ts`):** `CreateAdminUserRequest` (`:113-121`) add `project_id?: string | null`.
- **Tests:** update the `AdminDashboard.test.tsx` main test (`:243-275`) which currently asserts the POST body has **no** `project_id` — select a project and expect `project_id` in the body for project_admin. Backend `tests/api/test_admin_users_api.py`: add create-project_admin-with-`project_id` (200 + membership), without (422), standard-with-`project_id` (422). (No 409/uniqueness tests — many-to-many.)

### Story D — Sort Users Management + show project_admin's project(s) (item 4)

- **Frontend (`AdminDashboard.tsx`, `:791-832`):** derive a sorted copy (`useMemo` over `users`) before `.map` — do not mutate state. Sort keys, in order: (1) role rank `admin(0) → project_admin(1) → standard(2)/other(3)`; (2) `is_active` desc (active first); (3) `timezone` A→Z (`localeCompare`, guard `?? ''`); (4) `display_name` A→Z. For `project_admin` rows, render the administered project name(s) near the role badge (`:805-824`), derived from `u.project_memberships.filter(m => m.role==='project_admin').map(m => m.project_name)` (join with comma — many-to-many may yield several).
- Render `is_active` as a badge with **text + icon**, not color alone (green = Active, slate = Inactive) per the design system.
- **Backend:** none required; `_to_admin_user_response` already includes `project_memberships.project_name`. Recommend `selectinload(User.memberships).selectinload(ProjectMembership.project)` in `list_users` (`:282-289`) to avoid N+1.
- **Tests:** add a DOM-order assertion (admin → project_admin → standard) and that a project_admin row shows its project name.

### Story E — User Edit/Delete + update-user endpoint + admin-immutability (item 5)

- **Backend (`admin.py`):**
  - **New** `@router.put("/users/{user_id}")` (near `delete_user` `:323-338`) with a new `AdminUserUpdateRequest` (display_name, role, timezone, is_active, optional password reset ≥8, optional `project_id` for project_admin). `require_admin`-guarded; respond via `_to_admin_user_response`.
  - **Admin-immutability guard (decision 3):** if `target.role == ADMIN_ROLE` → **403** on both update and delete (no edit, no delete, no demotion of the platform admin). Also block self-deactivate / self-delete (lockout).
  - `AdminUserUpdateRequest.role` stays `Literal["project_admin","standard"]` — promotion to `admin` is impossible (mirrors create-side, Directive 1).
  - **Role transitions** (many-to-many): on `standard → project_admin`, require a `project_id` and create the `project_admin` membership; on `project_admin → standard`, **delete** the user's `project_admin` membership(s) (decision 5). Hash any password reset with `hash_password` (already imported `:24`); never echo it.
  - `delete_user` (`:323-338`): add the admin-immutability guard. Cascade behavior is safe for non-admin users (projects are admin-created; admin is protected).
- **Frontend (`AdminDashboard.tsx`):** add Edit + Delete buttons per user `<li>` (mirror the project-card pattern `:678-699`) and an inline edit form + handlers (mirror `startEditingProject`/`handleEditProject`/`handleDeleteProject` `:419-474`); refresh via `loadUsers()`. **Hide Edit/Delete for the `admin` row.** Use distinct `aria-label`s (`Edit user <name>` / `Delete user <name>`) to avoid collision with the project card's labels in tests.
- **Lib/types:** `lib/projects.ts` add `updateAdminUser(userId, req)` (mirror `updateAdminProject` `:46-57`); `types/project.ts` add `UpdateAdminUserRequest`.
- **Tests:** backend — valid update (200), invalid timezone (422), promote-to-admin rejected, edit/delete the platform admin rejected (403), non-admin forbidden (403), role flip membership side-effects. Frontend — Edit/Delete render + PUT/DELETE fetch-mock branches; verify the `admin` row has no Edit/Delete; keep aria-labels distinct from project buttons.

## Section 5 — Implementation Handoff

- **Change scope classification:** **Moderate** — backlog reorganization (one new epic + 5 stories) with coordinated backend + frontend work. Not Major (the RBAC design is already signed off; no replanning) and not Minor (multiple new stories + a new API endpoint).
- **Handoff recipients:**
  - **PO / Sprint planning:** DONE in this change — Epic 15 chartered in `epics.md` (Stories 15.1-15.5) and registered in `sprint-status.yaml`; former epics 15-21 renumbered +1 → 16-22. Remaining: run `bmad-create-story` to context-fill each story before dev.
  - **Developer:** implement per the story specs above. Suggested order: Story A (bug) → B → C → D → E (E last; it couples with C's role/membership rules). Run `uv run pytest` (use `--no-cov` for targeted runs), `npm run test`, `npm run typecheck`; Thuong runs `alembic upgrade head`.
- **Success criteria:**
  - Creating a project with name + (optional) description succeeds.
  - The three obsolete sentences are gone.
  - Creating a `project_admin` requires picking a project and creates the `project_admin` membership (many-to-many; no uniqueness error).
  - Users Management is sorted Role → status → timezone → display name, and project_admins show their project(s).
  - Users can be edited/deleted; the platform `admin` account cannot be edited or deleted; no self-lockout.
  - Backend + frontend test suites green; `npm run typecheck` clean.

## Appendix — Stale project-memory corrections (confirmed during analysis)

- The RBAC redesign is **signed off** (2026-06-21), not "AWAITING SIGN-OFF" as `MEMORY.md` states.
- The live DB is **already at head `c5b1e9a4d762`**; the "`alembic upgrade head` pending" follow-up is done.
