# TASK-003 — Delete stored exam files when a student, assessment or class is deleted

Status: READY

Origin: review finding TNY-2026-08-09-004

## Objective

Deleting anything that owns submissions removes their files from the storage volume, not just
their rows from the database.

## Context

Only `DELETE /api/submissions/{id}` cleans the volume. Deleting a student, an assessment or a
class cascades correctly in PostgreSQL and leaves every PDF and rendered page image on disk,
unreachable through the product and invisible to the teacher who thought they had deleted them.

These files are scanned exams: students' names, handwriting, personal data. That makes this a
data-retention problem rather than wasted disk — a teacher deleting a class at the end of term
has every reason to believe the exams went with it.

## Relevant Code

- `app/api/routes/students.py`, `assessments.py`, `classes.py` — the three delete endpoints
- `app/api/routes/submissions.py` — `delete_submission`, which already collects paths and
  removes them after the commit
- `app/models/submission.py`, `submission_page.py` — `passive_deletes=True`, which is why the
  ORM never sees the rows the database removes

## Requirements

- Deleting a student, an assessment or a class removes the stored files of every submission
  affected, including the rendered page images.
- The collection and cleanup live in one place rather than being repeated in three routes.
- A file already missing must not turn a delete into an error.

## Non-Goals

- Do not change the database cascade behaviour; it is correct.
- Do not add a background reaper or an orphan sweep.
- Do not add soft deletes or a retention policy.

## Architectural Constraints

Files are removed after the transaction commits, so a rolled-back delete never destroys data.
The path helpers in `app/core/storage.py` stay the only way file locations are derived.

## Expected Interfaces

No new endpoints, no response change. The three deletes keep returning 204.

## Failure Behavior

A failure while removing files must not leave the API reporting an error for a delete that
already succeeded in the database. Decide and document which side wins, and make the outcome
consistent.

## Acceptance Criteria

- Deleting a class with students, assessments, submissions and OCR results leaves no file under
  the storage root for that class's assessments.
- The same holds for deleting a single student and a single assessment.

## Tests Expected

One integration test per route asserting the storage directory is empty afterwards, plus the
missing-file case.

## Out of Scope

Replacement invalidation (TASK-002) and the commit-ordering guarantee (TASK-009).
