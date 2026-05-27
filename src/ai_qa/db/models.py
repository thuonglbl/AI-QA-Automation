"""Core SQLAlchemy ORM models for project-scoped persistence."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_qa.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Local account foundation for later authentication stories."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    settings: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    ai_provider_config: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    ai_agents_config: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_projects: Mapped[list["Project"]] = relationship(back_populates="created_by_user")
    memberships: Mapped[list["ProjectMembership"]] = relationship(back_populates="user")
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="started_by_user")
    artifact_versions: Mapped[list["ArtifactVersion"]] = relationship(
        back_populates="created_by_user"
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="user")


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project/workspace boundary for generated QA artifacts."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confluence_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="start")
    conversation_data: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    created_by_user: Mapped[User | None] = relationship(back_populates="created_projects")
    memberships: Mapped[list["ProjectMembership"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    pipeline_runs: Mapped[list["PipelineRun"]] = relationship(back_populates="project")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="project")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="project")


class ProjectMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """User-to-project membership and role assignment."""

    __tablename__ = "project_memberships"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_memberships_project_user"),
        Index("ix_project_memberships_user_project", "user_id", "project_id"),
    )

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="member")

    project: Mapped[Project] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(back_populates="memberships")


class PipelineRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution history for a project-scoped QA generation pipeline."""

    __tablename__ = "pipeline_runs"
    __table_args__ = (Index("ix_pipeline_runs_project_status", "project_id", "status"),)

    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    started_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    config_summary: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )

    project: Mapped[Project | None] = relationship(back_populates="pipeline_runs")
    started_by_user: Mapped[User | None] = relationship(back_populates="pipeline_runs")
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="pipeline_run")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="pipeline_run")


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project-scoped generated artifact metadata."""

    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_kind", "project_id", "kind"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    project: Mapped[Project] = relationship(back_populates="artifacts")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="artifacts")
    versions: Mapped[list["ArtifactVersion"]] = relationship(
        back_populates="artifact", cascade="all, delete-orphan"
    )


class ArtifactVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Versioned artifact metadata and content hash."""

    __tablename__ = "artifact_versions"
    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_artifact_versions_artifact_version"),
    )

    artifact_id: Mapped[UUID] = mapped_column(
        ForeignKey("artifacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    artifact: Mapped[Artifact] = relationship(back_populates="versions")
    created_by_user: Mapped[User | None] = relationship(back_populates="artifact_versions")


class AuditEvent(UUIDPrimaryKeyMixin, Base):
    """Compliance and troubleshooting audit trail."""

    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_project_event_created", "project_id", "event_type", "created_at"),
    )

    user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    pipeline_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="audit_events")
    project: Mapped[Project | None] = relationship(back_populates="audit_events")
    pipeline_run: Mapped[PipelineRun | None] = relationship(back_populates="audit_events")
