"""Endpoints backing the review screen: run the OCR and correct its output."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import SessionDep
from app.core import pdf, storage
from app.core.config import get_settings
from app.models import OcrLine, Submission, SubmissionPage
from app.schemas import OcrLineRead, OcrLineUpdate, ReviewRead
from app.services.ocr_client import OcrServiceError, recognise_image

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])


@router.get("/submissions/{submission_id}/review", response_model=ReviewRead)
def get_review(submission_id: uuid.UUID, session: SessionDep) -> ReviewRead:
    """Return the pages and OCR lines already stored for a submission.

    A submission whose OCR has not been run yet simply comes back with no pages.
    """
    submission = _get_submission(session, submission_id)
    return _to_review(submission)


@router.post("/submissions/{submission_id}/ocr", response_model=ReviewRead)
def run_ocr(submission_id: uuid.UUID, session: SessionDep) -> ReviewRead:
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

    # A ceiling on the whole run, distinct from the per-page HTTP timeout
    # already enforced inside `recognise_image`: a document with many pages,
    # each individually fast enough, could otherwise run unbounded.
    deadline = time.monotonic() + settings.ocr_job_timeout_seconds
    recognised = []
    try:
        for page in rendered:
            if time.monotonic() > deadline:
                raise HTTPException(
                    status.HTTP_504_GATEWAY_TIMEOUT,
                    detail=(
                        f"The OCR run exceeded its {settings.ocr_job_timeout_seconds:.0f}s "
                        f"job timeout after reading {len(recognised)} of {len(rendered)} "
                        "page(s). The previous reading, if any, was left untouched."
                    ),
                )
            regions = recognise_image(page.png, f"page-{page.number}.png", page.width, page.height)
            recognised.append((page, regions))
    except OcrServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error

    # Replace any previous reading of this submission.
    for page in submission.pages:
        session.delete(page)
    session.flush()

    # Every page image is staged now but only published below, after the
    # commit succeeds — so a failure partway through never leaves images from
    # this run sitting next to rows from the previous one.
    staged_images: list[tuple[str, Path]] = []
    for rendered_page, regions in recognised:
        image_path = storage.submission_page_image_path(
            submission.assessment_id, submission.student_id, rendered_page.number
        )
        staged_images.append((image_path, storage.stage(image_path, rendered_page.png)))

        page = SubmissionPage(
            submission_id=submission.id,
            number=rendered_page.number,
            width=rendered_page.width,
            height=rendered_page.height,
            image_path=image_path,
        )
        page.lines = [
            OcrLine(position=position, text=region.text, label=region.label, box=region.box)
            for position, region in enumerate(regions, 1)
        ]
        session.add(page)

    try:
        session.commit()
    except BaseException:
        for _, staged_path in staged_images:
            storage.discard(staged_path)
        raise
    session.refresh(submission)

    publish_failures = []
    for image_path, staged_path in staged_images:
        try:
            storage.publish(staged_path, image_path)
        except OSError:
            publish_failures.append(image_path)
    if publish_failures:
        # The database already committed and is the source of truth; this
        # inconsistency (rows referencing images that failed to land) must
        # stay visible rather than being silently swallowed.
        logger.error(
            "Submission %s committed its OCR reading but %d page image(s) failed to publish: %s",
            submission.id,
            len(publish_failures),
            publish_failures,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The OCR reading was recorded but some page images could not be stored.",
        )

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
        pages=submission.pages,
    )
