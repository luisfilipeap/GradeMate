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
from app.core.config import Settings, get_settings
from app.models import OcrLine, Submission, SubmissionPage
from app.schemas import OcrLineRead, OcrLineUpdate, ReviewRead
from app.services import normalization_guard
from app.services.gpu_handoff import GpuHandoffError, gpu_service
from app.services.llm_client import LlmServiceError, generate_structured
from app.services.ocr_client import OcrServiceError, recognise_image

logger = logging.getLogger(__name__)

router = APIRouter(tags=["review"])

# Schema the LLM's structured-output response must match (see
# app.services.llm_client.generate_structured). A single string field keeps
# the contract simple; the semantic guard, not the schema, is what protects
# meaning.
_NORMALIZE_SCHEMA = {
    "type": "object",
    "properties": {"normalized": {"type": "string"}},
    "required": ["normalized"],
    "additionalProperties": False,
}


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

    def _deadline_exceeded() -> HTTPException:
        return HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT,
            detail=(
                f"The OCR run exceeded its {settings.ocr_job_timeout_seconds:.0f}s "
                f"job timeout after reading {len(recognised)} of {len(rendered)} "
                "page(s). The previous reading, if any, was left untouched."
            ),
        )

    recognised = []
    try:
        # Sequential GPU handoff (issue #21): the OCR container is brought up
        # for this run and stopped again as soon as this block exits, so it
        # is never GPU-resident at the same time as the `llm` container the
        # normalization step below brings up in turn.
        with gpu_service("ocr"):
            for page in rendered:
                now = time.monotonic()
                if now > deadline:
                    raise _deadline_exceeded()
                # The remaining job budget also bounds this call's own HTTP
                # timeout, so a page can never wait past the deadline for a
                # response that would be discarded anyway.
                call_timeout = min(deadline - now, settings.ocr_timeout_seconds)
                regions = recognise_image(
                    page.png,
                    f"page-{page.number}.png",
                    page.width,
                    page.height,
                    timeout=call_timeout,
                )
                recognised.append((page, regions))

            # The loop above only checks the deadline *before* each call; the
            # last call itself could still have run past it, so it must be
            # re-checked once more before anything is persisted.
            if time.monotonic() > deadline:
                raise _deadline_exceeded()
    except OcrServiceError as error:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, detail=str(error)) from error
    except GpuHandoffError as error:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            detail=f"Could not bring up the OCR service for this run: {error}",
        ) from error

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

    # The OCR reading is durably committed by this point; normalization is a
    # best-effort enhancement layered on top of it, never a precondition for
    # it. Any failure here — the LLM unreachable, timing out, answering
    # something malformed, or the semantic guard rejecting its proposal —
    # flags the affected line and returns normally, per issue #21.
    _normalize_submission(session, submission)

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


def _normalize_submission(session: Session, submission: Submission) -> None:
    """Normalize every eligible line of a freshly OCR'd submission (issue #21).

    Eligible lines are formula regions and math-bearing text lines (see
    `normalization_guard.is_eligible`). When there are none, the `llm`
    container is never brought up at all — nothing to gain from paying that
    GPU handoff for a submission with no math on it.
    """
    lines = [line for page in submission.pages for line in page.lines]
    eligible = [line for line in lines if normalization_guard.is_eligible(line.text, line.label)]
    if not eligible:
        return

    settings = get_settings()
    try:
        # Same sequential handoff as the OCR call above, mirrored: `llm` is
        # brought up only for this block and stopped again as soon as it
        # exits, so `ocr` (already stopped above) and `llm` are never
        # GPU-resident together.
        with gpu_service("llm", profile="tools"):
            for line in eligible:
                _normalize_line(line, settings)
    except GpuHandoffError as error:
        logger.warning(
            "Submission %s: could not bring up the LLM service for normalization: %s",
            submission.id,
            error,
        )
        # Nothing in the block above ran (the handoff failed before it could
        # yield) or it was cut short partway through; either way, every line
        # that did not get a result must be flagged, not silently left as
        # "not attempted" — the review screen has no other way to know.
        for line in eligible:
            if line.normalized_text is None:
                line.normalization_incomplete = True

    session.commit()


def _normalize_line(line: OcrLine, settings: Settings) -> None:
    """Ask the LLM to normalize one line and apply the semantic guard to its answer."""
    try:
        response = generate_structured(
            _normalize_prompt(line.text), _NORMALIZE_SCHEMA, timeout=settings.llm_timeout_seconds
        )
    except LlmServiceError as error:
        logger.warning("Line %s: normalization request failed: %s", line.id, error)
        line.normalized_text = None
        line.normalization_incomplete = True
        return

    proposal = response.get("normalized")
    if not isinstance(proposal, str) or not proposal.strip():
        logger.warning("Line %s: normalization returned an empty proposal", line.id)
        line.normalized_text = None
        line.normalization_incomplete = True
        return

    if not normalization_guard.guard_passes(line.text, proposal):
        logger.info("Line %s: normalization proposal rejected by the semantic guard", line.id)
        line.normalized_text = None
        line.normalization_incomplete = True
        return

    line.normalized_text = proposal
    line.normalization_incomplete = False


def _normalize_prompt(text: str) -> str:
    return (
        "Rewrite the following OCR transcription of a handwritten exam answer "
        "as syntactically valid LaTeX/Markdown. Preserve every number, "
        "variable and symbol exactly as given — do not fix, simplify, "
        "evaluate, or otherwise change what was written, only its "
        "formatting.\n\n"
        f"OCR transcription:\n{text}\n\n"
        'Answer as JSON of the shape {"normalized": "<the rewritten text>"}.'
    )


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
