"""TASK-008: the OCR service protects its own GPU and refuses oversized input.

Runs against ``services/ocr/app.py`` directly, with the model engine mocked
out (no GPU, no paddleocr install needed) — only the HTTP-level guards this
task adds are under test here.
"""

from __future__ import annotations

import io
import threading
import time

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter

import app as ocr_app

client = TestClient(ocr_app.app)


class _FakeResult:
    """Stands in for one page of ``PaddleOCRVL.predict()``."""

    def __init__(self, width: int = 10, height: int = 10) -> None:
        self.json = {"res": {"width": width, "height": height, "parsing_res_list": []}}


@pytest.fixture(autouse=True)
def _fake_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets a trivial, GPU-free engine unless it overrides this."""

    class _FakeEngine:
        def predict(self, path: str) -> list[_FakeResult]:
            return [_FakeResult()]

    monkeypatch.setattr(ocr_app, "get_engine", lambda: _FakeEngine())


@pytest.fixture(autouse=True)
def _reset_semaphore() -> None:
    """Guard against one test's acquired slot leaking into the next."""
    yield
    # Drain and restore, in case a test left the semaphore in a bad state.
    ocr_app._inference_slots = threading.Semaphore(ocr_app.MAX_CONCURRENT_INFERENCES)


def _pdf_bytes(pages: int) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=200)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


def _png_bytes(width: int, height: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_unsupported_file_type_is_refused() -> None:
    response = client.post(
        "/ocr", files={"file": ("exam.docx", b"not a pdf", "application/msword")}
    )
    assert response.status_code == 415


def test_pdf_within_limits_is_accepted() -> None:
    response = client.post("/ocr", files={"file": ("exam.pdf", _pdf_bytes(2), "application/pdf")})
    assert response.status_code == 200
    assert response.json()["page_count"] == 1  # one fake result, regardless of input page count


def test_pdf_beyond_the_page_ceiling_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_PAGES", 3)
    response = client.post("/ocr", files={"file": ("exam.pdf", _pdf_bytes(5), "application/pdf")})
    assert response.status_code == 413
    assert "5 pages" in response.json()["detail"]


def test_image_beyond_the_pixel_ceiling_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 100)
    response = client.post("/ocr", files={"file": ("page.png", _png_bytes(50, 50), "image/png")})
    assert response.status_code == 413


def test_image_within_the_pixel_ceiling_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 100_000)
    response = client.post("/ocr", files={"file": ("page.png", _png_bytes(50, 50), "image/png")})
    assert response.status_code == 200


def test_a_saturated_queue_answers_503_instead_of_hanging(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "QUEUE_TIMEOUT_SECONDS", 0.2)

    # Hold the only GPU slot from another thread, longer than the queue timeout.
    ocr_app._inference_slots.acquire()
    released = threading.Event()

    def _release_later() -> None:
        released.wait(timeout=2)
        ocr_app._inference_slots.release()

    holder = threading.Thread(target=_release_later)
    holder.start()
    try:
        started = time.monotonic()
        response = client.post(
            "/ocr", files={"file": ("page.png", _png_bytes(10, 10), "image/png")}
        )
        elapsed = time.monotonic() - started
    finally:
        released.set()
        holder.join()

    assert response.status_code == 503
    # It answered close to the configured queue timeout, not immediately and
    # not by hanging indefinitely.
    assert elapsed < 2
