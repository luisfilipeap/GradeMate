"""Post-OCR LaTeX normalization (issue #21): triggered automatically inside
`run_ocr()`, guarded against altering any number or symbol, and never able
to break the submission or the teacher's accept/rewrite flow.

`gpu_handoff_enabled` stays off (the autouse fixture in conftest.py), so the
GPU handoff itself is a no-op here; `review_module.gpu_service` is replaced
with a recording fake in the tests that care about call order, so the
sequencing is checked without touching real containers — the mechanics of
`docker compose` itself are covered by test_gpu_handoff.py.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.routes import review as review_module
from app.core import storage
from app.models import Submission
from app.services.gpu_handoff import GpuHandoffError
from app.services.llm_client import LlmServiceError
from app.services.ocr_client import RecognisedRegion
from tests.factories import minimal_pdf_bytes


def _recording_gpu_service(log: list[tuple[str, str]]):
    @contextmanager
    def _fake(name: str, *, profile: str | None = None) -> Iterator[None]:
        log.append(("start", name))
        try:
            yield
        finally:
            log.append(("stop", name))

    return _fake


def _formula_region(text: str) -> RecognisedRegion:
    return RecognisedRegion(text=text, box=[[0, 0], [1, 0], [1, 1], [0, 1]], label="inline_formula")


def _plain_text_region(text: str) -> RecognisedRegion:
    return RecognisedRegion(text=text, box=[[0, 0], [1, 0], [1, 1], [0, 1]], label="text")


def _lines_of(response_json: dict) -> list[dict]:
    return [line for page in response_json["pages"] for line in page["lines"]]


def test_single_page_submission_normalizes_an_eligible_formula_line(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_formula_region("2+2=4")]
    )

    calls: list[str] = []

    def _fake_generate(prompt: str, schema: dict, timeout: float | None = None) -> dict:
        calls.append(prompt)
        return {"normalized": "$$2 + 2 = 4$$"}

    monkeypatch.setattr(review_module, "generate_structured", _fake_generate)

    gpu_log: list[tuple[str, str]] = []
    monkeypatch.setattr(review_module, "gpu_service", _recording_gpu_service(gpu_log))

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    lines = _lines_of(response.json())
    assert len(lines) == 1
    assert lines[0]["text"] == "2+2=4"
    assert lines[0]["normalized_text"] == "$$2 + 2 = 4$$"
    assert lines[0]["normalization_incomplete"] is False
    assert len(calls) == 1

    # ocr's handoff fully completes (start, stop) before llm's begins, and
    # llm's completes before the request returns: never both up at once.
    assert gpu_log == [("start", "ocr"), ("stop", "ocr"), ("start", "llm"), ("stop", "llm")]


def test_a_submission_with_no_math_never_brings_up_the_llm_container(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_plain_text_region("just prose")]
    )

    calls = 0

    def _fake_generate(prompt: str, schema: dict, timeout: float | None = None) -> dict:
        nonlocal calls
        calls += 1
        return {"normalized": "should never be called"}

    monkeypatch.setattr(review_module, "generate_structured", _fake_generate)

    gpu_log: list[tuple[str, str]] = []
    monkeypatch.setattr(review_module, "gpu_service", _recording_gpu_service(gpu_log))

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    assert calls == 0
    assert gpu_log == [("start", "ocr"), ("stop", "ocr")]  # no "llm" entries at all


def test_multi_page_submission_normalizes_each_eligible_line(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, db_session: Session, submission: Submission
) -> None:
    storage.write(submission.file_path, minimal_pdf_bytes(pages=2))

    def _fake_recognise(
        png: bytes, filename: str, width: int, height: int, timeout: float | None = None
    ) -> list[RecognisedRegion]:
        # One eligible formula line per page, distinguishable by content.
        page_number = filename.split("-")[1].split(".")[0]
        return [_formula_region(f"{page_number}+{page_number}={int(page_number) * 2}")]

    monkeypatch.setattr(review_module, "recognise_image", _fake_recognise)

    # Echoes the original content wrapped as display math, so each page's
    # own normalized result can be told apart from the other's below.
    def _echo_generate(prompt: str, schema: dict, timeout: float | None = None) -> dict:
        original = prompt.split("OCR transcription:\n", 1)[1].split("\n\n", 1)[0]
        return {"normalized": f"$${original}$$"}

    monkeypatch.setattr(review_module, "generate_structured", _echo_generate)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2
    lines = _lines_of(body)
    assert len(lines) == 2
    normalized_by_text = {line["text"]: line["normalized_text"] for line in lines}
    assert normalized_by_text == {
        "1+1=2": "$$1+1=2$$",
        "2+2=4": "$$2+2=4$$",
    }
    assert all(not line["normalization_incomplete"] for line in lines)


def test_llm_timeout_preserves_the_ocr_text_and_flags_the_region(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_formula_region("2+2=4")]
    )

    def _fake_generate(prompt: str, schema: dict, timeout: float | None = None) -> dict:
        raise LlmServiceError("The LLM service at http://localhost:11434 timed out")

    monkeypatch.setattr(review_module, "generate_structured", _fake_generate)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    lines = _lines_of(response.json())
    assert lines[0]["text"] == "2+2=4"  # untouched
    assert lines[0]["normalized_text"] is None
    assert lines[0]["normalization_incomplete"] is True

    # The teacher's accept/rewrite flow is entirely unaffected.
    line_id = lines[0]["id"]
    patch_response = client.patch(f"/api/ocr-lines/{line_id}", json={"accepted": True})
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["accepted"] is True


def test_llm_service_unreachable_during_the_gpu_handoff_preserves_the_reading(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    """Unreachable at the container level (the handoff itself), not just the HTTP call."""
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_formula_region("2+2=4")]
    )

    @contextmanager
    def _fake_gpu_service(name: str, *, profile: str | None = None) -> Iterator[None]:
        if name == "llm":
            raise GpuHandoffError("could not bring up the llm container")
        yield

    monkeypatch.setattr(review_module, "gpu_service", _fake_gpu_service)

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    lines = _lines_of(response.json())
    assert lines[0]["text"] == "2+2=4"
    assert lines[0]["normalized_text"] is None
    assert lines[0]["normalization_incomplete"] is True

    line_id = lines[0]["id"]
    patch_response = client.patch(
        f"/api/ocr-lines/{line_id}", json={"corrected_text": "rewritten by the teacher"}
    )
    assert patch_response.status_code == 200, patch_response.text
    assert patch_response.json()["corrected_text"] == "rewritten by the teacher"


def test_guard_rejects_a_proposal_that_alters_a_numeral(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_formula_region("2+2=4")]
    )
    monkeypatch.setattr(
        review_module,
        "generate_structured",
        lambda prompt, schema, timeout=None: {"normalized": "2+2=5"},
    )

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    lines = _lines_of(response.json())
    assert lines[0]["text"] == "2+2=4"  # ocr_lines.text never changes
    assert lines[0]["normalized_text"] is None  # the proposal was not applied
    assert lines[0]["normalization_incomplete"] is True


@pytest.mark.parametrize(
    ("label", "expected_snippet"),
    [
        ("display_formula", "$$ ... $$"),
        ("inline_formula", "$ ... $"),
        ("text", "Wrap only the mathematical portions"),
        (None, "Wrap only the mathematical portions"),
    ],
)
def test_normalize_prompt_gives_distinct_delimiter_guidance_per_label(
    label: str | None, expected_snippet: str
) -> None:
    prompt = review_module._normalize_prompt("2+2=4", label)
    assert expected_snippet in prompt
    # The transcription section itself stays label-independent, so callers
    # (and this test suite's `_echo_generate` fakes) can keep slicing it out
    # the same way regardless of which delimiter guidance preceded it.
    assert "OCR transcription:\n2+2=4\n\n" in prompt


def test_a_malformed_llm_response_is_treated_as_incomplete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    monkeypatch.setattr(
        review_module, "recognise_image", lambda *a, **kw: [_formula_region("2+2=4")]
    )
    # Well-formed per the schema, but an empty answer is not a usable proposal.
    monkeypatch.setattr(
        review_module,
        "generate_structured",
        lambda prompt, schema, timeout=None: {"normalized": "   "},
    )

    response = client.post(f"/api/submissions/{submission.id}/ocr")

    assert response.status_code == 200, response.text
    lines = _lines_of(response.json())
    assert lines[0]["text"] == "2+2=4"
    assert lines[0]["normalized_text"] is None
    assert lines[0]["normalization_incomplete"] is True
