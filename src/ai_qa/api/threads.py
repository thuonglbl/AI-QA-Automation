import logging
from typing import Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import UserSession
from ai_qa.api.schemas import ActionResponse, ConversationData, ConversationSaveRequest
from ai_qa.auth.service import ADMIN_ROLE
from ai_qa.threads.models import Thread
from ai_qa.threads.schemas import (
    AgentConfigEntry,
    AgentRunCreate,
    AgentRunResponse,
    AgentRunUpdate,
    MessageCreate,
    MessageResponse,
    ProviderConfigResponse,
    ThreadCreate,
    ThreadDetailsResponse,
    ThreadResponse,
    ThreadUpdate,
)
from ai_qa.threads.service import ThreadAccessDeniedError, ThreadService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/threads", tags=["threads"])

DbSessionDependency = Depends(get_db_session_dependency)

# Generic, detail-free denial reused for project-membership loss so the
# response never reveals whether a thread/project exists (mirrors
# require_project_member_or_admin in api/projects.py).
RESOURCE_NOT_FOUND_DETAIL = "Resource not found"


def get_current_user(request: Request) -> UserSession:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return cast(UserSession, user)


def _authorize_thread(thread_id: UUID, user_id: UUID, db: Session) -> Thread:
    """Load a thread and enforce ownership + current project membership.

    Mapping:
    - Missing thread -> 404 "Thread not found".
    - Owned by a different user -> 403 (existing ownership behavior).
    - Owner lost membership on the bound project -> generic 404 so no
      thread/project/artifact/agent-run detail leaks.
    """
    thread = db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    try:
        ThreadService(db).assert_thread_access(thread, user_id)
    except ThreadAccessDeniedError as exc:
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL) from exc
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Forbidden thread access") from exc
    return thread


@router.post("", response_model=ThreadResponse, status_code=201)
def create_thread(
    thread_create: ThreadCreate,
    request: Request,
    db: Session = DbSessionDependency,
) -> ThreadResponse:
    """Create a new thread."""
    current_user = get_current_user(request)
    service = ThreadService(db)
    try:
        thread = service.create_thread(thread_create, current_user)
        return ThreadResponse.model_validate(thread)
    except ValueError as e:
        err_msg = str(e)
        if "not a member" in err_msg or "another user" in err_msg:
            raise HTTPException(status_code=403, detail=err_msg) from e
        if "not found" in err_msg:
            raise HTTPException(status_code=404, detail=err_msg) from e
        raise HTTPException(status_code=400, detail=err_msg) from e
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail="Invalid project_id or user_id") from e
    except Exception as e:
        logger.exception("Unhandled error in create_thread")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("", response_model=list[ThreadResponse])
def get_user_threads_api(
    request: Request,
    db: Session = DbSessionDependency,
) -> list[ThreadResponse]:
    """Get all threads for the current user, scoped to current project access."""
    current_user = get_current_user(request)
    service = ThreadService(db)
    is_admin = (current_user.role or "").lower() == ADMIN_ROLE
    threads = service.get_user_threads(UUID(str(current_user.user_id)), is_admin=is_admin)
    return [ThreadResponse.model_validate(t) for t in threads]


@router.get("/{thread_id}", response_model=ThreadDetailsResponse)
def get_thread_details_api(
    thread_id: UUID,
    request: Request,
    db: Session = DbSessionDependency,
) -> ThreadDetailsResponse:
    """Get full details of a thread for the current user."""
    current_user = get_current_user(request)
    thread = _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)
    return ThreadDetailsResponse.model_validate(thread)


@router.patch("/{thread_id}", response_model=ThreadResponse)
def update_thread_api(
    thread_id: UUID,
    thread_update: ThreadUpdate,
    request: Request,
    db: Session = DbSessionDependency,
) -> ThreadResponse:
    """Update a thread's title and/or archived state (owner only)."""
    current_user = get_current_user(request)
    service = ThreadService(db)
    try:
        thread = service.update_thread(
            thread_id,
            UUID(str(current_user.user_id)),
            thread_update=thread_update,
        )
        return ThreadResponse.model_validate(thread)
    except ValueError as e:
        err_msg = str(e)
        if "another user" in err_msg:
            raise HTTPException(status_code=403, detail=err_msg) from e
        raise HTTPException(status_code=404, detail=err_msg) from e


