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
from app.schemas import (
    QuestionCreate,
    QuestionDraft,
    QuestionExtractionRead,
    QuestionRead,
    QuestionUpdate,
)
from app.services import question_extraction_guard
from app.services.gpu_handoff import GpuHandoffError, gpu_service
from app.services.llm_client import LlmServiceError, generate_structured
from app.services.ocr_client import OcrServiceError, RecognisedRegion, recognise_image

logger = logging.getLogger(__name__)

router = APIRouter(tags=["questions"])

# Schema the LLM's structured-output response must match (see
# app.services.llm_client.generate_structured). Loose on purpose — only the
# shape, not the content, is enforced here; `question_extraction_guard` is
# what protects meaning (a non-empty list, unique/non-empty numbers, etc).
_EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "number": {"type": "string"},
                    "statement": {"type": "string"},
                },
                "required": ["number", "statement"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}


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
    # A transcript of the file being replaced is meaningless once it's gone;
    # the next `POST .../extract` must read the new file, not reuse this.
    assessment.question_paper_ocr_pages = None

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


@router.post(
    "/assessments/{assessment_id}/question-paper/extract",
    response_model=QuestionExtractionRead,
)
def extract_questions(assessment: AssessmentDep, session: SessionDep) -> QuestionExtractionRead:
    """Read the uploaded question paper and propose draft questions from it.

    Renders the PDF, OCRs every page and asks the LLM to segment the
    resulting transcript into ``{number, statement}`` candidates. Nothing is
    written to ``questions`` here — a teacher reviews these drafts and only
    the existing ``POST .../questions`` turns an accepted one into a real
    row, same as one entered by hand.

    ``question_paper_ocr_pages`` is committed the moment OCR succeeds, before
    the LLM is even called, mirroring how ``run_ocr`` commits a submission's
    OCR reading before the normalization layered on top of it runs. A
    failure of the LLM call or a guard rejection afterwards is entirely a
    failure of that later, separate step: it never rolls back or otherwise
    touches the transcript this run already recorded.
    """
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

    settings = get_settings()
    try:
        rendered = pdf.render_pages(absolute.read_bytes(), settings.page_render_dpi)
    except pdf.PdfRenderError as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The stored PDF could not be rendered: {error}",
        ) from error
    if not rendered:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The PDF has no pages to read."
        )

    oversized = [page for page in rendered if page.width * page.height > settings.max_page_pixels]
    if oversized:
        numbers = ", ".join(str(page.number) for page in oversized)
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Page(s) {numbers} render larger than the {settings.max_page_pixels} pixel "
                "limit. Lowering PAGE_RENDER_DPI would let a page like this through."
            ),
        )

    try:
        # Sequential GPU handoff (issue #21), same as `run_ocr`: `ocr` is
        # brought up only for this block and stopped again as soon as it
        # exits, before `llm` is ever brought up below.
        with gpu_service("ocr"):
            ocr_pages = [
                _page_text(
                    recognise_image(
                        page.png,
                        f"page-{page.number}.png",
                        page.width,
                        page.height,
                        timeout=settings.ocr_timeout_seconds,
                    )
                )
                for page in rendered
            ]
    except OcrServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except GpuHandoffError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not bring up the OCR service for this run: {error}",
        ) from error

    # Replaces, never appends to, any transcript left by a previous run.
    assessment.question_paper_ocr_pages = ocr_pages
    session.commit()
    session.refresh(assessment)

    transcript = "\n\n".join(page for page in ocr_pages if page)
    try:
        with gpu_service("llm", profile="tools"):
            response = generate_structured(
                _extraction_prompt(transcript, assessment.title),
                _EXTRACTION_SCHEMA,
                timeout=settings.llm_timeout_seconds,
            )
    except LlmServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except GpuHandoffError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not bring up the LLM service for this run: {error}",
        ) from error

    if not question_extraction_guard.extraction_passes(response):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The LLM's extraction did not pass structural validation "
            "(no questions, or a blank/duplicate number).",
        )

    drafts = [
        QuestionDraft(number=entry["number"].strip(), statement=entry["statement"].strip())
        for entry in response["questions"]
    ]
    return QuestionExtractionRead(questions=drafts)


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


def _page_text(regions: list[RecognisedRegion]) -> str:
    """Concatenate one page's recognised regions into a single transcript string.

    `recognise_image` already drops blocks with no content (see
    `ocr_client._regions`), so every remaining region is joined as-is, in
    the reading order the OCR service returned them.
    """
    return "\n".join(region.text for region in regions)


def _extraction_prompt(text: str, label: str) -> str:
    """Build the prompt asking the LLM to segment a question paper's transcript.

    Distinct from `review._normalize_prompt`: that rewrites one already-known
    line without changing its meaning; this instead has to find the question
    boundaries themselves in an unstructured transcript, so the prompt asks
    for a list of `{number, statement}` pairs, not a single rewritten string.
    `label` (the assessment's title) is included only to give the LLM the
    same context a human proofreader would have — which paper this is.
    """
    return (
        f"The following is the OCR transcription of the blank question paper "
        f"for the assessment '{label}'. Split it into its individual "
        "questions, in the order they appear, and for each one report its "
        'number exactly as written on the paper (e.g. "1", "1a", "2.1") and '
        "its full statement.\n\n"
        "Reformat each statement as syntactically valid LaTeX/Markdown: wrap "
        "inline mathematical expressions in $ ... $ and standalone/display "
        "expressions in $$ ... $$. Preserve every number, variable and "
        "symbol exactly as written — do not fix, simplify, evaluate, or "
        "otherwise change what the paper says, only its formatting. Skip "
        "any text that is not itself part of a question, such as headers, "
        "instructions or page numbers.\n\n"
        f"OCR transcription:\n{text}\n\n"
        'Answer as JSON of the shape {"questions": [{"number": "<str>", '
        '"statement": "<str>"}, ...]}.'
    )
