from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from ai_qa.db.base import Base
from ai_qa.db.models import Project, ProjectMembership, User
from ai_qa.projects.service import get_user_projects


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def _create_user(session: Session, email: str) -> User:
    user = User(email=email, display_name="Test", password_hash="hash", role="standard")
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _create_project(session: Session, name: str) -> Project:
    project = Project(name=name, description="Test")
    session.add(project)
    session.commit()
    session.refresh(project)
    return project


def test_get_user_projects_returns_assigned_projects(db_session: Session):
    user = _create_user(db_session, "user@test.com")
    other_user = _create_user(db_session, "other@test.com")

    project1 = _create_project(db_session, "Project 1")
    project2 = _create_project(db_session, "Project 2")

    db_session.add(ProjectMembership(project_id=project1.id, user_id=user.id, role="member"))
    db_session.add(ProjectMembership(project_id=project2.id, user_id=other_user.id, role="member"))
    db_session.commit()

    user_projects = get_user_projects(db_session, user.id)
    assert len(user_projects) == 1
    assert user_projects[0].id == project1.id


def test_get_user_projects_returns_empty_when_none_assigned(db_session: Session):
    user = _create_user(db_session, "user@test.com")
    _create_project(db_session, "Project 1")

    user_projects = get_user_projects(db_session, user.id)
    assert len(user_projects) == 0
