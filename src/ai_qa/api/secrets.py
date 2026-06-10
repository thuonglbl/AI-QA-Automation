"""Per-user secret status and replacement API routes.

This router puts a thin, user-facing REST surface on top of the Story 9.1
storage primitive (``ai_qa.secrets.service``):

* ``GET /secrets/status`` — read-only configured/missing metadata for every
  canonical secret type. It NEVER returns a stored secret value or any masked /
  reversible representation of it (AC1).
* ``PUT /secrets/{secret_type}`` — replacement-only flow: validate the format,
  securely upsert (replace/supersede) the previous encrypted value, and return
  status metadata only (AC2, AC3).

Ownership is always derived from the authenticated session (``current_user.id``);
no endpoint accepts a ``user_id`` parameter (FR36).
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.rbac import get_current_active_user
from ai_qa.db.models import User
from ai_qa.secrets import (
    CANONICAL_SECRET_TYPES,
    SECRET_TYPE_BROWSER_USE,
    SECRET_TYPE_CLAUDE,
    SECRET_TYPE_GEMINI,
    SECRET_TYPE_MCP,
    SECRET_TYPE_ON_PREMISES,
    SECRET_TYPE_OPENAI,
)
from ai_qa.secrets.service import (
    SecretStatus,
    get_secret_status,
    list_secret_status,
    set_user_secret,
    validate_secret_format,
)

DbSessionDependency = Depends(get_db_session_dependency)
CurrentUserDependency = Depends(get_current_active_user)

UNKNOWN_SECRET_TYPE_DETAIL = "Unknown secret type"
SECRET_TYPE_MISMATCH_DETAIL = "secret_type in body does not match the path"

# Human-readable provider labels sourced from the UX provider table
# (ux-design-specification.md §AI Provider Selection).
PROVIDER_DISPLAY_NAMES: dict[str, str] = {
    SECRET_TYPE_CLAUDE: "Claude",
    SECRET_TYPE_OPENAI: "OpenAI",
    SECRET_TYPE_GEMINI: "Gemini / ChatGPT",
    SECRET_TYPE_BROWSER_USE: "Browser Use Cloud",
    SECRET_TYPE_ON_PREMISES: "On-Premises",
    SECRET_TYPE_MCP: "MCP",
}

router = APIRouter(prefix="/secrets", tags=["secrets"])


class SecretStatusResponse(BaseModel):
    """Secret-free status representation for credential management views.

    By construction this model carries NO secret bytes — there is no ``value``,
    ``encrypted_value``, or masked/reversible token field (AC1, AC3).
    """

    model_config = ConfigDict(from_attributes=True)

    secret_type: str
    provider_name: str
    configured: bool
    status: str
    validation_state: str
    last_updated: datetime | None


class SecretReplaceRequest(BaseModel):
    """Write-only replacement payload.

    ``value`` is request-only and must never appear in any response model. An
    optional ``secret_type`` may be supplied for client convenience; when
    present it must match the path parameter.
    """

    value: str
    secret_type: str | None = None


def _response_for_status(status: SecretStatus) -> SecretStatusResponse:
    """Map a :class:`SecretStatus` to its secret-free response model."""
    return SecretStatusResponse(
        secret_type=status.secret_type,
        provider_name=PROVIDER_DISPLAY_NAMES.get(status.secret_type, status.secret_type),
        configured=status.configured,
        status=status.status,
        validation_state=status.validation_state,
        last_updated=status.last_updated,
    )


@router.get("/status", response_model=list[SecretStatusResponse])
async def list_status(
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> list[SecretStatusResponse]:
    """Return configured/missing status for every canonical secret type.

    Scoped to the authenticated user only; no secret value is ever returned.
    """
    statuses = list_secret_status(db, current_user.id)
    return [_response_for_status(status) for status in statuses]


@router.put("/{secret_type}", response_model=SecretStatusResponse)
async def replace_secret(
    secret_type: str,
    payload: SecretReplaceRequest,
    current_user: User = CurrentUserDependency,
    db: Session = DbSessionDependency,
) -> SecretStatusResponse:
    """Replace (or supersede) the current user's secret for ``secret_type``.

    Validates the canonical type and format, then performs the secure upsert and
    commits. Returns status metadata only — never the stored value.
    """
    if secret_type not in CANONICAL_SECRET_TYPES:
        raise HTTPException(status_code=422, detail=UNKNOWN_SECRET_TYPE_DETAIL)

    if payload.secret_type is not None and payload.secret_type != secret_type:
        raise HTTPException(status_code=400, detail=SECRET_TYPE_MISMATCH_DETAIL)

    try:
        validate_secret_format(secret_type, payload.value)
    except ValueError as exc:
        # The submitted value is never placed in the detail or logs.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Store the stripped value so "future runs use the new value" matches what a
    # later (Story 9.3) connection test will validate.
    set_user_secret(db, current_user.id, secret_type, payload.value.strip())
    db.commit()

    return _response_for_status(get_secret_status(db, current_user.id, secret_type))


__all__ = [
    "PROVIDER_DISPLAY_NAMES",
    "SecretReplaceRequest",
    "SecretStatusResponse",
    "router",
]
