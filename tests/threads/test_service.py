"""Tests for ThreadService."""

from collections.abc import Generator
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import Table, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.auth.session import UserSession
from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User
from ai_qa.threads.models import AgentRun, Message, Thread
from ai_qa.threads.schemas import ThreadCreate, ThreadUpdate
from ai_qa.threads.service import ThreadAccessDeniedError, ThreadService


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=cast(
            list[Table],
            [
                User.__table__,
                Project.__table__,
                Thread.__table__,
                ProjectMembership.__table__,
                AgentRun.__table__,
                Message.__table__,
            ],
        ),
    )
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def user(db_session: Session) -> User:
    user = User(
        email="test@example.com", display_name="Test", password_hash="hash", role="standard"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def project(db_session: Session) -> Project:
    project = Project(name="Test Project", description="Test")
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def test_create_thread_success(db_session: Session, user: User) -> None:
    """Test creating a thread for a user."""
    service = ThreadService(db_session)
    thread_schema = ThreadCreate(user_id=user.id)
    user_session = UserSession(user_id=str(user.id), email=user.email, name=user.display_name)
    thread = service.create_thread(thread_schema, current_user=user_session)

    assert thread.id is not None
    assert thread.user_id == user.id
    assert thread.project_id is None


def test_create_thread_rbac_failure(db_session: Session, user: User) -> None:
    """Test creating a thread for a different user fails."""
    service = ThreadService(db_session)
    other_user_id = uuid4()
    thread_schema = ThreadCreate(user_id=other_user_id)
    user_session = UserSession(user_id=str(user.id), email=user.email, name=user.display_name)

    with pytest.raises(ValueError, match="Cannot create thread for another user"):
        service.create_thread(thread_schema, current_user=user_session)


def test_bind_project_success(db_session: Session, user: User, project: Project) -> None:
    """Test binding a project to an unbound thread."""
    service = ThreadService(db_session)

    # Add project membership first
    from ai_qa.db.models import ProjectMembership

    membership = ProjectMembership(project_id=project.id, user_id=user.id, role="member")
    db_session.add(membership)
    db_session.commit()

    # Create thread manually for test setup
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    updated_thread = service.bind_project(thread.id, project.id, user.id)
    assert updated_thread.project_id == project.id


def test_bind_project_already_bound(db_session: Session, user: User, project: Project) -> None:
    """Test binding a project to a thread that is already bound fails."""
    service = ThreadService(db_session)

    # Create bound thread
    thread = Thread(user_id=user.id, project_id=project.id)
    db_session.add(thread)
    db_session.commit()

    other_project_id = uuid4()
    with pytest.raises(ValueError, match="Thread is already bound to a project"):
        service.bind_project(thread.id, other_project_id, user.id)


def test_bind_project_not_owner(db_session: Session, user: User, project: Project) -> None:
    """Test binding a project to a thread owned by someone else fails."""
    service = ThreadService(db_session)

    # Create thread owned by someone else
    other_user_id = uuid4()
    thread = Thread(user_id=other_user_id)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot modify thread owned by another user"):
        service.bind_project(thread.id, project.id, user.id)


def test_add_message_success(db_session: Session, user: User) -> None:
    """Test adding a message to a thread."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    message = service.add_message(thread.id, role="user", content="Hello world")
    assert message.id is not None
    assert message.thread_id == thread.id
    assert message.role == "user"
    assert message.content == "Hello world"


def test_get_thread_messages(db_session: Session, user: User) -> None:
    """Test retrieving messages for a thread in order."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    service.add_message(thread.id, role="user", content="First")
    service.add_message(thread.id, role="agent", content="Second")

    messages = service.get_thread_messages(thread.id)
    assert len(messages) == 2
    assert messages[0].content == "First"
    assert messages[1].content == "Second"


def test_create_agent_run(db_session: Session, user: User) -> None:
    """Test creating an agent run."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    run = service.create_agent_run(thread.id, status="running")
    assert run.id is not None
    assert run.thread_id == thread.id
    assert run.status == "running"


def test_update_agent_run(db_session: Session, user: User) -> None:
    """Test updating agent run syncs thread current_step and status."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id, current_step=1, status="start")
    db_session.add(thread)
    db_session.commit()

    run = service.create_agent_run(thread.id, status="running")

    updated_run = service.update_agent_run(
        run.id, status="completed", summary="Done", current_step=2
    )
    assert updated_run.status == "completed"
    assert updated_run.summary == "Done"

    db_session.refresh(thread)
    assert thread.status == "completed"
    assert thread.current_step == 2


def test_get_user_threads(db_session: Session, user: User) -> None:
    """Test retrieving threads for a specific user."""
    service = ThreadService(db_session)
    other_user_id = uuid4()

    # Create threads for the user
    t1 = Thread(user_id=user.id, current_step=1, status="start")
    t2 = Thread(user_id=user.id, current_step=2, status="completed")

    # Create thread for another user
    t3 = Thread(user_id=other_user_id, current_step=1, status="start")

    db_session.add_all([t1, t2, t3])
    db_session.commit()

    threads = service.get_user_threads(user.id)
    assert len(threads) == 2
    assert {t.id for t in threads} == {t1.id, t2.id}


def test_get_thread_details_success(db_session: Session, user: User) -> None:
    """Test retrieving full thread details for the owner."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    service.add_message(thread.id, role="user", content="Hello")
    service.create_agent_run(thread.id, status="running")

    db_session.commit()

    details = service.get_thread_details(thread.id, user.id)
    assert details.id == thread.id
    assert len(details.messages) == 1
    assert len(details.agent_runs) == 1


def test_get_thread_details_forbidden(db_session: Session, user: User) -> None:
    """Test retrieving thread details for a non-owner fails."""
    service = ThreadService(db_session)
    other_user_id = uuid4()
    thread = Thread(user_id=other_user_id)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot access thread owned by another user"):
        service.get_thread_details(thread.id, user.id)


def test_create_thread_assigns_default_title(db_session: Session, user: User) -> None:
    """New threads get a sequential numeric default title ('N')."""
    service = ThreadService(db_session)
    user_session = UserSession(user_id=str(user.id), email=user.email, name=user.display_name)

    first = service.create_thread(ThreadCreate(user_id=user.id), current_user=user_session)
    second = service.create_thread(ThreadCreate(user_id=user.id), current_user=user_session)

    assert first.title == "1"
    assert second.title == "2"


def test_update_thread_rename(db_session: Session, user: User) -> None:
    """update_thread sets a custom title for the owner."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    updated = service.update_thread(
        thread.id, user.id, thread_update=ThreadUpdate(title="My Renamed Thread")
    )
    assert updated.title == "My Renamed Thread"


