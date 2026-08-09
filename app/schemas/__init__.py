"""Pydantic schemas exposed by the HTTP API."""

from app.schemas.assessment import AssessmentCreate, AssessmentRead, AssessmentUpdate
from app.schemas.class_group import ClassCreate, ClassRead, ClassUpdate
from app.schemas.review import OcrLineRead, OcrLineUpdate, ReviewRead, SubmissionPageRead
from app.schemas.student import StudentCreate, StudentRead, StudentUpdate
from app.schemas.submission import SubmissionRead

__all__ = [
    "OcrLineRead",
    "OcrLineUpdate",
    "ReviewRead",
    "SubmissionPageRead",
    "SubmissionRead",
    "AssessmentCreate",
    "AssessmentRead",
    "AssessmentUpdate",
    "ClassCreate",
    "ClassRead",
    "ClassUpdate",
    "StudentCreate",
    "StudentRead",
    "StudentUpdate",
]
