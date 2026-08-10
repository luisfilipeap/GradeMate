"""Endpoints for an assessment's question paper and the questions it contains."""

from __future__ import annotations

import hashlib
import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select

from app.api.deps import AssessmentDep, QuestionDep, SessionDep
from app.api.pdf_errors import as_http_exception
from app.core import pdf, storage
from app.core.config import get_settings
from app.models import Question
from app.schemas import QuestionCreate, QuestionRead, QuestionUpdate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["questions"])


@router.put("/assessments/{assessment_id}/question-paper", status_code=status.HTTP_204_NO_CONTENT)
def upload_question_paper(
    assessment: AssessmentDep,
    session: SessionDep,
    file: Annotated[UploadFile, File(description="The blank question paper, as a PDF.")],
) -> None:
    """Store (or replace) the question paper for this assessment.

    Replacing the paper does **not** delete the assessment's existing
    questions: they were confirmed by the teacher (by hand here, or later
    through the automatic extraction), and a new upload must not silently
    discard that work. Clearing them, if wanted, is a separate action.
    """
    content = file.file.read()
    settings = get_settings()
    try:
        page_count = pdf.validate_pdf_upload(content, settings.max_upload_mb * 1024 * 1024)
    except pdf.PdfValidationError as error:
        raise as_http_exception(error) from error

    relative_path = storage.question_paper_path(assessment.id)
    # Staged now, published only once the commit below succeeds - the volume
    # must never hold a file the database does not yet know about.
    staged_file = storage.stage(relative_path, content)

    assessment.question_paper_path = relative_path
    assessment.question_paper_original_filename = file.filename
    assessment.question_paper_file_size_bytes = len(content)
    assessment.question_paper_page_count = page_count
    assessment.question_paper_checksum_sha256 = hashlib.sha256(content).hexdigest()

    try:
        session.commit()
    except BaseException:
        storage.discard(staged_file)
        raise

    try:
        storage.publish(staged_file, relative_path)
    except OSError:
        logger.exception(
            "Assessment %s committed a question paper that could not be published to %r",
            assessment.id,
            relative_path,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The question paper was recorded but could not be stored. Try again.",
        ) from None


@router.get("/assessments/{assessment_id}/question-paper/file")
def download_question_paper(assessment: AssessmentDep) -> FileResponse:
    """Serve the stored question paper, for the teacher to read in the browser."""
    if assessment.question_paper_path is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, detail="No question paper has been uploaded yet."
        )
    absolute = storage.resolve(assessment.question_paper_path)
    if not absolute.is_file():
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="The file is registered but missing from the storage volume.",
        )
    return FileResponse(
        absolute,
        media_type="application/pdf",
        filename=assessment.question_paper_original_filename or absolute.name,
        content_disposition_type="inline",
    )


@router.get("/assessments/{assessment_id}/questions", response_model=list[QuestionRead])
def list_questions(assessment: AssessmentDep, session: SessionDep) -> list[Question]:
    """List the assessment's questions, in their defined order."""
    return list(
        session.scalars(
            select(Question)
            .where(Question.assessment_id == assessment.id)
            .order_by(Question.position)
        )
    )


@router.post(
    "/assessments/{assessment_id}/questions",
    response_model=QuestionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_question(
    assessment: AssessmentDep, payload: QuestionCreate, session: SessionDep
) -> Question:
    """Add a question at the end of the assessment's list."""
    next_position = (
        session.scalar(
            select(Question.position)
            .where(Question.assessment_id == assessment.id)
            .order_by(Question.position.desc())
            .limit(1)
        )
        or 0
    ) + 1
    question = Question(assessment_id=assessment.id, position=next_position, **payload.model_dump())
    session.add(question)
    session.commit()
    session.refresh(question)
    return question


@router.patch("/questions/{question_id}", response_model=QuestionRead)
def update_question(
    question: QuestionDep, payload: QuestionUpdate, session: SessionDep
) -> Question:
    """Update a question's number and/or statement, so a teacher can fix it by hand."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(question, field, value)
    session.commit()
    session.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(question: QuestionDep, session: SessionDep) -> None:
    """Remove a question from the assessment."""
    session.delete(question)
    session.commit()
