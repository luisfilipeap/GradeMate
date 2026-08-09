"""OCR microservice for GradeMate, backed by PaddleOCR-VL.

PaddleOCR-VL is a vision-language model. Instead of short text lines, it returns
**blocks** — a paragraph, a formula, a table — already labelled and formatted as
markdown or LaTeX, which is what makes it usable on handwritten exams full of
mathematics. It reports no per-region confidence.

The service is stateless: it never stores the uploaded file.
"""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, HTTPException, UploadFile, status
from pydantic import BaseModel

logger = logging.getLogger("grademate.ocr")
logging.basicConfig(level=logging.INFO)

# "gpu:0" or "cpu".
OCR_DEVICE = os.getenv("OCR_DEVICE", "gpu:0")

ACCEPTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

_engine: Any = None
_engine_lock = threading.Lock()


def get_engine() -> Any:
    """Return the PaddleOCR-VL pipeline, building it on first use.

    The first call downloads roughly 2 GB of weights and takes several minutes;
    every later call reuses the loaded pipeline.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from paddleocr import PaddleOCRVL

                logger.info("Loading PaddleOCR-VL (device=%s)", OCR_DEVICE)
                _engine = PaddleOCRVL(device=OCR_DEVICE)
                logger.info("PaddleOCR-VL ready")
    return _engine


class Block(BaseModel):
    """A labelled region recognised on a page."""

    label: str
    content: str
    # Polygon around the block, as [[x, y], ...] in pixels of the page.
    box: list[list[float]]
    order: int


class Page(BaseModel):
    number: int
    width: int
    height: int
    blocks: list[Block]

    @property
    def text(self) -> str:
        return "\n\n".join(block.content for block in self.blocks)


class OcrResponse(BaseModel):
    filename: str
    device: str
    page_count: int
    pages: list[Page]
    text: str


class HealthResponse(BaseModel):
    status: str
    device: str
    model_loaded: bool


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("OCR_PRELOAD", "false").lower() == "true":
        get_engine()
    yield


app = FastAPI(
    title="GradeMate OCR",
    description="Reads scanned exams with PaddleOCR-VL, returning labelled blocks per page.",
    version="0.2.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report whether the service is up and whether the model is loaded."""
    return HealthResponse(status="ok", device=OCR_DEVICE, model_loaded=_engine is not None)


@app.post("/ocr", response_model=OcrResponse)
def run_ocr(
    file: Annotated[UploadFile, File(description="Scanned exam, as PDF or image.")],
) -> OcrResponse:
    """Recognise every page of the uploaded file."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ACCEPTED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type {suffix or '(none)'}. Send a PDF or an image.",
        )

    # PaddleOCR reads from a path, and it needs the real extension to decide
    # whether the input is a PDF or a single image.
    with tempfile.NamedTemporaryFile(suffix=suffix) as scratch:
        scratch.write(file.file.read())
        scratch.flush()
        try:
            results = list(get_engine().predict(scratch.name))
        except Exception as error:  # pragma: no cover - depends on the model runtime
            logger.exception("OCR failed")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OCR failed: {error}"
            ) from error

    pages = [_to_page(index, result) for index, result in enumerate(results, 1)]
    return OcrResponse(
        filename=file.filename or "",
        device=OCR_DEVICE,
        page_count=len(pages),
        pages=pages,
        text="\n\n".join(page.text for page in pages),
    )


def _to_page(number: int, result: Any) -> Page:
    """Convert one PaddleOCR-VL result (a page) into our response shape."""
    payload = result.json["res"] if hasattr(result, "json") else result.get("res", result)
    blocks = [
        Block(
            label=str(block.get("block_label", "text")),
            content=str(block.get("block_content", "")),
            box=_to_box(block.get("block_polygon_points") or _corners(block["block_bbox"])),
            # block_order is absent, or null, on pages with a single group.
            order=int(block.get("block_order") or position),
        )
        for position, block in enumerate(payload.get("parsing_res_list", []), 1)
    ]
    return Page(
        number=number,
        width=int(payload.get("width", 0)),
        height=int(payload.get("height", 0)),
        blocks=blocks,
    )


def _corners(bbox: Any) -> list[list[float]]:
    """Turn an [x1, y1, x2, y2] rectangle into the four corners of a polygon."""
    x1, y1, x2, y2 = (float(value) for value in bbox)
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _to_box(poly: Any) -> list[list[float]]:
    """Normalise a polygon (numpy array or nested list) into plain floats."""
    return [[float(point[0]), float(point[1])] for point in poly]
