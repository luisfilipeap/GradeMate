"""Endpoints for the scanned PDF each student handed in."""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AssessmentDep, SessionDep, StudentDep
from app.api.pdf_errors import as_http_exception
from app.core import pdf, storage
from app.core.config import get_settings
from app.models import Submission
from app.schemas import SubmissionRead
from app.services.cleanup import collect_submission_files, delete_files

logger = logging.getLogger(__name__)

router = APIRouter(tags=["submissions"])


@router.get("/assessments/{assessment_id}/submissions", response_model=list[SubmissionRead])
def list_submissions(assessment: AssessmentDep, session: SessionDep) -> list[Submission]:
    """List every submission already uploaded for an assessment."""
    return list(
        session.scalars(select(Submission).where(Submission.assessment_id == assessment.id))
    )


@router.put(
    "/assessments/{assessment_id}/students/{student_id}/submission",
    response_model=SubmissionRead,
)
def upload_submission(
    assessment: AssessmentDep,
    student: StudentDep,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="The student's answered exam, as a PDF.")],
) -> Submission:
    """Store (or replace) the PDF a student handed in for this assessment.

    Uploading again for the same student overwrites the previous file, which is
    what a teacher expects after re-scanning a bad page.
    """
    if student.class_id != assessment.class_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="This student does not belong to the class of this assessment.",
        )

    content = file.file.read()
    page_count = _validate(content)

    relative_path = storage.submission_file_path(assessment.id, student.id)
    # Written to a staging location now, published at `relative_path` only
    # once the commit below actually happens: the volume must never hold a
    # file the database does not yet know about.
    staged_file = storage.stage(relative_path, content)

    submission = session.scalar(
        select(Submission).where(
            Submission.assessment_id == assessment.id,
            Submission.student_id == student.id,
        )
    )

    stale_image_paths: list[str] = []
    if submission is None:
        submission = Submission(
            class_id=assessment.class_id,
            assessment_id=assessment.id,
            student_id=student.id,
            file_path=relative_path,
        )
        session.add(submission)
    else:
        # A new PDF invalidates everything read from the previous one: the
        # rendered pages and their OCR lines no longer describe this document.
        stale_image_paths = _stored_page_image_paths(submission)
        for page in submission.pages:
            session.delete(page)

    submission.original_filename = file.filename
    submission.file_size_bytes = len(content)
    submission.page_count = page_count
    submission.checksum_sha256 = hashlib.sha256(content).hexdigest()

    try:
        session.commit()
    except BaseException:
        storage.discard(staged_file)
        raise
    session.refresh(submission)

    try:
        storage.publish(staged_file, relative_path)
    except OSError:
        # The database already committed and is the source of truth; the
        # inconsistency this leaves (a row pointing at a file that failed to
        # land) must stay visible rather than being silently swallowed.
        logger.exception(
            "Submission %s committed but its file could not be published to %r",
            submission.id,
            relative_path,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The submission was recorded but its file could not be stored. Try again.",
        ) from None

    # Only remove the stale images once the replacement is durable, so a
    # failed commit leaves the previous reading's files intact.
    for path in stale_image_paths:
        storage.delete(path)

    return submission


@router.get("/submissions/{submission_id}/file")
def download_submission(submission_id: uuid.UUID, session: SessionDep) -> FileResponse:
    """Serve the stored PDF, for the teacher to read in the browser."""
    submission = _get_or_404(session, submission_id)
    absolute = storage.resolve(submission.file_path)
    if not absolute.is_file():
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="The file is registered but missing from the storage volume.",
        )
    return FileResponse(
        absolute,
        media_type="application/pdf",
        filename=submission.original_filename or absolute.name,
        content_disposition_type="inline",
    )


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(submission_id: uuid.UUID, session: SessionDep) -> None:
    """Delete a submission and the PDF it points at."""
    submission = _get_or_404(session, submission_id)
    stored_files = collect_submission_files(session, submission_id=submission.id)
    session.delete(submission)
    session.commit()
    delete_files(stored_files)


def _get_or_404(session: Session, submission_id: uuid.UUID) -> Submission:
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission


def _stored_page_image_paths(submission: Submission) -> list[str]:
    """Relative paths of every rendered page image belonging to a submission."""
    return [page.image_path for page in submission.pages]


def _validate(content: bytes) -> int:
    """Reject empty, oversized, non-PDF, unparseable or too-long files.

    Returns the page count, so callers that already need it (storing it on the
    submission) do not parse the document a second time.
    """
    settings = get_settings()
    try:
        page_count = pdf.validate_pdf_upload(content, settings.max_upload_mb * 1024 * 1024)
    except pdf.PdfValidationError as error:
        raise as_http_exception(error) from error

    if page_count > settings.max_submission_pages:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"The PDF has {page_count} pages; at most "
                f"{settings.max_submission_pages} are accepted."
            ),
        )
    return page_count
