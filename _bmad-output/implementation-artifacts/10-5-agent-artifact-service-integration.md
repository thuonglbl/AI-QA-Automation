---
baseline_commit: 90d3f6fbcaa0f5c86df52437f898308884cbc0e8
---

# Story 10.5: Agent Artifact Service Integration

Status: ready-for-dev

<!-- markdownlint-disable MD033 MD041 -->
<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system developer,
I want all agents to read and write artifacts through the artifact service,
so that authorization, metadata, storage, audit, and realtime events stay consistent.

## Acceptance Criteria

### AC1 — Agents write through the artifact service, with originating thread + run metadata

**Given** Bob, Mary, Sarah, or Jack needs to save output
**When** the agent writes requirements, test cases, scripts, screenshots, or reports
**Then** the agent calls the artifact service rather than writing directly to local workspace paths or SeaweedFS clients
**And** artifact metadata includes originating thread and agent run where available.

### AC2 — Agents read project-scoped inputs through the artifact service

**Given** an agent needs input from a previous stage
**When** the agent reads requirements, test cases, or scripts
**Then** it queries project-scoped artifacts through the artifact service
**And** it only receives artifacts authorized for the thread's bound project.

### AC3 — Legacy workspace-path assumptions are isolated or removed; no new ones introduced

**Given** legacy workspace path assumptions still exist
**When** agent artifact integration is implemented
**Then** compatibility adapters are isolated behind the artifact service or removed where safe
**And** no new direct workspace-path dependency is introduced.

---

## ⚠️ CRITICAL: This is a RECONCILE + HARDEN + CLEANUP story, NOT a greenfield migration

The agent → artifact-service wiring **already physically exists and is load-bearing.** Bob, Mary, and Sarah were refactored off `workspace/*` paths during Epic 6 (story 6-7, `PipelineContext` + `PipelineArtifactAdapter`) and now route **all** artifact writes through `PipelineArtifactAdapter → ArtifactService`. A test file already exists labeled for this story — [tests/unit/test_workspace_adapters.py:1](tests/unit/test_workspace_adapters.py:1) (`"""Unit tests for workspace adapters (Story 10.5)."""`) — and [tests/integration/test_project_scoped_agents.py](tests/integration/test_project_scoped_agents.py) already exercises project-scoped persistence for all three agents. **Do NOT rebuild the adapter, the agents' write paths, or the storage backends.** Your job is to **close the real gaps** between what exists and what AC1–AC3 require, and to **prove** the contract with tests — without breaking the shipped behavior.

> **Jack is out of scope.** `jack.py` does **not** exist ([src/ai_qa/agents/](src/ai_qa/agents/) contains only `alice`, `bob`, `mary`, `sarah`, `base`). The "Run Test Scripts" agent (Jack) belongs to **Epic 15** (`15-2-playwright-execution-runner`). The AC names "Bob, Mary, Sarah, **or** Jack" to mean *whichever agents save output*; only Bob/Mary/Sarah exist today. This story must leave the adapter pattern in place so a future Jack inherits service-routed I/O for free — and must **not** introduce a new direct-workspace dependency Jack would copy.

### What ALREADY EXISTS (reuse — do not recreate)

