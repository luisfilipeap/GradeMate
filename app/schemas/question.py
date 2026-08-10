"""Schemas for the questions of an assessment's question paper."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class QuestionBase(BaseModel):
    # The teacher's own numbering ("1", "1a", "2.1"...), not assumed numeric.
    number: str = Field(min_length=1, max_length=20)
    statement: str = Field(min_length=1)

    @field_validator("number", "statement")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class QuestionCreate(QuestionBase):
    pass


class QuestionUpdate(BaseModel):
    number: str | None = Field(default=None, min_length=1, max_length=20)
    statement: str | None = Field(default=None, min_length=1)

    @field_validator("number", "statement")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value else value


class QuestionRead(QuestionBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    assessment_id: uuid.UUID
    # Reading order within the assessment; independent of what `number` reads.
    position: int
    created_at: datetime
    updated_at: datetime
