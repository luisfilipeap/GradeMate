"""Sequential GPU handoff via docker compose (issue #21).

`gpu_handoff_enabled` is off by default in tests (see the autouse
`gpu_handoff_disabled` fixture in conftest.py); each test here turns it back
on and replaces `subprocess.run` with a fake, so nothing here ever touches a
real container.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass

import pytest

from app.core.config import get_settings
from app.services import gpu_handoff


@dataclass
class _FakeCompletedProcess:
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


@pytest.fixture(autouse=True)
def _enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "gpu_handoff_enabled", True)


def test_start_service_runs_docker_compose_up_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(command: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(command)
        return _FakeCompletedProcess()

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _fake_run)
    gpu_handoff.start_service("ocr")

    assert calls[0][-4:] == ["up", "-d", "--wait", "ocr"]
    assert "--profile" not in calls[0]


def test_start_service_with_a_profile_passes_it_through(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(command: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(command)
        return _FakeCompletedProcess()

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _fake_run)
    gpu_handoff.start_service("llm", profile="tools")

    assert "--profile" in calls[0]
    assert calls[0][calls[0].index("--profile") + 1] == "tools"
    assert calls[0][-4:] == ["up", "-d", "--wait", "llm"]


def test_stop_service_runs_docker_compose_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def _fake_run(command: list[str], **kwargs: object) -> _FakeCompletedProcess:
        calls.append(command)
        return _FakeCompletedProcess()

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _fake_run)
    gpu_handoff.stop_service("ocr")

    assert calls[0][-2:] == ["stop", "ocr"]


def test_a_nonzero_exit_starting_becomes_a_service_start_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gpu_handoff.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess(returncode=1, stderr="boom"),
    )
    with pytest.raises(gpu_handoff.ServiceStartError):
        gpu_handoff.start_service("ocr")


def test_a_nonzero_exit_stopping_becomes_a_service_stop_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        gpu_handoff.subprocess,
        "run",
        lambda *a, **kw: _FakeCompletedProcess(returncode=1, stderr="boom"),
    )
    with pytest.raises(gpu_handoff.ServiceStopError):
        gpu_handoff.stop_service("ocr")


def test_a_timeout_becomes_a_service_start_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="docker compose", timeout=1)

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _raise)
    with pytest.raises(gpu_handoff.ServiceStartError):
        gpu_handoff.start_service("ocr")


def test_docker_not_being_available_becomes_a_service_start_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("docker: command not found")

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _raise)
    with pytest.raises(gpu_handoff.ServiceStartError):
        gpu_handoff.start_service("ocr")


def test_gpu_service_starts_then_stops_around_the_block(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gpu_handoff, "start_service", lambda name, profile=None: calls.append(("start", name))
    )
    monkeypatch.setattr(gpu_handoff, "stop_service", lambda name: calls.append(("stop", name)))

    with gpu_handoff.gpu_service("ocr"):
        calls.append(("use", "ocr"))

    assert calls == [("start", "ocr"), ("use", "ocr"), ("stop", "ocr")]


def test_gpu_service_stops_even_when_the_block_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        gpu_handoff, "start_service", lambda name, profile=None: calls.append(("start", name))
    )
    monkeypatch.setattr(gpu_handoff, "stop_service", lambda name: calls.append(("stop", name)))

    with pytest.raises(RuntimeError):
        with gpu_handoff.gpu_service("ocr"):
            raise RuntimeError("boom")

    assert calls == [("start", "ocr"), ("stop", "ocr")]


def test_ocr_and_llm_are_never_resident_at_the_same_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The literal acceptance criterion: at no instant are both containers up."""
    resident: set[str] = set()
    events: list[tuple[str, str]] = []

    def _start(name: str, profile: str | None = None) -> None:
        assert not resident, f"{name} started while {resident} was still resident"
        resident.add(name)
        events.append(("start", name))

    def _stop(name: str) -> None:
        resident.discard(name)
        events.append(("stop", name))

    monkeypatch.setattr(gpu_handoff, "start_service", _start)
    monkeypatch.setattr(gpu_handoff, "stop_service", _stop)

    with gpu_handoff.gpu_service("ocr"):
        pass
    with gpu_handoff.gpu_service("llm", profile="tools"):
        pass

    assert events == [("start", "ocr"), ("stop", "ocr"), ("start", "llm"), ("stop", "llm")]
    assert resident == set()


def test_gpu_service_is_a_no_op_when_the_handoff_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(get_settings(), "gpu_handoff_enabled", False)

    def _boom(*args: object, **kwargs: object) -> None:
        raise AssertionError("docker compose must not run when the handoff is disabled")

    monkeypatch.setattr(gpu_handoff.subprocess, "run", _boom)

    with gpu_handoff.gpu_service("ocr"):
        pass
