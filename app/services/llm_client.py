"""Client for the local LLM service (Ollama) defined in docker-compose.yml."""

from __future__ import annotations

import json

import httpx
import jsonschema

from app.core.config import get_settings


class LlmServiceError(RuntimeError):
    """The LLM service could not be reached, refused the request, or answered
    with something that does not match the requested schema.

    Every failure mode of this adapter — transport, HTTP status, malformed
    JSON, and a schema mismatch — becomes this one type, so callers need no
    per-failure-mode handling.
    """


def generate_structured(
    prompt: str,
    schema: dict,
    timeout: float | None = None,
) -> dict:
    """Ask the configured model to answer ``prompt`` as JSON shaped like ``schema``.

    Posts to Ollama's ``/api/generate`` with ``format`` set to ``schema``, which
    constrains the model's output; the response is still parsed and validated
    against that same schema before it is returned, rather than trusted just
    because Ollama accepted the request.

    ``timeout`` overrides ``settings.llm_timeout_seconds`` for this call only.
    """
    settings = get_settings()
    url = f"{settings.llm_service_url.rstrip('/')}/api/generate"
    if timeout is None:
        timeout = settings.llm_timeout_seconds

    try:
        response = httpx.post(
            url,
            json={
                "model": settings.llm_model,
                "prompt": prompt,
                "format": schema,
                "stream": False,
            },
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as error:
        raise LlmServiceError(
            f"The LLM service answered {error.response.status_code}: {error.response.text}"
        ) from error
    except httpx.HTTPError as error:
        raise LlmServiceError(f"The LLM service at {url} is unreachable: {error}") from error

    try:
        envelope = response.json()
    except ValueError as error:
        raise LlmServiceError(
            f"The LLM service at {url} returned a response that is not valid JSON: {error}"
        ) from error

    try:
        raw_answer = envelope["response"]
    except (KeyError, TypeError) as error:
        raise LlmServiceError(
            f"The LLM service at {url} returned a response missing the 'response' field."
        ) from error

    try:
        answer = json.loads(raw_answer)
    except (TypeError, ValueError) as error:
        raise LlmServiceError(
            f"The LLM service at {url} returned a 'response' field that is not valid JSON: {error}"
        ) from error

    try:
        jsonschema.validate(answer, schema)
    except jsonschema.ValidationError as error:
        raise LlmServiceError(
            f"The LLM service at {url} returned a response that does not match the requested "
            f"schema: {error.message}"
        ) from error
    except jsonschema.SchemaError as error:
        raise LlmServiceError(
            f"The requested schema is not itself valid: {error.message}"
        ) from error

    return answer
