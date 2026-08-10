"""Shared pytest fixtures: a disposable PostgreSQL database, an isolated storage
root per test, and a FastAPI test client wired to both.

The database is created once per test session (in ``pytest_configure``, which
runs before any test module is imported) and dropped in ``pytest_unconfigure``.
Creating it that early matters: ``app.db.session`` builds its SQLAlchemy engine
at import time, so ``DATABASE_URL`` must point at the disposable database
*before* anything imports that module, which happens as soon as pytest starts
collecting test files.

Each test then runs inside its own transaction (with savepoint support for the
``session.commit()`` calls the application code makes), which is rolled back at
teardown, and gets its own temporary storage root. Nothing here ever touches the
developer's ``grademate`` database or ``storage/`` directory.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

pytest_plugins = ["factories"]

# ---------------------------------------------------------------------------
# Session-wide disposable database, set up before any ``app`` module is
# imported and torn down after the whole run.
# ---------------------------------------------------------------------------

_TEST_DB_PREFIX = "grademate_test_"
_state: dict[str, object] = {}


def _admin_url(url):
    """Return the same connection, pointed at the always-present ``postgres`` db."""
    return url.set(database="postgres")


def _psycopg_conninfo(url) -> str:
    """Render a SQLAlchemy URL as a plain ``postgresql://`` conninfo for psycopg.

    SQLAlchemy URLs carry the driver in the scheme (``postgresql+psycopg://``),
    which psycopg's own parser rejects.
    """
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


def pytest_configure(config: pytest.Config) -> None:
    """Create a disposable database and point the application at it.

    Runs once, before test collection, so ``app.db.session`` (which builds its
    engine at import time) never sees the developer's real ``DATABASE_URL``.
    """
    from app.core.config import get_settings

    base_url = make_url(get_settings().database_url)
    admin_url = _admin_url(base_url)

    import psycopg

    try:
        admin_conn = psycopg.connect(_psycopg_conninfo(admin_url))
    except psycopg.OperationalError as error:
        pytest.exit(
            "Could not reach PostgreSQL to create the disposable test database.\n"
            f"Tried: {admin_url.render_as_string(hide_password=True)}\n"
            "Start it with `docker compose up -d db` and try again.\n"
            f"Original error: {error}",
            returncode=1,
        )
        return

    test_db_name = f"{_TEST_DB_PREFIX}{uuid.uuid4().hex[:12]}"
    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cursor:
            cursor.execute(f'CREATE DATABASE "{test_db_name}"')
    finally:
        admin_conn.close()

    test_url = base_url.set(database=test_db_name)
    test_url_str = test_url.render_as_string(hide_password=False)

    os.environ["DATABASE_URL"] = test_url_str
    get_settings.cache_clear()

    from alembic import command
    from alembic.config import Config

    repo_root = Path(__file__).resolve().parent.parent
    alembic_cfg = Config(str(repo_root / "alembic.ini"))
    alembic_cfg.set_main_option("script_location", str(repo_root / "migrations"))
    command.upgrade(alembic_cfg, "head")

    _state["admin_url"] = admin_url
    _state["test_db_name"] = test_db_name


def pytest_unconfigure(config: pytest.Config) -> None:
    """Drop the disposable database created in ``pytest_configure``."""
    if "test_db_name" not in _state:
        return

    try:
        from app.db.session import engine

        engine.dispose()
    except Exception:
        pass

    import psycopg

    admin_url = _state["admin_url"]
    test_db_name = _state["test_db_name"]
    try:
        admin_conn = psycopg.connect(_psycopg_conninfo(admin_url))
    except psycopg.OperationalError:
        return

    admin_conn.autocommit = True
    try:
        with admin_conn.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (test_db_name,),
            )
            cursor.execute(f'DROP DATABASE IF EXISTS "{test_db_name}"')
    finally:
        admin_conn.close()


# ---------------------------------------------------------------------------
# Per-test fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session() -> Iterator[Session]:
    """A ``Session`` bound to its own connection and transaction.

    The transaction is rolled back after the test, so nothing written by a test
    (or by the application code it drives through the client, including its own
    ``session.commit()`` calls, which only release a savepoint here) survives it.
    """
    from app.db.session import SessionLocal, engine

    connection = engine.connect()
    transaction = connection.begin()
    session = SessionLocal(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def storage_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point ``Settings.storage_root`` at a throwaway directory for this test.

    Autouse, so no test can accidentally write into the developer's ``storage/``
    even if it never asks for this fixture directly.
    """
    from app.core.config import get_settings

    root = tmp_path / "storage"
    root.mkdir()
    monkeypatch.setattr(get_settings(), "storage_root", root)
    return root


@pytest.fixture
def client(db_session: Session) -> Iterator[TestClient]:
    """A FastAPI ``TestClient`` bound to ``db_session`` instead of a fresh session."""
    from fastapi.testclient import TestClient

    from app.db.session import get_session
    from app.main import app

    def _override_get_session() -> Iterator[Session]:
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_session, None)
