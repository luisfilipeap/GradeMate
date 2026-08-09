"""Endpoints backing the review screen: run the OCR and correct its output."""

from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import SessionDep
from app.core import pdf, storage
from app.core.config import get_settings
from app.models import OcrLine, Submission, SubmissionPage
from app.schemas import OcrLineRead, OcrLineUpdate, ReviewRead
from app.services.ocr_client import OcrServiceError, recognise_image

router = APIRouter(tags=["review"])


@router.get("/submissions/{submission_id}/review", response_model=ReviewRead)
def get_review(submission_id: uuid.UUID, session: SessionDep) -> ReviewRead:
    """Return the pages and OCR lines already stored for a submission.

    A submission whose OCR has not been run yet simply comes back with no pages.
    """
    submission = _get_submission(session, submission_id)
    return _to_review(submission)


@router.post("/submissions/{submission_id}/ocr", response_model=ReviewRead)
def run_ocr(
    submission_id: uuid.UUID,
    session: SessionDep,
    engine: Annotated[
        Literal["ocr", "vl"],
        Query(description="`ocr` for the fast PP-OCR pipeline, `vl` for PaddleOCR-VL."),
    ] = "ocr",
) -> ReviewRead:
    """Rasterise the PDF, send every page to the OCR service and store the result.

    Running it again discards the previous reading, including the teacher's
    corrections, and starts from a clean transcription.
    """
    submission = _get_submission(session, submission_id)
    settings = get_settings()

    absolute = storage.resolve(submission.file_path)
    if not absolute.is_file():
        raise HTTPException(
            status.HTTP_410_GONE,
            detail="The file is registered but missing from the storage volume.",
        )

    rendered = pdf.render_pages(absolute.read_bytes(), settings.page_render_dpi)
    if not rendered:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY, detail="The PDF has no pages to read."
        )

    try:
        recognised = [
            (
                page,
                recognise_image(
                    page.png, f"page-{page.number}.png", engine, page.width, page.height
                ),
            )
            for page in rendered
        ]
    except OcrServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    # Replace any previous reading of this submission.
    for page in submission.pages:
        session.delete(page)
    session.flush()

    for rendered_page, lines in recognised:
        image_path = storage.submission_page_image_path(
            submission.assessment_id, submission.student_id, rendered_page.number
        )
        storage.write(image_path, rendered_page.png)

        page = SubmissionPage(
            submission_id=submission.id,
            number=rendered_page.number,
            width=rendered_page.width,
            height=rendered_page.height,
            image_path=image_path,
            engine=engine,
        )
        page.lines = [
            OcrLine(
                position=position,
                text=region.text,
                confidence=(
                    None if region.confidence is None else min(max(region.confidence, 0.0), 1.0)
                ),
                label=region.label,
                box=region.box,
            )
            for position, region in enumerate(lines, 1)
        ]
        session.add(page)

    session.commit()
    session.refresh(submission)
    return _to_review(submission)


@router.get("/pages/{page_id}/image")
def get_page_image(page_id: uuid.UUID, session: SessionDep) -> FileResponse:
    """Serve the rendered page the OCR boxes refer to."""
    page = session.get(SubmissionPage, page_id)
    if page is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Page not found")

    absolute = storage.resolve(page.image_path)
    if not absolute.is_file():
        raise HTTPException(
            status.HTTP_410_GONE, detail="The page image is missing from the storage volume."
        )
    return FileResponse(absolute, media_type="image/png")


@router.patch("/ocr-lines/{line_id}", response_model=OcrLineRead)
def update_line(line_id: uuid.UUID, payload: OcrLineUpdate, session: SessionDep) -> OcrLine:
    """Accept a line as recognised, or store the teacher's rewrite of it."""
    line = session.get(OcrLine, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Line not found")

    fields = payload.model_dump(exclude_unset=True)
    if "corrected_text" in fields:
        corrected = fields["corrected_text"]
        # An empty edit box means "no correction", not "empty line".
        line.corrected_text = corrected.strip() if corrected and corrected.strip() else None
    if "accepted" in fields:
        line.accepted = fields["accepted"]

    session.commit()
    session.refresh(line)
    return line


def _get_submission(session: Session, submission_id: uuid.UUID) -> Submission:
    submission = session.scalar(
        select(Submission)
        .where(Submission.id == submission_id)
        .options(selectinload(Submission.pages).selectinload(SubmissionPage.lines))
    )
    if submission is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Submission not found")
    return submission


def _to_review(submission: Submission) -> ReviewRead:
    return ReviewRead(
        submission_id=submission.id,
        student_id=submission.student_id,
        assessment_id=submission.assessment_id,
        page_count=len(submission.pages),
        engine=submission.pages[0].engine if submission.pages else None,
        pages=submission.pages,
    )
