# Sprint Change Proposal - Artifact Storage Optimization

## Section 1: Issue Summary
- **Trigger**: User requested performance optimization for the requirement extraction process (parsing phase). Additionally, the user requested a better organization of the artifacts folder structure in SeaweedFS.
- **Context**: Currently, the system saves raw HTML and URL text files into `mcp > confluence` which is unnecessary as the HTML is only needed in memory for generation and feedback. Artifacts are also lacking an explicit `reports` grouping, and Confluence images are being dumped into the default `artifacts` folder instead of alongside their requirement markdown files.
- **Evidence**: Saving `raw_html` takes unnecessary disk I/O and DB operations. The UI and SeaweedFS currently show scattered images instead of grouping them inside the `requirements` folder.

## Section 2: Impact Analysis
- **Epic Impact**: Epic 10 (Artifact Storage)
- **Story Impact**: Requires a new ad-hoc maintenance story or amendment to the current sprint to apply these tweaks.
- **Artifact Conflicts**: No conflicts.
- **Technical Impact**: Small code changes in `bob.py` (removing `save_raw_html`), `artifact_adapter.py` (removing raw HTML handling methods), and `storage.py` (updating `build_artifact_key` paths).

## Section 3: Recommended Approach
- **Direct Adjustment**: Implement the changes directly as a Minor scope maintenance task.
- **Rationale**: The change is well-contained, non-breaking, and the implementation plan is already fully mapped out and approved by the user.
- **Effort Estimate**: Very low (less than 1 hour).
- **Risk**: Very low (covered by existing unit tests which will just need their assertions updated).

## Section 4: Detailed Change Proposals

### Stories
Create a new maintenance task/story in the current sprint:
**Title**: Optimize Artifact Storage and Restructure Folders
**Description**:
1. Stop saving `raw_html` and URL text files during requirement extraction to improve I/O performance.
2. Group artifacts cleanly in SeaweedFS: `image`, `screenshot` and `configuration` (for `requirement.metadata`) go to `requirements` (same as `.md` files), `testcase` to `test_cases`, `testscript` to `test_scripts`, and everything else defaults to `reports` instead of `artifacts`.

### Code Changes (Approved Plan)
- `src/ai_qa/agents/bob.py`: Remove `save_raw_html` and `_save_text(kind="raw_html")`.
- `src/ai_qa/pipelines/artifact_adapter.py`: Remove `save_raw_html` and `load_raw_html` methods.
- `src/ai_qa/artifacts/storage.py`: Update `build_artifact_key` to match the new folder routing logic.
- **Tests**: Remove `raw_html` tests and update `folder_for_kind`/`build_artifact_key` assertions for `image` and `reports`.

## Section 5: Implementation Handoff
- **Scope**: Minor (Can be implemented directly by Developer agent / Quick Dev).
- **Handoff Recipients**: Developer Agent.
- **Success Criteria**:
  - `raw_html` is no longer saved to storage.
  - Newly extracted images are stored under `requirements/`.
  - All unit tests pass successfully.
