"""Collects and removes the files derived from submissions being deleted.

Every route that can make a submission's files unreachable — deleting the
submission itself, or deleting the student, assessment or class that owns it —
shares this module instead of repeating the collect-then-delete pattern.

The database is the source of truth: file paths are collected *before* the
owning rows are deleted, and the files are only removed *after* that deletion
commits. If the commit fails, nothing on the volume is touched. If removing a
file fails after a successful commit, the database has already won — the
delete is not undone and the endpoint still reports success — but the failure
is logged so it stays visible.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core import storage
from app.models import Assessment, Submission

logger = logging.getLogger(__name__)


def collect_submission_files(
    session: Session,
    *,
    class_id: uuid.UUID | None = None,
    assessment_id: uuid.UUID | None = None,
    student_id: uuid.UUID | None = None,
    submission_id: uuid.UUID | None = None,
) -> list[str]:
    """Return every stored path (PDF and rendered page images) still on record.

    At least one filter must be given. Submissions are matched by whichever
    filters are provided; all must hold for a submission's files to be
    included.
    """
    stmt = select(Submission).options(selectinload(Submission.pages))
    if class_id is not None:
        stmt = stmt.where(Submission.class_id == class_id)
    if assessment_id is not None:
        stmt = stmt.where(Submission.assessment_id == assessment_id)
    if student_id is not None:
        stmt = stmt.where(Submission.student_id == student_id)
    if submission_id is not None:
        stmt = stmt.where(Submission.id == submission_id)

    paths: list[str] = []
    for submission in session.scalars(stmt):
        paths.append(submission.file_path)
        paths.extend(page.image_path for page in submission.pages)
    return paths


def collect_question_paper_files(
    session: Session,
    *,
    class_id: uuid.UUID | None = None,
    assessment_id: uuid.UUID | None = None,
) -> list[str]:
    """Return the stored path of every question paper still on record.

    The question paper belongs to the assessment alone (one per assessment,
    unlike submissions), so this only needs to filter by assessment or class.
    """
    stmt = select(Assessment.question_paper_path).where(Assessment.question_paper_path.is_not(None))
    if class_id is not None:
        stmt = stmt.where(Assessment.class_id == class_id)
    if assessment_id is not None:
        stmt = stmt.where(Assessment.id == assessment_id)

    return list(session.scalars(stmt))


def delete_files(paths: list[str]) -> None:
    """Remove every stored file, tolerating files already missing.

    Called after the database transaction that made these files orphans has
    committed. An unexpected failure here (e.g. a permissions problem) is
    logged rather than raised: the database delete already succeeded, and the
    caller must not turn that success into an error response.
    """
    for path in paths:
        try:
            storage.delete(path)
        except OSError:
            logger.exception(
                "Could not remove stored file %r after its owning row was deleted", path
            )
