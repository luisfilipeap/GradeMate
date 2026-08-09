"""Endpoints for the scanned PDF each student handed in."""

from __future__ import annotations

import hashlib
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AssessmentDep, SessionDep, StudentDep
from app.core import pdf, storage
from app.core.config import get_settings
from app.models import Submission
from app.schemas import SubmissionRead

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
    _validate(content)

    relative_path = storage.submission_file_path(assessment.id, student.id)
    storage.write(relative_path, content)

    submission = session.scalar(
        select(Submission).where(
            Submission.assessment_id == assessment.id,
            Submission.student_id == student.id,
        )
    )
    if submission is None:
        submission = Submission(
            class_id=assessment.class_id,
            assessment_id=assessment.id,
            student_id=student.id,
            file_path=relative_path,
        )
        session.add(submission)

    submission.original_filename = file.filename
    submission.file_size_bytes = len(content)
    submission.page_count = pdf.count_pages(content)
    submission.checksum_sha256 = hashlib.sha256(content).hexdigest()

    session.commit()
    session.refresh(submission)
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
    # The rendered page images go away with the PDF they were made from.
    stored_files = [submission.file_path, *(page.image_path for page in submission.pages)]
    session.delete(submission)
    session.commit()
    for path in stored_files:
        storage.delete(path)


def _get_or_404(session: Session, submission_id: uuid.UUID) -> Submission:
    submission = session.get(Submission, submission_id)
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission


def _validate(content: bytes) -> None:
    """Reject empty files, oversized files and anything that is not a PDF."""
    if not content:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="The uploaded file is empty.")

    limit = get_settings().max_upload_mb * 1024 * 1024
    if len(content) > limit:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file is larger than the {get_settings().max_upload_mb} MB limit.",
        )

    if not pdf.looks_like_pdf(content):
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Only PDF files are accepted."
        )
