"""Helpers to build the recurring domain objects tests need.

Each function inserts a row (and commits, since tests run inside a savepoint
that is rolled back at teardown) using sensible defaults that can be
overridden. The matching fixtures below compose them, so a test that only
cares about a submission gets its class, student and assessment for free.
"""

from __future__ import annotations

import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from pypdf import PdfWriter
from sqlalchemy.orm import Session

from app.models import Assessment, ClassGroup, Student, Submission


def minimal_pdf_bytes(pages: int = 1) -> bytes:
    """Build a small, well-formed, parseable PDF with the given number of pages."""
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=595, height=842)  # A4 at 72 dpi
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def make_class(session: Session, **overrides: object) -> ClassGroup:
    defaults = {"name": f"Class {uuid.uuid4().hex[:6]}"}
    defaults.update(overrides)
    class_group = ClassGroup(**defaults)
    session.add(class_group)
    session.commit()
    session.refresh(class_group)
    return class_group


def make_student(session: Session, class_group: ClassGroup, **overrides: object) -> Student:
    suffix = uuid.uuid4().hex[:6]
    defaults = {
        "class_id": class_group.id,
        "full_name": f"Student {suffix}",
        "registration_number": suffix,
        "email": f"student-{suffix}@example.com",
    }
    defaults.update(overrides)
    student = Student(**defaults)
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


def make_assessment(session: Session, class_group: ClassGroup, **overrides: object) -> Assessment:
    defaults = {
        "class_id": class_group.id,
        "title": f"Assessment {uuid.uuid4().hex[:6]}",
        "applied_on": date(2026, 1, 1),
        "max_score": Decimal("100"),
    }
    defaults.update(overrides)
    assessment = Assessment(**defaults)
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return assessment


def make_submission(
    session: Session,
    assessment: Assessment,
    student: Student,
    *,
    write_file: bool = True,
    **overrides: object,
) -> Submission:
    from app.core import storage

    relative_path = storage.submission_file_path(assessment.id, student.id)
    content = minimal_pdf_bytes()
    if write_file:
        storage.write(relative_path, content)

    defaults = {
        "class_id": assessment.class_id,
        "assessment_id": assessment.id,
        "student_id": student.id,
        "file_path": relative_path,
        "original_filename": "exam.pdf",
        "file_size_bytes": len(content),
        "page_count": 1,
        "checksum_sha256": "0" * 64,
    }
    defaults.update(overrides)
    submission = Submission(**defaults)
    session.add(submission)
    session.commit()
    session.refresh(submission)
    return submission


@pytest.fixture
def class_group(db_session: Session) -> ClassGroup:
    return make_class(db_session)


@pytest.fixture
def student(db_session: Session, class_group: ClassGroup) -> Student:
    return make_student(db_session, class_group)


@pytest.fixture
def assessment(db_session: Session, class_group: ClassGroup) -> Assessment:
    return make_assessment(db_session, class_group)


@pytest.fixture
def submission(db_session: Session, assessment: Assessment, student: Student) -> Submission:
    return make_submission(db_session, assessment, student)