| Capability | Where it lives today | Status |
| --- | --- | --- |
| Bob writes raw HTML + requirements via the service | [bob.py](src/ai_qa/agents/bob.py) → `PipelineArtifactAdapter.save_raw_html` / `save_requirement_page` / `save_metadata` | ✅ done |
| Mary writes test cases + metadata via the service | [mary.py:289-302](src/ai_qa/agents/mary.py:289) → `adapter.save_test_case` / `save_metadata` | ✅ done |
| Mary reads requirements via the service | [mary.py](src/ai_qa/agents/mary.py) → `adapter.load_requirement_markdown()` (project-scoped) | ✅ done |
| Sarah writes scripts via the service | [sarah.py:537-539](src/ai_qa/agents/sarah.py:537) + `_save_approved_scripts` → `adapter.save_script` | ✅ done |
| Sarah reads test cases via the service | [sarah.py:212-213](src/ai_qa/agents/sarah.py:212) → `adapter.load_test_cases()` (project-scoped) | ✅ done |
| Intent facade over the service | `PipelineArtifactAdapter` — [artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py) (passes `project_id`, `owner_user_id`, `agent_run_id`) | ✅ done |
| No direct storage-client access from agents | grep confirms zero `boto3`/`S3ArtifactStorage`/`LocalArtifactStorage` imports in [src/ai_qa/agents/](src/ai_qa/agents/) | ✅ done |
| `agent_run_id` created on pipeline START | `_build_pipeline_context(..., create_run=True)` — [routes.py:355](src/ai_qa/api/routes.py:355) → `ThreadService.create_agent_run` | ✅ done |
| `thread_id` on `Artifact` + `save_artifact(thread_id=...)` + `_validate_thread` | shipped by Story 10.1 (migration `604f28c24393`) — [service.py](src/ai_qa/artifacts/service.py) | ✅ done (param exists, unused by adapter — see Gap 1) |
| Project-membership authz before context is built | `require_project_member_or_admin` gate in `_build_pipeline_context` — [routes.py:261](src/ai_qa/api/routes.py:261) | ✅ done |
| Storage adapters (Local + S3/SeaweedFS), config-driven selection | [storage.py](src/ai_qa/artifacts/storage.py); [test_workspace_adapters.py](tests/unit/test_workspace_adapters.py) | ✅ done |

### What is MISSING / must change in THIS story (the real scope)

1. **`thread_id` is never forwarded to artifact metadata (AC1 gap).** `PipelineArtifactAdapter._save_text` ([artifact_adapter.py:106-114](src/ai_qa/pipelines/artifact_adapter.py:106)) and `save_image` ([artifact_adapter.py:95-104](src/ai_qa/pipelines/artifact_adapter.py:95)) pass `project_id`, `owner_user_id`, and `agent_run_id` — but **not** `thread_id`. `PipelineContext.thread_id` **is** populated on both START and APPROVE paths ([routes.py:256](src/ai_qa/api/routes.py:256), [routes.py:279](src/ai_qa/api/routes.py:279)). Result: **every agent-written artifact has `thread_id = NULL`**, so AC1's "metadata includes originating thread" is not met.
2. **`agent_run_id` is `None` for artifacts written during APPROVE.** `agent_run_id` is only created when `create_run=True`, which only the `/start` route passes ([routes.py:355](src/ai_qa/api/routes.py:355)). Mary's `_write_approved_test_cases` and Sarah's `_save_approved_scripts` run during `/approve` ([routes.py:389](src/ai_qa/api/routes.py:389), `create_run` defaults to `False`), so those approved artifacts carry no run id. AC1 says "where available," so `None` is tolerated — but forwarding `thread_id` (Gap 1) gives those artifacts a reliable origin anchor. Decide & document; do **not** change run-creation timing.
3. **Legacy direct-filesystem `OutputWriter` is still exported (AC3).** [output_writer.py](src/ai_qa/pipelines/output_writer.py) writes straight to the filesystem (`mkdir` / `write_text` / `write_bytes`) and is exported from [pipelines/__init__.py:11](src/ai_qa/pipelines/__init__.py:11). It is **not called by any agent** (only refs: the `__init__` export, a stale [sarah.py:45](src/ai_qa/agents/sarah.py:45) docstring, and its own test). It is a workspace-path dependency that should be removed "where safe."
4. **Vestigial `output_base_dir` workspace param on the script path (AC3).** `ScriptGenerator.__init__` takes `output_base_dir: Path` but never writes; Sarah passes the sentinel `Path("/dev/null")` at [sarah.py:285](src/ai_qa/agents/sarah.py:285) and [sarah.py:402](src/ai_qa/agents/sarah.py:402). A dead workspace-path param that should be retired.
5. **Mary's requirement materialization leaks a temp dir + stale workspace docstrings (AC3 hygiene).** `MaryAgent._materialize_requirement_artifacts` ([mary.py:306-316](src/ai_qa/agents/mary.py:306)) reads requirements from the service then writes them to a `tempfile.mkdtemp()` dir to feed `TestCaseExtractor` (which consumes file *paths*). This is an *isolated* compat seam (transient temp, not a persistent workspace path) — but the temp dir is **never cleaned up**, and several docstrings/messages still claim "workspace/requirements/" / "workspace/testcases/" ([mary.py:23](src/ai_qa/agents/mary.py:23), [sarah.py:187](src/ai_qa/agents/sarah.py:187), etc.).
6. **No explicit cross-project leak-canary at the agent/adapter level (AC2 verification).** Reads are project-scoped via `list_artifacts(project_id=...)`, but there is no test proving an agent bound to project A cannot read project B's artifacts (the project convention from Story 10.1).
7. **No regression guard that agents never bypass the service (AC3 verification).** Nothing fails CI if a future change re-introduces a direct storage/filesystem write in an agent.

