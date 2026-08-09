"""OCR microservice for GradeMate, backed by PaddleOCR.

Two engines are exposed, because they read a page in very different ways:

* ``/ocr`` runs the classic PP-OCR pipeline. It returns one short **line** per
  detected region, with a recognition confidence. Fast, and good on print.
* ``/ocr-vl`` runs PaddleOCR-VL, a vision-language model. It returns larger
  **blocks** (a paragraph, a formula, a table) already labelled and formatted as
  markdown or LaTeX, which is far better on handwriting and mathematics. It has
  no per-region confidence to report.

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

from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

logger = logging.getLogger("grademate.ocr")
logging.basicConfig(level=logging.INFO)

# Recognition model language. Portuguese, English, Spanish and the other
# latin-script languages share one recognition model, so "pt" and "en" differ
# only in the dictionary used.
OCR_LANG = os.getenv("OCR_LANG", "pt")

# "gpu:0" or "cpu".
OCR_DEVICE = os.getenv("OCR_DEVICE", "gpu:0")

# Extra preprocessing models. They are off by default: scanned exams come from a
# flatbed scanner already upright, and each one adds a model to download and run.
USE_DOC_ORIENTATION = os.getenv("OCR_USE_DOC_ORIENTATION", "false").lower() == "true"
USE_DOC_UNWARPING = os.getenv("OCR_USE_DOC_UNWARPING", "false").lower() == "true"
USE_TEXTLINE_ORIENTATION = os.getenv("OCR_USE_TEXTLINE_ORIENTATION", "false").lower() == "true"

ACCEPTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

_engine: Any = None
_engine_lock = threading.Lock()

_vl_engine: Any = None
_vl_engine_lock = threading.Lock()


def get_engine() -> Any:
    """Return the PaddleOCR engine, building it on first use.

    The first call downloads the model weights, so it can take a couple of
    minutes; every later call reuses the loaded engine.
    """
    global _engine
    if _engine is None:
        with _engine_lock:
            if _engine is None:
                from paddleocr import PaddleOCR

                logger.info("Loading PaddleOCR (lang=%s, device=%s)", OCR_LANG, OCR_DEVICE)
                _engine = PaddleOCR(
                    lang=OCR_LANG,
                    device=OCR_DEVICE,
                    use_doc_orientation_classify=USE_DOC_ORIENTATION,
                    use_doc_unwarping=USE_DOC_UNWARPING,
                    use_textline_orientation=USE_TEXTLINE_ORIENTATION,
                )
                logger.info("PaddleOCR ready")
    return _engine


def get_vl_engine() -> Any:
    """Return the PaddleOCR-VL pipeline, building it on first use.

    The first call downloads roughly 2 GB of weights and takes several minutes.
    """
    global _vl_engine
    if _vl_engine is None:
        with _vl_engine_lock:
            if _vl_engine is None:
                from paddleocr import PaddleOCRVL

                logger.info("Loading PaddleOCR-VL (device=%s)", OCR_DEVICE)
                _vl_engine = PaddleOCRVL(device=OCR_DEVICE)
                logger.info("PaddleOCR-VL ready")
    return _vl_engine


class TextLine(BaseModel):
    """A single line of text recognised on a page."""

    text: str
    confidence: float
    # Polygon around the line, as [[x, y], ...] in pixels of the rendered page.
    box: list[list[float]]


class Page(BaseModel):
    number: int
    lines: list[TextLine]

    @property
    def text(self) -> str:
        return "\n".join(line.text for line in self.lines)


class OcrResponse(BaseModel):
    filename: str
    language: str
    device: str
    page_count: int
    pages: list[Page]
    text: str


class Block(BaseModel):
    """A labelled region recognised by PaddleOCR-VL."""

    label: str
    content: str
    # Polygon around the block, as [[x, y], ...] in pixels of the page.
    box: list[list[float]]
    order: int


class VlPage(BaseModel):
    number: int
    width: int
    height: int
    blocks: list[Block]

    @property
    def text(self) -> str:
        return "\n\n".join(block.content for block in self.blocks)


class VlResponse(BaseModel):
    filename: str
    device: str
    page_count: int
    pages: list[VlPage]
    text: str


class HealthResponse(BaseModel):
    status: str
    language: str
    device: str
    model_loaded: bool
    vl_model_loaded: bool


@asynccontextmanager
async def lifespan(_: FastAPI):
    if os.getenv("OCR_PRELOAD", "false").lower() == "true":
        get_engine()
    yield


app = FastAPI(
    title="GradeMate OCR",
    description="Extracts text and bounding boxes from scanned exams using PaddleOCR.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report whether the service is up and whether the models are loaded."""
    return HealthResponse(
        status="ok",
        language=OCR_LANG,
        device=OCR_DEVICE,
        model_loaded=_engine is not None,
        vl_model_loaded=_vl_engine is not None,
    )


