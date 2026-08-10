# TASK-006 — Align the documented storage topology with what Compose actually runs

Status: READY

Origin: review finding TNY-2026-08-09-012

## Objective

The README's account of where exam files live matches what a reader gets by following its
instructions.

## Context

The README states that the `grademate_storage` volume is mounted into the backend container at
`/data/storage`. There is no backend service in `docker-compose.yml`: the API runs on the host
under `uvicorn`, so it writes to the default `./storage`, and the declared volume is never
mounted by anything.

The consequence is operational — a backup or a cleanup aimed at the volume touches nothing, and
the files it was meant to protect sit somewhere else entirely.

## Relevant Code

- `README.md` — the File storage section and the running-the-application section
- `docker-compose.yml` — the volume declaration with no service mounting it
- `app/core/config.py` — `storage_root` and its default

## Requirements

Choose one and make everything consistent:

- add an `api` service to Compose that mounts the volume and sets `STORAGE_ROOT`, keeping the
  host workflow documented as the development alternative; or
- drop the unused volume and state plainly that the backend stores files under `./storage`.

The choice is the owner's to confirm — it decides whether GradeMate ships as a single
`docker compose up` or stays a two-terminal development setup.

## Non-Goals

- Do not containerise the frontend as part of this task.
- Do not change how paths are stored in the database; relative paths are correct either way.

## Architectural Constraints

Documentation is part of the deliverable, not a description of it. A declared volume that
nothing mounts is a defect regardless of which option is chosen.

## Expected Interfaces

None. This is configuration and documentation.

## Failure Behavior

If the containerised option is taken, the storage root inside the container and the one used by
a host-run backend must not silently diverge — a developer switching between them should not
lose sight of their files.

## Acceptance Criteria

- The README's storage section matches what following the setup instructions produces.
- No volume is declared in `docker-compose.yml` without a service mounting it.

## Tests Expected

None. Verified by following the README from a clean checkout.

## Out of Scope

Production deployment and backup procedures.
