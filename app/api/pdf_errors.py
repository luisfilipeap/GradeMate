"""Translates `PdfValidationError` into the HTTP response the interface shows.

Kept separate from `app.core.pdf` so that module stays free of a web
framework dependency; every route accepting a PDF (submissions, question
papers) shares this translation instead of repeating it.
"""

from __future__ import annotations

from fastapi import HTTPException, status

from app.core.pdf import PdfValidationError

_STATUS_BY_CODE = {
    "empty": status.HTTP_400_BAD_REQUEST,
    "too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    "not_pdf": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
    "unreadable": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def as_http_exception(error: PdfValidationError) -> HTTPException:
    """Map a validation failure to the status code it has always had."""
    return HTTPException(_STATUS_BY_CODE[error.code], detail=str(error))
