"""TASK-003: deleting a student, an assessment or a class removes its files too."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core import storage
from app.models import Assessment, ClassGroup, Student, SubmissionPage
from tests.factories import make_assessment, make_class, make_student, make_submission


def _submission_with_page_image(db_session: Session, assessment: Assessment, student: Student):
    submission = make_submission(db_session, assessment, student)
    image_path = storage.submission_page_image_path(assessment.id, student.id, 1)
    storage.write(image_path, b"fake-png-bytes")
    db_session.add(
        SubmissionPage(
            submission_id=submission.id, number=1, width=10, height=10, image_path=image_path
        )
    )
    db_session.commit()
    return submission, image_path


def test_deleting_a_student_removes_their_submission_files(
    client: TestClient, db_session: Session, class_group: ClassGroup
) -> None:
    student = make_student(db_session, class_group)
    assessment = make_assessment(db_session, class_group)
    _submission, image_path = _submission_with_page_image(db_session, assessment, student)
    pdf_path = storage.submission_file_path(assessment.id, student.id)
    assert storage.resolve(pdf_path).is_file()
    assert storage.resolve(image_path).is_file()

    response = client.delete(f"/api/students/{student.id}")
    assert response.status_code == 204

    assert not storage.resolve(pdf_path).is_file()
    assert not storage.resolve(image_path).is_file()


def test_deleting_an_assessment_removes_submission_files(
    client: TestClient, db_session: Session, class_group: ClassGroup
) -> None:
    student = make_student(db_session, class_group)
    assessment = make_assessment(db_session, class_group)
    _submission, image_path = _submission_with_page_image(db_session, assessment, student)
    pdf_path = storage.submission_file_path(assessment.id, student.id)

    response = client.delete(f"/api/assessments/{assessment.id}")
    assert response.status_code == 204

    assert not storage.resolve(pdf_path).is_file()
    assert not storage.resolve(image_path).is_file()


def test_deleting_a_class_removes_every_submission_file(
    client: TestClient, db_session: Session
) -> None:
    class_group = make_class(db_session)
    student_a = make_student(db_session, class_group)
    student_b = make_student(db_session, class_group)
    assessment = make_assessment(db_session, class_group)
    _sub_a, image_a = _submission_with_page_image(db_session, assessment, student_a)
    _sub_b, image_b = _submission_with_page_image(db_session, assessment, student_b)

    response = client.delete(f"/api/classes/{class_group.id}")
    assert response.status_code == 204

    for path in (
        storage.submission_file_path(assessment.id, student_a.id),
        storage.submission_file_path(assessment.id, student_b.id),
        image_a,
        image_b,
    ):
        assert not storage.resolve(path).is_file()


def test_deleting_a_student_with_a_missing_file_still_succeeds(
    client: TestClient, db_session: Session, class_group: ClassGroup
) -> None:
    """A file already gone from disk must not turn the delete into an error."""
    student = make_student(db_session, class_group)
    assessment = make_assessment(db_session, class_group)
    submission = make_submission(db_session, assessment, student)
    storage.resolve(submission.file_path).unlink()
    assert not storage.resolve(submission.file_path).is_file()

    response = client.delete(f"/api/students/{student.id}")
    assert response.status_code == 204
