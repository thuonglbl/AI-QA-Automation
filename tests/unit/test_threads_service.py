"""Unit tests for Thread service."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from ai_qa.threads.models import Thread
from ai_qa.threads.service import ThreadAccessDeniedError, ThreadService


class TestThreadService:
    def test_create_thread_sets_defaults(self, db_session):
        service = ThreadService(db_session)
        thread = service.create_thread(
            MagicMock(title="Test Thread", project_id=None),
            MagicMock(),
        )
        assert thread.title == "Test Thread"
        assert thread.status == "active"
        assert thread.current_step == 1

    def test_get_user_threads_returns_owned(self, db_session, db_user):
        service = ThreadService(db_session)
        threads = service.get_user_threads(db_user.id)
        assert isinstance(threads, list)

    def test_assert_thread_access_owned_thread_passes(self, db_session, db_thread):
        thread = db_session.get(Thread, db_thread.id)
        service = ThreadService(db_session)
        # Should not raise
        service.assert_thread_access(thread, db_thread.user_id)

    def test_assert_thread_access_other_user_raises(self, db_session, db_thread):
        other_user_id = uuid4()
        thread = db_session.get(Thread, db_thread.id)
        service = ThreadService(db_session)
        with pytest.raises((ValueError, ThreadAccessDeniedError)):
            service.assert_thread_access(thread, other_user_id)

    def test_create_agent_run_creates_run(self, db_session, db_thread):
        service = ThreadService(db_session)
        run = service.create_agent_run(db_thread.id, "running")
        assert run.status == "running"
        assert run.thread_id == db_thread.id

    def test_update_agent_run_updates_status(self, db_session, db_thread):
        service = ThreadService(db_session)
        run = service.create_agent_run(db_thread.id, "running")
        updated = service.update_agent_run(run.id, "completed")
        assert updated.status == "completed"

    def test_add_message_to_thread(self, db_session, db_thread):
        service = ThreadService(db_session)
        msg = service.add_message(db_thread.id, "user", "Hello")
        assert msg.content == "Hello"
        assert msg.sender == "user"

    def test_get_thread_messages_returns_messages(self, db_session, db_thread):
        service = ThreadService(db_session)
        service.add_message(db_thread.id, "user", "Hi")
        service.add_message(db_thread.id, "agent", "Hello!")
        messages = service.get_thread_messages(db_thread.id)
        assert len(messages) == 2
