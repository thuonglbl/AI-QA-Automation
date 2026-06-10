"""API tests for threads routes."""

import uuid
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.api.app import create_app
from ai_qa.api.auth.local import get_db_session_dependency
from ai_qa.api.auth.session import SessionManager
from ai_qa.db.base import Base
from ai_qa.db.models import Project, User
from ai_qa.threads.models import Thread

TEST_USER_ID = uuid.uuid4()
TEST_PROJECT_ID = uuid.uuid4()


@pytest.fixture
def db_session() -> Generator[Session]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)

    user = User(
        id=TEST_USER_ID,
        email="test@example.com",
        role="standard",
        display_name="Test User",
        password_hash="fakehash",
    )
    project = Project(id=TEST_PROJECT_ID, name="Test Project", created_by_user_id=TEST_USER_ID)

    from ai_qa.db.models import ProjectMembership

    membership = ProjectMembership(user_id=TEST_USER_ID, project_id=TEST_PROJECT_ID, role="member")

    session = session_factory()
    session.add(user)
    session.add(project)
    session.add(membership)
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def auth_client(db_session: Session) -> Generator[TestClient]:
    def override_get_db_session() -> Generator[Session]:
        yield db_session

    app = create_app()
    app.dependency_overrides[get_db_session_dependency] = override_get_db_session

    session_manager = SessionManager(app.state.settings)
    user_session = session_manager.create_session(
        {
            "user_id": str(TEST_USER_ID),
            "email": "test@example.com",
            "role": "standard",
            "name": "Test User",
        }
    )
    token = session_manager.encode_session(user_session)

    with TestClient(app) as client:
        client.cookies.set(app.state.settings.session_cookie_name, token)
        yield client

    app.dependency_overrides.clear()


@pytest.fixture
def user_thread(db_session: Session) -> str:
    thread = Thread(user_id=TEST_USER_ID, project_id=TEST_PROJECT_ID)
    db_session.add(thread)
    db_session.commit()
    return str(thread.id)


