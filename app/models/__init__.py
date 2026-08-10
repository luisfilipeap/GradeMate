"""ORM models.

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``metadata.create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.assessment import Assessment
from app.models.class_group import ClassGroup
from app.models.ocr_line import OcrLine
from app.models.question import Question
from app.models.student import Student
from app.models.submission import Submission
from app.models.submission_page import SubmissionPage

__all__ = [
    "Base",
    "Assessment",
    "ClassGroup",
    "OcrLine",
    "Question",
    "Student",
    "Submission",
    "SubmissionPage",
]
