"""TASK-009: files are published only after the transaction that references
them actually commits.

Each test injects a commit failure and checks the volume, not just the
database: nothing on disk should reference a row that was never written.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import review as review_module
from app.core import storage
from app.models import Assessment, Student, Submission, SubmissionPage
from app.services.ocr_client import RecognisedRegion
from tests.factories import minimal_pdf_bytes


class _SimulatedCommitFailure(RuntimeError):
    """A stand-in for a real commit failure (constraint violation, disk full...)."""


def _break_commit(monkeypatch: pytest.MonkeyPatch, session: Session) -> None:
    def _boom() -> None:
        raise _SimulatedCommitFailure("simulated commit failure")

    monkeypatch.setattr(session, "commit", _boom)


def test_upload_commit_failure_leaves_no_orphan_file(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    assessment: Assessment,
    student: Student,
) -> None:
    _break_commit(monkeypatch, db_session)

    with pytest.raises(_SimulatedCommitFailure):
        client.put(
            f"/api/assessments/{assessment.id}/students/{student.id}/submission",
            files={"file": ("exam.pdf", minimal_pdf_bytes(), "application/pdf")},
        )
    db_session.rollback()

    relative_path = storage.submission_file_path(assessment.id, student.id)
    assert not storage.resolve(relative_path).is_file()

    remaining = db_session.scalars(
        select(Submission).where(
            Submission.assessment_id == assessment.id, Submission.student_id == student.id
        )
    ).all()
    assert remaining == []


def test_replace_commit_failure_leaves_the_previous_file_intact(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    assessment: Assessment,
    student: Student,
) -> None:
    """A half-replaced submission (new file, old row) must never happen."""
    first = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", minimal_pdf_bytes(pages=1), "application/pdf")},
    )
    assert first.status_code == 200
    relative_path = storage.submission_file_path(assessment.id, student.id)
    original_bytes = storage.resolve(relative_path).read_bytes()

    _break_commit(monkeypatch, db_session)
    with pytest.raises(_SimulatedCommitFailure):
        client.put(
            f"/api/assessments/{assessment.id}/students/{student.id}/submission",
            files={"file": ("exam.pdf", minimal_pdf_bytes(pages=3), "application/pdf")},
        )
    db_session.rollback()

    # The original file is exactly what it was, not partially overwritten.
    assert storage.resolve(relative_path).read_bytes() == original_bytes


def test_ocr_commit_failure_leaves_the_previous_reading_intact(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    submission: Submission,
) -> None:
    old_image_path = storage.submission_page_image_path(
        submission.assessment_id, submission.student_id, 1
    )
    storage.write(old_image_path, b"old-image-bytes")
    db_session.add(
        SubmissionPage(
            submission_id=submission.id, number=1, width=10, height=10, image_path=old_image_path
        )
    )
    db_session.commit()

    def _fake_recognise(png: bytes, filename: str, width: int, height: int) -> list:
        return [RecognisedRegion(text="new reading", box=[[0, 0], [1, 0], [1, 1], [0, 1]])]

    monkeypatch.setattr(review_module, "recognise_image", _fake_recognise)
    _break_commit(monkeypatch, db_session)

    with pytest.raises(_SimulatedCommitFailure):
        client.post(f"/api/submissions/{submission.id}/ocr")
    # A real request's session is closed after the handler raises (see
    # `app.db.session.get_session`), which rolls back whatever the failed
    # commit left pending. This test's session is long-lived across requests,
    # so it does the same thing explicitly to see the state a fresh request
    # would actually see.
    db_session.rollback()

    # The old page's image is untouched: not overwritten, not deleted.
    assert storage.resolve(old_image_path).read_bytes() == b"old-image-bytes"

    remaining_pages = db_session.scalars(
        select(SubmissionPage).where(SubmissionPage.submission_id == submission.id)
    ).all()
    assert [page.image_path for page in remaining_pages] == [old_image_path]


def test_ocr_run_on_a_fresh_submission_leaves_no_reading_at_all_on_commit_failure(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    submission: Submission,
) -> None:
    def _fake_recognise(png: bytes, filename: str, width: int, height: int) -> list:
        return [RecognisedRegion(text="new reading", box=[[0, 0], [1, 0], [1, 1], [0, 1]])]

    monkeypatch.setattr(review_module, "recognise_image", _fake_recognise)
    _break_commit(monkeypatch, db_session)

    with pytest.raises(_SimulatedCommitFailure):
        client.post(f"/api/submissions/{submission.id}/ocr")
    db_session.rollback()

    remaining_pages = db_session.scalars(
        select(SubmissionPage).where(SubmissionPage.submission_id == submission.id)
    ).all()
    assert remaining_pages == []

    image_path = storage.submission_page_image_path(
        submission.assessment_id, submission.student_id, 1
    )
    assert not storage.resolve(image_path).is_file()