def test_create_thread_scoped_to_current_user(auth_client: TestClient) -> None:
    response = auth_client.post(
        "/api/threads", json={"user_id": str(TEST_USER_ID), "project_id": str(TEST_PROJECT_ID)}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["project_id"] == str(TEST_PROJECT_ID)
    assert data["user_id"] == str(TEST_USER_ID)


def test_enforce_project_id_immutability(auth_client: TestClient) -> None:
    create_res = auth_client.post(
        "/api/threads", json={"user_id": str(TEST_USER_ID), "project_id": str(TEST_PROJECT_ID)}
    )
    assert create_res.status_code == 201
    thread_id = create_res.json()["id"]

    other_project_id = str(uuid.uuid4())
    update_res = auth_client.post(
        f"/api/threads/{thread_id}/bind", params={"project_id": other_project_id}
    )
    assert update_res.status_code == 400


def test_thread_messages_api(auth_client: TestClient, user_thread: str) -> None:
    # 1. Add message
    msg_res = auth_client.post(
        f"/api/threads/{user_thread}/messages", json={"role": "user", "content": "Hello thread!"}
    )
    assert msg_res.status_code == 201
    data = msg_res.json()
    assert data["role"] == "user"
    assert data["content"] == "Hello thread!"
    assert data["thread_id"] == user_thread

    # 2. Get messages
    get_res = auth_client.get(f"/api/threads/{user_thread}/messages")
    assert get_res.status_code == 200
    msgs = get_res.json()
    assert len(msgs) == 1
    assert msgs[0]["content"] == "Hello thread!"


def test_agent_runs_api(auth_client: TestClient, user_thread: str) -> None:
    # 1. Create agent run
    run_res = auth_client.post(f"/api/threads/{user_thread}/runs", json={"status": "running"})
    assert run_res.status_code == 201
    run_data = run_res.json()
    assert run_data["status"] == "running"
    run_id = run_data["id"]

    # 2. Update agent run
    patch_res = auth_client.patch(
        f"/api/threads/{user_thread}/runs/{run_id}",
        json={"status": "completed", "summary": "Done", "current_step": 3},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["status"] == "completed"
    assert updated["summary"] == "Done"

    # We cannot directly test thread status via API if there's no endpoint for it,
    # but the service tests cover it.


def test_get_messages_returns_404_for_unknown_thread(auth_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    res = auth_client.get(f"/api/threads/{fake_id}/messages")
    assert res.status_code == 404


def test_add_message_returns_404_for_unknown_thread(auth_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    res = auth_client.post(
        f"/api/threads/{fake_id}/messages", json={"role": "user", "content": "hello"}
    )
    assert res.status_code == 404


def test_create_agent_run_returns_404_for_unknown_thread(auth_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    res = auth_client.post(f"/api/threads/{fake_id}/runs", json={"status": "running"})
    assert res.status_code == 404


def test_conversation_save_and_get(auth_client: TestClient, user_thread: str) -> None:
    """Test saving and getting conversation data."""
    # Save conversation
    save_res = auth_client.post(
        f"/api/threads/{user_thread}/conversation",
        json={"conversation": {"messages": [], "current_step": 1, "status": "active"}},
    )
    assert save_res.status_code == 200
    data = save_res.json()
    assert data["success"] is True

    # Get conversation
    get_res = auth_client.get(f"/api/threads/{user_thread}/conversation")
    assert get_res.status_code == 200


def test_conversation_get_returns_404_for_unknown_thread(auth_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    res = auth_client.get(f"/api/threads/{fake_id}/conversation")
    assert res.status_code == 404


def test_conversation_save_returns_404_for_unknown_thread(auth_client: TestClient) -> None:
    fake_id = str(uuid.uuid4())
    res = auth_client.post(
        f"/api/threads/{fake_id}/conversation",
        json={"conversation": {"messages": [], "current_step": 1, "status": "active"}},
    )
    assert res.status_code == 404


def test_unauthenticated_cannot_create_thread(auth_client: TestClient) -> None:
    """Without auth cookie/token, thread creation returns 401."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    sf = sessionmaker(bind=engine, expire_on_commit=False)

    def _override() -> Generator[Session]:
        s = sf()
        try:
            yield s
        finally:
            s.close()

    app2 = create_app()
    app2.dependency_overrides[get_db_session_dependency] = _override
    with TestClient(app2) as c:
        res = c.post(
            "/api/threads", json={"user_id": str(uuid.uuid4()), "project_id": str(uuid.uuid4())}
        )
    assert res.status_code == 401
    engine.dispose()


def test_get_user_threads_api(auth_client: TestClient, user_thread: str) -> None:
    # 1. Create a second thread to ensure list is populated
    create_res = auth_client.post(
        "/api/threads", json={"user_id": str(TEST_USER_ID), "project_id": str(TEST_PROJECT_ID)}
    )
    assert create_res.status_code == 201

    # 2. Get threads list
    list_res = auth_client.get("/api/threads")
    assert list_res.status_code == 200
    threads = list_res.json()
    assert len(threads) >= 2
    assert any(t["id"] == user_thread for t in threads)


def test_get_thread_details_api(auth_client: TestClient, user_thread: str) -> None:
    # 1. Add some details
    auth_client.post(
        f"/api/threads/{user_thread}/messages", json={"role": "user", "content": "Hello"}
    )
    auth_client.post(f"/api/threads/{user_thread}/runs", json={"status": "running"})

    # 2. Get details
    detail_res = auth_client.get(f"/api/threads/{user_thread}")
    assert detail_res.status_code == 200
    details = detail_res.json()

    assert details["id"] == user_thread
    assert "messages" in details
    assert len(details["messages"]) == 1
    assert "agent_runs" in details
    assert len(details["agent_runs"]) == 1


def test_get_thread_details_forbidden(auth_client: TestClient, db_session: Session) -> None:
    # 1. Create thread for another user
    other_user_id = uuid.uuid4()
    thread = Thread(user_id=other_user_id)
    db_session.add(thread)
    db_session.commit()

    # 2. Attempt to get
    res = auth_client.get(f"/api/threads/{thread.id}")
    assert res.status_code in [403, 404]