### FROZEN CONTRACTS — DO NOT change

- **`ArtifactChangeEvent`** and realtime emission belong to **Story 10.6** — do not add, rename, or emit artifact change events in this story.
- **`ARTIFACT_KINDS`** frozenset values ([service.py:15-29](src/ai_qa/artifacts/service.py:15)) — `requirements`, `testcase`, `testscript`, `playwright_script`, `raw_html`, `configuration`, `image`, `report`, `screenshot`, `markdown`, `mermaid`. Do not add/rename kinds.
- **`ArtifactService.save_artifact` / `create_version` signatures** ([service.py](src/ai_qa/artifacts/service.py)) — keyword-only; `thread_id` is **already** an accepted param. Pass it; do **not** change the signature.
- **`PipelineContext` field names** ([context.py](src/ai_qa/pipelines/context.py)) — `user_id`, `user_email`, `project_id`, `thread_id`, `artifact_service`, `agent_run_id`. Read them; do not rename.
- **`/start` and `/approve` route surface + `create_run` semantics** ([routes.py](src/ai_qa/api/routes.py)) — do not change when/where agent runs are created.
- **`ArtifactResponse`** existing field names — additive-only, per Story 10.1.

---

## Tasks / Subtasks

- [ ] **Task 1 — Forward originating thread to all agent-written artifacts (AC1)**
  - [ ] 1.1 In `PipelineArtifactAdapter._save_text` ([artifact_adapter.py:106](src/ai_qa/pipelines/artifact_adapter.py:106)) and `save_image` ([artifact_adapter.py:95](src/ai_qa/pipelines/artifact_adapter.py:95)), pass `thread_id=self.context.thread_id` to `service.save_artifact(...)`. The param already exists and `_validate_thread` already rejects a thread that does not belong to `project_id` — no service change required.
  - [ ] 1.2 Confirm `context.thread_id` is populated on both the START (`create_run=True`) and APPROVE (`create_run=False`) paths — it is set from the request/thread regardless of `create_run` ([routes.py:256](src/ai_qa/api/routes.py:256), [routes.py:279](src/ai_qa/api/routes.py:279)). So approved artifacts now record their originating thread even though `agent_run_id` is `None` there.
  - [ ] 1.3 **Decide & document** the `agent_run_id`-during-approve behavior (Gap 2): default is to **leave run-creation timing unchanged** (AC1 only requires "where available") and rely on `thread_id` as the origin anchor for approve-time saves. Do NOT add `create_run=True` to `/approve` — that would change run semantics and risk double-counting runs. Record the decision in Dev Notes / Open Question Q1.
  - [ ] 1.4 The adapter only ever calls `save_artifact` (never `create_version`), so forwarding `thread_id` there covers every agent write. Verify there is no second agent write path that bypasses `_save_text`/`save_image` (grep agents for `save_artifact`, `.write(`, `create_version`).

