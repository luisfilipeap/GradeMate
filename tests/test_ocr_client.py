"""TASK-007: the OCR client validates the response instead of trusting it."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.services import ocr_client


@dataclass
class _FakeResponse:
    """Stands in for ``httpx.Response`` in these adapter-level tests."""

    status_code: int = 200
    _body: Any = field(default_factory=dict)
    _raw_text: str | None = None

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=object(),  # type: ignore[arg-type]
                response=self,  # type: ignore[arg-type]
            )

    def json(self) -> Any:
        if self._raw_text is not None:
            return json.loads(self._raw_text)  # may raise json.JSONDecodeError
        return self._body

    @property
    def text(self) -> str:
        return self._raw_text if self._raw_text is not None else json.dumps(self._body)


def _patch_post(monkeypatch: pytest.MonkeyPatch, response: _FakeResponse) -> None:
    def _fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        return response

    monkeypatch.setattr(ocr_client.httpx, "post", _fake_post)


def test_non_json_response_becomes_an_ocr_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(monkeypatch, _FakeResponse(_raw_text="<html>not json</html>"))
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)


def test_valid_json_missing_blocks_key_becomes_an_ocr_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {"pages": [{"number": 1, "width": 100, "height": 100}]}  # no "blocks"
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)


def test_valid_json_missing_content_key_becomes_an_ocr_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    body = {
        "pages": [
            {
                "number": 1,
                "width": 100,
                "height": 100,
                "blocks": [{"label": "text", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]}],
            }
        ]
    }
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)


def test_a_malformed_box_becomes_an_ocr_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    body = {
        "pages": [
            {
                "number": 1,
                "width": 100,
                "height": 100,
                "blocks": [
                    {
                        "label": "text",
                        "content": "hello",
                        # Each point should be a pair; this one has three values.
                        "box": [[0, 0, 0], [1, 0], [1, 1], [0, 1]],
                    }
                ],
            }
        ]
    }
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)


def test_a_well_formed_response_parses_and_rescales_coordinates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The service worked on a 50x50 image; we rendered the page at 100x100,
    # so every coordinate should come back doubled.
    body = {
        "pages": [
            {
                "number": 1,
                "width": 50,
                "height": 50,
                "blocks": [
                    {
                        "label": "text",
                        "content": "hello",
                        "box": [[0, 0], [10, 0], [10, 10], [0, 10]],
                        "order": 1,
                    },
                    # Blank content is dropped: nothing for the teacher to review.
                    {"label": "text", "content": "   ", "box": [[0, 0], [1, 0], [1, 1], [0, 1]]},
                ],
            }
        ]
    }
    _patch_post(monkeypatch, _FakeResponse(_body=body))

    regions = ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)

    assert len(regions) == 1
    region = regions[0]
    assert region.text == "hello"
    assert region.label == "text"
    assert region.box == [[0.0, 0.0], [20.0, 0.0], [20.0, 20.0], [0.0, 20.0]]


def test_transport_and_status_failures_still_map_to_the_same_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_connect_error(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(ocr_client.httpx, "post", _raise_connect_error)
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)

    _patch_post(monkeypatch, _FakeResponse(status_code=500, _raw_text="internal error"))
    with pytest.raises(ocr_client.OcrServiceError):
        ocr_client.recognise_image(b"png-bytes", "page.png", 100, 100)