@app.post("/ocr", response_model=OcrResponse)
def run_ocr(
    file: Annotated[UploadFile, File(description="Scanned exam, as PDF or image.")],
    min_confidence: Annotated[
        float, Query(ge=0.0, le=1.0, description="Drop recognised lines below this confidence.")
    ] = 0.0,
) -> OcrResponse:
    """Recognise the text of every page of the uploaded file."""
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
            results = get_engine().predict(scratch.name)
        except Exception as error:  # pragma: no cover - depends on the model runtime
            logger.exception("OCR failed")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OCR failed: {error}"
            ) from error

    pages = [_to_page(index, result, min_confidence) for index, result in enumerate(results, 1)]
    return OcrResponse(
        filename=file.filename or "",
        language=OCR_LANG,
        device=OCR_DEVICE,
        page_count=len(pages),
        pages=pages,
        text="\n\n".join(page.text for page in pages),
    )


@app.post("/ocr-vl", response_model=VlResponse)
def run_ocr_vl(
    file: Annotated[UploadFile, File(description="Scanned exam, as PDF or image.")],
) -> VlResponse:
    """Read the file with PaddleOCR-VL, returning labelled blocks per page."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ACCEPTED_SUFFIXES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type {suffix or '(none)'}. Send a PDF or an image.",
        )

    with tempfile.NamedTemporaryFile(suffix=suffix) as scratch:
        scratch.write(file.file.read())
        scratch.flush()
        try:
            results = list(get_vl_engine().predict(scratch.name))
        except Exception as error:  # pragma: no cover - depends on the model runtime
            logger.exception("PaddleOCR-VL failed")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OCR failed: {error}"
            ) from error

    pages = [_to_vl_page(index, result) for index, result in enumerate(results, 1)]
    return VlResponse(
        filename=file.filename or "",
        device=OCR_DEVICE,
        page_count=len(pages),
        pages=pages,
        text="\n\n".join(page.text for page in pages),
    )


def _to_vl_page(number: int, result: Any) -> VlPage:
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
    return VlPage(
        number=number,
        width=int(payload.get("width", 0)),
        height=int(payload.get("height", 0)),
        blocks=blocks,
    )


def _corners(bbox: Any) -> list[list[float]]:
    """Turn an [x1, y1, x2, y2] rectangle into the four corners of a polygon."""
    x1, y1, x2, y2 = (float(value) for value in bbox)
    return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]


def _to_page(number: int, result: Any, min_confidence: float) -> Page:
    """Convert one PaddleOCR result (a page) into our response shape."""
    payload = result.get("res", result) if isinstance(result, dict) else result
    texts = payload.get("rec_texts", [])
    scores = payload.get("rec_scores", [])
    polys = payload.get("rec_polys", payload.get("dt_polys", []))

    lines = [
        TextLine(text=text, confidence=float(score), box=_to_box(poly))
        for text, score, poly in zip(texts, scores, polys, strict=False)
        if float(score) >= min_confidence
    ]
    return Page(number=number, lines=lines)


def _to_box(poly: Any) -> list[list[float]]:
    """Normalise a polygon (numpy array or nested list) into plain floats."""
    return [[float(point[0]), float(point[1])] for point in poly]
