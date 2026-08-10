"""Schemas for assessments."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AssessmentBase(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str | None = None
    applied_on: date | None = None
    max_score: Decimal = Field(default=Decimal("100"), gt=0, max_digits=6, decimal_places=2)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("description")
    @classmethod
    def normalise_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip() or None


class AssessmentCreate(AssessmentBase):
    pass


class AssessmentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    applied_on: date | None = None
    max_score: Decimal | None = Field(default=None, gt=0, max_digits=6, decimal_places=2)


class AssessmentRead(AssessmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    submission_count: int = 0
    question_count: int = 0
    # Metadata about the uploaded question paper, never the stored path: read
    # the file itself through the download endpoint. `None` means no paper
    # has been uploaded yet.
    question_paper_original_filename: str | None = None
    question_paper_page_count: int | None = None
