"""TASK-002: replacing a submission's PDF invalidates its previous OCR reading."""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.models import Assessment, OcrLine, Student, Submission, SubmissionPage
from tests.factories import minimal_pdf_bytes


def _add_reading_with_image(db_session: Session, submission: Submission) -> str:
    """Attach a page, an accepted OCR line and a real PNG file to a submission."""
    image_path = storage.submission_page_image_path(
        submission.assessment_id, submission.student_id, 1
    )
    storage.write(image_path, b"fake-png-bytes")

    page = SubmissionPage(
        submission_id=submission.id,
        number=1,
        width=100,
        height=100,
        image_path=image_path,
    )
    db_session.add(page)
    db_session.flush()
    db_session.add(
        OcrLine(
            page_id=page.id,
            position=1,
            text="original reading",
            accepted=True,
            box=[[0, 0], [1, 0], [1, 1], [0, 1]],
        )
    )
    db_session.commit()
    return image_path


def _upload(client: TestClient, assessment: Assessment, student: Student) -> None:
    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", minimal_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200, response.text


def test_replacing_the_pdf_removes_pages_lines_and_images(
    client: TestClient,
    db_session: Session,
    assessment: Assessment,
    student: Student,
    submission: Submission,
) -> None:
    image_path = _add_reading_with_image(db_session, submission)
    assert storage.resolve(image_path).is_file()

    _upload(client, assessment, student)

    remaining_pages = db_session.scalars(
        select(SubmissionPage).where(SubmissionPage.submission_id == submission.id)
    ).all()
    assert remaining_pages == []

    remaining_lines = db_session.scalars(
        select(OcrLine).join(SubmissionPage).where(SubmissionPage.submission_id == submission.id)
    ).all()
    assert remaining_lines == []

    assert not storage.resolve(image_path).is_file()

    # The page directory itself is empty; nothing from the old reading survives.
    page_dir = storage.resolve(image_path).parent
    assert not page_dir.exists() or list(page_dir.iterdir()) == []


def test_review_reports_no_pages_immediately_after_replacement(
    client: TestClient,
    db_session: Session,
    assessment: Assessment,
    student: Student,
    submission: Submission,
) -> None:
    _add_reading_with_image(db_session, submission)

    _upload(client, assessment, student)

    response = client.get(f"/api/submissions/{submission.id}/review")
    assert response.status_code == 200
    body = response.json()
    assert body["pages"] == []
    assert body["page_count"] == 0


def test_replacement_survives_a_missing_image_file(
    client: TestClient,
    db_session: Session,
    assessment: Assessment,
    student: Student,
    submission: Submission,
) -> None:
    """A page row whose image already vanished from disk must not break the upload."""
    image_path = storage.submission_page_image_path(
        submission.assessment_id, submission.student_id, 1
    )
    page = SubmissionPage(
        submission_id=submission.id,
        number=1,
        width=100,
        height=100,
        image_path=image_path,
    )
    db_session.add(page)
    db_session.commit()
    # Note: the file is never written, simulating one that went missing.
    assert not storage.resolve(image_path).is_file()

    _upload(client, assessment, student)

    remaining_pages = db_session.scalars(
        select(SubmissionPage).where(SubmissionPage.submission_id == submission.id)
    ).all()
    assert remaining_pages == []


def test_first_upload_for_a_student_has_nothing_to_invalidate(
    client: TestClient, assessment: Assessment, student: Student
) -> None:
    """The happy path (no previous submission) keeps working."""
    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", io.BytesIO(minimal_pdf_bytes()), "application/pdf")},
    )
    assert response.status_code == 200, response.text
