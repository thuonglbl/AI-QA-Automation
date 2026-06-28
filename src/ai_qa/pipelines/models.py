"""Pipeline-specific data models.

Models for pipeline stage inputs and outputs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConfluencePage(BaseModel):
    """Represents a retrieved Confluence page.

    Attributes:
        page_id: Unique page identifier from Confluence
        title: Page title
        content: Raw HTML or markdown content
        space_key: Confluence space key (e.g., "TEST")
        url: Original URL used to retrieve the page
        retrieved_at: ISO 8601 timestamp when page was retrieved
        author: Page author (optional)
        version: Page version number (optional)
        labels: List of page labels/tags
    """

    page_id: str = Field(description="Unique page identifier from Confluence")
    title: str = Field(description="Page title")
    content: str = Field(description="Raw HTML or markdown content")
    space_key: str = Field(description="Confluence space key (e.g., 'TEST')")
    url: str = Field(description="Original URL used to retrieve the page")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp when page was retrieved",
    )
    author: str | None = Field(default=None, description="Page author")
    version: int | None = Field(default=None, description="Page version number")
    labels: list[str] = Field(default_factory=list, description="List of page labels/tags")

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at_timezone(cls, v: datetime) -> datetime:
        """Ensure retrieved_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")


class JiraIssue(BaseModel):
    """Represents a retrieved Jira issue.

    Attributes:
        issue_key: Issue key (e.g. "PROJ-123")
        summary: Issue summary/title
        description: Issue description body
        acceptance_criteria: Acceptance criteria text (from description or custom field)
        status: Issue status name
        labels: List of issue labels
        project_key: Jira project key
        url: Direct URL to the issue in Jira
        retrieved_at: ISO 8601 timestamp when issue was retrieved
        issue_type: Issue type name (e.g. "Story", "Bug")
        reporter: Display name of reporter
        assignee: Display name of assignee
    """

    issue_key: str = Field(description="Jira issue key (e.g. 'PROJ-123')")
    summary: str = Field(description="Issue summary/title")
    description: str | None = Field(default=None, description="Issue description body")
    acceptance_criteria: str | None = Field(default=None, description="Acceptance criteria text")
    status: str | None = Field(default=None, description="Issue status name")
    labels: list[str] = Field(default_factory=list, description="List of issue labels")
    project_key: str = Field(description="Jira project key")
    url: str = Field(description="Direct URL to the issue in Jira")
    retrieved_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp when issue was retrieved",
    )
    issue_type: str | None = Field(default=None, description="Issue type name")
    reporter: str | None = Field(default=None, description="Display name of reporter")
    assignee: str | None = Field(default=None, description="Display name of assignee")

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("retrieved_at")
    @classmethod
    def validate_retrieved_at_timezone(cls, v: datetime) -> datetime:
        """Ensure retrieved_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")


class ParsedContent(BaseModel):
    """Represents LLM-optimized content parsed from a Confluence page."""

    page_id: str = Field(description="Source Confluence page ID")
    page_title: str = Field(description="Source page title")
    source_url: str = Field(description="Original Confluence page URL")
    markdown: str = Field(description="Clean Markdown text for LLM consumption")
    mermaid_diagrams: list[str] = Field(
        default_factory=list,
        description=(
            "Extracted diagram definitions. Pure Mermaid blocks are stored verbatim. "
            "PlantUML blocks are prefixed with '%% PlantUML original format\\n' so callers "
            "can detect the type without a separate field. Draw.io conversions use Mermaid syntax."
        ),
    )
    image_paths: list[str] = Field(
        default_factory=list,
        description="Relative paths to saved images under workspace/requirements/",
    )
    test_cases_detected: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Detected test case structures: {title, preconditions, steps, expected_results}",
    )
    parsed_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp of parse operation",
    )

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("parsed_at")
    @classmethod
    def validate_parsed_at_timezone(cls, v: datetime) -> datetime:
        """Ensure parsed_at is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("parsed_at must be timezone-aware")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")


QualityCategory = Literal[
    "unsupported_content",
    "missing_expected_results",
    "missing_preconditions",
    "vague_language",
    "ambiguous_ui_reference",
    "insufficient_content",
]


class QualityIssue(BaseModel):
    """A single detected quality issue on a source requirement page."""

    category: QualityCategory
    location: str
    message: str
    impact: str

    model_config = ConfigDict(validate_assignment=True)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")


class PageSummary(BaseModel):
    """Summary for page listing operations.

    Used when listing pages in a space without fetching full content.

    Attributes:
        page_id: Unique page identifier
        title: Page title
        url: Full page URL
        last_modified: When page was last modified (optional)
    """

    page_id: str = Field(description="Unique page identifier")
    title: str = Field(description="Page title")
    url: str = Field(description="Full page URL")
    last_modified: datetime | None = Field(default=None, description="When page was last modified")
    version: int | None = Field(
        default=None, description="Confluence revision number (for change detection)"
    )
    parent_id: str | None = Field(
        default=None, description="Immediate parent page id (for hierarchy), None for the root"
    )
    ancestor_ids: list[str] = Field(
        default_factory=list,
        description="Ordered list of ancestor page ids (root to immediate parent)",
    )

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("last_modified")
    @classmethod
    def validate_last_modified_timezone(cls, v: datetime | None) -> datetime | None:
        """Ensure last_modified is timezone-aware if present."""
        if v is not None and v.tzinfo is None:
            raise ValueError("last_modified must be timezone-aware")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")


class OutputMetadata(BaseModel):
    """Metadata accompanying generated files."""

    source_url: str = Field(description="Original source URL")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="ISO 8601 timestamp",
    )
    model: str | None = Field(default=None, description="Model used for generation")
    confidence: float | None = Field(default=None, description="Confidence score")

    model_config = ConfigDict(validate_assignment=True)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp_timezone(cls, v: datetime) -> datetime:
        """Ensure timestamp is timezone-aware."""
        if v.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return v

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return self.model_dump(mode="json")
