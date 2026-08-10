"""Holds the Alembic chain accountable in both directions.

The disposable database is already at ``head`` by the time any test runs (see
``pytest_configure`` in ``conftest.py``); this test drives the chain down to
``base`` and back up again, on that same database, to prove every revision's
``upgrade`` and ``downgrade`` actually run without the schema drifting.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect

REPO_ROOT = Path(__file__).resolve().parent.parent


def _alembic_config() -> Config:
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    return cfg


def test_migration_chain_upgrades_and_downgrades_cleanly() -> None:
    from app.db.session import engine

    cfg = _alembic_config()

    command.downgrade(cfg, "base")
    with engine.connect() as connection:
        inspector = inspect(connection)
        # Alembic's own bookkeeping table is the only thing left at "base".
        assert set(inspector.get_table_names()) <= {"alembic_version"}
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() is None

    command.upgrade(cfg, "head")
    head_revision = ScriptDirectory.from_config(cfg).get_current_head()
    with engine.connect() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        context = MigrationContext.configure(connection)
        assert context.get_current_revision() == head_revision

    assert {
        "classes",
        "students",
        "assessments",
        "submissions",
        "submission_pages",
        "ocr_lines",
    } <= tables
