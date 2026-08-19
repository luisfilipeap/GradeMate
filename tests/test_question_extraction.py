"""Extracting draft questions from a question paper via OCR + LLM (issue #32).

`extract_questions` reuses the same OCR pipeline as `run_ocr` (render, check
for oversized pages, `gpu_service("ocr")` + `recognise_image`) and then asks
the LLM to segment the resulting transcript into `{number, statement}`
drafts, exactly like `run_ocr` uses `gpu_service("llm")` +
`generate_structured` to normalize a line. `gpu_handoff_enabled` stays off
(the autouse fixture in conftest.py), so `recognise_image` and
`generate_structured` are monkeypatched directly on the `questions` module,
same pattern as `test_review_normalization.py`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes import questions as questions_module
from app.models import Assessment, Question
from app.services.gpu_handoff import GpuHandoffError
from app.services.llm_client import LlmServiceError
from app.services.ocr_client import RecognisedRegion
from tests.factories import minimal_pdf_bytes


def _upload_paper(client: TestClient, assessment: Assessment, *, pages: int = 1) -> None:
    response = client.put(
        f"/api/assessments/{assessment.id}/question-paper",
        files={"file": ("paper.pdf", minimal_pdf_bytes(pages=pages), "application/pdf")},
    )
    assert response.status_code == 204, response.text


def _text_region(text: str) -> RecognisedRegion:
    return RecognisedRegion(text=text, box=[[0, 0], [1, 0], [1, 1], [0, 1]], label="text")


def _stub_ocr(monkeypatch, texts_by_page: list[str]) -> None:
    """Make `recognise_image` return one text region per call, in order."""
    remaining = list(texts_by_page)

    def _fake_recognise(png, filename, width, height, timeout=None):
        return [_text_region(remaining.pop(0))]

    monkeypatch.setattr(questions_module, "recognise_image", _fake_recognise)


def _stub_llm(monkeypatch, answer: dict) -> None:
    monkeypatch.setattr(
        questions_module,
        "generate_structured",
        lambda prompt, schema, timeout=None: answer,
    )


def _stored_ocr_pages(db_session: Session, assessment: Assessment) -> list[str] | None:
    db_session.refresh(assessment)
    return assessment.question_paper_ocr_pages


def test_extract_without_a_paper_is_404(client: TestClient, assessment: Assessment) -> None:
    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")
    assert response.status_code == 404


def test_extract_when_the_file_is_missing_from_storage_is_410(
    client: TestClient, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment)
    from app.core import storage

    storage.resolve(assessment.question_paper_path).unlink()

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")
    assert response.status_code == 410


def test_extract_returns_draft_questions_and_persists_ocr_pages(
    client: TestClient,
    monkeypatch,
    db_session: Session,
    assessment: Assessment,
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["1. What is 2+2? 2. What is 3+3?"])
    _stub_llm(
        monkeypatch,
        {
            "questions": [
                {"number": "1", "statement": "What is $2+2$?"},
                {"number": "2", "statement": "What is $3+3$?"},
            ]
        },
    )

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["questions"] == [
        {"number": "1", "statement": "What is $2+2$?"},
        {"number": "2", "statement": "What is $3+3$?"},
    ]

    # question_paper_ocr_pages is populated by the OCR step...
    assert _stored_ocr_pages(db_session, assessment) == ["1. What is 2+2? 2. What is 3+3?"]
    # ...but nothing was written to `questions`: extraction only proposes.
    stored = db_session.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    ).all()
    assert stored == []


def test_extract_rerun_replaces_rather_than_appends_ocr_pages(
    client: TestClient,
    monkeypatch,
    db_session: Session,
    assessment: Assessment,
) -> None:
    _upload_paper(client, assessment, pages=1)

    _stub_ocr(monkeypatch, ["first run text"])
    _stub_llm(monkeypatch, {"questions": [{"number": "1", "statement": "First statement."}]})
    first = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")
    assert first.status_code == 200, first.text
    assert _stored_ocr_pages(db_session, assessment) == ["first run text"]

    _stub_ocr(monkeypatch, ["second run text, completely different"])
    _stub_llm(monkeypatch, {"questions": [{"number": "1", "statement": "Second statement."}]})
    second = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")
    assert second.status_code == 200, second.text

    # Replaced, not appended: exactly one page's worth of text, the new one.
    assert _stored_ocr_pages(db_session, assessment) == ["second run text, completely different"]


def test_extract_reupload_clears_a_stale_ocr_pages_value(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["stale transcript"])
    _stub_llm(monkeypatch, {"questions": [{"number": "1", "statement": "Statement."}]})
    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")
    assert response.status_code == 200, response.text
    assert _stored_ocr_pages(db_session, assessment) == ["stale transcript"]

    _upload_paper(client, assessment, pages=1)

    assert _stored_ocr_pages(db_session, assessment) is None


def test_extract_guard_rejects_an_empty_question_list(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["only noise, no recognisable question"])
    _stub_llm(monkeypatch, {"questions": []})

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 422
    stored = db_session.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    ).all()
    assert stored == []


def test_extract_guard_rejects_a_duplicate_number(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["1. Question one. 1. Question one again, mislabeled."])
    _stub_llm(
        monkeypatch,
        {
            "questions": [
                {"number": "1", "statement": "Question one."},
                {"number": "1", "statement": "Question one again, mislabeled."},
            ]
        },
    )

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 422
    stored = db_session.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    ).all()
    assert stored == []


def test_extract_guard_rejects_a_blank_number(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["some question with no visible number"])
    _stub_llm(monkeypatch, {"questions": [{"number": "   ", "statement": "Some statement."}]})

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 422


def test_extract_llm_service_error_is_502(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["transcript"])
    monkeypatch.setattr(
        questions_module,
        "generate_structured",
        lambda prompt, schema, timeout=None: (_ for _ in ()).throw(
            LlmServiceError("The LLM service is unreachable")
        ),
    )

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 502
    # OCR itself succeeded and is recorded regardless of the later LLM failure.
    assert _stored_ocr_pages(db_session, assessment) == ["transcript"]
    stored = db_session.scalars(
        select(Question).where(Question.assessment_id == assessment.id)
    ).all()
    assert stored == []


def test_extract_ocr_gpu_handoff_failure_is_502_and_leaves_ocr_pages_untouched(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)

    from contextlib import contextmanager

    @contextmanager
    def _failing_ocr_handoff(name, *, profile=None):
        if name == "ocr":
            raise GpuHandoffError("could not bring up the ocr container")
        yield

    monkeypatch.setattr(questions_module, "gpu_service", _failing_ocr_handoff)

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 502
    assert _stored_ocr_pages(db_session, assessment) is None


def test_extract_llm_gpu_handoff_failure_is_502(
    client: TestClient, monkeypatch, db_session: Session, assessment: Assessment
) -> None:
    _upload_paper(client, assessment, pages=1)
    _stub_ocr(monkeypatch, ["transcript"])

    from contextlib import contextmanager

    @contextmanager
    def _failing_llm_handoff(name, *, profile=None):
        if name == "llm":
            raise GpuHandoffError("could not bring up the llm container")
        yield

    monkeypatch.setattr(questions_module, "gpu_service", _failing_llm_handoff)

    response = client.post(f"/api/assessments/{assessment.id}/question-paper/extract")

    assert response.status_code == 502
    # The OCR step ran (under the real, no-op `gpu_service("ocr")` branch)
    # before the LLM handoff failed, so its result is still recorded.
    assert _stored_ocr_pages(db_session, assessment) == ["transcript"]


def test_extraction_prompt_mentions_the_assessment_title_and_delimiters(
    assessment: Assessment,
) -> None:
    prompt = questions_module._extraction_prompt("some transcript", "Midterm Exam")
    assert "Midterm Exam" in prompt
    assert "some transcript" in prompt
    assert "$ ... $" in prompt
    assert "$$ ... $$" in prompt


def test_extraction_guard_is_a_distinct_module_from_normalization_guard() -> None:
    """Sanity check that issue #32 added a new module rather than reusing #21's."""
    from app.services import normalization_guard, question_extraction_guard

    assert question_extraction_guard is not normalization_guard
    assert question_extraction_guard.extraction_passes(
        {"questions": [{"number": "1", "statement": "A statement."}]}
    )
    assert not question_extraction_guard.extraction_passes({"questions": []})
    assert not question_extraction_guard.extraction_passes(
        {
            "questions": [
                {"number": "1", "statement": "A."},
                {"number": "1", "statement": "B."},
            ]
        }
    )
    assert not question_extraction_guard.extraction_passes(
        {"questions": [{"number": "", "statement": "A."}]}
    )
    assert not question_extraction_guard.extraction_passes(
        {"questions": [{"number": "1", "statement": "   "}]}
    )
