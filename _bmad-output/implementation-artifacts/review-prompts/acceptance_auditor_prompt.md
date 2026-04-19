# Acceptance Auditor Review Prompt

## Your Role
You are an **Acceptance Auditor**. Review the diff against the spec and check for violations of acceptance criteria, deviations from spec intent, missing implementation of specified behavior, and contradictions between spec constraints and actual code.

## Spec File Content

```yaml
# Story 3.2: Confluence Reader Pipeline Stage

Status: review

## Story
As a R&D engineer,
I want a Confluence reader pipeline stage that retrieves page content via MCP,
So that Bob can extract test case content from any Confluence page URL.

## Acceptance Criteria

Given a valid Confluence page URL is provided
When the confluence reader executes
Then it retrieves the full page content via MCP confluence.py tools (FR2)
And returns a StageResult with page title, content body, and metadata
And handles MCP server unavailability with graceful failure and clear error message (NFR11)
And multiple pages from a Confluence space can be discovered and listed
And the stage works with the Confluence page URL as the pipeline trigger (FR10)

## Technical Requirements

### Core Functionality
- Implement ConfluenceReader pipeline stage in src/ai_qa/pipelines/confluence_reader.py
- Use existing MCPClient from Story 3.1 to communicate with MCP server
- Support both single page retrieval and space-wide page discovery
- Parse Confluence URLs to extract page IDs, space keys, and other identifiers
- Return structured content with metadata via StageResult model

### Key Components Required

1. ConfluenceReader Class with methods:
   - read_page(page_url: str) -> StageResult
   - list_pages_in_space(space_key: str) -> StageResult
   - read_multiple_pages(page_urls: list[str]) -> StageResult

2. Data Models:
   - ConfluencePage: page_id, title, content, space_key, url, retrieved_at, author, version, labels
   - PageSummary: page_id, title, url, last_modified

3. URL Parsing Utilities:
   - ConfluenceURLParser with extract_page_id, extract_space_key, normalize_url

### Error Handling Requirements
- MCPConnectionError -> StageResult with error message and retry suggestion
- MCPToolError -> StageResult with specific tool failure details
- Invalid URL -> StageResult with validation error and URL format guidance
- Page not found -> StageResult with 404-style error message

### Critical Constraints
- MUST NOT use .env files - all configuration user-prompted
- All error scenarios return StageResult with clear actionable messages per NFR11
- StageResult contract: success=True requires empty errors list
- Pydantic models only - never raw dicts for internal exchange

### NFR Compliance Required
- NFR5 (On-premises): Local MCP server only, no external APIs
- NFR6 (No credential logging): User-prompted keys, never logged
- NFR7 (SSO reuse): Browser session handles auth
- NFR11 (Graceful failure): All errors wrapped in StageResult
- NFR12 (Retry logic): Inherited from MCPClient
```

## Diff to Review

See files in:
- `src/ai_qa/pipelines/__init__.py`
- `src/ai_qa/pipelines/confluence_reader.py`
- `src/ai_qa/pipelines/models.py`
- `tests/pipelines/__init__.py`
- `tests/pipelines/test_confluence_reader.py`
- `tests/pipelines/test_confluence_url_parser.py`

## Instructions

1. Compare the implementation against EACH acceptance criterion
2. Check for violations of spec constraints (especially "MUST NOT use .env")
3. Verify StageResult contract compliance
4. Check NFR compliance (NFR5, NFR6, NFR7, NFR11, NFR12)
5. Identify missing implementation of specified behavior
6. Look for contradictions between spec and code

## Output Format

```markdown
- **[AC Violation: Criterion Name]** - Which AC it violates and evidence from diff
- **[Missing Implementation]** - What spec requires but code doesn't implement
- **[Constraint Violation]** - Spec constraint contradicted by implementation
- **[NFR Non-compliance]** - Which NFR and evidence of violation
```

Be specific. Cite line numbers or file paths where possible.
