---
baseline_commit: 589e1f217f17453e3c06b2d2ffe66dea2f8f94d6
---
# Story 15.1: Fix Project Creation Regression

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a platform admin,
I want to create a project with only a name (and optional description),
so that project creation succeeds without requiring Confluence/Jira config up front.

## Acceptance Criteria

1. **Schema migrated to nullable.** Given the live database constraint on `projects.confluence_base_url`, when the schema is migrated, then the column is nullable. An Alembic migration reverses the prior `NOT NULL` (set by `f3a9c8b21d47`); the `downgrade` backfills `NULL → ''` before re-adding `NOT NULL` (mirrors `f3a9c8b21d47`).
2. **Name-only create succeeds.** Given an admin submits the Create Project form with a non-blank name and no Confluence/Jira config, when the request is processed, then the project is created (HTTP 2xx) with `confluence_base_url = NULL` and appears in the project list.
3. **Blank name rejected.** Given an admin submits a blank project name, when the request is validated, then creation is rejected with a clear "Project name is required" message (description remains optional). *(Already enforced — guard against regression.)*
4. **Conflict messages are distinguishable.** Given a duplicate project name OR another integrity violation occurs, when the error is returned, then the visible message distinguishes a genuine duplicate-name conflict ("Project name already exists") from other failures — the NOT-NULL violation no longer masquerades as "Project name already exists", and the generic "Something went wrong" banner no longer hides a real duplicate-name conflict.

## Tasks / Subtasks

- [x] **Task 1 — Alembic migration to make `confluence_base_url` nullable (AC: 1)**
  - [x] Confirm the single head: `uv run alembic heads` → must be `c5b1e9a4d762 (head)`. If it is NOT a single head, STOP and report (do not guess `down_revision`).
  - [x] Generate the migration shell: `uv run alembic revision -m "make confluence_base_url nullable"`. This auto-sets `down_revision = "c5b1e9a4d762"`. Verify that value in the generated file.
  - [x] Implement `upgrade()`: `op.alter_column("projects", "confluence_base_url", existing_type=sa.String(length=512), nullable=True)`.
  - [x] Implement `downgrade()`: `op.execute("UPDATE projects SET confluence_base_url = '' WHERE confluence_base_url IS NULL")` then `op.alter_column("projects", "confluence_base_url", existing_type=sa.String(length=512), nullable=False)`.
  - [x] Do NOT run `alembic upgrade head` — Thuong applies migrations himself (see Dev Notes).
- [x] **Task 2 — Backend: stop masquerading non-duplicate integrity errors as duplicate-name (AC: 4)**
  - [x] In `create_project` and `update_project` (`src/ai_qa/api/admin.py`), narrow the `except IntegrityError` block: only report `409 "Project name already exists"` when a same-name row genuinely exists (re-query inside the except); otherwise raise a distinct error (`409 "Could not save the project due to a data conflict."`).
  - [x] Keep the existing pre-insert name-existence check (the primary duplicate path) unchanged.
- [x] **Task 3 — Frontend: surface 409 conflicts instead of the generic banner (AC: 4)**
  - [x] In `frontend/src/lib/api.ts` add a `"conflict"` kind: `kindForStatus(409) → "conflict"`; `safeMessage("conflict")` → a sensible default ("This action conflicts with existing data. Please review and try again.").
  - [x] In `apiFetch`, when `kind` is `conflict` or `validation`, prefer the server `detail` string (if `payload?.detail` is a non-empty string) over the safe default, so "Project name already exists" reaches the user. Fall back to the safe default otherwise.
  - [x] Add `"conflict"` to the `ApiErrorKind` union.
- [x] **Task 4 — Tests (AC: 1, 2, 4)**
  - [x] Backend: add a metadata/round-trip assertion in `tests/api/test_admin_projects_api.py` that `Project.__table__.c.confluence_base_url.nullable is True` (the live-PostgreSQL-only bug is invisible to the SQLite suite — see Dev Notes). Confirm `test_create_project_name_only_succeeds` still passes.
  - [x] Frontend: update the two `AdminDashboard.test.tsx` tests that currently assert the generic "Something went wrong" message on a 409 (around lines 362 and 431) — a duplicate-name 409 now surfaces "Project name already exists". Optionally add a negative case for a non-duplicate conflict.
  - [x] Run `uv run pytest --no-cov tests/api/test_admin_projects_api.py`, `npm run test`, `npm run typecheck`.

## Dev Notes

### The bug — confirmed root cause (do not re-investigate)