- [ ] **Task 2 — Remove the legacy direct-filesystem `OutputWriter` (AC3, "removed where safe")**
  - [ ] 2.1 **Re-confirm zero production callers** with a fresh grep for `OutputWriter` across `src/` before deleting (current state: only [pipelines/__init__.py:11,22](src/ai_qa/pipelines/__init__.py:11), the [sarah.py:45](src/ai_qa/agents/sarah.py:45) docstring, and [tests/pipelines/test_output_writer.py](tests/pipelines/test_output_writer.py)).
  - [ ] 2.2 Delete [src/ai_qa/pipelines/output_writer.py](src/ai_qa/pipelines/output_writer.py); remove its `import` and `__all__` entry from [pipelines/__init__.py](src/ai_qa/pipelines/__init__.py); delete [tests/pipelines/test_output_writer.py](tests/pipelines/test_output_writer.py); fix the stale [sarah.py:45](src/ai_qa/agents/sarah.py:45) docstring line ("- OutputWriter for file management").
  - [ ] 2.3 **KEEP `OutputMetadata`** ([pipelines/models.py](src/ai_qa/pipelines/models.py)) — it is referenced by `tests/test_brute_models_ext.py` and is a standalone model. Only remove its export from `pipelines/__init__.py` if nothing else imports it from there (grep first); otherwise leave the export.
  - [ ] 2.4 **Decision fallback:** if 2.1 surfaces a hidden caller, do NOT delete — instead keep `OutputWriter` but prove it is unreachable from any agent path and mark it deprecated in its docstring. Default is removal.

- [ ] **Task 3 — Retire the vestigial `output_base_dir` workspace param on the script path (AC3)**
  - [ ] 3.1 Grep ALL `ScriptGenerator(` call sites first — known sites: [sarah.py:284](src/ai_qa/agents/sarah.py:284), [sarah.py:401](src/ai_qa/agents/sarah.py:401), a `__main__`/demo at [script_generator.py:599](src/ai_qa/pipelines/script_generator.py:599), and ~8 calls in [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py).
  - [ ] 3.2 Remove the unused `output_base_dir` param from `ScriptGenerator.__init__` and drop `self.output_base_dir` (it is never used to write — confirmed). Remove the `Path("/dev/null")` arg at both Sarah call sites and update every other call site (demo + tests) to the new signature.
  - [ ] 3.3 **Decision point:** removing the param touches ~8 test constructor calls. Default: remove + update all call sites (cleanest, satisfies "no new workspace dependency"). Acceptable alternative if churn is risky: keep the param but default it to `None`, stop passing `/dev/null`, and document it as deprecated. Pick one and record it.
  - [ ] 3.4 Do **not** change `TestCaseExtractor`'s file-path input interface (it reads paths the caller materializes — see Task 4). Reworking it to accept in-memory content is a separate, larger change and is **out of scope**; just ensure no *new* workspace dependency is added.

- [ ] **Task 4 — Isolate & document Mary's materialization compat seam; fix the temp-dir leak (AC3)**
  - [ ] 4.1 Keep `MaryAgent._materialize_requirement_artifacts` ([mary.py:306](src/ai_qa/agents/mary.py:306)) — it is a *legitimate, isolated* compatibility adapter: it pulls requirements **from the artifact service** then materializes transient temp files only because `TestCaseExtractor` consumes file paths. This satisfies AC3's "compatibility adapters isolated behind the artifact service." It is **not** a persistent workspace path.
  - [ ] 4.2 **Fix the temp-dir leak:** the `tempfile.mkdtemp()` dir is never removed. Use `tempfile.TemporaryDirectory()` (context manager) or `shutil.rmtree(..., ignore_errors=True)` in a `finally`, ensuring extraction completes before cleanup. Verify the caller does not retain the `Path`s after the block.
  - [ ] 4.3 Update stale workspace docstrings/messages so no misleading "workspace path assumption" language remains (doc/text only — no behavior change): [mary.py:23](src/ai_qa/agents/mary.py:23), [mary.py:69](src/ai_qa/agents/mary.py:69), [mary.py:148](src/ai_qa/agents/mary.py:148), [mary.py:285](src/ai_qa/agents/mary.py:285); [sarah.py:175](src/ai_qa/agents/sarah.py:175), [sarah.py:187](src/ai_qa/agents/sarah.py:187) (the misleading `"No test cases found in workspace/testcases/"` warning), [sarah.py:209](src/ai_qa/agents/sarah.py:209). Reword to reflect artifact-service sourcing.
  - [ ] 4.4 Leave the test-only `workspace_dir` override params on `BaseAgent`/`MaryAgent`/`SarahAgent` ([base.py:68](src/ai_qa/agents/base.py:68), [mary.py:37](src/ai_qa/agents/mary.py:37), [sarah.py:58](src/ai_qa/agents/sarah.py:58)) — they are unused for artifact writes and removing them churns constructor call sites for no AC benefit. Note them in Dev Notes as known-inert.

