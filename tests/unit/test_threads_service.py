"""Unit tests for ThreadService."""

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.auth.session import UserSession
from ai_qa.db.base import Base
from ai_qa.db.models import User
from ai_qa.threads.models import AgentRun, Thread
from ai_qa.threads.schemas import ThreadCreate
from ai_qa.threads.service import ThreadAccessDeniedError, ThreadService


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def db_user(db_session: Session) -> User:
    user = User(
        email="owner@example.com",
        display_name="Owner",
        password_hash="hash",
        role="standard",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def db_thread(db_session: Session, db_user: User) -> Thread:
    thread = Thread(user_id=db_user.id)
    db_session.add(thread)
    db_session.commit()
    db_session.refresh(thread)
    return thread


class TestThreadService:
    def test_create_thread_sets_defaults(self, db_session: Session, db_user: User) -> None:
        service = ThreadService(db_session)
        user_session = UserSession(
            user_id=str(db_user.id), email=db_user.email, name=db_user.display_name
        )
        thread = service.create_thread(ThreadCreate(user_id=db_user.id), current_user=user_session)
        # First thread gets the sequential default title "1"; status/current_step
        # come from the model defaults.
        assert thread.title == "1"
        assert thread.status == "start"
        assert thread.current_step == 1

    def test_get_user_threads_returns_owned(self, db_session: Session, db_user: User) -> None:
        service = ThreadService(db_session)
        threads = service.get_user_threads(db_user.id)
        assert isinstance(threads, list)

    def test_assert_thread_access_owned_thread_passes(
        self, db_session: Session, db_thread: Thread
    ) -> None:
        service = ThreadService(db_session)
        # Unbound thread owned by the caller — should not raise.
        service.assert_thread_access(db_thread, db_thread.user_id)

    def test_assert_thread_access_other_user_raises(
        self, db_session: Session, db_thread: Thread
    ) -> None:
        service = ThreadService(db_session)
        with pytest.raises((ValueError, ThreadAccessDeniedError)):
            service.assert_thread_access(db_thread, uuid4())

    def test_create_agent_run_creates_run(self, db_session: Session, db_thread: Thread) -> None:
        service = ThreadService(db_session)
        run = service.create_agent_run(db_thread.id, "running")
        assert run.status == "running"
        assert run.thread_id == db_thread.id

    def test_update_agent_run_updates_status(self, db_session: Session, db_thread: Thread) -> None:
        service = ThreadService(db_session)
        run = service.create_agent_run(db_thread.id, "running")
        updated = service.update_agent_run(run.id, "completed")
        assert updated.status == "completed"

    def test_add_message_to_thread(self, db_session: Session, db_thread: Thread) -> None:
        service = ThreadService(db_session)
        msg = service.add_message(db_thread.id, "user", "Hello")
        assert msg.content == "Hello"
        assert msg.sender == "user"

    def test_get_thread_messages_returns_messages(
        self, db_session: Session, db_thread: Thread
    ) -> None:
        service = ThreadService(db_session)
        service.add_message(db_thread.id, "user", "Hi")
        service.add_message(db_thread.id, "agent", "Hello!")
        messages = service.get_thread_messages(db_thread.id)
        assert len(messages) == 2

    def test_reconcile_resets_processing_thread_to_start(
        self, db_session: Session, db_user: User
    ) -> None:
        thread = Thread(
            user_id=db_user.id, status="processing", current_step=2, current_agent="Bob"
        )
        db_session.add(thread)
        db_session.commit()
        db_session.refresh(thread)

        service = ThreadService(db_session)
        threads_reset, runs_reset = service.reconcile_interrupted_work()
        db_session.refresh(thread)

        assert (threads_reset, runs_reset) == (1, 0)
        assert thread.status == "start"
        # current_step/agent are preserved so the user retries the SAME step.
        assert thread.current_step == 2
        assert thread.current_agent == "Bob"
        # Exactly one explanatory system message is appended.
        messages = service.get_thread_messages(thread.id)
        assert len(messages) == 1
        assert messages[0].sender == "system"
        assert messages[0].message_type == "warning"
        assert "interrupted" in messages[0].content.lower()

    def test_reconcile_marks_running_run_interrupted_without_cascade(
        self, db_session: Session, db_user: User
    ) -> None:
        thread = Thread(user_id=db_user.id, status="processing")
        db_session.add(thread)
        db_session.commit()
        db_session.refresh(thread)
        run = AgentRun(thread_id=thread.id, status="running")
        db_session.add(run)
        db_session.commit()
        db_session.refresh(run)

        service = ThreadService(db_session)
        threads_reset, runs_reset = service.reconcile_interrupted_work()
        db_session.refresh(thread)
        db_session.refresh(run)

        assert (threads_reset, runs_reset) == (1, 1)
        assert run.status == "interrupted"
        # The run's thread is reset to "start" — NOT cascaded to the run's status.
        assert thread.status == "start"

    def test_reconcile_clean_boot_is_noop(self, db_session: Session, db_user: User) -> None:
        thread = Thread(user_id=db_user.id, status="review_request")
        db_session.add(thread)
        db_session.commit()
        db_session.refresh(thread)
        run = AgentRun(thread_id=thread.id, status="completed")
        db_session.add(run)
        db_session.commit()

        service = ThreadService(db_session)
        threads_reset, runs_reset = service.reconcile_interrupted_work()
        db_session.refresh(thread)

        assert (threads_reset, runs_reset) == (0, 0)
        assert thread.status == "review_request"
        assert service.get_thread_messages(thread.id) == []

    def test_reconcile_is_idempotent(self, db_session: Session, db_user: User) -> None:
        thread = Thread(user_id=db_user.id, status="processing")
        db_session.add(thread)
        db_session.commit()

        service = ThreadService(db_session)
        service.reconcile_interrupted_work()
        threads_reset, runs_reset = service.reconcile_interrupted_work()

        # Second pass finds nothing left to reset and adds no duplicate message.
        assert (threads_reset, runs_reset) == (0, 0)
        assert len(service.get_thread_messages(thread.id)) == 1
