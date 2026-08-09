"""Client for the PaddleOCR-VL service defined in services/ocr."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings


class OcrServiceError(RuntimeError):
    """The OCR service could not be reached or refused the request."""


@dataclass(frozen=True)
class RecognisedRegion:
    """A labelled region of a page, as read by the model."""

    text: str
    box: list[list[float]]
    label: str | None = None


def recognise_image(
    png: bytes, filename: str, page_width: int, page_height: int
) -> list[RecognisedRegion]:
    """Send one rendered page to the OCR service and return what it read.

    Boxes come back in the coordinate space of the image the service worked on,
    which the pipeline may resize; they are rescaled here to the pixels of the
    image we rendered, the one the interface displays.
    """
    payload = _post(png, filename)

    regions = []
    for page in payload.get("pages", []):
        scale_x = page_width / page["width"] if page.get("width") else 1.0
        scale_y = page_height / page["height"] if page.get("height") else 1.0
        regions.extend(_regions(page, scale_x, scale_y))
    return regions


def _post(png: bytes, filename: str) -> dict[str, Any]:
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

    return response.json()


def _regions(page: dict[str, Any], scale_x: float, scale_y: float) -> list[RecognisedRegion]:
    return [
        RecognisedRegion(
            text=block["content"],
            box=[[float(x) * scale_x, float(y) * scale_y] for x, y in block["box"]],
            label=block.get("label"),
        )
        for block in page.get("blocks", [])
        # A block with no content has nothing for the teacher to review.
        if block.get("content", "").strip()
    ]
