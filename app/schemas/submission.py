"""Schemas for submissions (the scanned PDF a student handed in)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SubmissionRead(BaseModel):
    """A stored submission.

    ``file_path`` is deliberately not exposed: it is an internal detail of the
    storage volume. Clients read the PDF through ``/api/submissions/{id}/file``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    assessment_id: uuid.UUID
    student_id: uuid.UUID
    original_filename: str | None
    file_size_bytes: int | None
    page_count: int | None
    checksum_sha256: str | None
    created_at: datetime
    updated_at: datetime
