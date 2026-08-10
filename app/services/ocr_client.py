"""Client for the PaddleOCR-VL service defined in services/ocr."""

from __future__ import annotations

from dataclasses import dataclass

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from app.core.config import get_settings


class OcrServiceError(RuntimeError):
    """The OCR service could not be reached, refused the request, or answered
    with something that does not match its contract.

    Every failure mode of this adapter — transport, HTTP status, malformed
    JSON, and a schema mismatch — becomes this one type, so callers need no
    per-failure-mode handling.
    """


@dataclass(frozen=True)
class RecognisedRegion:
    """A labelled region of a page, as read by the model."""

    text: str
    box: list[list[float]]
    label: str | None = None


# --- Transport models -------------------------------------------------------
#
# Local to this adapter, deliberately duplicating the shape of
# `services/ocr/app.py`'s response models rather than importing them: the two
# services are independent deployments, and this is where the response the
# OCR service actually sent is checked against the contract we rely on,
# instead of being trusted by convention.


class _Block(BaseModel):
    model_config = ConfigDict(extra="ignore")

    content: str
    box: list[tuple[float, float]]
    label: str | None = None


class _Page(BaseModel):
    model_config = ConfigDict(extra="ignore")

    width: int
    height: int
    blocks: list[_Block]


class _OcrResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pages: list[_Page]


def recognise_image(
    png: bytes, filename: str, page_width: int, page_height: int
) -> list[RecognisedRegion]:
    """Send one rendered page to the OCR service and return what it read.

    Boxes come back in the coordinate space of the image the service worked on,
    which the pipeline may resize; they are rescaled here to the pixels of the
    image we rendered, the one the interface displays.
    """
    parsed = _post(png, filename)

    regions = []
    for page in parsed.pages:
        scale_x = page_width / page.width if page.width else 1.0
        scale_y = page_height / page.height if page.height else 1.0
        regions.extend(_regions(page, scale_x, scale_y))
    return regions


def _post(png: bytes, filename: str) -> _OcrResponse:
    settings = get_settings()
    url = f"{settings.ocr_service_url.rstrip('/')}/ocr"

    try:
        response = httpx.post(
            url,
            files={"file": (filename, png, "image/png")},
            timeout=settings.ocr_timeout_seconds,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise OcrServiceError(
            f"The OCR service answered {error.response.status_code}: {error.response.text}"
        ) from error
    except httpx.HTTPError as error:
        raise OcrServiceError(f"The OCR service at {url} is unreachable: {error}") from error

    try:
        payload = response.json()
    except ValueError as error:
        raise OcrServiceError(
            f"The OCR service at {url} returned a response that is not valid JSON: {error}"
        ) from error

    try:
        return _OcrResponse.model_validate(payload)
    except ValidationError as error:
        raise OcrServiceError(
            f"The OCR service at {url} returned a response that does not match the expected "
            f"shape ({error.error_count()} field(s) failed validation)."
        ) from error


def _regions(page: _Page, scale_x: float, scale_y: float) -> list[RecognisedRegion]:
    return [
        RecognisedRegion(
            text=block.content,
            box=[[x * scale_x, y * scale_y] for x, y in block.box],
            label=block.label,
        )
        for block in page.blocks
        # A block with no content has nothing for the teacher to review.
        if block.content.strip()
    ]
