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

# The engine holds a single GPU. A page costs roughly 15s of GPU time, so an
# unbounded number of concurrent requests would either OOM the card or make
# every caller wait an unpredictable amount of time. Callers instead queue for
# a slot, and are told plainly when the queue itself is full rather than
# blocking forever or failing with something unrelated to the real cause.
MAX_CONCURRENT_INFERENCES = int(os.getenv("OCR_MAX_CONCURRENT_INFERENCES", "1"))
QUEUE_TIMEOUT_SECONDS = float(os.getenv("OCR_QUEUE_TIMEOUT_SECONDS", "60"))
_inference_slots = threading.Semaphore(MAX_CONCURRENT_INFERENCES)

# A single page costs about 4 GB of GPU memory; these ceilings exist because
# this service is published on its own port and can be called directly,
# bypassing whatever limits the backend enforces on its own uploads.
MAX_PAGES = int(os.getenv("OCR_MAX_PAGES", "50"))
MAX_IMAGE_PIXELS = int(os.getenv("OCR_MAX_IMAGE_PIXELS", str(40_000_000)))  # ~40 MP

# Read in bounded chunks so an oversized upload is refused before it is ever
# fully buffered in memory, rather than after.
MAX_UPLOAD_BYTES = int(os.getenv("OCR_MAX_UPLOAD_BYTES", str(200_000_000)))  # ~200 MB
_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB

# A PDF page's MediaBox is expressed in points (1/72 inch) and says nothing
# about the resolution it will be rasterised at. To apply the same pixel
# ceiling to PDFs as to images, this service has to assume a DPI: it does not
# know the backend's actual `page_render_dpi` (a caller can hit this service
# directly, and the two are independent deployments), so this default simply
# mirrors it.
ASSUMED_PDF_DPI = int(os.getenv("OCR_ASSUMED_PDF_DPI", "150"))

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
        _write_bounded(file.file, scratch)
        scratch.flush()
        _enforce_size_limits(Path(scratch.name), suffix)

        if not _inference_slots.acquire(timeout=QUEUE_TIMEOUT_SECONDS):
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    f"The OCR engine is busy with other requests and no GPU slot freed up "
                    f"within {QUEUE_TIMEOUT_SECONDS:.0f}s. Retry shortly."
                ),
            )
        try:
            results = list(get_engine().predict(scratch.name))
        except Exception as error:  # pragma: no cover - depends on the model runtime
            logger.exception("OCR failed")
            raise HTTPException(
                status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OCR failed: {error}"
            ) from error
        finally:
            _inference_slots.release()

    pages = [_to_page(index, result) for index, result in enumerate(results, 1)]
    return OcrResponse(
        filename=file.filename or "",
        device=OCR_DEVICE,
        page_count=len(pages),
        pages=pages,
        text="\n\n".join(page.text for page in pages),
    )


def _write_bounded(source: Any, destination: Any) -> None:
    """Copy ``source`` into ``destination`` in chunks, refusing an oversized upload.

    Reads at most ``_UPLOAD_CHUNK_BYTES`` at a time and stops as soon as the
    running total exceeds ``MAX_UPLOAD_BYTES``, so an oversized upload is
    never buffered whole in memory before being rejected.
    """
    total = 0
    while True:
        chunk = source.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=(
                    f"The upload is at least {total} bytes; "
                    f"at most {MAX_UPLOAD_BYTES} bytes are accepted."
                ),
            )
        destination.write(chunk)


def _enforce_size_limits(path: Path, suffix: str) -> None:
    """Refuse a document beyond the page or pixel ceiling.

    Runs after the file is already on disk (it has to be, for PaddleOCR to
    read it), but before it reaches the engine, so an oversized document costs
    a stat/decode instead of a GPU slot.
    """
    if suffix == ".pdf":
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError

        try:
            reader = PdfReader(str(path))
            pages = reader.pages
            page_count = len(pages)
        except (PdfReadError, ValueError, OSError) as error:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"The PDF could not be read to check its page count: {error}",
            ) from error
        if page_count > MAX_PAGES:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"The PDF has {page_count} pages; at most {MAX_PAGES} are accepted.",
            )

        dpi_scale = ASSUMED_PDF_DPI / 72  # MediaBox units are points, 1/72 inch.
        for index, page in enumerate(pages, 1):
            mediabox = page.mediabox
            width = round(float(mediabox.width) * dpi_scale)
            height = round(float(mediabox.height) * dpi_scale)
            if width * height > MAX_IMAGE_PIXELS:
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=(
                        f"Page {index} of the PDF would render to {width}x{height} "
                        f"({width * height} pixels) at {ASSUMED_PDF_DPI} DPI; "
                        f"at most {MAX_IMAGE_PIXELS} pixels are accepted."
                    ),
                )
        return

    from PIL import Image
    from PIL import UnidentifiedImageError as PillowUnidentifiedImageError

    try:
        with Image.open(path) as image:
            width, height = image.size
    except (PillowUnidentifiedImageError, OSError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"The image could not be read to check its size: {error}",
        ) from error

    if width * height > MAX_IMAGE_PIXELS:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"The image is {width}x{height} ({width * height} pixels); "
                f"at most {MAX_IMAGE_PIXELS} pixels are accepted."
            ),
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
