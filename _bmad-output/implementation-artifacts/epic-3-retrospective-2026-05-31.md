# Epic 3 Retrospective

## Epic Summary

Epic 3 connected the system to real source content and delivered the first end-to-end extraction workflow. It added MCP client integration, Confluence page retrieval, content parsing, structured output writing, and Bob’s review-oriented extraction agent.

## What Went Well

- On-prem MCP integration was established, enabling secure access to Confluence content without external data transmission.
- The Confluence reader pipeline stage successfully retrieved page content and metadata via MCP tools.
- The content parser converted raw Confluence content into cleaner markdown, preserved images, and extracted diagram and test structure hints.
- The output writer stage made results persist safely with metadata and atomic file writes.
- Bob’s agent workflow enabled paginated review, letting users approve or reject extracted pages one at a time.

## Challenges

- MCP tool discovery and failure handling proved to be a fragile integration point and required robust retry and error messaging.
- Confluence content varied widely in markup and macros, so parsing HTML, macros, diagrams, and images required many heuristics.
- Preserving output integrity while writing files atomically was important to avoid corrupt partial output in the workspace.
- Paginated review introduced state complexity around per-page approval, rejection, and feedback-driven reprocessing.

## Key Insights

- StageResult-based pipeline stages are a strong pattern for keeping failure modes explicit and recoverable.
- Early investment in content parsing heuristics pays off by making later LLM stages consume much cleaner markdown.
- Human-in-the-loop review at the extraction stage is valuable because it catches source-level issues before they cascade into test generation.

## Action Items

- Add richer Confluence URL validation and user guidance for common URL formats.
- Expand content parser coverage for additional macro types and diagram conversions.
- Improve MCP connection diagnostics so users can quickly resolve server or auth problems.
- Add more automated tests around writer atomicity and per-page Bob review transitions.

## Next Epic Preview

Epic 4 uses the cleaned requirements output from Epic 3 and turns it into structured test cases with an LLM abstraction, then delivers Mary’s per-test-case review workflow.
