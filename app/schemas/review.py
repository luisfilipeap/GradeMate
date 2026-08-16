"""Schemas for the review screen: rendered pages and their OCR lines."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OcrLineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    page_id: uuid.UUID
    position: int
    text: str
    corrected_text: str | None
    accepted: bool
    # Region type: "text", "inline_formula", "display_formula", "table"…
    label: str | None
    # Polygon in pixels of the page image: [[x, y], ...].
    box: list[list[float]]
    # LLM-normalized LaTeX/Markdown, set only when normalization ran and
    # passed the semantic guard (issue #21). Distinct from `corrected_text`.
    normalized_text: str | None
    # True when normalization did not produce a usable `normalized_text`:
    # the LLM was unreachable, timed out, answered something malformed, or
    # the guard rejected its proposal.
    normalization_incomplete: bool
    created_at: datetime
    updated_at: datetime


class OcrLineUpdate(BaseModel):
    """Partial update: accept a line, rewrite it, or undo the rewrite.

    Sending ``corrected_text: null`` restores the original OCR reading.
    """

    corrected_text: str | None = Field(default=None)
    accepted: bool | None = None


class SubmissionPageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    submission_id: uuid.UUID
    number: int
    width: int
    height: int
    lines: list[OcrLineRead] = []


class ReviewRead(BaseModel):
    """Everything the review screen needs for one submission."""

    submission_id: uuid.UUID
    student_id: uuid.UUID
    assessment_id: uuid.UUID
    page_count: int
    pages: list[SubmissionPageRead]
