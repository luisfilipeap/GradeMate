# TASK-009 — Publish stored files only after the database commit succeeds

Status: READY

Origin: review finding TNY-2026-08-09-003

## Objective

The volume never holds a file the database does not know about, and an OCR run never leaves
images from one reading beside rows from another.

## Context

Both the upload and the OCR run write to the final path before committing. If the commit fails,
the file stays and nothing references it. `run_ocr` additionally overwrites the previous
reading's page images before the new rows are committed, so a failure midway leaves a mixture:
images from the new run, rows from the old one, boxes that no longer match the picture.

The audit rated this HIGH on concurrency grounds. GradeMate is single-teacher with no login, so
the realistic risk is the commit-failure path rather than a race — scoped and prioritised
accordingly, and placed last among the correctness fixes for that reason.

## Relevant Code

- `app/core/storage.py` — `write`, already atomic per file via `os.replace`
- `app/api/routes/submissions.py` — `upload_submission`, writing before the commit
- `app/api/routes/review.py` — `run_ocr`, flushing, overwriting images, then committing

## Requirements

- Files become visible at their final path only after the transaction that references them
  commits, or are removed if it rolls back.
- The same holds for the page images written during an OCR run.
- The cleanup is idempotent, so a retry after a crash converges rather than compounding.

## Non-Goals

- Do not add locking or a concurrency-control scheme; the product has one user.
- Do not add a background reconciliation job.

## Architectural Constraints

The database stays the source of truth. Everything on the volume is derived, and derived state
is published after the fact it depends on is durable.

## Expected Interfaces

No contract change. Callers see the same responses; only the ordering of effects changes.

## Failure Behavior

A failure at any point leaves either the previous consistent state or a clean absence — never a
half-published reading. If a cleanup itself fails, the inconsistency must be visible in the log
rather than silent.

## Acceptance Criteria

- Forcing a commit failure after the file write leaves no orphan file on the volume.
- Forcing a failure midway through an OCR run leaves the previous reading intact, or no reading
  at all, never a mixture of the two.

## Tests Expected

Both failures, injected deliberately.

## Out of Scope

Concurrency control, retries, and orphan sweeping.