Pure **model/DB schema drift**. The ORM model declares the column nullable, but the live PostgreSQL column is still `NOT NULL`:

- `src/ai_qa/db/models.py:63-65` — `confluence_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)`.
- `alembic/versions/f3a9c8b21d47_*.py:41-46` set it `NOT NULL` (Story 8.3); no later migration relaxed it. Live DB is at head `c5b1e9a4d762` (in the applied lineage).
- The post-redesign admin create-flow sends only name + description (`AdminDashboard.tsx` `handleCreateProject` → `createAdminProject({ name, description })`), so `create_project` inserts `confluence_base_url = NULL` into a `NOT NULL` column → PostgreSQL `IntegrityError`.
- `create_project` (`src/ai_qa/api/admin.py:367-369`) re-labels EVERY `IntegrityError` as `409 "Project name already exists"`. The frontend (`api.ts:62-68`) maps 409 → `"server"` → `safeMessage` → "Something went wrong. Please try again." — the banner in the bug screenshot.

**The migration (Task 1) is the only change that fixes the bug.** Tasks 2-3 satisfy AC4 (distinguishable messages) and harden the error path.

### Migration — exact body

After `uv run alembic revision -m "make confluence_base_url nullable"`, the file's header must already carry `down_revision = "c5b1e9a4d762"`. Fill the bodies:

```python
import sqlalchemy as sa
from alembic import op

def upgrade() -> None:
    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=True,
    )

def downgrade() -> None:
    op.execute("UPDATE projects SET confluence_base_url = '' WHERE confluence_base_url IS NULL")
    op.alter_column(
        "projects",
        "confluence_base_url",
        existing_type=sa.String(length=512),
        nullable=False,
    )
```

The `downgrade` mirrors `f3a9c8b21d47` (empty-string backfill before re-adding `NOT NULL`) so a roll-back never fails on the rows this story creates.

### Why the suite never caught this (important for test design)

Backend tests build the schema from `Base.metadata.create_all` on in-memory SQLite, where the model is already `nullable=True`. So `test_create_project_name_only_succeeds` (`tests/api/test_admin_projects_api.py:109-121`) **already passes** and the bug is invisible to pytest. Don't expect a failing test to reproduce it — add the `nullable is True` metadata assertion as a forward-regression guard instead, and rely on Thuong's live PostgreSQL run for end-to-end confirmation.

### Backend error-path narrowing (AC4)

`create_project` (`admin.py:341-371`) and `update_project` (`admin.py:374-405`) both do a pre-insert name check, then `except IntegrityError → 409 "Project name already exists"`. After the migration the only realistic `IntegrityError` is a genuine unique-name race, but the masquerade is still wrong for any other constraint. Re-query for the name inside the except and only claim duplicate when one truly exists:

```python
except IntegrityError as exc:
    db.rollback()
    duplicate = db.execute(
        select(Project).where(Project.name == request.name)
        # update_project also: .where(Project.id != project_id)
    ).scalar_one_or_none()
    detail = (
        "Project name already exists"
        if duplicate is not None
        else "Could not save the project due to a data conflict."
    )
    raise HTTPException(status_code=409, detail=detail) from exc
```

### Frontend 409 surfacing (AC4)

`api.ts` currently collapses everything except 401/403/404/422/400 into `"server"` → "Something went wrong." (`kindForStatus:62-68`, `safeMessage:45-60`). A genuine duplicate-name 409 is therefore invisible. Add a `"conflict"` kind and surface the server `detail` for `conflict`/`validation`:

- `ApiErrorKind` union (`api.ts:1-7`): add `"conflict"`.
- `kindForStatus`: `if (status === 409) return "conflict";` (before the `return "server"` default).
- `safeMessage`: `case "conflict": return "This action conflicts with existing data. Please review and try again.";`
- In `apiFetch` where `ApiError` is thrown (`api.ts:127-132`): if `kind === "conflict" || kind === "validation"`, and `payload` is an object with a non-empty string `detail`, use that `detail` as the message (still allow `overrideMessage` to win). This keeps the change scoped to 409/422 — no global detail leakage. Admin 409 details are display-safe ("Project name already exists", "User already exists", etc.).

This is a shared helper — grep for other call sites that assert on 409 generic copy before finishing (the two `AdminDashboard.test.tsx` cases are the known ones).

### Constraints / conventions

- `uv` only; `uv run alembic …`. NEVER `python3` (Windows). Python 3.14.
- Full-stack sync: the `api.ts` kind change is TS-visible; run `npm run typecheck` (Vite skips strict errors).
- Markdown/lint: not applicable (no .md authored in code).

