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


def test_pdf_with_an_oversized_page_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    # Within the page-count ceiling (one page), but its 200x200pt MediaBox
    # rendered at the assumed DPI must exceed a tight pixel ceiling.
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 1_000)
    response = client.post("/ocr", files={"file": ("exam.pdf", _pdf_bytes(1), "application/pdf")})
    assert response.status_code == 413
    assert "Page 1" in response.json()["detail"]


def test_pdf_page_size_is_accepted_below_the_pixel_ceiling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 1_000_000)
    response = client.post("/ocr", files={"file": ("exam.pdf", _pdf_bytes(1), "application/pdf")})
    assert response.status_code == 200


def test_image_beyond_the_pixel_ceiling_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 100)
    response = client.post("/ocr", files={"file": ("page.png", _png_bytes(50, 50), "image/png")})
    assert response.status_code == 413


def test_image_within_the_pixel_ceiling_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_IMAGE_PIXELS", 100_000)
    response = client.post("/ocr", files={"file": ("page.png", _png_bytes(50, 50), "image/png")})
    assert response.status_code == 200


def test_upload_beyond_the_byte_ceiling_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_UPLOAD_BYTES", 100)
    response = client.post(
        "/ocr", files={"file": ("exam.pdf", b"x" * 1_000, "application/pdf")}
    )
    assert response.status_code == 413
    assert "100 bytes" in response.json()["detail"]


def test_upload_within_the_byte_ceiling_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ocr_app, "MAX_UPLOAD_BYTES", 1_000_000)
    response = client.post("/ocr", files={"file": ("exam.pdf", _pdf_bytes(1), "application/pdf")})
    assert response.status_code == 200


def test_write_bounded_refuses_before_reading_the_whole_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_write_bounded`` must read in bounded chunks, never the whole body at once."""
    monkeypatch.setattr(ocr_app, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(ocr_app, "_UPLOAD_CHUNK_BYTES", 4)

    class _FakeSource:
        def __init__(self, data: bytes) -> None:
            self._data = data
            self._offset = 0
            self.read_sizes: list[int] = []

        def read(self, size: int = -1) -> bytes:
            # A full-buffering read passes no size (or -1); a bounded read
            # always asks for a fixed, small number of bytes.
            assert size != -1, "source was read without a size limit"
            self.read_sizes.append(size)
            chunk = self._data[self._offset : self._offset + size]
            self._offset += len(chunk)
            return chunk

    source = _FakeSource(b"x" * 1_000)
    destination = io.BytesIO()

    with pytest.raises(ocr_app.HTTPException) as excinfo:
        ocr_app._write_bounded(source, destination)

    assert excinfo.value.status_code == 413
    # Stopped after a handful of 4-byte chunks, nowhere near the 1000-byte source.
    assert sum(source.read_sizes) < 1_000


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