@router.post("/{thread_id}/bind", response_model=ThreadResponse)
def bind_project(
    thread_id: UUID,
    project_id: UUID,
    request: Request,
    db: Session = DbSessionDependency,
) -> ThreadResponse:
    """Bind a project to a thread."""
    current_user = get_current_user(request)
    service = ThreadService(db)
    try:
        thread = service.bind_project(thread_id, project_id, UUID(str(current_user.user_id)))
        return ThreadResponse.model_validate(thread)
    except ValueError as e:
        err_msg = str(e)
        if "modify thread owned by another user" in err_msg:
            raise HTTPException(status_code=403, detail=err_msg) from e
        if "not found" in err_msg:
            raise HTTPException(status_code=404, detail=err_msg) from e
        if "not a member" in err_msg:
            raise HTTPException(status_code=403, detail=err_msg) from e
        raise HTTPException(status_code=400, detail=err_msg) from e
    except IntegrityError as e:
        raise HTTPException(status_code=400, detail="Invalid project_id") from e


@router.get("/{thread_id}/conversation", response_model=ConversationData)
def get_thread_conversation(
    thread_id: UUID,
    request: Request,
    db: Session = DbSessionDependency,
) -> ConversationData:
    """Get thread's saved conversation history from database."""
    current_user = get_current_user(request)
    thread = _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    try:
        service = ThreadService(db)
        messages = service.get_thread_messages(thread_id)
        from ai_qa.api.schemas import ConversationMessage

        conv_messages = [
            ConversationMessage(
                id=str(m.id),
                sender=cast(Literal["agent", "user", "system"], m.sender),
                agent_name=m.agent_name,
                content=m.content,
                timestamp=m.created_at,
                message_type=m.message_type,
                metadata=m.message_metadata,
            )
            for m in messages
        ]

        return ConversationData(
            messages=conv_messages,
            current_step=thread.current_step,
            status=thread.status,
            current_agent=thread.current_agent,
            updated_at=thread.updated_at,
        )
    except Exception as e:
        logger.error("Failed to load conversation for thread %s: %s", thread_id, e)
        return ConversationData()


@router.post("/{thread_id}/conversation", response_model=ActionResponse)
def save_thread_conversation(
    thread_id: UUID,
    request_data: ConversationSaveRequest,
    request: Request,
    db: Session = DbSessionDependency,
) -> ActionResponse:
    """Save thread's conversation history to database."""
    from ai_qa.threads.models import Message

    current_user = get_current_user(request)
    thread = _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    try:
        # Clear existing messages and insert new ones.
        # flush() after delete ensures the DELETE is written to the DB session
        # before we start inserting, so a crash before commit only loses the new
        # messages (not all messages).
        db.query(Message).filter(Message.thread_id == thread_id).delete()
        db.flush()

        for msg in request_data.conversation.messages:
            db_msg = Message(
                thread_id=thread_id,
                sender=msg.sender,
                agent_name=msg.agent_name,
                content=msg.content,
                message_type=msg.message_type,
                message_metadata=msg.metadata,
                created_at=msg.timestamp,
            )
            # Make sure we use the frontend's ID if we want, but since they are UUID Primary Keys,
            # we should parse it if it's a valid UUID, otherwise let it default.
            try:
                db_msg.id = UUID(msg.id)
            except Exception:
                pass

            db.add(db_msg)

        thread.current_step = request_data.conversation.current_step
        thread.status = request_data.conversation.status
        thread.current_agent = request_data.conversation.current_agent
        db.commit()
        return ActionResponse(
            success=True,
            message="Conversation saved",
            current_step=request_data.conversation.current_step,
            status=request_data.conversation.status,
        )
    except Exception as e:
        db.rollback()
        logger.error("Failed to save conversation for thread %s: %s", thread_id, e)
        raise HTTPException(status_code=500, detail=f"Failed to save conversation: {e}") from e


@router.get("/{thread_id}/messages", response_model=list[MessageResponse])
def get_thread_messages_api(
    thread_id: UUID,
    request: Request,
    db: Session = DbSessionDependency,
) -> list[MessageResponse]:
    current_user = get_current_user(request)
    _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    service = ThreadService(db)
    messages = service.get_thread_messages(thread_id)
    return [MessageResponse.model_validate(m) for m in messages]


@router.post("/{thread_id}/messages", response_model=MessageResponse, status_code=201)
def add_thread_message_api(
    thread_id: UUID,
    message: MessageCreate,
    request: Request,
    db: Session = DbSessionDependency,
) -> MessageResponse:
    current_user = get_current_user(request)
    _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    service = ThreadService(db)
    msg = service.add_message(
        thread_id,
        message.sender,
        message.content,
        agent_name=message.agent_name,
        message_type=message.message_type,
        message_metadata=message.message_metadata,
    )
    return MessageResponse.model_validate(msg)


