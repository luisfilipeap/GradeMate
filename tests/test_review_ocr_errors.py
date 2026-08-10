"""TASK-007, end to end: a malformed OCR response never reaches the caller as a 500."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.models import Submission
from app.services import ocr_client
from tests.test_ocr_client import _FakeResponse, _patch_post


def test_non_json_ocr_response_is_a_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    _patch_post(monkeypatch, _FakeResponse(_raw_text="<not json>"))
    response = client.post(f"/api/submissions/{submission.id}/ocr")
    assert response.status_code == 502


def test_ocr_response_missing_blocks_is_a_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    body = {"pages": [{"number": 1, "width": 100, "height": 100}]}
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    response = client.post(f"/api/submissions/{submission.id}/ocr")
    assert response.status_code == 502


def test_ocr_response_with_a_malformed_box_is_a_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    body: dict[str, Any] = {
        "pages": [
            {
                "number": 1,
                "width": 100,
                "height": 100,
                "blocks": [{"content": "hi", "box": [[0, 0, 0]]}],
            }
        ]
    }
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    response = client.post(f"/api/submissions/{submission.id}/ocr")
    assert response.status_code == 502


def test_ocr_service_unreachable_is_a_502(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, submission: Submission
) -> None:
    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(ocr_client.httpx, "post", _raise)
    response = client.post(f"/api/submissions/{submission.id}/ocr")
    assert response.status_code == 502
