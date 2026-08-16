"""Schemas for classes."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _blank_to_none(value: str | None) -> str | None:
    """Treat an empty form field as "not provided"."""
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class ClassBase(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=60)
    academic_term: str | None = Field(default=None, max_length=40)
    description: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", "academic_term", "description")
    @classmethod
    def normalise_optional(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, max_length=60)
    academic_term: str | None = Field(default=None, max_length=40)
    description: str | None = None

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("code", "academic_term", "description")
    @classmethod
    def normalise_optional(cls, value: str | None) -> str | None:
        return _blank_to_none(value)


class ClassRead(ClassBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    student_count: int = 0
    assessment_count: int = 0
