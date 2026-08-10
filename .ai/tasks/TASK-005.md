# TASK-005 — Stop publishing PostgreSQL and Adminer on every host interface

Status: READY

Origin: review finding TNY-2026-08-09-005

## Objective

The database and Adminer are reachable only from the machine running them, and no password
literal remains in a versioned file.

## Context

`docker-compose.yml` publishes `5432:5432` and `8080:8080` with no address, so Docker binds
them on all interfaces, with `grademate/grademate` written in the file. Anything that can reach
the host can authenticate against PostgreSQL and bypass the API entirely — reading students'
names, e-mail addresses and exam transcripts, and writing whatever it likes.

The credentials are trivial on purpose, for local development. That is defensible; publishing
them to every interface is not, and the repository is now shared.

## Relevant Code

- `docker-compose.yml` — the `db` and `adminer` services
- `.env.example`, `.env` — the connection string that must stay in step
- `README.md` — the setup steps, the Adminer section, and the process table

## Requirements

- Development ports bound explicitly to the loopback address.
- Adminer moved behind a compose profile, so it is not part of the default stack.
- Database credentials read from environment variables, with `.env.example` documenting them.
- The README updated so the documented setup still works, including how to start Adminer when
  it is wanted.

## Non-Goals

- Do not build a production deployment configuration.
- Do not add TLS, a secrets manager, or authentication to the application.

## Architectural Constraints

The default posture is the safe one: a developer who follows the README must end up with a
database that is not reachable from the network without opting in.

## Expected Interfaces

The connection string keeps its shape; only where the values come from changes.

## Failure Behavior

Changing `POSTGRES_*` does not affect an already-initialised volume — those variables apply
only on first initialisation. The README must say so, or a reader will change the password and
be quietly confused when the old one still works.

## Acceptance Criteria

- After `docker compose up -d`, 5432 is bound to the loopback address only, and Adminer is not
  running.
- Adminer starts on demand through its profile and still connects.
- No password literal remains in `docker-compose.yml`.

## Tests Expected

Verified by inspection of the listening sockets rather than by an automated test.

## Out of Scope

Production credentials, network policy, and application-level authentication.
