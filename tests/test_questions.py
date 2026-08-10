"""TASK-011: the question paper and the questions it contains."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.models import Assessment, ClassGroup, Question
from tests.factories import make_assessment, minimal_pdf_bytes


def _upload_paper(client: TestClient, assessment: Assessment, *, pages: int = 2) -> None:
    response = client.put(
        f"/api/assessments/{assessment.id}/question-paper",
        files={"file": ("paper.pdf", minimal_pdf_bytes(pages=pages), "application/pdf")},
    )
    assert response.status_code == 204, response.text


def test_question_paper_can_be_uploaded_served_and_replaced(
    client: TestClient, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=3)

    download = client.get(f"/api/assessments/{assessment.id}/question-paper/file")
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"

    meta = client.get(f"/api/assessments/{assessment.id}").json()
    assert meta["question_paper_original_filename"] == "paper.pdf"
    assert meta["question_paper_page_count"] == 3

    # Replace with a different paper.
    _upload_paper(client, assessment, pages=1)
    meta_after = client.get(f"/api/assessments/{assessment.id}").json()
    assert meta_after["question_paper_page_count"] == 1


def test_question_paper_download_before_upload_is_404(
    client: TestClient, assessment: Assessment
) -> None:
    response = client.get(f"/api/assessments/{assessment.id}/question-paper/file")
    assert response.status_code == 404


def test_corrupt_question_paper_is_refused(client: TestClient, assessment: Assessment) -> None:
    truncated = minimal_pdf_bytes(pages=2)[:20]
    response = client.put(
        f"/api/assessments/{assessment.id}/question-paper",
        files={"file": ("paper.pdf", truncated, "application/pdf")},
    )
    assert 400 <= response.status_code < 500

    meta = client.get(f"/api/assessments/{assessment.id}").json()
    assert meta["question_paper_original_filename"] is None


def test_questions_crud_and_ordering(client: TestClient, assessment: Assessment) -> None:
    first = client.post(
        f"/api/assessments/{assessment.id}/questions",
        json={"number": "1", "statement": "What is $1+1$?"},
    )
    assert first.status_code == 201
    second = client.post(
        f"/api/assessments/{assessment.id}/questions",
        json={"number": "2", "statement": "What is $2+2$?"},
    )
    assert second.status_code == 201
    assert first.json()["position"] == 1
    assert second.json()["position"] == 2

    listed = client.get(f"/api/assessments/{assessment.id}/questions").json()
    assert [q["number"] for q in listed] == ["1", "2"]

    edited = client.patch(
        f"/api/questions/{first.json()['id']}", json={"statement": "What is $1+2$?"}
    )
    assert edited.status_code == 200
    assert edited.json()["statement"] == "What is $1+2$?"
    assert edited.json()["number"] == "1"  # unchanged field stays as it was

    deleted = client.delete(f"/api/questions/{second.json()['id']}")
    assert deleted.status_code == 204
    remaining = client.get(f"/api/assessments/{assessment.id}/questions").json()
    assert len(remaining) == 1

    meta = client.get(f"/api/assessments/{assessment.id}").json()
    assert meta["question_count"] == 1


def test_duplicate_question_number_is_rejected_with_409(
    client: TestClient, assessment: Assessment
) -> None:
    client.post(
        f"/api/assessments/{assessment.id}/questions",
        json={"number": "1", "statement": "First statement."},
    )
    response = client.post(
        f"/api/assessments/{assessment.id}/questions",
        json={"number": "1", "statement": "A different statement, same number."},
    )
    assert response.status_code == 409


def test_the_same_number_is_allowed_across_different_assessments(
    client: TestClient, db_session: Session, class_group: ClassGroup
) -> None:
    assessment_a = make_assessment(db_session, class_group, title="Midterm")
    assessment_b = make_assessment(db_session, class_group, title="Final")

    first = client.post(
        f"/api/assessments/{assessment_a.id}/questions",
        json={"number": "1", "statement": "Statement A."},
    )
    second = client.post(
        f"/api/assessments/{assessment_b.id}/questions",
        json={"number": "1", "statement": "Statement B."},
    )
    assert first.status_code == 201
    assert second.status_code == 201


def test_deleting_an_assessment_removes_its_questions_and_paper_file(
    client: TestClient, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment)
    client.post(
        f"/api/assessments/{assessment.id}/questions",
        json={"number": "1", "statement": "Statement."},
    )
    paper_path = storage.question_paper_path(assessment.id)
    assert storage.resolve(paper_path).is_file()

    response = client.delete(f"/api/assessments/{assessment.id}")
    assert response.status_code == 204

    assert not storage.resolve(paper_path).is_file()
    remaining_questions = db_session.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    ).all()
    assert remaining_questions == []
