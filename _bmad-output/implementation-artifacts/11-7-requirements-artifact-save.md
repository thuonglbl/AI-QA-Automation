---
baseline_commit: 8cf53eb
---

# Story 11.7: Requirements Artifact Save

Status: done

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a project member,
I want approved extracted requirements saved as project artifacts with full provenance metadata,
so that Mary and other project members can use them as shared source inputs through project-scoped queries.

## Acceptance Criteria

### AC1 — Approved item is saved under `projects/{project_id}/requirements/` with full metadata

**Given** an extracted item is approved
**When** Bob saves it
**Then** the artifact service stores it under `projects/{project_id}/requirements/`
**And** artifact metadata includes **source type**, **source URL/reference**, **creator**, **updater**, **originating thread**, **originating agent run**, **timestamp**, **warnings**, and **artifact kind**.

### AC2 — Saved requirements are reachable through project-scoped artifact queries (no workspace paths)

**Given** saved requirement artifacts exist
**When** Mary or a project member requests requirements for the selected project
**Then** the artifacts are available through project-scoped artifact queries
**And** direct workspace path reads are not required.

### AC3 — Save failure does not corrupt partial output and yields a clear recovery message

**Given** saving fails
**When** Bob reports the failure
**Then** partial output is not corrupted
**And** the user receives a clear retry or recovery message
**And** the item stays reviewable so the user can re-approve (it is **not** marked resolved and Bob does **not** transition to DONE).

---

## ⚠️ CRITICAL: This story makes the on-approve save AUTHORITATIVE and FULLY PROVENANCED — it adds 3 first-class metadata columns and hardens the save against failure

By the time control reaches this story, the approve path already saves an approved requirement. After **11.6** merges, `BobAgent.handle_approve`'s markdown-review branch saves `requirement.md` (kind `requirements`) + a `requirement.metadata.json` side-car, resolves the page id, and transitions to DONE when every page is resolved. After **11.5** merges, that side-car already carries `source_url`, `extracted_at`, `source_type`, and the quality-warning acknowledgement fields. **None of these are merged on disk yet** (11.1–11.6 are all `ready-for-dev`); this story is written for the post-11.6 shape and degrades gracefully if a dependency is unmerged (see **Build-order reality**).

Story 11.7 does exactly four things and **nothing else**:

1. **Promote provenance to first-class, queryable columns (AC1).** The native `Artifact` row already records **creator** (`created_by_user_id`), **updater** (`updated_by_user_id`), **originating thread** (`thread_id`), **originating agent run** (`agent_run_id`), **timestamp** (`created_at`/`updated_at`), and **artifact kind** (`kind`) — 6 of the 9 AC1 fields. This story adds the **3 missing** fields as nullable columns on `artifacts`: `source_type`, `source_url`, `warnings`. (Decided by Thuong, 2026-06-11: **first-class columns + migration**, not a side-car-only record — so Mary/12.x can query provenance without parsing JSON.)
2. **Make the on-approve save authoritative + provenanced (AC1).** A dedicated `PipelineArtifactAdapter.save_requirement(...)` writes the approved markdown under `kind="requirements"` (which already maps to `projects/{project_id}/requirements/…` via `build_artifact_key`) **and** stamps the 3 provenance columns from the page. The 11.5 side-car `requirement.metadata.json` (acknowledgement record) is **kept** for backward-compat / human-readable audit.
3. **Harden the save (AC3).** Wrap the save in `try/except` inside `handle_approve`. On failure: the `ArtifactService` per-artifact write is already atomic (DB rollback + storage delete on exception → **no partial single-artifact corruption**); Bob sends a UX-DR12 three-part retry message, and **does not** add the page to `_resolved_page_ids` and **does not** transition to DONE — the item stays reviewable for re-approval.
4. **Surface the new fields through the existing project-scoped query surface (AC2).** Add `source_type`/`source_url`/`warnings` to `ArtifactResponse`, the detail response, and the artifact-tree entry (+ the TS `Artifact` interface — full-stack sync). The query paths (`GET /projects/{id}/artifacts`, `/tree`, `/{artifact_id}`, `load_requirement_markdown()`) already require **no** workspace-path reads; this story keeps that true and exposes provenance on those responses.

### Confirmed scope decisions (Thuong, 2026-06-11) — implement exactly these

- **Provenance = first-class columns + Alembic migration.** Add `source_type` (`String(50)`), `source_url` (`Text`), and `warnings` (`JSON`) to the `artifacts` table. *(Alternative rejected: side-car-JSON-only, no migration — cheaper but not directly queryable.)* These are **generic** artifact columns (nullable), so future test-case/script provenance can reuse them; they are populated for requirements in this story.
- **Keep the pre-approval extraction-time save as a draft cache.** The existing `_extract_descendants` call `adapter.save_requirement_page(page.page_id, requirement_md)` ([bob.py:459](src/ai_qa/agents/bob.py)) **stays**. It writes a draft requirement (name `{page_id}.md`, **no** provenance) before review. The **on-approve** save (name `{page_id}/requirement.md`, **with** provenance columns set) is the authoritative copy. *(Alternative rejected: remove the premature save so requirements persist only on approval.)* Consequence to manage: two `kind="requirements"` artifacts can exist per page — see **The draft-vs-approved discriminator (AC2)**.

### In scope

- **DB:** Alembic migration adding `source_type`/`source_url`/`warnings` to `artifacts`; matching `Mapped[...]` columns on the `Artifact` model.
- **Service:** `ArtifactService.save_artifact(...)` accepts optional `source_type`/`source_url`/`warnings` and persists them; `list_artifact_tree` carries them in its entry dict.
- **Adapter:** `PipelineArtifactAdapter.save_requirement(...)` (provenance-aware requirement save).
- **Agent:** `BobAgent.handle_approve` approved branch uses `save_requirement(...)`, builds provenance from the page, keeps the 11.5 acknowledgement side-car, and wraps the save in `try/except` (AC3) so a failure leaves the page un-resolved with a UX-DR12 retry message.
- **API + types:** `ArtifactResponse` / `ArtifactDetailResponse` / `ArtifactTreeEntry` (+ `ArtifactTreeEntryDict`) expose the 3 fields; frontend `Artifact` TS interface gains the 3 optional fields.
- **Tests:** service persistence, adapter pass-through, on-approve save provenance, AC3 failure path, AC2 query reachability, API response shape, frontend typecheck.

### Out of scope (do NOT build)

