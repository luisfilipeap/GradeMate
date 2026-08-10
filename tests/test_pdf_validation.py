"""TASK-004: refuse unparseable PDFs at upload, and fail OCR runs cleanly."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import pdf, storage
from app.models import Assessment, Student, Submission
from tests.factories import minimal_pdf_bytes


def _truncated_pdf() -> bytes:
    """A file that starts with the PDF header but is otherwise garbage."""
    content = minimal_pdf_bytes(pages=2)
    return content[: len(content) // 2]


def test_render_pages_raises_a_controlled_error_for_a_truncated_pdf() -> None:
    with pytest.raises(pdf.PdfRenderError):
        pdf.render_pages(_truncated_pdf(), dpi=72)


def test_uploading_a_corrupt_pdf_is_refused_and_leaves_no_trace(
    client: TestClient, db_session: Session, assessment: Assessment, student: Student
) -> None:
    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", _truncated_pdf(), "application/pdf")},
    )
    assert 400 <= response.status_code < 500

    remaining = db_session.scalars(
        select(Submission).where(
            Submission.assessment_id == assessment.id, Submission.student_id == student.id
        )
    ).all()
    assert remaining == []

    relative_path = storage.submission_file_path(assessment.id, student.id)
    assert not storage.resolve(relative_path).is_file()


def test_corrupt_upload_message_is_distinct_from_other_validation_errors(
    client: TestClient, assessment: Assessment, student: Student
) -> None:
    corrupt = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", _truncated_pdf(), "application/pdf")},
    )
    not_a_pdf = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.txt", b"not a pdf at all", "text/plain")},
    )
    assert corrupt.json()["detail"] != not_a_pdf.json()["detail"]


def test_running_ocr_on_an_unrenderable_file_returns_a_controlled_response(
    client: TestClient, db_session: Session, assessment: Assessment, student: Student
) -> None:
    """A file that goes bad on disk after being stored must not crash the OCR run."""
    relative_path = storage.submission_file_path(assessment.id, student.id)
    storage.write(relative_path, _truncated_pdf())

    submission = Submission(
        class_id=assessment.class_id,
        assessment_id=assessment.id,
        student_id=student.id,
        file_path=relative_path,
        page_count=2,
    )
    db_session.add(submission)
    db_session.commit()

    response = client.post(f"/api/submissions/{submission.id}/ocr")
    assert response.status_code == 422
    assert response.status_code != 500

    # No half-written reading was left behind.
    review = client.get(f"/api/submissions/{submission.id}/review").json()
    assert review["pages"] == []
