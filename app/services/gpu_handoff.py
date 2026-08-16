"""Sequential GPU handoff between the `ocr` and `llm` containers (issue #21).

Both containers in `docker-compose.yml` request the whole GPU and neither
gives its memory back reliably on its own — `ocr` never does, `llm` only
after its idle keep-alive expires. On a single card that means only one of
them can actually run at a time.

Rather than trust whatever state the containers happen to be left in, each
call to `run_ocr()` drives `docker compose` directly around the OCR and LLM
calls it makes: bring a service up, use it, stop it, before bringing the
other one up. `gpu_service()` is the building block for that — a context
manager that starts a service on entry and always stops it again on exit,
so a failure partway through a normalization run can never leave both
services GPU-resident at once.

Every stage (start, stop) gets its own exception type, mirroring
`OcrServiceError`/`LlmServiceError`: a `subprocess` failure, a non-zero
`docker compose` exit, or a timeout waiting for the service to become
healthy all become one of these, never an unhandled `OSError` or
`subprocess.TimeoutExpired` reaching the caller.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)


class GpuHandoffError(RuntimeError):
    """Base type for a failure of one stage of the docker compose handoff."""


class ServiceStartError(GpuHandoffError):
    """`docker compose up` for a service failed, timed out, or never became healthy."""


class ServiceStopError(GpuHandoffError):
    """`docker compose stop` for a service failed or timed out."""


def start_service(name: str, *, profile: str | None = None, timeout: float | None = None) -> None:
    """Bring `name` up and wait for it to report healthy.

    `profile` is passed to `docker compose --profile`, needed for `llm`,
    which sits behind the opt-in "tools" profile in `docker-compose.yml`.
    """
    settings = get_settings()
    command = _compose_command(settings)
    if profile:
        command += ["--profile", profile]
    command += ["up", "-d", "--wait", name]
    _run(
        command,
        timeout if timeout is not None else settings.gpu_handoff_start_timeout_seconds,
        ServiceStartError,
        f"start the '{name}' service",
    )


def stop_service(name: str, *, timeout: float | None = None) -> None:
    """Stop `name`, freeing whatever GPU memory it held."""
    settings = get_settings()
    command = _compose_command(settings) + ["stop", name]
    _run(
        command,
        timeout if timeout is not None else settings.gpu_handoff_stop_timeout_seconds,
        ServiceStopError,
        f"stop the '{name}' service",
    )


@contextmanager
def gpu_service(name: str, *, profile: str | None = None) -> Iterator[None]:
    """Bring `name` up for the duration of the block, then stop it again.

    The `finally` guarantees the stop attempt runs even if the block raises
    (a network failure calling the service it just started, for instance),
    so this service is never left GPU-resident because of an error inside
    the block — the caller only has to decide what an unavailable `name`
    means for whatever it was trying to do.

    A no-op (besides yielding) when `settings.gpu_handoff_enabled` is off,
    so callers do not need their own conditional around every use.
    """
    if not get_settings().gpu_handoff_enabled:
        yield
        return

    start_service(name, profile=profile)
    try:
        yield
    finally:
        stop_service(name)


def _compose_command(settings: Settings) -> list[str]:
    return ["docker", "compose", "-f", str(settings.gpu_handoff_compose_file)]


def _run(
    command: list[str], timeout: float, error_type: type[GpuHandoffError], action: str
) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise error_type(
            f"Timed out trying to {action} ({timeout:.0f}s): {' '.join(command)}"
        ) from error
    except OSError as error:
        raise error_type(f"Could not run docker compose to {action}: {error}") from error

    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise error_type(f"docker compose exited {result.returncode} trying to {action}: {detail}")

    logger.info("docker compose %s", action)
