"""TASK-008: nothing on the backend can be exhausted by one upload or OCR run."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import review as review_module
from app.core.config import get_settings
from app.models import Assessment, Student, Submission
from app.services.ocr_client import RecognisedRegion
from tests.factories import minimal_pdf_bytes


def test_oversized_upload_is_refused_before_the_body_is_parsed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    assessment: Assessment,
    student: Student,
    db_session: Session,
) -> None:
    # 1 MB declared limit + the middleware's 1 MB multipart slack = 2 MB ceiling.
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)
    oversized_body = b"x" * (3 * 1024 * 1024)

    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        content=oversized_body,
        headers={"content-type": "multipart/form-data; boundary=none"},
    )

    assert response.status_code == 413
    # Never reached the route, so no row was created for it.
    remaining = db_session.scalars(
        select(Submission).where(
            Submission.assessment_id == assessment.id, Submission.student_id == student.id
        )
    ).all()
    assert remaining == []


def test_an_upload_within_the_limit_still_works(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, assessment: Assessment, student: Student
) -> None:
    monkeypatch.setattr(get_settings(), "max_upload_mb", 5)
    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", minimal_pdf_bytes(), "application/pdf")},
    )
    assert response.status_code == 200


def test_a_pdf_beyond_the_page_ceiling_is_refused(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    assessment: Assessment,
    student: Student,
    db_session: Session,
) -> None:
    monkeypatch.setattr(get_settings(), "max_submission_pages", 2)
    response = client.put(
        f"/api/assessments/{assessment.id}/students/{student.id}/submission",
        files={"file": ("exam.pdf", minimal_pdf_bytes(pages=5), "application/pdf")},
    )
    assert response.status_code == 413
    assert "5 pages" in response.json()["detail"]

    remaining = db_session.scalars(
        select(Submission).where(
            Submission.assessment_id == assessment.id, Submission.student_id == student.id
        )
    ).all()
    assert remaining == []


def test_a_page_beyond_the_pixel_ceiling_is_refused(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(get_settings(), "max_page_pixels", 10)  # any real page exceeds this

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 413
    review = client.get(f"/api/submissions/{submission.id}/review").json()
    assert review["pages"] == []


def test_ocr_job_timeout_stops_a_run_that_takes_too_long(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session, submission: Submission
) -> None:
    from app.core import storage

    # A 2-page document, so the deadline can be crossed between page 1 and page 2.
    storage.write(submission.file_path, minimal_pdf_bytes(pages=2))

    monkeypatch.setattr(get_settings(), "ocr_job_timeout_seconds", 0.05)

    def _slow_recognise(
        png: bytes, filename: str, width: int, height: int, timeout: float | None = None
    ) -> list:
        time.sleep(0.08)
        return [RecognisedRegion(text="x", box=[[0, 0], [1, 0], [1, 1], [0, 1]])]

    monkeypatch.setattr(review_module, "recognise_image", _slow_recognise)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 504
    review = client.get(f"/api/submissions/{submission.id}/review").json()
    # No half-written reading: the run was rejected before anything was stored.
    assert review["pages"] == []


def test_ocr_job_timeout_when_the_only_call_exceeds_the_deadline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session, submission: Submission
) -> None:
    """A single-page submission has no "between pages" gap to catch a slow call:
    the deadline is only crossed *during* the one and only call, so it must be
    re-checked after that call returns, not merely before it starts.
    """
    from app.core import storage

    storage.write(submission.file_path, minimal_pdf_bytes(pages=1))

    monkeypatch.setattr(get_settings(), "ocr_job_timeout_seconds", 0.05)

    def _slow_recognise(
        png: bytes, filename: str, width: int, height: int, timeout: float | None = None
    ) -> list:
        time.sleep(0.08)
        return [RecognisedRegion(text="x", box=[[0, 0], [1, 0], [1, 1], [0, 1]])]

    monkeypatch.setattr(review_module, "recognise_image", _slow_recognise)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 504
    review = client.get(f"/api/submissions/{submission.id}/review").json()
    assert review["pages"] == []


def test_ocr_job_timeout_when_only_the_last_page_call_exceeds_the_deadline(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session, submission: Submission
) -> None:
    """Every call before the last one stays within budget; only the final call
    runs long enough to cross the deadline. The pre-call check ahead of that
    last page still passes, so only the post-loop re-check can catch it.
    """
    from app.core import storage

    storage.write(submission.file_path, minimal_pdf_bytes(pages=2))

    monkeypatch.setattr(get_settings(), "ocr_job_timeout_seconds", 0.05)

    calls = 0

    def _recognise(
        png: bytes, filename: str, width: int, height: int, timeout: float | None = None
    ) -> list:
        nonlocal calls
        calls += 1
        if calls == 2:
            time.sleep(0.08)
        return [RecognisedRegion(text="x", box=[[0, 0], [1, 0], [1, 1], [0, 1]])]

    monkeypatch.setattr(review_module, "recognise_image", _recognise)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 504
    assert calls == 2  # both pages were attempted; only the last one ran long
    review = client.get(f"/api/submissions/{submission.id}/review").json()
    assert review["pages"] == []
