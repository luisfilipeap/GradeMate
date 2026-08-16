"""Schemas for students."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class StudentBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=160)
    registration_number: str = Field(min_length=1, max_length=40)
    email: EmailStr = Field(max_length=255)

    @field_validator("full_name", "registration_number", mode="before")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str) -> str:
        # The per-class uniqueness constraint is case-sensitive, so store one casing.
        return value.strip().lower()


class StudentCreate(StudentBase):
    pass


class StudentUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    registration_number: str | None = Field(default=None, min_length=1, max_length=40)
    email: EmailStr | None = Field(default=None, max_length=255)

    @field_validator("full_name", "registration_number", mode="before")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if isinstance(value, str) else value

    @field_validator("email")
    @classmethod
    def normalise_email(cls, value: str | None) -> str | None:
        return value.strip().lower() if value else value


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    class_id: uuid.UUID
    created_at: datetime
    updated_at: datetime
