# TASK-001 — Set up the automated test harness and cover the migration chain

Status: READY

Origin: review finding TNY-2026-08-09-008

## Objective

`pytest` runs from a clean checkout against a disposable database, with fixtures every later
task can build on, and a first test that holds the Alembic chain in both directions.

## Context

The project has no automated tests. Every verification so far has been manual, which means
nothing protects the eight tasks that follow from regressing each other, and nobody
contributing from outside has a way to know their change is safe.

This comes first, ahead of the correctness fixes, because otherwise each of those tasks has to
invent its own harness. It also settles an open question empirically: the audit claimed the
migration chain was broken; running it proved otherwise. A test makes that checkable in CI
instead of by hand.

## Relevant Code

- `pyproject.toml` — the `dev` extra where `pytest` already sits
- `alembic.ini`, `migrations/env.py` — how the URL is resolved
- `app/db/session.py` — engine and `SessionLocal`, currently built at import time
- `app/core/config.py` — `database_url`, `storage_root`
- `app/main.py` — the app to wire a `TestClient` to

## Requirements

- Pytest configuration and a `conftest.py` providing: a disposable PostgreSQL database created
  and dropped around the session, a `Session`, and a FastAPI test client bound to that database.
- A temporary storage root per test, so nothing writes into the developer's `storage/`.
- Fixtures or factories for the recurring objects: class, student, assessment, submission.
- A test that runs `upgrade head` from `base`, then `downgrade base`, then `upgrade head` again.

## Non-Goals

- Do not fix any of the defects the other tasks cover; this task only builds the ground to stand on.
- Do not add a CI pipeline configuration.
- Do not mock PostgreSQL with SQLite — the schema depends on composite foreign keys, JSONB and
  `gen_random_uuid()`.

## Architectural Constraints

- Tests must not depend on the developer's running instance, its data, or its `storage/`.
- The engine is currently created at import time; if that blocks binding to a test database,
  changing it is in scope, but keep the change minimal.

## Expected Interfaces

Fixtures should compose: a test asking for a submission gets the class, student and assessment
behind it without restating them.

## Failure Behavior

- No PostgreSQL reachable: fail with a clear message saying how to start it, not a connection
  traceback.
- A failing test must leave no database and no temporary storage behind.

## Acceptance Criteria

- `pytest` passes from a clean checkout after `pip install -e ".[dev]"` with PostgreSQL running.
- The migration test fails if any revision breaks the chain in either direction.
- Running the suite leaves the `grademate` database and the `storage/` directory untouched.

## Tests Expected

The migration chain, and a smoke test proving the client and fixtures reach the database.

## Out of Scope

CI configuration, frontend tests, and coverage thresholds.
