"""Application settings, loaded from environment variables or a local .env file."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for GradeMate."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # SQLAlchemy URL for the PostgreSQL database (psycopg 3 driver).
    database_url: str = "postgresql+psycopg://grademate:grademate@localhost:5432/grademate"

    # Log every SQL statement issued by SQLAlchemy.
    sql_echo: bool = False

    # Root directory on the host filesystem holding the uploaded PDFs (the
    # backend runs as a plain host process, not in a container). The database
    # stores paths relative to it, never absolute ones.
    storage_root: Path = Path("./storage")

    # Largest exam PDF the teacher is allowed to upload.
    max_upload_mb: int = 25

    # Largest number of pages a single submission may have. Each page costs
    # about 15s of GPU time and a render buffer, so this bounds both.
    max_submission_pages: int = 60

    # Largest rasterised page, in pixels (width * height), sent to the OCR
    # service. Guards against a PDF whose page size or DPI would otherwise
    # blow up the render and the upload to the OCR service.
    max_page_pixels: int = 40_000_000  # ~40 MP, e.g. a 6350x6300 page

    # The OCR service from docker-compose.
    ocr_service_url: str = "http://localhost:8001"
    # Per-page HTTP timeout for a single call to the OCR service.
    ocr_timeout_seconds: float = 180.0
    # Ceiling for a whole OCR run (every page of one submission), distinct
    # from the per-page timeout above: a document with many pages, each
    # individually fast enough, could otherwise run unbounded.
    ocr_job_timeout_seconds: float = 900.0

    # Resolution used to rasterise the PDF pages. The same image is sent to the
    # OCR service and shown in the review screen, so the boxes always match.
    page_render_dpi: int = 150

    # The LLM service from docker-compose (Ollama, opt-in via the "tools"
    # profile; see docker-compose.yml).
    llm_service_url: str = "http://localhost:11434"
    # Model Ollama should use to answer a generate_structured call. Never
    # hardcode a model name in application code; it belongs here so it can
    # be swapped without a code change.
    llm_model: str = "qwen3"
    # Per-call HTTP timeout for a single call to the LLM service.
    llm_timeout_seconds: float = 180.0


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
