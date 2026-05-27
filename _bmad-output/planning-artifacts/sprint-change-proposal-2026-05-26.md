# Sprint Change Proposal

## Section 1: Issue Summary
- **Trigger**: Bug reported on Bob's process status displaying "Read Confluence page via MCP: processing" instead of "request_review".
- **Context**: Discovered during testing of the requirements extraction step where the user expects the UI to update its process status alongside the backend transitioning to `request_review`.
- **Evidence**: The frontend UI continues to show "processing" because the `thinking_trace` emitted by the backend overwrote the message instead of explicitly indicating the "request_review" state.

## Section 2: Impact Analysis
- **Epic Impact**: Minimal. Confined to UI representation of the existing requirement extraction epic.
- **Story Impact**: A new bug-fix story is needed to address the thinking_trace update in Bob's process.
- **Artifact Conflicts**: No major conflict with existing architecture or PRD.
- **Technical Impact**: Small code change in `src/ai_qa/agents/bob.py` affecting the websocket payload for the `thinking_trace`.

## Section 3: Recommended Approach
- **Direct Adjustment**: Modify the code directly within the current sprint to correct the string passed to `chain_of_thought`.
- **Rationale**: It's a quick fix that improves user experience without impacting the overall sprint timeline.
- **Effort**: Low (minor code edit).

## Section 4: Detailed Change Proposals
### src/ai_qa/agents/bob.py
**Rationale**: The frontend relies on the last thinking trace to display the Process Status. By updating this before returning confirm_parent, the UI will reflect "request_review" instead of "processing".

```diff
-                        "chain_of_thought": [
-                            "Connect status: OK",
-                            f"Requirements page: {suggested}",
-                        ],
+                        "chain_of_thought": [
+                            "Connect status: OK",
+                            "Read Confluence page via MCP: request_review",
+                        ],
```

## Section 5: Implementation Handoff
- **Scope**: Minor
- **Handoff Recipients**: Developer agent
- **Success Criteria**: The frontend correctly displays "Read Confluence page via MCP: request_review" when the user is prompted to confirm the requirements link.