- [ ] **Task 5 — Prove project-scoped reads + add a no-bypass regression guard (AC2, AC3)**
  - [ ] 5.1 **AC2 cross-project leak-canary:** extend [tests/integration/test_project_scoped_agents.py](tests/integration/test_project_scoped_agents.py) — create projects A and B, write a requirement/test-case artifact under B, build a `PipelineContext` bound to A, and assert `adapter.load_requirement_markdown()` / `load_test_cases()` return **only** A's artifacts (never B's). Mirrors the Story 10.1 leak-canary discipline.
  - [ ] 5.2 **AC3 no-bypass guard:** add a unit test (e.g. in [tests/unit/test_workspace_adapters.py](tests/unit/test_workspace_adapters.py) or a new `tests/unit/test_agent_no_direct_storage.py`) asserting the agent modules do not import storage clients directly — assert `boto3`, `S3ArtifactStorage`, `LocalArtifactStorage` do not appear in the import graph of `ai_qa.agents.bob/mary/sarah`, and that no agent module calls filesystem write APIs for artifact content. Reconcile with the existing Story-10.5-labeled tests; **extend, do not duplicate**.
  - [ ] 5.3 **Authorization guarantee:** document/assert that an agent's `PipelineContext.project_id` is only ever set after `require_project_member_or_admin` passes in `_build_pipeline_context` ([routes.py:261](src/ai_qa/api/routes.py:261)); the adapter `project_id` property ([artifact_adapter.py:37](src/ai_qa/pipelines/artifact_adapter.py:37)) cannot widen scope. A short integration assertion is sufficient.
  - [ ] 5.4 **AC1 thread_id persistence test:** extend [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) to assert (a) a save with `context.thread_id` set persists `Artifact.thread_id`; (b) a save with `context.thread_id = None` persists `None` without error; (c) a `context.thread_id` belonging to a *different* project is rejected by `_validate_thread`.

- [ ] **Task 6 — Full gate + DoD**
  - [ ] 6.1 Run the gate (see Definition of Done) and paste outputs into the Dev Agent Record.
  - [ ] 6.2 **No DB migration is required** — `Artifact.thread_id` already exists (Story 10.1 migration `604f28c24393`). State this explicitly in the DoD so the migration-in-DoD guardrail is consciously satisfied (a no-op here).
  - [ ] 6.3 **No frontend change expected** — confirm no files under `frontend/` were touched (`npm run typecheck` therefore N/A unless a type was incidentally affected; run it only if `frontend/` changed).

---

## Dev Notes

### Architecture & module layout (authoritative)

The architecture mandates: *"Write artifacts through the artifact service so metadata, SeaweedFS object storage, authorization, audit, and realtime events stay consistent"* and lists as a **FORBIDDEN anti-pattern**: *"Reading/writing SeaweedFS directly from agents or UI code without the artifact service"* ([architecture.md:518](_bmad-output/planning-artifacts/architecture.md:518), [architecture.md:533](_bmad-output/planning-artifacts/architecture.md:533)). The data-flow diagram ([architecture.md:811-834](_bmad-output/planning-artifacts/architecture.md:811)) shows each agent reading prior-stage inputs and writing outputs through `artifacts/service.py`. The agents currently honor this via `PipelineArtifactAdapter`; this story closes the remaining metadata and hygiene gaps.

