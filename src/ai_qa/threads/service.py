"""Service for managing threads."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from ai_qa.api.auth.session import UserSession
from ai_qa.threads.models import AgentRun, Message, Thread
from ai_qa.threads.schemas import ThreadCreate, ThreadUpdate


class ThreadAccessDeniedError(Exception):
    """Raised when a user loses project-membership access to a bound thread.

    Carries no resource details so the API layer can map it to a generic
    ``404 Resource not found`` response, mirroring
    ``require_project_member_or_admin`` and avoiding existence leaks.
    """


class ThreadService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_thread(self, thread_create: ThreadCreate, current_user: UserSession) -> Thread:
        """Create a new thread."""
        user_id_str = current_user.user_id
        if user_id_str is None:
            raise ValueError("Invalid user session: missing user_id")
        user_id = UUID(user_id_str)

        if thread_create.user_id != user_id:
            raise ValueError("Cannot create thread for another user")

        # Check membership/access if project_id is provided
        if thread_create.project_id:
            from ai_qa.auth.service import ADMIN_ROLE
            from ai_qa.db.models import Project, User

            project = self.db.get(Project, thread_create.project_id)
            if not project:
                raise ValueError(f"Project {thread_create.project_id} not found")

            db_user = self.db.get(User, user_id)
            if not db_user:
                raise ValueError(f"User {user_id} not found")

            if db_user.role != ADMIN_ROLE:
                from sqlalchemy import select

                from ai_qa.db.models import ProjectMembership

                membership = self.db.execute(
                    select(ProjectMembership)
                    .where(ProjectMembership.project_id == thread_create.project_id)
                    .where(ProjectMembership.user_id == user_id)
                ).scalar_one_or_none()
                if not membership:
                    raise ValueError("User is not a member of the target project")

        # Assign a default sequential title ("N") based on how many threads the
        # user already has (archived included, so numbers never collide).
        from sqlalchemy import func, select

        existing_count = self.db.execute(
            select(func.count()).select_from(Thread).where(Thread.user_id == thread_create.user_id)
        ).scalar_one()

        thread = Thread(
            user_id=thread_create.user_id,
            project_id=thread_create.project_id,
            title=f"{existing_count + 1}",
        )
        self.db.add(thread)
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def bind_project(self, thread_id: UUID, project_id: UUID, user_id: UUID) -> Thread:
        """Bind a project to an unbound thread."""
        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        if thread.user_id != user_id:
            raise ValueError("Cannot modify thread owned by another user")

        if thread.project_id is not None:
            raise ValueError("Thread is already bound to a project")

        from ai_qa.auth.service import ADMIN_ROLE
        from ai_qa.db.models import Project, User

        project = self.db.get(Project, project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found")

        db_user = self.db.get(User, user_id)
        if not db_user:
            raise ValueError(f"User {user_id} not found")

        if db_user.role != ADMIN_ROLE:
            from sqlalchemy import select

            from ai_qa.db.models import ProjectMembership

            membership = self.db.execute(
                select(ProjectMembership)
                .where(ProjectMembership.project_id == project_id)
                .where(ProjectMembership.user_id == user_id)
            ).scalar_one_or_none()
            if not membership:
                raise ValueError("User is not a member of the target project")

        thread.project_id = project_id
        self.db.commit()
        self.db.refresh(thread)
        return thread

    def update_thread(
        self,
        thread_id: UUID,
        user_id: UUID,
        *,
        thread_update: ThreadUpdate,
    ) -> Thread:
        """Update a thread's title and/or archived state (owner only)."""
        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        if thread.user_id != user_id:
            raise ValueError("Cannot modify thread owned by another user")

        if thread_update.title is not None:
            thread.title = thread_update.title
        if thread_update.is_archived is not None:
            thread.is_archived = thread_update.is_archived

        self.db.commit()
        self.db.refresh(thread)
        return thread

    def add_message(
        self,
        thread_id: UUID,
        sender: str,
        content: str,
        agent_name: str | None = None,
        message_type: str = "text",
        message_metadata: dict[str, Any] | None = None,
    ) -> Message:
        """Add a message to a thread."""
        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        message = Message(
            thread_id=thread_id,
            sender=sender,
            content=content,
            agent_name=agent_name,
            message_type=message_type,
            message_metadata=message_metadata,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def get_thread_messages(self, thread_id: UUID) -> list[Message]:
        """Get all messages for a thread."""
        from sqlalchemy import select

        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        messages = (
            self.db.execute(
                select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)
            )
            .scalars()
            .all()
        )
        return list(messages)

    def create_agent_run(
        self,
        thread_id: UUID,
        status: str,
        summary: str | None = None,
        execution_metadata: dict[str, Any] | None = None,
    ) -> AgentRun:
        """Create an agent run for a thread."""
        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        run = AgentRun(
            thread_id=thread_id,
            status=status,
            summary=summary,
            execution_metadata=execution_metadata,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def update_agent_run(
        self,
        run_id: UUID,
        status: str | None = None,
        summary: str | None = None,
        execution_metadata: dict[str, Any] | None = None,
        current_step: int | None = None,
        *,
        expected_thread_id: UUID | None = None,
    ) -> AgentRun:
        """Update an agent run and sync its thread's status and current_step.

        When ``expected_thread_id`` is provided, the run must belong to that
        thread. A mismatch raises ``ThreadAccessDeniedError`` *before* any
        mutation, so a caller cannot update (or leak the existence of) a run
        bound to a different thread/project. Internal callers that already
        trust the run id omit this argument.
        """
        from ai_qa.threads.models import AgentRun

        run = self.db.get(AgentRun, run_id)
        if not run:
            raise ValueError(f"AgentRun {run_id} not found")

        if expected_thread_id is not None and run.thread_id != expected_thread_id:
            raise ThreadAccessDeniedError()

        if status is not None:
            run.status = status
            run.thread.status = status

        if summary is not None:
            run.summary = summary

        if execution_metadata is not None:
            run.execution_metadata = execution_metadata

        if current_step is not None:
            run.thread.current_step = current_step

        self.db.commit()
        self.db.refresh(run)
        return run

    def get_user_threads(self, user_id: UUID, *, is_admin: bool = False) -> list[Thread]:
        """Get non-archived threads for a user, scoped to current project access.

        For non-admins, threads bound to a project the user no longer belongs to
        are excluded. Unbound threads (``project_id IS NULL``) and threads in
        still-active memberships remain. Admins see all their own threads.
        """
        from sqlalchemy import select

        from ai_qa.db.models import ProjectMembership

        stmt = select(Thread).where(Thread.user_id == user_id).where(Thread.is_archived.is_(False))

        if not is_admin:
            member_project_ids = select(ProjectMembership.project_id).where(
                ProjectMembership.user_id == user_id
            )
            stmt = stmt.where(
                Thread.project_id.is_(None) | Thread.project_id.in_(member_project_ids)
            )

        stmt = stmt.order_by(Thread.updated_at.desc())
        threads = self.db.execute(stmt).scalars().all()
        return list(threads)

    def assert_thread_access(self, thread: Thread, user_id: UUID) -> None:
        """Enforce ownership and current project membership for a thread.

        Layered on top of ownership: a project-bound thread is only accessible
        to its owner while that owner is a global admin or an active member of
        the bound project.

        Raises:
            ValueError: if the thread is owned by a different user (existing
                ownership semantics).
            ThreadAccessDeniedError: if the owner has lost membership on the
                thread's bound project (mapped to a generic 404 by the API).
        """
        if thread.user_id != user_id:
            raise ValueError("Cannot access thread owned by another user")

        if thread.project_id is not None:
            from ai_qa.db.models import User
            from ai_qa.projects.service import user_can_access_project

            user = self.db.get(User, user_id)
            if user is None or not user_can_access_project(self.db, user, thread.project_id):
                raise ThreadAccessDeniedError()

    def get_thread_details(self, thread_id: UUID, user_id: UUID) -> Thread:
        """Get full details of a thread for its owner with active project access."""
        thread = self.db.get(Thread, thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        self.assert_thread_access(thread, user_id)

        return thread
