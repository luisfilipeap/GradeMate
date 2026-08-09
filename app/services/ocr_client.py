"""Client for the PaddleOCR service defined in services/ocr."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings


class OcrServiceError(RuntimeError):
    """The OCR service could not be reached or refused the request."""


@dataclass(frozen=True)
class RecognisedRegion:
    """A region of a page, as read by either engine.

    The classic engine returns short lines with a confidence and no label; the
    VL engine returns larger labelled blocks with no confidence.
    """

    text: str
    box: list[list[float]]
    confidence: float | None = None
    label: str | None = None


def recognise_image(
    png: bytes, filename: str, engine: str, page_width: int, page_height: int
) -> list[RecognisedRegion]:
    """Send one rendered page to the OCR service and return what it read.

    Boxes come back in the coordinate space of the image the service worked on,
    which the VL pipeline may resize; they are rescaled here to the pixels of
    the image we rendered, the one the interface displays.
    """
    path = "/ocr-vl" if engine == "vl" else "/ocr"
    payload = _post(path, png, filename)

    regions = []
    for page in payload.get("pages", []):
        scale_x = page_width / page["width"] if page.get("width") else 1.0
        scale_y = page_height / page["height"] if page.get("height") else 1.0
        regions.extend(_regions(page, scale_x, scale_y))
    return regions


def _post(path: str, png: bytes, filename: str) -> dict[str, Any]:
    settings = get_settings()
    url = f"{settings.ocr_service_url.rstrip('/')}{path}"

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
    def box(points: Any) -> list[list[float]]:
        return [[float(x) * scale_x, float(y) * scale_y] for x, y in points]

    if "blocks" in page:
        return [
            RecognisedRegion(
                text=block["content"],
                box=box(block["box"]),
                label=block.get("label"),
            )
            for block in page["blocks"]
            # A block with no content has nothing for the teacher to review.
            if block.get("content", "").strip()
        ]

    return [
        RecognisedRegion(
            text=line["text"],
            box=box(line["box"]),
            confidence=float(line["confidence"]),
        )
        for line in page.get("lines", [])
    ]