### The artifact path is SYNCHRONOUS — do not async-ify it

Per the Epic 10 UI gotchas, the artifact code path uses a **synchronous SQLAlchemy `Session`**, not the async session used elsewhere. `_build_pipeline_context` receives `db: Session` and calls `db.get(...)` synchronously ([routes.py:205](src/ai_qa/api/routes.py:205), [routes.py:226](src/ai_qa/api/routes.py:226)); `ArtifactService(db, storage)` is sync; `PipelineArtifactAdapter` methods are sync. **Do NOT add `await`, `selectinload`, or async eager-load patterns to the adapter/service in this story** — the `MissingGreenlet`/eager-load rules apply to the *async* sessions, not this path. Keep all edits synchronous.

### Adapter call shape (the exact change for AC1)

```python
# artifact_adapter.py  — _save_text and save_image today omit thread_id:
return self.service.save_artifact(
    project_id=self.project_id,
    owner_user_id=self.context.user_id,
    agent_run_id=self.context.agent_run_id,
    thread_id=self.context.thread_id,   # <-- ADD THIS (param already exists on save_artifact)
    kind=kind,
    name=name,
    content=content,
)
```

`save_artifact` is keyword-only and already validates `thread_id` against `project_id` via `_validate_thread` ([service.py](src/ai_qa/artifacts/service.py)); passing `None` is valid and is the existing behavior.

### Anti-patterns to avoid (FORBIDDEN)

