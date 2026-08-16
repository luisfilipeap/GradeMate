"""The LLM client validates the response instead of trusting it (issue #20)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import pytest

from app.services import llm_client

_SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
    },
    "required": ["answer"],
    "additionalProperties": False,
}


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

    monkeypatch.setattr(llm_client.httpx, "post", _fake_post)


def _envelope(response_field: Any) -> dict:
    """The shape Ollama's /api/generate wraps its answer in."""
    return {"model": "qwen3", "response": response_field, "done": True}


def test_non_json_envelope_becomes_an_llm_service_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_post(monkeypatch, _FakeResponse(_raw_text="<html>not json</html>"))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)


def test_envelope_missing_response_field_becomes_an_llm_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(monkeypatch, _FakeResponse(_body={"model": "qwen3", "done": True}))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)


def test_response_field_not_json_becomes_an_llm_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_post(monkeypatch, _FakeResponse(_body=_envelope("not-json-at-all")))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)


def test_response_outside_schema_becomes_an_llm_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Well-formed JSON, but missing the required "answer" key.
    body = _envelope(json.dumps({"unexpected": "field"}))
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)


def test_response_with_wrong_type_becomes_an_llm_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # "answer" is present but the wrong type for the schema.
    body = _envelope(json.dumps({"answer": 42}))
    _patch_post(monkeypatch, _FakeResponse(_body=body))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)


def test_a_well_formed_response_parses_and_validates(monkeypatch: pytest.MonkeyPatch) -> None:
    body = _envelope(json.dumps({"answer": "hello"}))
    _patch_post(monkeypatch, _FakeResponse(_body=body))

    result = llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)

    assert result == {"answer": "hello"}


def test_transport_and_status_failures_still_map_to_the_same_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_connect_error(*args: Any, **kwargs: Any) -> Any:
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm_client.httpx, "post", _raise_connect_error)
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)

    def _raise_timeout(*args: Any, **kwargs: Any) -> Any:
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(llm_client.httpx, "post", _raise_timeout)
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)

    _patch_post(monkeypatch, _FakeResponse(status_code=500, _raw_text="internal error"))
    with pytest.raises(llm_client.LlmServiceError):
        llm_client.generate_structured("say hello", _SIMPLE_SCHEMA)
