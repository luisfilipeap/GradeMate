"""Translation of database integrity errors into HTTP responses."""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

# Constraint name -> message shown to the user.
CONSTRAINT_MESSAGES = {
    "uq_classes_code": "Another class already uses this code.",
    "uq_students_class_registration": (
        "This registration number is already used by another student in this class."
    ),
    "uq_students_class_email": (
        "This e-mail address is already used by another student in this class."
    ),
    "uq_assessments_class_title": "This class already has an assessment with this title.",
    "uq_submissions_assessment_student": (
        "This student already has a submission for this assessment."
    ),
    "uq_submissions_file_path": "Another submission already points at this file.",
    "ck_assessments_max_score_positive": "The maximum score must be greater than zero.",
    "uq_questions_assessment_number": ("This assessment already has a question with this number."),
}

DEFAULT_MESSAGE = "The operation conflicts with data already stored."


def describe_integrity_error(error: IntegrityError) -> str:
    """Return a human-readable message for a violated constraint."""
    constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
    if constraint in CONSTRAINT_MESSAGES:
        return CONSTRAINT_MESSAGES[constraint]
    return DEFAULT_MESSAGE


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the application-wide exception handlers."""

    @app.exception_handler(IntegrityError)
    async def _integrity_error_handler(_: Request, exc: IntegrityError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": describe_integrity_error(exc)},
        )