def test_update_thread_archive(db_session: Session, user: User) -> None:
    """update_thread can flip the archived flag."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id)
    db_session.add(thread)
    db_session.commit()

    updated = service.update_thread(
        thread.id, user.id, thread_update=ThreadUpdate(is_archived=True)
    )
    assert updated.is_archived is True


def test_update_thread_not_owner(db_session: Session, user: User) -> None:
    """update_thread rejects edits to another user's thread."""
    service = ThreadService(db_session)
    other_user_id = uuid4()
    thread = Thread(user_id=other_user_id)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot modify thread owned by another user"):
        service.update_thread(thread.id, user.id, thread_update=ThreadUpdate(title="Nope"))


def test_get_user_threads_excludes_archived(db_session: Session, user: User) -> None:
    """Archived threads are hidden from the user's thread list."""
    service = ThreadService(db_session)
    active = Thread(user_id=user.id, current_step=1, status="start")
    archived = Thread(user_id=user.id, current_step=1, status="start", is_archived=True)
    db_session.add_all([active, archived])
    db_session.commit()

    threads = service.get_user_threads(user.id)
    assert {t.id for t in threads} == {active.id}


# ---------------------------------------------------------------------------
# Story 7.6: Membership removal access enforcement
# ---------------------------------------------------------------------------