- **No new requirement-EXTRACTION behavior.** Connect/extract/parse/Jira/quality-detection/review UX are 11.1–11.6. This story only changes how the **approved** item is persisted and queried.
- **No Mary / test-case consumption logic.** AC2's "Mary requests requirements" is satisfied by the **query reachability** (artifacts are listable/readable by project + kind with provenance, no workspace path). The actual input-selection logic is **Story 12.1** (`12-1-test-case-generation-input-selection`). Do not build Mary's loader here — just prove the query surface returns approved requirements with provenance.
- **No removal of the 11.5 acknowledgement side-car.** Keep `requirement.metadata.json`. The new `warnings` column and the side-car's `acknowledged_quality_issues` carry the same data by design (column = queryable; side-car = audit record).
- **No removal of the pre-approval draft save** (Thuong kept it — see scope decisions).
- **No change to secret resolution, MCP/connect, the confirm-parent flow, `_extract_descendants` extraction logic, or the single-MCP-client / disconnect invariants.** The save path opens no MCP client.
- **No frontend rendering of provenance beyond type sync.** A visible "source" badge/column in the artifact browser is a nice-to-have deferred to a later UX story; this story only adds the TS fields (full-stack sync) so types resolve and the data is available on the payload.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status / action |
| --- | --- | --- |
| `Artifact` model with native provenance (`created_by_user_id`, `updated_by_user_id`, `thread_id`, `agent_run_id`, `kind`, `created_at`/`updated_at` via `TimestampMixin`) | [src/ai_qa/db/models.py:127-157](src/ai_qa/db/models.py) | ✅ done — **add 3 columns: `source_type`, `source_url`, `warnings`** |
| `kind="requirements"` → storage key `projects/{project_id}/requirements/{artifact_id}/v{version}/{name}` | [src/ai_qa/artifacts/storage.py:28-38](src/ai_qa/artifacts/storage.py) | ✅ done — **AC1 path is already correct; no storage change** |
| `ArtifactService.save_artifact(*, project_id, owner_user_id, kind, name, content, agent_run_id, thread_id)` — atomic write (rollback + storage delete on exception) | [src/ai_qa/artifacts/service.py:71-131](src/ai_qa/artifacts/service.py) | ✅ done — **add optional `source_type`/`source_url`/`warnings`; set on the `Artifact`** |
| `ArtifactService.list_artifacts(project_id, kind=...)` / `get_artifact(...)` / `read_current_content(...)` — project-scoped queries, **no** workspace path | [src/ai_qa/artifacts/service.py:185-229](src/ai_qa/artifacts/service.py) | ✅ done — AC2 query surface; **no change needed beyond field exposure** |
| `ArtifactService.list_artifact_tree(...)` + `ArtifactTreeEntryDict` | [src/ai_qa/artifacts/service.py:36-52,239-329](src/ai_qa/artifacts/service.py) | ✅ done — **add the 3 fields to the TypedDict + populate them in the entry dict** |
| `PipelineArtifactAdapter.save_requirement_page` / `save_metadata` / `_save_text` (sync; schedules a fire-and-forget change event) | [src/ai_qa/pipelines/artifact_adapter.py:42-46,69-75,109-120](src/ai_qa/pipelines/artifact_adapter.py) | ✅ done — **add `save_requirement(...)`; reuse `save_metadata` for the side-car; keep `save_requirement_page` for the draft cache** |
| `PipelineContext` (`user_id`, `user_email`, `project_id`, `thread_id`, `artifact_service`, `agent_run_id`) | [src/ai_qa/pipelines/context.py:11-19](src/ai_qa/pipelines/context.py) | ✅ done — provenance source for `created_by`/`thread`/`agent_run` (the adapter already threads these into `save_artifact`) |
| `BobAgent.handle_approve` markdown-review branch (saves on approve) | [src/ai_qa/agents/bob.py:560-599](src/ai_qa/agents/bob.py) **(11.6 reshapes this to the resolved-id model)** | ✅ exists — **swap the save for `save_requirement(...)`; add `try/except` (AC3)** |
| `BobAgent` page dict shape (`page_id`, `page_title`, `source_url`, `raw_html`, `requirement_md`; + `parsed_markdown`/`warnings` from 11.3, `source_type` from 11.4, `quality_issues` from 11.5) | [src/ai_qa/agents/bob.py:461-469](src/ai_qa/agents/bob.py) | ✅ done — **read provenance defensively (`page.get(...) or default`)** |
| `_format_error_message(errors)` — UX-DR12 three-part error | [src/ai_qa/agents/base.py:400](src/ai_qa/agents/base.py) | ✅ done — **reuse for the AC3 retry message** |
| `ArtifactResponse` / `ArtifactDetailResponse` / `ArtifactTreeEntry` (Pydantic, `from_attributes=True`) | [src/ai_qa/api/artifacts.py:61-116,172-191](src/ai_qa/api/artifacts.py) | ✅ done — **add the 3 optional fields (`= None`) + populate in `_artifact_detail_response` + the tree-entry construction** |
| Frontend `Artifact` TS interface | [frontend/src/components/conversations/ProjectSidebar.tsx:39-53](frontend/src/components/conversations/ProjectSidebar.tsx) | ✅ done — **add 3 optional fields (full-stack sync)** |
| WS approve dispatch (`data = message.get("data", {})` → `await agent.handle_approve(data)`); generic error catch keeps the connection open | [src/ai_qa/api/websocket.py:316-331](src/ai_qa/api/websocket.py) | ✅ done — **no change** (Bob's own AC3 catch produces the user-facing retry message before the generic catch would) |
| `QualityIssue` model (`category`, `location`, `message`, `impact`) — 11.5 | [src/ai_qa/pipelines/models.py](src/ai_qa/pipelines/models.py) | ✅ (after 11.5) — the `warnings` column stores these dicts |

---

## Tasks / Subtasks

- [x] **Task 1 — DB: add provenance columns to `artifacts` (AC1)**
  - [x] 1.1 In [src/ai_qa/db/models.py](src/ai_qa/db/models.py), add three nullable columns to the `Artifact` class (after `current_version`, before the relationships at [models.py:151-153](src/ai_qa/db/models.py)). `JSON` is already imported at [models.py:9-19](src/ai_qa/db/models.py):

    ```python
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    ```

    `Any` is already imported ([models.py:6](src/ai_qa/db/models.py)). Generic + nullable so non-requirement artifacts (and the pre-approval draft) simply leave them `NULL`.
  - [x] 1.2 Create an Alembic migration. `down_revision = "604f28c24393"` (current head — verify with `uv run alembic heads`). `upgrade()` adds the 3 columns to `artifacts`; `downgrade()` drops them. Use `sa.JSON()` for `warnings` (cross-dialect: PostgreSQL prod + SQLite tests). Match the existing migration style in [alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py](alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py). Example body:

    ```python
    def upgrade() -> None:
        op.add_column("artifacts", sa.Column("source_type", sa.String(length=50), nullable=True))
        op.add_column("artifacts", sa.Column("source_url", sa.Text(), nullable=True))
        op.add_column("artifacts", sa.Column("warnings", sa.JSON(), nullable=True))

    def downgrade() -> None:
        op.drop_column("artifacts", "warnings")
        op.drop_column("artifacts", "source_url")
        op.drop_column("artifacts", "source_type")
    ```
  - [x] 1.3 `uv run alembic upgrade head` must apply cleanly; `uv run alembic heads` must show the new single head.

- [x] **Task 2 — Service: persist + expose provenance (AC1/AC2)**
  - [x] 2.1 In [src/ai_qa/artifacts/service.py](src/ai_qa/artifacts/service.py), extend `save_artifact(...)` ([service.py:71-131](src/ai_qa/artifacts/service.py)) with three optional keyword params **after** the existing ones (keeps every current call site valid):

    ```python
    source_type: str | None = None,
    source_url: str | None = None,
    warnings: list[dict[str, Any]] | None = None,
    ```

    Set them on the `Artifact(...)` constructor ([service.py:90-100](src/ai_qa/artifacts/service.py)): `source_type=source_type, source_url=source_url, warnings=warnings`. Add `from typing import Any` (the module imports `TypedDict` from `typing` already — extend that import). No change to the atomic write/rollback logic.
  - [x] 2.2 Add the 3 fields to `ArtifactTreeEntryDict` ([service.py:36-52](src/ai_qa/artifacts/service.py)): `source_type: str | None`, `source_url: str | None`, `warnings: list[dict[str, Any]] | None`. Populate them in the entry dict built in `list_artifact_tree` ([service.py:288-310](src/ai_qa/artifacts/service.py)): `"source_type": artifact.source_type, "source_url": artifact.source_url, "warnings": artifact.warnings`.
  - [x] 2.3 Do **not** change `create_version(...)` — edits don't alter provenance (an edited requirement keeps its original source). `updated_by_user_id` already tracks the editor.

- [x] **Task 3 — Adapter: provenance-aware `save_requirement` (AC1)**
  - [x] 3.1 In [src/ai_qa/pipelines/artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py), add a dedicated method (next to `save_requirement_page`, [artifact_adapter.py:42-46](src/ai_qa/pipelines/artifact_adapter.py)):

    ```python
    def save_requirement(
        self,
        *,
        page_id: str,
        markdown: str,
        source_type: str | None = None,
        source_url: str | None = None,
        warnings: list[dict[str, Any]] | None = None,
    ) -> Artifact:
        """Persist an APPROVED requirement under projects/{id}/requirements/ with provenance."""
        name = f"{page_id}/requirement.md"
        artifact = self.service.save_artifact(
            project_id=self.project_id,
            owner_user_id=self.context.user_id,
            agent_run_id=self.context.agent_run_id,
            thread_id=self.context.thread_id,
            kind="requirements",
            name=name,
            content=markdown,
            source_type=source_type,
            source_url=source_url,
            warnings=warnings,
        )
        self._schedule_change_event(artifact.id, "created")
        return artifact
    ```

    This mirrors `_save_text` but threads provenance through and keeps the change-event broadcast (so 10.6/10.7 realtime refresh fires for approved requirements). Keep `save_requirement_page` unchanged (still used by the pre-approval draft cache and as a generic helper).

- [x] **Task 4 — Agent: authoritative provenanced save + AC3 hardening (AC1/AC3)**
  - [x] 4.1 In `BobAgent.handle_approve`'s **approved** action branch (the 11.6 resolved-id model; on the current baseline it is [bob.py:561-584](src/ai_qa/agents/bob.py)), replace the two loose `adapter.save_requirement_page(...)` + `adapter.save_metadata(...)` calls with a provenance build + the new `save_requirement(...)`, wrapped in `try/except` (AC3). Build provenance defensively from the page:

    ```python
    if action == "approved":
        updated_markdown = data.get("markdown")
        if updated_markdown:
            page["requirement_md"] = updated_markdown
            if self.project_context is None:
                raise ValueError("BobAgent requires an active project context.")
            adapter = PipelineArtifactAdapter(self.project_context)

            source_type = str(page.get("source_type") or "confluence")
            source_url = str(page.get("source_url") or "")
            warnings = page.get("quality_issues") or page.get("warnings") or []

            try:
                adapter.save_requirement(
                    page_id=page["page_id"],
                    markdown=updated_markdown,
                    source_type=source_type,
                    source_url=source_url,
                    warnings=warnings,
                )
                # Keep the 11.5 acknowledgement side-car (audit record).
                adapter.save_metadata(
                    f"{page['page_id']}/requirement.metadata.json",
                    {
                        "source_url": source_url,
                        "source_type": source_type,
                        "extracted_at": datetime.now(UTC).isoformat(),
                        "quality_warnings_acknowledged": bool(warnings),
                        "acknowledged_quality_issues": warnings,
                        "acknowledged_at": datetime.now(UTC).isoformat(),
                        "artifact_kind": "requirements",
                    },
                )
                self.output_files_saved += 1
            except Exception as exc:
                # AC3: no partial corruption (save_artifact is atomic per-artifact),
                # clear recovery message, and the page stays reviewable for retry.
                logger.error("Bob failed to save requirement: %s", exc, exc_info=True)
                await self.send_message(
                    content=self._format_error_message(
                        [
                            "Failed to save the approved requirement to the project artifact store.",
                            f"Reason: {type(exc).__name__}.",
                            "Please approve again to retry. No partial requirement was saved.",
                        ]
                    ),
                    message_type="error",
                )
                return  # do NOT resolve this page id; do NOT transition to DONE
    if page_id:
        self._resolved_page_ids.add(page_id)
    ```

    > Snippet-fidelity note (see [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md)): this **replaces only the save body** inside 11.6's `if action == "approved":` block. **Preserve** the surrounding 11.6 structure verbatim — the `page = next(...)` lookup, `self.current_page_index = self.pages.index(page)`, the `not_requirement` handling, the `self._resolved_page_ids.add(page_id)` for **either** action, and the DONE-when-all-resolved tail. The `return` on save failure is the **only** new early-exit — it must land **before** `self._resolved_page_ids.add(page_id)` so a failed save does not resolve the page. If 11.6 is **not** merged (baseline counter model), apply the same `try/except` + provenance build around the [bob.py:567-584](src/ai_qa/agents/bob.py) save, and on failure `return` **before** the `self.current_page_index += 1` so the page is re-presentable.
  - [x] 4.2 Confirm `datetime`, `UTC` are imported ([bob.py:2](src/ai_qa/agents/bob.py)) and `PipelineArtifactAdapter` is imported ([bob.py:11](src/ai_qa/agents/bob.py)) — both already present. No new imports.
  - [x] 4.3 Leave the **pre-approval draft save** in `_extract_descendants` ([bob.py:459](src/ai_qa/agents/bob.py)) unchanged (Thuong's decision — draft cache). Do **not** add provenance to it (drafts are unapproved → provenance columns stay `NULL`, which is the discriminator — see Dev Notes).

- [x] **Task 5 — API + frontend: expose provenance on the query surface (AC2)**
  - [x] 5.1 In [src/ai_qa/api/artifacts.py](src/ai_qa/api/artifacts.py), add to `ArtifactResponse` ([artifacts.py:61-76](src/ai_qa/api/artifacts.py)) — keeps the "frozen base" intent because these are additive optional fields with defaults (do not break the 10-7/10-8 assignability note at [artifacts.py:79-86](src/ai_qa/api/artifacts.py)):

    ```python
    source_type: str | None = None
    source_url: str | None = None
    warnings: list[dict[str, Any]] | None = None
    ```

    Add `from typing import Any` (module imports `Literal` from `typing` — extend it). `list_artifacts`/`create_artifact` use `model_validate(artifact)` (`from_attributes=True`) so they auto-populate.
  - [x] 5.2 Update the **manual** constructor `_artifact_detail_response` ([artifacts.py:176-191](src/ai_qa/api/artifacts.py)) to pass `source_type=artifact.source_type, source_url=artifact.source_url, warnings=artifact.warnings`.
  - [x] 5.3 Update the **manual** `ArtifactTreeEntry(...)` construction in `get_artifact_tree` ([artifacts.py:240-254](src/ai_qa/api/artifacts.py)) to pass `source_type=e["source_type"], source_url=e["source_url"], warnings=e["warnings"]` (keys added in Task 2.2).
  - [x] 5.4 In [frontend/src/components/conversations/ProjectSidebar.tsx](frontend/src/components/conversations/ProjectSidebar.tsx) `Artifact` interface ([ProjectSidebar.tsx:39-53](frontend/src/components/conversations/ProjectSidebar.tsx)), add (full-stack sync rule):

    ```ts
    source_type?: string | null;
    source_url?: string | null;
    warnings?: Array<Record<string, unknown>> | null;
    ```

    No rendering change required; this keeps `npm run typecheck` clean and makes provenance available to any consumer of the artifact tree.

- [x] **Task 6 — Backend tests: service + adapter + agent + AC3 + AC2 (AC1/AC2/AC3)**
  - [x] 6.1 **Service persistence** — extend the artifact-service tests ([tests/test_artifacts/](tests/test_artifacts/) — match the existing `test_artifact_service*.py` style with a real in-memory SQLite `db_session` + project/user fixtures). New test: `save_artifact(..., kind="requirements", name="p1/requirement.md", content="md", source_type="confluence", source_url="https://x", warnings=[{"category":"vague_language","message":"m"}])` → reload the `Artifact`; assert `source_type`, `source_url`, `warnings` round-trip; assert `storage_path` starts with `projects/{project_id}/requirements/` (AC1 path). A second test with the params omitted → all three are `None` (back-compat).
  - [x] 6.2 **Adapter pass-through** — in the adapter tests ([tests/pipelines/](tests/pipelines/) or wherever `PipelineArtifactAdapter` is tested), patch/inspect the `ArtifactService.save_artifact` call: `adapter.save_requirement(page_id="p1", markdown="md", source_type="jira", source_url="PROJ-1", warnings=[...])` calls `save_artifact` with `kind="requirements"`, `name="p1/requirement.md"`, and the provenance kwargs forwarded.
  - [x] 6.3 **On-approve save provenance (AC1)** — extend [tests/test_agents/test_bob.py](tests/test_agents/test_bob.py) (reuse `bob_agent` + `mock_project_context`). Set `phase="review_markdown"`, a one-page `self.pages` with `source_type`/`source_url`/`quality_issues`. Patch `ai_qa.agents.bob.PipelineArtifactAdapter` (class), `transition_to`, `send_message`. Call `handle_approve({"action":"approved","page_id":"p1","markdown":"edited"})`. Assert the adapter instance's `save_requirement` was called with `page_id="p1"`, `markdown="edited"`, `source_type="..."`, `source_url="..."`, `warnings=<the page's quality_issues>`; and `output_files_saved == 1`; and the page resolved/advanced per the 11.6 model.
  - [x] 6.4 **AC3 — save failure keeps the page reviewable.** Same setup, but `mock_adapter.return_value.save_requirement.side_effect = RuntimeError("storage down")`. Call `handle_approve(...)`. Assert: a `send_message` with `message_type="error"` fired (the UX-DR12 retry text), `page_id` is **not** in `bob_agent._resolved_page_ids` (or, on the baseline counter model, `current_page_index` did **not** advance), `transition_to(AgentState.DONE)` was **not** called, and `output_files_saved == 0`. (No assertion on partial files — the service's atomic write owns that; assert the agent-level "stays reviewable" contract.)
  - [x] 6.5 **AC2 — query reachability (no workspace path).** A backend test using the real `ArtifactService` + in-memory SQLite: save an approved requirement via `adapter.save_requirement(...)`, then `service.list_artifacts(project_id=..., kind="requirements")` returns it, `service.read_current_content(artifact)` returns the markdown bytes, and `artifact.source_type`/`source_url`/`warnings` are populated. Assert the read used the storage backend (no filesystem `workspace/...` path is constructed by the test). This is the seam Mary/12.1 will consume.
  - [x] 6.6 **Regression (must stay green):** the single-MCP-client test, the disconnect tests, the confirm-parent test, and 11.6's reject/`process(feedback)` tests — the save path opens **no** MCP client and calls **no** LLM, so `mock_mcp_client_class.call_count` assertions are unaffected. The pre-approval draft save (`save_requirement_page`) is unchanged.

- [x] **Task 7 — API tests: response shape carries provenance (AC2)**
  - [x] 7.1 Extend the artifact API tests ([tests/api/test_artifacts_api*.py](tests/api/) — match the canonical RBAC scaffold from `tests/api/test_admin_rbac_api.py`). Create a requirement artifact with `source_type`/`source_url`/`warnings` (via the service directly, or POST then patch the row), then:
    - `GET /projects/{id}/artifacts?kind=requirements` → each item has `source_type`, `source_url`, `warnings`.
    - `GET /projects/{id}/artifacts/{artifact_id}` (detail) → carries the 3 fields.
    - `GET /projects/{id}/artifacts/tree` → the `requirements` folder entry carries the 3 fields.
  - [x] 7.2 **Leak-canary / response-schema regression:** confirm no test that asserts an **exact** field set on `ArtifactResponse` breaks (the new fields are optional with defaults). The secret-leak canary tests must stay green — `source_url` is non-secret (a Confluence/Jira URL); never put tokens/credentials in any provenance field.

- [x] **Task 8 — Frontend gate (AC2)**
  - [x] 8.1 `npm run typecheck` clean (new optional `Artifact` fields resolve everywhere the type is consumed — `ArtifactTreeFolder.entries`, `ProjectSidebar`, `lib/artifacts.ts`). `npm run lint` clean. `npm run test` green (no behavior change; existing artifact-tree tests must still pass since the fields are optional).

- [x] **Task 9 — Full gate + DoD**
  - [x] 9.1 `uv run alembic upgrade head` applies the new migration cleanly; `uv run alembic heads` shows one head; **and** a downgrade/upgrade round-trip works (`uv run alembic downgrade -1 && uv run alembic upgrade head`).
  - [x] 9.2 `uv run ruff check .` and `uv run mypy src` clean. (`warnings` column typed `list[dict[str, Any]] | None`; narrow `Optional` page reads with `or default`/`str(...)`; the `Artifact(...)` kwargs and Pydantic optionals are fully typed — no `# type: ignore`.)
  - [x] 9.3 `uv run pytest tests/test_agents/test_bob.py tests/test_artifacts tests/pipelines tests/api -q` (or the affected subset) green — new + existing.
  - [x] 9.4 `npm run lint` + `npm run typecheck` + `npm run test` green in `/frontend`.
  - [x] 9.5 Update the Dev Agent Record (file list, commands run, outputs).

---

## Dev Notes

### Build-order reality — what's on disk vs. what this story assumes

On the `8cf53eb` baseline, **none of 11.1–11.6 are merged** (all `ready-for-dev`). The current [bob.py](src/ai_qa/agents/bob.py) `handle_approve` still uses the positional-counter model ([bob.py:586-596](src/ai_qa/agents/bob.py)) and the page dict has no `source_type`/`quality_issues`. The natural build order is **11.1 → 11.2 → 11.3 → 11.4 → 11.5 → 11.6 → 11.7**, so by the time 11.7 is implemented:

- 11.6 will have reshaped `handle_approve` to the **resolved-id model** (`_resolved_page_ids` set; both `approved` and `not_requirement` actions; DONE when all resolved). Task 4.1 modifies **that** branch.
- 11.5 will have added `quality_issues` per page + the acknowledgement side-car. Task 4.1 reads `page.get("quality_issues")` for the `warnings` column and keeps the side-car.
- 11.4 will have added Jira items with `source_type="jira"`, `source_url=<ticket ref>`. Task 4.1 reads `page.get("source_type")`.

**Defensive defaults** make Task 4.1 correct even if a dependency is unmerged: `source_type` defaults to `"confluence"`, `source_url` to `""`, `warnings` to `[]`. If 11.6 is unmerged, apply the same provenance build + `try/except` around the baseline counter save and `return` before `current_page_index += 1` on failure (see the Task 4.1 snippet-fidelity note). Treat any divergence (e.g. 11.6's exact variable names) as a flag-during-dev item, not a guess — see [create-story-snippet-hazards](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/create-story-snippet-hazards.md) and [verify-subagent-claims](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/verify-subagent-claims.md).

### AC1 — the 9 metadata fields, and where each lives

| AC1 field | Where it is stored | Source |
| --- | --- | --- |
| creator | `artifacts.created_by_user_id` (native) | `context.user_id` via `save_artifact(owner_user_id=...)` |
| updater | `artifacts.updated_by_user_id` (native) | same; edits update it via `create_version` |
| originating thread | `artifacts.thread_id` (native) | `context.thread_id` |
| originating agent run | `artifacts.agent_run_id` (native) | `context.agent_run_id` |
| timestamp | `artifacts.created_at` / `updated_at` (native, `TimestampMixin`) | DB default |
| artifact kind | `artifacts.kind` (native) | `"requirements"` |
| **source type** | **`artifacts.source_type` (NEW column)** | `page.source_type` (`confluence`/`jira`) |
| **source URL/reference** | **`artifacts.source_url` (NEW column)** | `page.source_url` |
| **warnings** | **`artifacts.warnings` (NEW column, JSON)** | `page.quality_issues` (11.5) ⟶ `[{category,location,message,impact}, …]` |

So this story adds exactly the **3 columns** the native model lacks. The 11.5 side-car `requirement.metadata.json` is kept as a human-readable acknowledgement audit; the `warnings` column and the side-car's `acknowledged_quality_issues` intentionally hold the same data (column = machine-queryable; side-car = audit trail). Architecture confirms the path + native metadata model ([architecture.md:280,350-360](_bmad-output/planning-artifacts/architecture.md)).

### AC2 — query reachability, and the draft-vs-approved discriminator

AC2 requires saved requirements to be reachable through **project-scoped artifact queries** with **no workspace path**. That surface already exists and needs no new endpoint:

- Backend: `ArtifactService.list_artifacts(project_id, kind="requirements")` + `read_current_content(artifact)`; the adapter's `load_requirement_markdown()` ([artifact_adapter.py:48-50](src/ai_qa/pipelines/artifact_adapter.py)) wraps it. Storage reads go through `ArtifactStorage` (Local/S3) keyed by `storage_path` — never a raw `workspace/` path.
- API: `GET /projects/{id}/artifacts?kind=requirements`, `/tree`, `/{artifact_id}`, `/{artifact_id}/content`.

**The draft-vs-approved discriminator (consequence of keeping the pre-approval cache):** because Thuong kept the pre-approval `save_requirement_page(page.page_id, ...)` ([bob.py:459](src/ai_qa/agents/bob.py)), a project can hold **two** `kind="requirements"` artifacts per page:

| | Pre-approval draft | Approved (this story) |
| --- | --- | --- |
| Name | `{page_id}.md` | `{page_id}/requirement.md` |
| `source_type`/`source_url`/`warnings` | `NULL` | populated |
| When written | during extraction | on user approval |

**The discriminator is provenance presence:** approved requirements have `source_type`/`source_url` set; drafts have them `NULL`. Document this so **Story 12.1** (Mary's input selection) filters to approved requirements (`source_type IS NOT NULL`, or the `{page_id}/requirement.md` name pattern). This is a **Saved Question** (below) flagged for 12.1 — do not build Mary's filter here, but the data model makes it trivially expressible.

### AC3 — what "no partial corruption" means here, and the layered error handling

There are **two** error layers; this story relies on both:

1. **`ArtifactService.save_artifact` is atomic per artifact** ([service.py:104-128](src/ai_qa/artifacts/service.py)): it `flush`es the row, writes storage, appends the version, then `commit`s; on **any** exception it `rollback`s the DB and `delete`s the just-written storage object. So a single failed save leaves **no** half-written artifact. (`LocalArtifactStorage.write` also writes to a temp file then atomically `replace`s — no half-written bytes — [storage.py:110-121](src/ai_qa/artifacts/storage.py).)
2. **Bob's `handle_approve` catch (Task 4.1)** turns a save failure into the AC3 user experience: a UX-DR12 three-part retry message **and** leaving the page **un-resolved** (not added to `_resolved_page_ids`, no DONE transition). The user re-approves to retry; re-approval re-runs the save (a fresh `save_artifact` → a new artifact row/version, which is acceptable and idempotent-enough for a requirement).

Edge case to note in the dev record: the requirement save and the side-car `save_metadata` are **two** `save_artifact` calls. If the requirement saves but the side-car fails, the `except` fires **after** the requirement was already committed — so the requirement exists without its side-car. This is acceptable (the side-car is an audit duplicate of the `warnings` column; the page stays un-resolved and re-approval rewrites both). Do **not** attempt a cross-artifact transaction — the `warnings` column already carries the durable record; the side-car is best-effort audit. The WS-layer generic catch ([websocket.py:322-331](src/ai_qa/api/websocket.py)) is the backstop if anything escapes Bob's own catch, but Bob's catch is what produces the **specific** retry message AC3 asks for.

### Why a dedicated `save_requirement` (not just extending `save_requirement_page`)

`save_requirement_page` is a thin generic helper used by **both** the pre-approval draft (no provenance) and historically by approval. Splitting out `save_requirement` (provenance-bearing, fixed `{page_id}/requirement.md` name) gives a clean, testable seam for the **authoritative** save and keeps the draft path untouched — so the two saves can't accidentally converge. It mirrors the existing per-kind adapter methods (`save_test_case`, `save_script`).

### Project-context rules that bite here

- **Full-stack sync:** the new `Artifact` columns ripple to `ArtifactResponse`/detail/tree + the TS `Artifact` interface. Run `npm run typecheck` and `npm run build` (Vite skips strict errors). The fields are **optional** on both sides so older payloads/tests don't break.
- **Narrow Optional before use:** `source_type = str(page.get("source_type") or "confluence")`, `source_url = str(page.get("source_url") or "")`, `warnings = page.get("quality_issues") or page.get("warnings") or []` — never let `None` reach a column or a message (Pyrefly/mypy `bad-argument-type`). `assert self.project_context is not None` before building the adapter (already present).
- **No bare `except`:** the AC3 catch is `except Exception as exc:` with `logger.error(..., exc_info=True)` then a user-safe message — it does **not** re-raise (it's the recovery path). Test it with a specific `side_effect` type and `pytest.raises(...)` only where a raise is actually expected (it is not, on the recovery path).
- **Security:** provenance fields carry only page title / source URL / canned quality `message`/`impact`. **Never** put `raw_html`, MCP/LLM tokens, or config into `source_url`/`warnings`/any message or log. The leak-canary tests must stay green.
- **JSON column iteration:** read `warnings`/`quality_issues` with the `or []` empty-fallback idiom; store `qi.model_dump(mode="json")` dicts (11.5 already does), never `QualityIssue` objects, into the JSON column.
- **Migrations:** `uv` only (`uv run alembic ...`), never `python3`. `sa.JSON()` for cross-dialect (PostgreSQL prod + in-memory SQLite tests). Confirm `down_revision` = the live head (`604f28c24393`).
- **Type safety:** no `# type: ignore` / `@ts-ignore`. The `warnings` column is `Mapped[list[dict[str, Any]] | None]`; the Pydantic field is `list[dict[str, Any]] | None = None`; the TS field is `Array<Record<string, unknown>> | null`.

### Do NOT regress these existing behaviors

- The confirm-parent → `_extract_descendants` → review → approve flow still works end-to-end; `_extract_descendants` still builds exactly **one** MCPClient and `disconnect()`s it (pinned by `test_bob_extract_descendants_creates_single_mcp_client` + the disconnect tests). The save path opens **no** MCP client and calls **no** LLM.
- The pre-approval draft save (`save_requirement_page` at [bob.py:459](src/ai_qa/agents/bob.py)) and `save_raw_html` are unchanged.
- 11.6's resolved-id DONE model, reject/reprocess loop, and `process(feedback)` are untouched (this story only changes the **save** inside the `approved` branch).
- Existing artifact API responses stay backward-compatible (3 additive optional fields). Epic-10 artifact-tree behavior (4 folders, newest-first, batch display-name resolution, 10-7/10-8 `onSelectArtifact` assignability) is unchanged — see [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md).
- `create_version` (artifact edit, 10.4) is untouched — provenance is set only at first save.

### Testing approach (match the house style)

- **Backend agent:** `@pytest.mark.asyncio`; patch `ai_qa.agents.bob.PipelineArtifactAdapter` at the class boundary; assert on `mock_adapter.return_value.save_requirement.call_args` (provenance) and on the AC3 `side_effect` path (error message + un-resolved page + no DONE). Build `self.pages` directly.
- **Service / adapter / AC2:** use the real `ArtifactService` over in-memory SQLite with project/user fixtures (copy the scaffold from existing `tests/test_artifacts/*`); assert columns round-trip and `storage_path` is under `projects/{id}/requirements/`.
- **API:** canonical RBAC scaffold ([tests/api/test_admin_rbac_api.py](tests/api/test_admin_rbac_api.py)); `cast(FastAPI, client.app)` for `dependency_overrides`; assert the 3 fields on list/detail/tree responses; non-member still 404.
- **Frontend:** no new component; the change is type-only — `npm run typecheck`/`lint`/`test` must stay green. (Existing artifact-tree Vitest tests should be unaffected because the fields are optional.)
- A full Playwright E2E is **not** required (consistent with prior Bob stories — the approve path needs live MCP+LLM extraction to reach, and `frontend/support/fixtures.ts` referenced by existing specs is currently missing). Component-level + backend pytest are the guardrails.

### Latest tech / external context

No new external library or version is introduced. All tech is already pinned in [project-context.md](project-context.md): SQLAlchemy 2.0 `Mapped`/`mapped_column` + `JSON`, Alembic 1.13 (`op.add_column`/`op.drop_column`), Pydantic optional fields with `from_attributes=True`, FastAPI response models, React 19.2/TS 6 strict. Use `sa.JSON()` (not `JSONB`) in the migration for SQLite-test compatibility. No web research required.

### Project Structure Notes

**Modified files (backend):**

- `src/ai_qa/db/models.py` — add `source_type`/`source_url`/`warnings` columns to `Artifact`.
- `alembic/versions/<new>.py` — migration adding the 3 columns (`down_revision = "604f28c24393"`).
- `src/ai_qa/artifacts/service.py` — `save_artifact` accepts + persists the 3 fields; `ArtifactTreeEntryDict` + `list_artifact_tree` carry them.
- `src/ai_qa/pipelines/artifact_adapter.py` — add `save_requirement(...)` (provenance-aware).
- `src/ai_qa/agents/bob.py` — `handle_approve` approved branch uses `save_requirement(...)`, builds provenance, keeps the side-car, wraps the save in `try/except` (AC3). No change to `_extract_descendants` extraction logic or the draft save.
- `src/ai_qa/api/artifacts.py` — add the 3 fields to `ArtifactResponse`, `_artifact_detail_response`, and the tree-entry construction.

**Modified files (frontend):**

- `frontend/src/components/conversations/ProjectSidebar.tsx` — add 3 optional fields to the `Artifact` interface.

**New files:** the Alembic migration; new tests in `tests/test_artifacts/`, `tests/pipelines/`, `tests/test_agents/test_bob.py` (extend), `tests/api/`. **One DB migration. No new package.**

### Previous-story intelligence

- **Story 11.6** (`ready-for-dev`) — reshapes `handle_approve` to the resolved-id model and the reject/reprocess loop; explicitly defers the dedicated `projects/{id}/requirements/` save **to this story** ([11-6 §Out of scope](_bmad-output/implementation-artifacts/11-6-bob-reviewable-extraction-output.md), Resolved Decision 4). Task 4.1 modifies 11.6's `approved` branch.
- **Story 11.5** (`ready-for-dev`) — produces `quality_issues` per page + the acknowledgement side-car. This story stores `quality_issues` in the `warnings` column and keeps the side-car. Decision 3/4 in 11.5 lock the side-car shape.
- **Story 11.4** (`ready-for-dev`) — Jira items carry `source_type="jira"`, a ticket-ref `source_url`, `raw_html=""`. The provenance build reads these defensively.
- **Epic 10** (done) — `ArtifactService`/`PipelineArtifactAdapter`/storage keys/`save_artifact` atomicity/artifact API/realtime change events. This story extends `save_artifact` + the API responses without changing the sync path. See [epic-10-artifact-ui-gotchas](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/epic-10-artifact-ui-gotchas.md): artifact path is **sync**; `_schedule_change_event` no-ops outside an event loop (fine for unit tests).
- **Epic 9** (done) — per-user secret resolution; the save path needs **no** secret access (no MCP/LLM).
- See [agent-gate-conftest-regression](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/agent-gate-conftest-regression.md): if 11.2's intake gate is merged and a happy-path Bob test trips it, fix the shared `mock_db`/`mock_project_context` centrally.
- See [backend-test-suite-orphaned-legacy-tests](C:/Users/thuong/.claude/projects/C--Users-thuong-source-repos-ai-qa-automation/memory/backend-test-suite-orphaned-legacy-tests.md): a full `uv run pytest` is red from orphaned legacy tests — verify only the 11.7-touched files, not the whole-suite baseline.

### Git intelligence (recent work patterns)

Recent commits (`8cf53eb epic 10 all code done`, `9d878c5 feat(api): emit project-scoped artifact change events`, `1852886 feat(10-3)`, `39db313` 3.12→3.14) center on Epic 10 artifact events + the 3.14 upgrade. None touch the `artifacts` schema since 10.x, so `604f28c24393` is a clean `down_revision`. The established pattern: artifact metadata in PostgreSQL + bytes in storage, additive optional API fields, sync save with a fire-and-forget change event. 11.7 follows it exactly — additive columns, additive optional response fields, the same atomic `save_artifact` path.

### References

- [Source: _bmad-output/planning-artifacts/epics.md:1097-1118] — Story 11.7 ACs (save under `projects/{project_id}/requirements/`; full metadata list; project-scoped queries, no workspace paths; save-failure recovery)
- [Source: _bmad-output/planning-artifacts/architecture.md:280] — required folders `projects/{project_id}/requirements/…`; metadata links `thread_id`/`agent_run_id`
- [Source: _bmad-output/planning-artifacts/architecture.md:336-360] — output structure + Artifact metadata field list (creator/updater, thread, agent_run, timestamps, non-secret execution metadata)
- [Source: src/ai_qa/db/models.py:127-157] — `Artifact` model (add 3 columns); `TimestampMixin` = created_at/updated_at
- [Source: src/ai_qa/artifacts/service.py:71-131] — `save_artifact` atomic write (extend params); :185-229 query methods (AC2); :36-52,239-329 tree + TypedDict
- [Source: src/ai_qa/artifacts/storage.py:28-38] — `build_artifact_key` (requirements → `projects/{id}/requirements/`); :110-121 atomic temp-then-replace
- [Source: src/ai_qa/pipelines/artifact_adapter.py:42-46,69-75,109-120] — `save_requirement_page`/`save_metadata`/`_save_text` (add `save_requirement`)
- [Source: src/ai_qa/pipelines/context.py:11-19] — `PipelineContext` provenance fields
- [Source: src/ai_qa/agents/bob.py:459,513-599] — draft save (kept); `handle_approve` approved branch (harden + provenance)
- [Source: src/ai_qa/agents/base.py:400] — `_format_error_message` (UX-DR12)
- [Source: src/ai_qa/api/artifacts.py:61-116,172-260] — `ArtifactResponse`/detail/tree (add 3 fields)
- [Source: src/ai_qa/api/websocket.py:316-331] — approve dispatch + generic error backstop
- [Source: frontend/src/components/conversations/ProjectSidebar.tsx:39-53] — `Artifact` TS interface (add 3 fields); [frontend/src/lib/artifacts.ts] — tree client types
- [Source: tests/test_agents/test_bob.py] — Bob test patterns; tests/conftest.py:50-56 `mock_project_context`
- [Source: alembic/versions/604f28c24393_add_artifact_ownership_and_thread_.py] — current head + migration style
- [Source: project-context.md] — `uv`/`npm` only; Ruff + Mypy strict; no `# type: ignore`/`@ts-ignore`; narrow Optional; no bare except; full-stack TS sync; security (no secret/HTML/config in fields/logs); `sa.JSON` cross-dialect

### Definition of Done

- [ ] `artifacts` table gains `source_type`/`source_url`/`warnings` via an Alembic migration (`down_revision = 604f28c24393`); `uv run alembic upgrade head` + a downgrade/upgrade round-trip are clean; one head.
- [ ] `Artifact` model has the 3 typed nullable columns; `ArtifactService.save_artifact` accepts + persists them (optional, default `None`); `list_artifact_tree` carries them.
- [ ] `PipelineArtifactAdapter.save_requirement(...)` saves the approved markdown under `kind="requirements"` (→ `projects/{id}/requirements/…`) with provenance + a change event.
- [ ] `BobAgent.handle_approve` (approved branch) saves via `save_requirement(...)` with `source_type`/`source_url`/`warnings` built from the page, keeps the 11.5 acknowledgement side-car, and the page resolves only on success (AC1).
- [ ] Save failure → UX-DR12 retry message, page **not** resolved, **no** DONE transition, no partial single-artifact corruption (service atomicity) (AC3).
- [ ] Saved requirements are reachable via `list_artifacts(kind="requirements")` / `read_current_content` / the artifact API (list/detail/tree) **with provenance** and **no** workspace-path read (AC2); the draft-vs-approved discriminator (provenance presence) is documented for 12.1.
- [ ] `ArtifactResponse`/`ArtifactDetailResponse`/`ArtifactTreeEntry` + the frontend `Artifact` interface expose the 3 fields (full-stack sync); existing responses stay backward-compatible; leak-canary tests green.
- [ ] Existing Bob regression tests (single-MCP-client, disconnect, confirm-parent, 11.6 reject/process) pass unchanged; the save path opens no MCP client.
- [ ] New tests: service round-trip + path, adapter pass-through, on-approve provenance, AC3 failure-keeps-reviewable, AC2 query reachability, API response shape.
- [ ] `uv run ruff check .` + `uv run mypy src` clean; affected pytest green; `npm run lint`/`typecheck`/`test` green in `/frontend`.

---

## Resolved Decisions (confirmed by Thuong — do NOT revisit)

Confirmed 2026-06-11 during story creation; locked — implement exactly as stated.

1. **Provenance = first-class columns + Alembic migration.** Add `source_type` (`String(50)`), `source_url` (`Text`), `warnings` (`JSON`) to `artifacts`, populated on approval. *(Alternative rejected: side-car-JSON-only with no migration — cheaper but not directly queryable by Mary/12.x.)* The native columns already cover creator/updater/thread/agent_run/timestamp/kind; these 3 complete AC1.
2. **Keep the pre-approval extraction-time requirement save as a draft cache.** `_extract_descendants`'s `save_requirement_page(page.page_id, …)` stays (draft, no provenance); the on-approve `save_requirement(…)` (provenance-bearing, `{page_id}/requirement.md`) is authoritative. *(Alternative rejected: remove the premature save so requirements persist only on approval.)* The provenance-presence discriminator (Dev Notes → AC2) keeps the two distinguishable for 12.1.
3. **Keep the 11.5 acknowledgement side-car alongside the new `warnings` column (default, applied).** Both hold the acknowledged quality issues — column = queryable, side-car = human-readable audit. No removal/rename of 11.5's metadata artifact.
4. **AC3 = atomic per-artifact write + agent-level "stays reviewable" (default, applied).** Rely on `save_artifact`'s existing rollback+delete for no-partial-corruption; Bob catches the failure, sends a UX-DR12 retry message, and leaves the page un-resolved (no DONE). No cross-artifact transaction.

## Saved Questions

1. **Mary's draft-vs-approved filter (for Story 12.1, not this story).** Because the pre-approval draft save is kept (Decision 2), `kind="requirements"` can contain both a draft (`{page_id}.md`, provenance `NULL`) and the approved copy (`{page_id}/requirement.md`, provenance set). 12.1 should select **approved** requirements (`source_type IS NOT NULL`, or the `requirement.md` name pattern). Flagged for 12.1 — do not build the filter in 11.7. *(If Thuong later prefers a single artifact per page, that's an 11.8 tech-debt item: dedupe the draft on approval.)*
2. **Re-approval creates a new artifact row/version.** `save_artifact` always creates a **new** `Artifact` (it does not dedupe by name); so re-approving after a transient failure (AC3 retry) yields a second approved row. Acceptable for this story (queries still return the latest by `updated_at`). If a stable single-artifact-per-page identity is wanted, that's a follow-up (11.8) — flag during dev only if a test needs idempotency.
3. **Side-car location.** The side-car `requirement.metadata.json` is `kind="configuration"` → it lands under the storage catch-all (`artifacts/`) and the "reports" browse folder, not under `requirements/`. This matches 11.5's existing behavior and is intentional (the **requirement content** is what AC1 requires under `requirements/`; the side-car is an audit duplicate). No change unless Thuong wants the side-car colocated.

---

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

- Alembic autogenerate picked up unrelated nullability changes on `ai_provider_configs.updated_at` and `projects.confluence_base_url` — stripped to only the 3 new `artifacts` columns.
- `bob.py handle_approve` still called `save_requirement_page` (not updated in prior session) — corrected to `save_requirement` with provenance kwargs; 2 Bob tests then passed.
- `uv run ruff check src/` returned "No Python files found" on Windows; used `uv run python -c "import ..."` to verify imports instead.

### Completion Notes List

- All 9 tasks and subtasks complete. All ACs satisfied.
- AC1: `source_type`/`source_url`/`warnings` columns added to `artifacts` table via migration `c8e6ace95b08`; `save_artifact` accepts + persists them; `BobAgent.handle_approve` calls `save_requirement(...)` with provenance on approval.
- AC2: Approved requirements reachable via `list_artifacts(kind="requirements")`, `read_current_content`, and all 3 API endpoints (list/detail/tree) — all carrying provenance. Frontend `Artifact` TS interface synced. Draft-vs-approved discriminator: `source_type IS NOT NULL` for approved (documented for Story 12.1).
- AC3: `try/except Exception` wraps the save; on failure UX-DR12 retry message sent, page not added to `_resolved_page_ids`, no DONE transition, `output_files_saved` stays 0.
- Edge case noted: requirement save + side-car `save_metadata` are two `save_artifact` calls. If requirement commits but side-car fails, requirement exists without side-car — acceptable (warnings column is the durable record; page stays un-resolved for retry). Documented in AC3 Dev Notes.
- Pre-approval draft save (`save_requirement_page` in `_extract_descendants`) left unchanged per Thuong's decision.
- `test_bob_handle_approve_save_failure_no_mcp_client` confirms the save path opens no MCP client.

### File List

- `src/ai_qa/db/models.py` — added `source_type`, `source_url`, `warnings` columns to `Artifact`
- `alembic/versions/c8e6ace95b08_add_provenance_columns_to_artifacts.py` — NEW: migration adding 3 columns, `down_revision="604f28c24393"`
- `src/ai_qa/artifacts/service.py` — `save_artifact` accepts 3 optional provenance params; `ArtifactTreeEntryDict` + `list_artifact_tree` carry them
- `src/ai_qa/pipelines/artifact_adapter.py` — NEW `save_requirement(...)` method with provenance
- `src/ai_qa/agents/bob.py` — `handle_approve` approved branch: use `save_requirement(...)`, build provenance defensively, `try/except` AC3 hardening
- `src/ai_qa/api/artifacts.py` — `ArtifactResponse`, `_artifact_detail_response`, `ArtifactTreeEntry` carry 3 provenance fields
- `frontend/src/components/conversations/ProjectSidebar.tsx` — `Artifact` TS interface gains 3 optional provenance fields
- `tests/unit/test_artifact_service_provenance.py` — NEW: 4 service tests (round-trip, defaults, query reachability, draft-vs-approved discriminator)
- `tests/pipelines/test_pipeline_artifact_adapter.py` — extended: `test_save_requirement_forwards_provenance_to_save_artifact`
- `tests/test_agents/test_bob.py` — extended: 3 tests (on-approve provenance, AC3 failure-keeps-reviewable, no-MCP-client regression)
- `tests/api/test_artifact_provenance_api.py` — NEW: 5 API tests (list/detail/tree carry provenance, non-member 404, draft backward-compat)

### Change Log

- 2026-06-12: Story 11.7 implementation complete. 746 backend tests passed (targeted suite). Frontend: 171 tests passed, typecheck + lint clean. Alembic round-trip (downgrade/upgrade) clean. Status → review.

---

## Review Findings (code review 2026-06-12)

> Scope reviewed: Story 11.7 surface **combined with Story 11.8 / decision D8** logic that was merged into the same uncommitted working tree during the review (`save_requirement` delete-then-save dedupe + new `delete_draft_requirement`, called from `handle_approve`). 3 adversarial layers ran (Blind Hunter, Edge Case Hunter, Acceptance Auditor); all passed. **AC1, AC2, and AC3 (first-save-failure case) verified satisfied and tested.** The findings below are dominated by the D8 entanglement, not by 11.7's own deltas.

### Decision needed

- [x] `[Review][Decision]` **D8 delete-then-save regresses AC3 "no partial corruption" — zero-approved-row window on re-approval** — `save_requirement` ([artifact_adapter.py:69-83](src/ai_qa/pipelines/artifact_adapter.py)) deletes the prior approved `{page_id}/requirement.md` via `delete_artifact`, which **commits and deletes storage** ([service.py:226-233](src/ai_qa/artifacts/service.py)), **before** the new `save_artifact`. If the re-save then fails, the page is left with **no approved artifact**. `handle_approve` has no guard against re-approving an already-resolved page ([bob.py:1111-1135](src/ai_qa/agents/bob.py)), so this is reachable in normal flow. It also contradicts this story's locked **Saved Question #2** ("re-approval creates a NEW row; single-artifact-per-page is a follow-up"). This is 11.8/D8 code being actively written by a concurrent dev process. **RESOLVED (Thuong, fix now/atomic):** `save_requirement` reordered to **save-new-first, then delete superseded prior rows** ([artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py)) — if the new save fails the prior approved artifact is left intact (no zero-row window), and the happy path still converges to a single approved row. Verified: adapter + provenance tests green; ruff + mypy clean.

### Patch (action items)

- [x] `[Review][Patch]` **AC3 retry message is gutted** — `_format_error_message` renders only `errors[0]` ([base.py:402-413](src/ai_qa/agents/base.py)); the "Reason: …" and "Please approve again to retry. No partial requirement was saved." lines passed by the AC3 catch are silently dropped. Compose the AC3 message into a single `errors[0]` string. [bob.py:1166-1175](src/ai_qa/agents/bob.py)
- [x] `[Review][Patch]` **`project_context is None` raises a bare `ValueError` mid-handler** ([bob.py:1135](src/ai_qa/agents/bob.py)) — outside the try, it escapes to the WebSocket generic catch with a raw internal message. Replace with `send_message(..., "error")` + `return`.
- [x] `[Review][Patch]` **Provenance happy-path test under-asserts** — `test_bob_handle_approve_saves_requirement_with_provenance` never asserts `save_metadata` (or `delete_draft_requirement`) was called; both side effects could be removed and the test still passes. Add the call assertions. [tests/test_agents/test_bob.py:1417-1425](tests/test_agents/test_bob.py)
- [x] `[Review][Patch]` **`# type: ignore[arg-type]` masks a wrong annotation** — `_seed_requirement(client, project: User, ...)` is annotated `User` but receives a `Project`; fix the annotation and drop the `[arg-type]` ignores (project-context rule: never `# type: ignore`). [tests/api/test_artifact_provenance_api.py:113](tests/api/test_artifact_provenance_api.py)
- [x] `[Review][Patch]` **Double `datetime.now(UTC)` in the metadata side-car** — two calls produce two timestamps for one approve event; capture once and reuse. [bob.py:1155,1159](src/ai_qa/agents/bob.py)
- [x] `[Review][Patch]` **Pre-existing lint debt surfaced & fixed** — `ruff check` was red on 4 `F841` unused-variable assignments in `tests/test_agents/test_bob.py` (1 in 11.7's AC3 test, 3 leftover scaffolding in 11.6's reject test, incl. `is_review_calls = [c.kwargs for c in MagicMock().mock_calls]` which is always empty). Removed all 4 dead vars — no real assertion lost (the reject re-emit is covered by `test_bob_handle_reject_re_emits_is_review_ready_metadata`). `ruff check` now clean.

### Deferred (flagged to Story 11.8 / D8 owner)

- [x] `[Review][Defer]` **Side-car `save_metadata` is not deduped** — duplicate `configuration` metadata rows accumulate on retry/re-approve while `save_requirement` dedupes the requirement; D8 should dedupe the side-car too. [bob.py:1153](src/ai_qa/agents/bob.py) — deferred to 11.8
- [x] `[Review][Defer]` **No `"deleted"` change event for the dedupe-removed row** — realtime artifact-sync clients may keep a stale entry. [artifact_adapter.py:97](src/ai_qa/pipelines/artifact_adapter.py) — deferred to 11.8
- [x] `[Review][Defer]` **`not_requirement` skip leaves the orphan draft** — `delete_draft_requirement` runs only on the approved branch, so a skipped page keeps its `{page_id}.md` draft. [bob.py:1128-1152](src/ai_qa/agents/bob.py) — deferred to 11.8
- [x] `[Review][Defer]` **No test for D8 dedupe / re-approval / the zero-row window** — the existing failure test makes `save_requirement` itself raise (before any commit), so the post-delete failure path is uncovered. — deferred to 11.8
- [x] `[Review][Defer]` **`output_files_saved` count drift** — re-approving a resolved page increments it again; an all-skipped run hands "Saved 0 approved requirements" to Mary. [bob.py:1165,1183](src/ai_qa/agents/bob.py) — deferred
- [x] `[Review][Defer]` **`source_type` defaults to `"confluence"`** when missing (mislabels a Jira-origin page that lost its type); `source_url` stored as `""` not NULL. Spec-sanctioned defensive default — revisit only if a source can legitimately lack `source_type`. [bob.py:1139-1140](src/ai_qa/agents/bob.py) — deferred
- [x] `[Review][Defer]` **`source_type` `String(50)` has no length guard** — an over-long value fails at PostgreSQL commit (handled as a save failure) but passes SQLite tests. [models.py:152](src/ai_qa/db/models.py) — deferred
- [x] `[Review][Defer]` **`warnings=[]` vs NULL semantic untested on Postgres** — the `[]`-means-approved-no-issues vs NULL-means-draft distinction is load-bearing and only verified on SQLite. [models.py:154](src/ai_qa/db/models.py) — deferred
- [x] `[Review][Defer]` **Duplicate `page_id` in `self.pages` breaks the DONE invariant** (`len(_resolved_page_ids) >= len(self.pages)` can never be reached). [bob.py:1183](src/ai_qa/agents/bob.py) — deferred
