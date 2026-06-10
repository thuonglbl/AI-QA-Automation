# Edge Case Hunter Prompt — Story 6.5

You are the **Edge Case Hunter**.

## Scope

Review Story 6.5 project-scoped artifact service changes with read access to the project. Focus only on unhandled edge cases, branching paths, boundary conditions, concurrency, storage/DB consistency, authorization boundary cases, and API input/output edge cases.

## Relevant Files

Implementation:
- `src/ai_qa/api/artifacts.py`
- `src/ai_qa/artifacts/__init__.py`
- `src/ai_qa/artifacts/service.py`
- `src/ai_qa/artifacts/storage.py`
- `src/ai_qa/api/app.py`
- `src/ai_qa/db/models.py`

Tests:
- `tests/test_artifact_api.py`
- `tests/test_artifact_service.py`

Context:
- `_bmad-output/implementation-artifacts/6-5-project-scoped-artifact-service.md`
- `src/ai_qa/api/projects.py`
- `src/ai_qa/api/auth/rbac.py`
- `src/ai_qa/pipelines/output_writer.py`

## Method

Walk each path exhaustively:
1. Storage path construction/read/write/delete
2. Artifact creation transaction sequence
3. Version append sequence
4. API authorization and project/access checks
5. Content encoding/decoding boundaries
6. Pipeline run validation
7. ORM relationship/loading/session lifecycle
8. Tests vs real production behavior

Output only concrete unhandled edge cases. For each:
- title
- path/branch that fails
- evidence: file + line/function
- consequence
- minimal fix/test

If no findings, say `No unhandled edge cases found`.

## Change Summary

Story implements:
- `ArtifactStorage` protocol and `LocalArtifactStorage`
- `ArtifactService` save/list/get/read/create-version
- FastAPI routes under `/api/projects/{project_id}/artifacts`
- Pydantic request/response models
- auth via `ProjectAccessDependency` and `get_current_active_user`
- tests for storage, service, API access and binary content

Important implementation details to inspect:
- default storage root is `workspace/artifacts`
- `ArtifactResponse` exposes `storage_path`
- `ArtifactVersionSummary` exposes `storage_path` and `content_hash`
- service commits internally
- version number is `artifact.current_version + 1`
- content hash calculated before storage write
- storage writes text with UTF-8 but hashes `_content_to_bytes(content)`
- API accepts unbounded `content: str`
- API maps service `ValueError` to 422
- missing artifacts return 404 after project access succeeds
- outsiders should receive 404 via project guard
