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


class PdfRenderError(RuntimeError):
    """A stored PDF could not be rasterised.

    Wraps pypdfium2's own exception so callers only need to know about this
    module, not about the rendering library behind it.
    """


class PdfValidationError(RuntimeError):
    """An uploaded file failed a basic check before being accepted.

    ``code`` lets a caller tell the failures apart (to map them to distinct
    HTTP statuses) without parsing the message text.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


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


def validate_pdf_upload(content: bytes, max_bytes: int) -> int:
    """Reject an empty, oversized, non-PDF or unparseable upload.

    Shared by every endpoint that accepts a PDF (submissions, question
    papers): the header check, the size limit and the "does it actually
    parse" check are the same regardless of what the PDF will become.

    Returns:
        The page count, so callers that need it do not parse the document a
        second time.

    Raises:
        PdfValidationError: with a ``code`` of ``"empty"``, ``"too_large"``,
            ``"not_pdf"`` or ``"unreadable"``.
    """
    if not content:
        raise PdfValidationError("empty", "The uploaded file is empty.")

    if len(content) > max_bytes:
        raise PdfValidationError(
            "too_large", f"The file is larger than the {max_bytes} byte limit."
        )

    if not looks_like_pdf(content):
        raise PdfValidationError("not_pdf", "Only PDF files are accepted.")

    page_count = count_pages(content)
    if page_count is None:
        raise PdfValidationError(
            "unreadable",
            "The file could not be read as a PDF. Re-scan the document and try again.",
        )
    return page_count


def render_pages(content: bytes, dpi: int) -> list[RenderedPage]:
    """Rasterise every page of a PDF to a PNG image.

    Raises:
        PdfRenderError: the document could not be opened or a page could not
            be rasterised. This can happen even after ``count_pages`` and
            ``looks_like_pdf`` succeeded: a document can be well-formed enough
            to report its page count while still failing to render.
    """
    try:
        document = pdfium.PdfDocument(content)
    except pdfium.PdfiumError as error:
        raise PdfRenderError(f"The PDF could not be opened for rendering: {error}") from error

    try:
        pages = []
        for index, page in enumerate(document, 1):
            try:
                bitmap = page.render(scale=dpi / BASE_DPI)
            except pdfium.PdfiumError as error:
                raise PdfRenderError(
                    f"Page {index} of the PDF could not be rendered: {error}"
                ) from error
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
