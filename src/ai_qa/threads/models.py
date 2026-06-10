"""SQLAlchemy ORM models for the Threads domain."""

from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import JSON, Boolean, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_qa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from ai_qa.db.models import Artifact, AuditEvent


class Thread(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Conversation thread context."""

    __tablename__ = "threads"
    __table_args__ = (Index("ix_threads_project_user", "project_id", "user_id"),)

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="start")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provider_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    provider_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    current_agent: Mapped[str] = mapped_column(String(50), nullable=False, default="Alice")

    messages: Mapped[list["Message"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="Message.created_at"
    )
    agent_configs: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="thread", cascade="all, delete-orphan", order_by="AgentRun.created_at"
    )


class Message(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Individual message within a conversation thread."""

    __tablename__ = "messages"

    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sender: Mapped[str] = mapped_column(String(50), nullable=False)
    agent_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    message_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    thread: Mapped[Thread] = relationship(back_populates="messages")


class AgentRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution record of an agent workflow."""

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_thread_status", "thread_id", "status"),)

    thread_id: Mapped[UUID] = mapped_column(
        ForeignKey("threads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_metadata: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)

    thread: Mapped[Thread] = relationship(back_populates="agent_runs")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="agent_run")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="agent_run")
