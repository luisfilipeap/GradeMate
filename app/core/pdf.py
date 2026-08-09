"""Small helpers to inspect an uploaded PDF before storing it."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass

import pypdfium2 as pdfium
from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF-"

# pypdfium2 renders in units of 72 dpi.
BASE_DPI = 72


@dataclass(frozen=True)
class RenderedPage:
    """A page of a PDF rasterised to PNG."""

    number: int
    png: bytes
    width: int
    height: int


def looks_like_pdf(content: bytes) -> bool:
    """Check the file header, so a renamed .doc is not accepted as a PDF."""
    return content.startswith(PDF_MAGIC)


def count_pages(content: bytes) -> int | None:
    """Return the number of pages, or None when the file cannot be parsed."""
    try:
        return len(PdfReader(io.BytesIO(content)).pages)
    except (PdfReadError, ValueError, OSError):
        logger.warning("Could not read the page count of an uploaded PDF")
        return None


def render_pages(content: bytes, dpi: int) -> list[RenderedPage]:
    """Rasterise every page of a PDF to a PNG image."""
    document = pdfium.PdfDocument(content)
    try:
        pages = []
        for index, page in enumerate(document, 1):
            bitmap = page.render(scale=dpi / BASE_DPI)
            image = bitmap.to_pil()
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            pages.append(
                RenderedPage(
                    number=index,
                    png=buffer.getvalue(),
                    width=image.width,
                    height=image.height,
                )
            )
        return pages
    finally:
        document.close()