- Re-introducing any direct filesystem or SeaweedFS/S3 write for artifact content in an agent or pipeline stage (architecture anti-pattern). All artifact bytes flow through `ArtifactService`.
- Rebuilding `PipelineArtifactAdapter`, `ArtifactService`, or the agents' existing write paths — extend/forward only.
- Emitting or reshaping `ArtifactChangeEvent` (that is Story 10.6's scope).
- Changing `kind` strings, `ArtifactResponse` fields, `PipelineContext` field names, or `save_artifact`/`create_version` signatures.
- Adding `create_run=True` to `/approve` to "fix" the run id — changes run semantics; out of scope.
- `# type: ignore` / `@ts-ignore`; global lint disables; mixing formatting with logic in one commit; `print()` instead of `logging`; bare `except:`/`except Exception:` (project rules).

### Previous-story / brownfield intelligence

- **Story 10.1** (the storage foundation, `done`) was itself a "RECONCILE + EXTEND" story and **shipped the `Artifact.thread_id` column, the `save_artifact(thread_id=...)` param, and `_validate_thread`** — explicitly flagged as *"foundation-only — no production caller passes `thread_id`"* (10.1 Review → Deferred). **Story 10.5 is the consumer that closes that loop.** See [10-1-project-artifact-storage-foundation.md](_bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md).
- **Stories 10.2 / 10.3 / 10.4** are in flight (`review` / `ready-for-dev`) and live partly in the working tree. They touch artifact *browsing/read/edit* (the UI + REST surface), **not** the agent write path — so 10.5's edits to `agents/`, `pipelines/artifact_adapter.py`, and the agent tests should not collide. If a merge conflict appears in `service.py`/`artifacts.py`, prefer their REST/read changes and keep 10.5 limited to the adapter `thread_id` forward.
- **Epic 6 (story 6-7)** introduced `PipelineContext` / `PipelineArtifactAdapter` and migrated Bob/Mary/Sarah off `workspace/*`. That is why the migration "already exists." The `tests/unit/test_workspace_adapters.py` header literally reads `"(Story 10.5)"` — reconcile against it; do not recreate it.
- **Git signal:** recent commits are Story 10.1 (`90d3f6f`), 10.7/10.8 (`04b2843`, `8c693db`), and Epic 9. Nothing in flight touches the agent write path other than the uncommitted 10.2/10.3/10.4 work above.

### Latest tech / dependencies

No new dependencies. Reuse the pinned stack (SQLAlchemy 2.0, Alembic 1.13, FastAPI 0.115, Pydantic v2, `boto3` for the S3/SeaweedFS backend). `uv` only for any package operation (never `pip`). `tempfile`/`shutil` are stdlib (Task 4 cleanup).

### Testing requirements

- **Backend (pytest):** in-memory SQLite; reuse the existing fixtures in [tests/integration/test_project_scoped_agents.py](tests/integration/test_project_scoped_agents.py) (it already builds `User`/`Project`/`Thread`/`AgentRun`/`Artifact`/`ArtifactVersion` tables and a bound `PipelineContext`) and [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py). `engine.dispose()` in teardown. No bare `pytest.raises(Exception)` — use a specific type + `match=`.
- **Coverage targets:** `thread_id` persisted on agent save when context carries it / `None` when it does not / cross-project thread rejected (AC1); cross-project read leak-canary returns only the bound project's artifacts (AC2); no-bypass import guard (AC3); approve-time save records `thread_id` with `agent_run_id=None` (Gap 2 documentation test).
- **Deletions:** removing `OutputWriter` (Task 2) deletes [tests/pipelines/test_output_writer.py](tests/pipelines/test_output_writer.py); updating `ScriptGenerator` (Task 3) edits ~8 constructor calls in [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py). Confirm the suite stays green after both.
- **Frontend:** none expected. Run `npm run typecheck` only if a file under `frontend/` is touched.

### Project Structure Notes

Touch points (all existing files — extend/forward/clean, no new core modules; the no-bypass guard test may be a new test file):

- [src/ai_qa/pipelines/artifact_adapter.py](src/ai_qa/pipelines/artifact_adapter.py) — forward `thread_id` in `_save_text` + `save_image` (AC1)
- [src/ai_qa/pipelines/output_writer.py](src/ai_qa/pipelines/output_writer.py) — **delete** (AC3); update [pipelines/__init__.py](src/ai_qa/pipelines/__init__.py) exports
- [src/ai_qa/pipelines/script_generator.py](src/ai_qa/pipelines/script_generator.py) — drop unused `output_base_dir` (AC3)
- [src/ai_qa/agents/sarah.py](src/ai_qa/agents/sarah.py) — remove `Path("/dev/null")` args; fix stale docstrings/warning (AC3)
- [src/ai_qa/agents/mary.py](src/ai_qa/agents/mary.py) — fix temp-dir leak in `_materialize_requirement_artifacts`; fix stale docstrings (AC3)
- [tests/integration/test_project_scoped_agents.py](tests/integration/test_project_scoped_agents.py) — cross-project read leak-canary (AC2)
- [tests/pipelines/test_pipeline_artifact_adapter.py](tests/pipelines/test_pipeline_artifact_adapter.py) — `thread_id` persistence cases (AC1)
- [tests/unit/test_workspace_adapters.py](tests/unit/test_workspace_adapters.py) — reconcile / add no-bypass guard (AC3)
- [tests/pipelines/test_output_writer.py](tests/pipelines/test_output_writer.py) — **delete** with `OutputWriter`
- [tests/pipelines/test_script_generator.py](tests/pipelines/test_script_generator.py) — update `ScriptGenerator(...)` call sites

No structural conflict with the unified project layout. `jack.py` is intentionally absent (Epic 15).

### References

- [Source: _bmad-output/planning-artifacts/epics.md#Story-10.5] (lines 869-890) + Epic 10 FRs FR45/FR46/FR52 (lines 215-221)
- [Source: _bmad-output/planning-artifacts/architecture.md:513-533] — "All AI Agents MUST… write artifacts through the artifact service"; FORBIDDEN: direct SeaweedFS access from agents
- [Source: _bmad-output/planning-artifacts/architecture.md:811-834] — agent data-flow: read prior stage via artifact service, write via `artifacts/service.py`; `jack.py` listed (Epic 15)
- [Source: src/ai_qa/pipelines/artifact_adapter.py:95-114] — `_save_text`/`save_image` omit `thread_id` (the AC1 gap)
- [Source: src/ai_qa/pipelines/context.py:11-21] — `PipelineContext` fields incl. `thread_id`
- [Source: src/ai_qa/api/routes.py:200-282] — `_build_pipeline_context` sets `thread_id` + `agent_run_id` (run only when `create_run=True`)
- [Source: src/ai_qa/api/routes.py:349-356, 389-408] — `/start` uses `create_run=True`; `/approve` does not
- [Source: src/ai_qa/agents/mary.py:284-316] — `_write_approved_test_cases` + temp-dir materialization leak
- [Source: src/ai_qa/agents/sarah.py:284-285, 401-402] — `ScriptGenerator(output_base_dir=Path("/dev/null"))`
- [Source: src/ai_qa/pipelines/output_writer.py] — legacy direct-filesystem writer (removal candidate)
- [Source: src/ai_qa/pipelines/__init__.py:11,22] — `OutputWriter` export
- [Source: _bmad-output/implementation-artifacts/10-1-project-artifact-storage-foundation.md] — `thread_id` column + `_validate_thread` shipped as foundation-only
- [Source: project-context.md] — `uv` only; Ruff + Mypy strict; sync vs async session rule; no `print`/bare-except; no secrets in artifacts; migration-in-DoD guardrail
- [Source: MEMORY.md → epic-10-artifact-ui-gotchas] — artifact path is sync session; reconcile-not-rebuild

### Definition of Done

- [ ] AC1–AC3 satisfied; all six tasks complete.
- [ ] `thread_id` is persisted on every agent-written artifact when the context carries one; `None` is tolerated; a cross-project thread is rejected.
- [ ] No agent or pipeline stage writes artifact content directly to the filesystem or a storage client (no-bypass guard test passes); `OutputWriter` removed (or proven unreachable + deprecated) without breaking imports.
- [ ] Cross-project read leak-canary proves agents read only their bound project's artifacts.
- [ ] **No DB migration required** — `Artifact.thread_id` already exists (migration `604f28c24393`); confirm `uv run alembic upgrade head` is a no-op and the schema is unchanged.
- [ ] `uv run ruff check .` clean; `uv run mypy` clean (strict).
- [ ] `uv run pytest` green, including the new AC1/AC2/AC3 tests and after the `OutputWriter`/`ScriptGenerator` edits.
- [ ] No frozen contract changed (`ArtifactChangeEvent`, `kind` strings, `ArtifactResponse` fields, `PipelineContext` fields, `save_artifact`/`create_version` signatures, `/start`+`/approve` semantics).
- [ ] `frontend/` untouched (or `npm run typecheck` clean if it was touched).
- [ ] Dev Agent Record updated with file list, commands run, and outputs.

### Decisions (CONFIRMED by Thuong 2026-06-11 — all defaults locked; implement these exactly)

- **D1 — `agent_run_id` for approve-time artifacts → KEEP DEFAULT.** Leave run-creation timing unchanged; approve-time saves carry `agent_run_id = None` and rely on the forwarded `thread_id` as the origin anchor (AC1 "where available"). Do **not** add `create_run=True` to `/approve`. (Task 1.3)
- **D2 — `OutputWriter` → DELETE.** Remove the class, its export from `pipelines/__init__.py`, and `tests/pipelines/test_output_writer.py` (no production caller). Keep `OutputMetadata`. The Task 2.4 "deprecate instead" fallback applies **only** if a hidden caller surfaces during the Task 2.1 grep. (Task 2)
- **D3 — `ScriptGenerator.output_base_dir` → REMOVE THE PARAM.** Drop it from `__init__`, remove the `Path("/dev/null")` args in Sarah, and update all ~8 `ScriptGenerator(...)` call sites in `tests/pipelines/test_script_generator.py` (+ the demo at `script_generator.py:599`). Do not take the "default to `None`" alternative. (Task 3)
- **D4 — `TestCaseExtractor` file-path interface → OUT OF SCOPE.** Mary's temp-dir materialization stays as the isolated compat seam (now leak-free, Task 4.2). The extractor refactor to in-memory content is deferred to Epic 12 — do not pull it into this story.

---

## Dev Agent Record

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed — comprehensive developer guide created.

### File List

### Change Log