@router.post("/{thread_id}/runs", response_model=AgentRunResponse, status_code=201)
def create_agent_run_api(
    thread_id: UUID,
    run: AgentRunCreate,
    request: Request,
    db: Session = DbSessionDependency,
) -> AgentRunResponse:
    current_user = get_current_user(request)
    _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    service = ThreadService(db)
    created_run = service.create_agent_run(
        thread_id, run.status, run.summary, run.execution_metadata
    )
    return AgentRunResponse.model_validate(created_run)


@router.get("/{thread_id}/provider-config", response_model=ProviderConfigResponse)
def get_thread_provider_config(
    thread_id: UUID,
    request: Request,
    db: Session = DbSessionDependency,
) -> ProviderConfigResponse:
    """Return non-secret provider configuration for a thread (Story 9.7).

    Returns the thread snapshot if present; falls back to the saved (user, project)
    default. Never returns secrets, API keys, or credential values.
    Authorization: thread owner only.
    """
    from ai_qa.agents.alice import PROVIDER_OPTIONS, AliceAgent
    from ai_qa.userconfig.service import get_provider_config

    current_user = get_current_user(request)
    user_id = UUID(str(current_user.user_id))
    thread = _authorize_thread(thread_id, user_id, db)

    _provider_display_names = {p["id"]: p["name"] for p in PROVIDER_OPTIONS}

    def _build_agent_entries(agent_configs: dict[str, object] | None) -> list[AgentConfigEntry]:
        if not agent_configs:
            return []
        entries = []
        for name, raw in agent_configs.items():
            if isinstance(raw, dict):
                model = raw.get("model") or raw.get("model_name")
                temperature = float(raw.get("temperature", 0.0))
                rationale = str(raw.get("rationale", ""))
            else:
                model = raw if isinstance(raw, str) else None
                temperature = 0.0
                rationale = ""
            entries.append(
                AgentConfigEntry(
                    agent=name,
                    model=model,
                    temperature=temperature,
                    rationale=rationale,
                )
            )
        return entries

    # Source 1: thread snapshot
    if thread.provider_name:
        return ProviderConfigResponse(
            configured=True,
            source="thread",
            provider=thread.provider_name,
            provider_name=_provider_display_names.get(
                thread.provider_name, thread.provider_name.capitalize()
            ),
            endpoint=AliceAgent._mask_endpoint(thread.provider_base_url or ""),
            test_result=None,
            tested_at=None,
            agents=_build_agent_entries(thread.agent_configs),
        )

    # Source 2: saved (user, project) default
    if thread.project_id:
        saved = get_provider_config(db, user_id, thread.project_id)
        if saved and saved.get("provider"):
            prov = saved["provider"] or {}
            agt_data = (saved.get("agents") or {}).get("agents") or {}
            return ProviderConfigResponse(
                configured=True,
                source="saved",
                provider=prov.get("provider"),
                provider_name=prov.get("provider_name"),
                endpoint=AliceAgent._mask_endpoint(prov.get("endpoint", "")),
                test_result=prov.get("test_result"),
                tested_at=prov.get("tested_at"),
                agents=[
                    AgentConfigEntry(
                        agent=n,
                        model=v.get("model"),
                        temperature=float(v.get("temperature", 0.0)),
                        rationale=v.get("rationale", ""),
                    )
                    for n, v in agt_data.items()
                ],
            )

    return ProviderConfigResponse(configured=False, source="none")


@router.patch("/{thread_id}/runs/{run_id}", response_model=AgentRunResponse)
def update_agent_run_api(
    thread_id: UUID,
    run_id: UUID,
    run_update: AgentRunUpdate,
    request: Request,
    db: Session = DbSessionDependency,
) -> AgentRunResponse:
    current_user = get_current_user(request)
    _authorize_thread(thread_id, UUID(str(current_user.user_id)), db)

    service = ThreadService(db)
    try:
        updated_run = service.update_agent_run(
            run_id,
            run_update.status,
            run_update.summary,
            run_update.execution_metadata,
            run_update.current_step,
            expected_thread_id=thread_id,
        )
        return AgentRunResponse.model_validate(updated_run)
    except ThreadAccessDeniedError as e:
        # Run belongs to a different thread/project — generic 404, no leak.
        raise HTTPException(status_code=404, detail=RESOURCE_NOT_FOUND_DETAIL) from e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
