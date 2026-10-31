import os
from collections.abc import Iterator

import pytest
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from alembic import command

# Never fall back to the application database. Require an explicitly selected test database.
url = os.getenv("TEST_DATABASE_URL")
if not url:
    raise pytest.UsageError(
        "Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test"
    )
parsed = make_url(url)
if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
    raise pytest.UsageError(
        "TEST_DATABASE_URL must be PostgreSQL with a database name ending in _test"
    )
if url == os.getenv("DATABASE_URL"):
    raise pytest.UsageError("Test and application database URLs must differ")
os.environ["DATABASE_URL"] = url

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402

engine = create_engine(url)


@pytest.fixture(scope="session", autouse=True)
def migrate() -> Iterator[None]:
    command.upgrade(Config("alembic.ini"), "head")
    yield
    engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(migrate: None) -> Iterator[None]:
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE calibration_tag_memberships, calibrations"))
    yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    def session_override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def db() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
