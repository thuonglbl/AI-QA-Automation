# Acceptance Auditor Prompt — Story 6.5

You are the **Acceptance Auditor**.

## Task

Review the Story 6.5 implementation against the story/spec below. Check for:
- acceptance criteria violations
- deviations from spec intent
- missing required behavior
- contradictions between constraints and actual code
- unsafe omissions hidden by tests

Output findings as a Markdown list. Each finding must include:
- one-line title
- violated AC/constraint
- evidence from implementation
- required correction

If no findings, say `No acceptance findings`.

## Story Spec Summary

Story: `6-5-project-scoped-artifact-service`

Acceptance Criteria:
1. Artifact metadata persisted with project ownership:
   - artifact row: `project_id`, `kind`, `name`, `storage_path`, `current_version`, timestamps, optional `pipeline_run_id`
   - initial version row: version 1, content hash, storage path, created by user, timestamps
   - response schemas expose safe metadata, not raw ORM graphs
2. Large content stored through local storage abstraction:
   - text or bytes content
   - use `LocalArtifactStorage`, not direct agent filesystem writes
   - deterministic, traversal-safe paths
   - atomic/temp-file behavior to prevent corrupt partial output
   - swappable storage interface
3. Versions preserve edit history:
   - append version `current_version + 1`
   - artifact current version/path point to newest
   - earlier versions queryable/unchanged
   - hash changes when content changes
4. Project membership gates artifact access:
   - non-members rejected without artifact data/hidden project details
   - admins may access any project metadata
   - unauthenticated/deleted/inactive/stale users rejected consistently
5. Agents consume cohesive service contract rather than hard-coded workspace paths:
   - service supports save/list/read/version
   - legacy OutputWriter remains compatibility boundary until Story 6.7
   - supports artifact type filters

Implementation Expectations:
- FastAPI routes under `/api/projects/{project_id}/artifacts`
- Include router from `create_app()` under `/api`
- Reuse `get_current_active_user()` and `require_project_member_or_admin()` / project access helper
- Generic unauthorized errors; avoid hidden-project leaks
- Prevent path traversal; artifact names/storage keys untrusted
- Store content through narrow storage interface
- no external storage/network calls
- validate kinds centrally
- validate non-empty reasonable-length names
- derive filenames from sanitized names plus artifact/version IDs
- hash exact bytes written with SHA-256
- careful DB/file transaction cleanup
- default local root acceptable as `workspace/artifacts/` if settings not available
- leave legacy `OutputWriter` intact

## Implementation Under Review

Files:
- `src/ai_qa/api/app.py`
- `src/ai_qa/api/artifacts.py`
- `src/ai_qa/artifacts/__init__.py`
- `src/ai_qa/artifacts/service.py`
- `src/ai_qa/artifacts/storage.py`
- `src/ai_qa/db/models.py`
- `tests/test_artifact_api.py`
- `tests/test_artifact_service.py`

Important observed details:
- API router prefix: `/projects/{project_id}/artifacts`; included under `/api`
- Routes: list/create/detail/content/create-version
- Auth: `ProjectAccessDependency`; writes also use `get_current_active_user`
- `ArtifactResponse` includes `storage_path`
- `ArtifactVersionSummary` includes `content_hash`, `storage_path`, and `created_by_user_id`
- API supports `content_encoding` of `text` or `base64`
- Service validates kind and name, pipeline_run project ownership
- Service uses internal `db.commit()` and cleanup on exception after storage write
- Storage root: `workspace/artifacts`
- Storage path shape: `projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}`
- Storage rejects absolute paths and `..` parts
- Tests report full regression passed: 474 passed, 2 skipped

## Specific Code Excerpts

### app router inclusion
```python
from ai_qa.api.artifacts import router as artifacts_router
...
app.include_router(artifacts_router, prefix="/api")
```

### service transaction/write pattern
```python
artifact = Artifact(... storage_path="pending", current_version=1)
self.db.add(artifact)
self.db.flush()
storage_path = self.storage.write(... content=content)
artifact.storage_path = storage_path
artifact.versions.append(ArtifactVersion(... content_hash=hashlib.sha256(_content_to_bytes(content)).hexdigest()))
self.db.commit()
```

### storage pattern
```python
self.root = Path(root).resolve()
safe_name = sanitize_artifact_name(name)
storage_path = f"projects/{project_id}/artifacts/{artifact_id}/v{version}/{safe_name}"
temp_path = target_path.with_name(f".{target_path.name}.tmp.{uuid.uuid4().hex}")
# write temp, replace target, cleanup temp on exception
```

### API schema exposure
```python
class ArtifactResponse(BaseModel):
    id: UUID
    project_id: UUID
    pipeline_run_id: UUID | None
    kind: str
    name: str
    storage_path: str
    current_version: int
    created_at: datetime
    updated_at: datetime

class ArtifactVersionSummary(BaseModel):
    id: UUID
    artifact_id: UUID
    version: int
    content_hash: str
    storage_path: str | None
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
```
