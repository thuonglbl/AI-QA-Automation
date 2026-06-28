"""Core SQLAlchemy ORM models for project-scoped persistence."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
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
from ai_qa.db.types import UserSecretEncryptedString, UserSecretEncryptedText
from ai_qa.secrets.models import UserSecret  # noqa: F401  # register UserSecret mapper
from ai_qa.threads.models import AgentRun  # noqa: F401  # register AgentRun mapper


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Local account foundation for later authentication stories."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Nullable after Epic 23 / story 23.3: SSO-provisioned users have no local password
    # (the column is dropped entirely in 23.6). Local password login still works until then.
    # Stable Entra object id (oid) — the cross-login join key (email/UPN can change).
    # Populated on first SSO provision; email is the fallback match for pre-existing rows.
    azure_oid: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Best-effort Azure-synced avatar (Epic 23, story 23.4), stored as a `data:` URI.
    # Populated on SSO login when the Graph photo fetch succeeds; served from our own
    # backend (GET /auth/me/avatar). Null => the FE renders an initials fallback.
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    # IANA timezone (e.g. "Asia/Ho_Chi_Minh") set by an admin at user creation; the
    # frontend formats message timestamps in this zone. Defaults to UTC.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    conversation_language: Mapped[str] = mapped_column(String(10), nullable=False, default="en")

    created_projects: Mapped[list[Project]] = relationship(back_populates="created_by_user")
    memberships: Mapped[list[ProjectMembership]] = relationship(back_populates="user")
    artifact_versions: Mapped[list[ArtifactVersion]] = relationship(
        back_populates="created_by_user"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="user")
    secrets: Mapped[list[UserSecret]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project/workspace boundary for generated QA artifacts."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    confluence_base_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True, default=None
    )
    jira_base_url: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    # NOTE: Default is [] (empty list), but the frontend treats empty/missing as
    # "all providers enabled" for backward compatibility with pre-Epic-9 projects.
    # The API enforces at-least-one-provider on create/update, so API-created
    # projects always have a non-empty list. Direct DB writes bypass this guard.
    enabled_providers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # Named target environments for the app under test, e.g.
    # ``[{"name": "Production", "url": "https://app.example.com"}]``. Project-wide and
    # admin-managed; Sarah picks one when generating scripts and Jack (future) picks one
    # to run against. All optional — empty list is valid. URLs are NOT secrets.
    environments: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False, default=list)
    # Role names *of the application under test* (e.g. ["Admin", "User", "Guest"]).
    # Project-wide and admin-managed. DISTINCT from ``ProjectMembership.role`` /
    # ``User.role`` (which gate pipeline access) — these label which login a test runs as.
    # Together with ``environments`` they form the (environment × role) matrix a captured
    # browser session is keyed by. All optional — empty list is valid.
    app_roles: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    created_by_user: Mapped[User | None] = relationship(back_populates="created_projects")
    memberships: Mapped[list[ProjectMembership]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(back_populates="project")
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="project")


class CapturedSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A per-user captured browser session for a project's (environment, role).

    Holds a Playwright ``storageState`` blob (cookies + localStorage captured AFTER the
    user logged in) — the reusable proof-of-authentication that Sarah (script debug) and
    Jack (run, future) rehydrate via ``new_context(storage_state=...)``. The blob is a
    LIVE credential: encrypted at rest with the per-user-secrets Fernet key, NEVER
    returned to the frontend or written to logs/messages/artifacts. Keyed per user so
    each tester captures and owns their own session (no shared store).
    """

    __tablename__ = "captured_sessions"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "environment",
            "role",
            name="uq_captured_sessions_user_project_env_role",
        ),
        Index("ix_captured_sessions_user_project", "user_id", "project_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    # How the session was obtained: SSO_MANUAL | PASSWORD | API_TOKEN | SSO_TOTP.
    auth_method: Mapped[str] = mapped_column(String(20), nullable=False, default="SSO_MANUAL")
    # Encrypted Playwright storageState JSON — the single secret-bearing column.
    encrypted_storage_state: Mapped[str] = mapped_column(UserSecretEncryptedText, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


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


class AiProviderConfig(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-(user, project) non-secret AI provider configuration.

    Stores the user's last-approved provider/model selection as a default
    suggestion for future threads in the same project. Secrets (API keys)
    remain exclusively in ``user_secrets`` — never copied here (AC1).
    """

    __tablename__ = "ai_provider_configs"
    __table_args__ = (
        UniqueConstraint("user_id", "project_id", name="uq_ai_provider_configs_user_project"),
        Index("ix_ai_provider_configs_user_id", "user_id"),
        Index("ix_ai_provider_configs_project_id", "project_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    # Non-secret provider metadata: provider id, name, endpoint, test metadata, rationale.
    ai_provider_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    # Non-secret per-agent config: model, temperature, prompt_template, tools, rationale.
    ai_agents_config: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)


class Artifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Project-scoped generated artifact metadata."""

    __tablename__ = "artifacts"
    __table_args__ = (Index("ix_artifacts_project_kind", "project_id", "kind"),)

    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON, nullable=True)
    # Human-friendly title (e.g. Confluence page / Jira issue title) shown in the
    # UI instead of the numeric id embedded in `name`. Nullable for legacy rows.
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Source id of this artifact's PARENT page (Confluence), for rendering a
    # Confluence-like tree. Null for root pages and non-hierarchical sources (Jira).
    parent_source_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Ordered list of ancestor source ids (root to immediate parent) for full-chain tree.
    ancestor_source_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    project: Mapped[Project] = relationship(back_populates="artifacts")
    agent_run: Mapped[AgentRun | None] = relationship(back_populates="artifacts")
    versions: Mapped[list[ArtifactVersion]] = relationship(
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
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
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
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    agent_run_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    resource_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    details: Mapped[dict[str, object] | None] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    user: Mapped[User | None] = relationship(back_populates="audit_events")
    project: Mapped[Project | None] = relationship(back_populates="audit_events")
    agent_run: Mapped[AgentRun | None] = relationship(back_populates="audit_events")


# Sentinel capability meaning "applies to every agent" (a global benchmark score).
GLOBAL_CAPABILITY = "global"


class ModelBenchmarkScore(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Operator-supplied quality score for a model id (admin dashboard).

    Feeds Alice's Tier-0 model selection so admins can promote a brand-new model
    the curated/heuristic tiers do not yet rank. ``capability`` is ``"global"``
    for a score that applies to every agent, or a specific capability
    (reasoning/vision/instruction/coding/fast) to target one agent.
    """

    __tablename__ = "model_benchmark_scores"
    __table_args__ = (
        UniqueConstraint(
            "model_id", "capability", name="uq_model_benchmark_scores_model_capability"
        ),
        Index("ix_model_benchmark_scores_model_id", "model_id"),
    )

    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    capability: Mapped[str] = mapped_column(String(50), nullable=False, default=GLOBAL_CAPABILITY)
    # Float so admins can enter real benchmark numbers (e.g. SWE-bench 58.4) directly.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )


class TestExecutionResult(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Per-test result of a Jack execution run (Story 14.2/14.4).

    One row per ``(test, browser)``. The Jack ``agent_run`` IS the execution run —
    ``agent_run_id`` is the run id; the run-level summary lives on
    ``AgentRun.execution_metadata``. Provenance links back to the source script /
    test-case artifacts (``source_test_case_artifact_id`` is best-effort —
    "where available"). ``error_message``/``stack_trace`` are SCRUBBED of secrets
    by the runner before persistence (leak-canary convention).
    """

    __tablename__ = "test_execution_results"
    __table_args__ = (Index("ix_test_execution_results_project_status", "project_id", "status"),)
    # Not a pytest test class (name starts with "Test").
    __test__ = False

    agent_run_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    thread_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("threads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_script_artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_test_case_artifact_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True
    )
    test_name: Mapped[str] = mapped_column(String(512), nullable=False)
    browser: Mapped[str] = mapped_column(String(50), nullable=False, default="chromium")
    # Application role this test ran AS (Slice 6 role-grouped runs). The captured-session
    # role its script belongs to; NULL for role-less / single-session runs.
    role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    failure_classification: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stack_trace: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class DiscoveredModelSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Last-seen snapshot of a model advertised by a provider.

    Written on each successful Alice configuration run so the admin dashboard can
    list models to score WITHOUT holding live gateway credentials.
    """

    __tablename__ = "discovered_models"
    __table_args__ = (UniqueConstraint("model_id", name="uq_discovered_models_model_id"),)

    model_id: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supports_vision: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TestAccountCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Dedicated test-account credential for a project's (environment, role).

    Used to automatically generate a ``storageState`` session (Epic 25).
    Credentials are encrypted at rest with the per-user-secrets Fernet key,
    never leaked, and managed by Project Admins.
    """

    __tablename__ = "test_account_credentials"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "project_id",
            "environment",
            "role",
            name="uq_test_account_credentials_user_project_env_role",
        ),
        Index("ix_test_account_credentials_user_project", "user_id", "project_id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    username: Mapped[str] = mapped_column(UserSecretEncryptedString(1024), nullable=False)
    password: Mapped[str] = mapped_column(UserSecretEncryptedString(1024), nullable=False)
    # Optional TOTP seed for MFA bypass. Encrypted UserSecret.
    totp_secret: Mapped[str | None] = mapped_column(UserSecretEncryptedString, nullable=True)

    user: Mapped[User] = relationship()
    project: Mapped[Project] = relationship()