def _add_membership(db_session: Session, project_id: object, user_id: object) -> None:
    db_session.add(ProjectMembership(project_id=project_id, user_id=user_id, role="member"))
    db_session.commit()


def test_get_user_threads_hides_removed_project_threads(
    db_session: Session, user: User, project: Project
) -> None:
    """Threads bound to a project the user no longer belongs to are hidden."""
    service = ThreadService(db_session)

    # A second project the user is still a member of.
    other_project = Project(name="Other Project", description="Other")
    db_session.add(other_project)
    db_session.commit()
    _add_membership(db_session, other_project.id, user.id)

    # No membership for `project` -> user has been removed from it.
    removed = Thread(user_id=user.id, project_id=project.id, current_step=1, status="start")
    unbound = Thread(user_id=user.id, project_id=None, current_step=1, status="start")
    member_bound = Thread(
        user_id=user.id, project_id=other_project.id, current_step=1, status="start"
    )
    db_session.add_all([removed, unbound, member_bound])
    db_session.commit()

    threads = service.get_user_threads(user.id)

    assert {t.id for t in threads} == {unbound.id, member_bound.id}


def test_get_user_threads_admin_sees_own_threads(db_session: Session, project: Project) -> None:
    """An admin still sees their own threads even without project membership."""
    admin = User(
        email="admin@example.com", display_name="Admin", password_hash="hash", role="admin"
    )
    db_session.add(admin)
    db_session.commit()

    service = ThreadService(db_session)
    bound = Thread(user_id=admin.id, project_id=project.id, current_step=1, status="start")
    unbound = Thread(user_id=admin.id, project_id=None, current_step=1, status="start")
    db_session.add_all([bound, unbound])
    db_session.commit()

    threads = service.get_user_threads(admin.id, is_admin=True)

    assert {t.id for t in threads} == {bound.id, unbound.id}


def test_assert_thread_access_denied_for_removed_member(
    db_session: Session, user: User, project: Project
) -> None:
    """A bound thread is inaccessible once the owner loses project membership."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id, project_id=project.id)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ThreadAccessDeniedError):
        service.assert_thread_access(thread, user.id)


def test_assert_thread_access_allows_active_member(
    db_session: Session, user: User, project: Project
) -> None:
    """The owner keeps access while membership on the bound project is active."""
    _add_membership(db_session, project.id, user.id)
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id, project_id=project.id)
    db_session.add(thread)
    db_session.commit()

    # Should not raise.
    service.assert_thread_access(thread, user.id)


def test_assert_thread_access_allows_admin_without_membership(
    db_session: Session, project: Project
) -> None:
    """A global admin bypasses the project-membership requirement."""
    admin = User(
        email="admin2@example.com", display_name="Admin", password_hash="hash", role="admin"
    )
    db_session.add(admin)
    db_session.commit()

    service = ThreadService(db_session)
    thread = Thread(user_id=admin.id, project_id=project.id)
    db_session.add(thread)
    db_session.commit()

    # Should not raise despite no membership row.
    service.assert_thread_access(thread, admin.id)


def test_assert_thread_access_unbound_thread_allows_owner(db_session: Session, user: User) -> None:
    """An unbound (personal) thread stays accessible to its owner."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id, project_id=None)
    db_session.add(thread)
    db_session.commit()

    service.assert_thread_access(thread, user.id)


def test_assert_thread_access_rejects_different_owner(db_session: Session, user: User) -> None:
    """A different owner still raises the ownership ValueError (not 404 path)."""
    service = ThreadService(db_session)
    thread = Thread(user_id=uuid4(), project_id=None)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ValueError, match="Cannot access thread owned by another user"):
        service.assert_thread_access(thread, user.id)


def test_get_thread_details_denied_after_membership_removal(
    db_session: Session, user: User, project: Project
) -> None:
    """get_thread_details surfaces ThreadAccessDeniedError for a removed member."""
    service = ThreadService(db_session)
    thread = Thread(user_id=user.id, project_id=project.id)
    db_session.add(thread)
    db_session.commit()

    with pytest.raises(ThreadAccessDeniedError):
        service.get_thread_details(thread.id, user.id)
