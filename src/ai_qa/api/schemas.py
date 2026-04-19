"""Pydantic schemas for API request/response validation.

These models define the structure of data exchanged between frontend and backend.
"""

from pydantic import BaseModel, Field


class StartRequest(BaseModel):
    """Request body for /api/start endpoint."""

    step: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Pipeline step to start (1-5)",
    )
    input_data: dict[str, object] = Field(
        default_factory=dict,
        description="Step-specific input data (e.g., Confluence URL for step 2)",
    )


class ActionResponse(BaseModel):
    """Response for pipeline action endpoints."""

    success: bool = Field(description="Whether the action was accepted")
    message: str = Field(description="Human-readable status message")
    current_step: int = Field(description="Current pipeline step after action")
    status: str = Field(description="Agent status (start/processing/review/done)")


class ApproveRequest(BaseModel):
    """Request body for /api/approve endpoint."""

    step: int = Field(ge=1, le=5, description="Step being approved")
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being approved (for paginated review)",
    )


class RejectRequest(BaseModel):
    """Request body for /api/reject endpoint."""

    step: int = Field(ge=1, le=5, description="Step being rejected")
    feedback: str = Field(
        min_length=1,
        max_length=2000,
        description="User feedback explaining why output is rejected",
    )
    item_index: int | None = Field(
        default=None,
        description="Index of specific item being rejected (for paginated review)",
    )


class ContinueRequest(BaseModel):
    """Request body for /api/continue endpoint."""

    from_step: int = Field(ge=1, le=5, description="Step that was just completed")