### Project Structure Notes

- Migration lands in `alembic/versions/` (single head `c5b1e9a4d762` → one new revision; no merge needed).
- No ORM model change (model is already correct). No request-schema change (`name` already required, links already optional — `ProjectCreateRequest`, `admin.py:94-170`).
- Frontend change is confined to the shared `api.ts` error helper + the dashboard tests.

### References

- [Sprint change proposal — Story A](../planning-artifacts/sprint-change-proposal-2026-06-21.md) (bug root cause; migration spec; optional hardening)
- [Investigation — Findings 1-4 + Deduction 1](investigations/admin-dashboard-project-user-mgmt-investigation.md)
- [Epic 15 / Story 15.1](../planning-artifacts/epics.md) (lines 1576-1598)
- Code: `src/ai_qa/api/admin.py:341-405` (`create_project`/`update_project`), `src/ai_qa/db/models.py:63-65`, `alembic/versions/f3a9c8b21d47_*.py:39-58`, `frontend/src/lib/api.ts:45-68,127-132`
- Tests: `tests/api/test_admin_projects_api.py:109-121`, `frontend/src/components/admin/AdminDashboard.test.tsx` (~362, ~431)

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, bmad-dev-story)

### Debug Log References

- `uv run alembic heads` → single head `c5b1e9a4d762` (confirmed before generating migration).
- `uv run pytest --no-cov tests/api/test_admin_projects_api.py` → 12 passed (incl. new `test_confluence_base_url_column_is_nullable`).
- `npm run typecheck` → clean; `npm run test src/components/admin/AdminDashboard.test.tsx` → 13 passed; `npm run lint` → clean.

### Completion Notes List

- **AC1** — Added migration `a3d0b6703a7d` (down_revision `c5b1e9a4d762`) relaxing `projects.confluence_base_url` to `nullable=True`; `downgrade` backfills `NULL → ''` before re-adding `NOT NULL` (mirrors `f3a9c8b21d47`). **Not applied** — Thuong runs `alembic upgrade head` himself.
- **AC4** — `create_project`/`update_project` now re-query for the name inside `except IntegrityError`; only a genuine same-name row yields `409 "Project name already exists"`, otherwise `409 "Could not save the project due to a data conflict."` (no more NOT-NULL masquerading as a name clash). `update_project` excludes its own row from the re-check.
- **AC4 (FE)** — `api.ts` gains a `"conflict"` kind (`kindForStatus(409)`), a safe default, and surfaces the display-safe server `detail` for `conflict`/`validation` 409/422 responses (overrideMessage still wins). The two `AdminDashboard.test.tsx` 409 tests now assert the surfaced detail; the now-unused `ApiError`/`getSafeApiErrorMessage` import was removed.
- **AC2/AC3** — already enforced (name-only create + blank-name guard); the metadata regression test guards AC1 because the live-PostgreSQL bug is invisible to the SQLite suite.

### File List

- `alembic/versions/a3d0b6703a7d_make_confluence_base_url_nullable.py` (new)
- `src/ai_qa/api/admin.py` (modified — `create_project` / `update_project` IntegrityError narrowing)
- `frontend/src/lib/api.ts` (modified — `"conflict"` kind + server-detail surfacing)
- `tests/api/test_admin_projects_api.py` (modified — `test_confluence_base_url_column_is_nullable`)
- `frontend/src/components/admin/AdminDashboard.test.tsx` (modified — two 409 tests now assert the surfaced detail)

### Review Findings

#### Patch

- [x] `[Review][Patch]` No backend test asserting the 409 `detail` strings for duplicate vs other conflict [`tests/api/test_admin_projects_api.py`] — AC4 requires distinguishable messages; current tests only assert `status_code == 409`, not `response.json()["detail"]` for either path.

#### Deferred

- [x] `[Review][Defer]` Downgrade fills `confluence_base_url = ''` (empty string) for NULL rows before re-adding NOT NULL [`alembic/versions/a3d0b6703a7d_make_confluence_base_url_nullable.py`] — deferred, by design (mirrors f3a9c8b21d47 pattern); `normalize_links` converts `""` → `None` in admin layer; downgrade is rarely exercised.

## Change Log

- 2026-06-21 — Story 15.1 implemented: migration `a3d0b6703a7d` (confluence_base_url nullable), backend 409 conflict narrowing, FE `"conflict"` error kind + server-detail surfacing, tests updated. Status → review. (claude-opus-4-8)
