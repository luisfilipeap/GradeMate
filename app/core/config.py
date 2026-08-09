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

    # Root of the storage volume holding the uploaded PDFs. Inside the container
    # this is the mount point of the `grademate_storage` volume; the database
    # stores paths relative to it, never absolute ones.
    storage_root: Path = Path("./storage")

    # Largest exam PDF the teacher is allowed to upload.
    max_upload_mb: int = 25

    # The OCR service from docker-compose.
    ocr_service_url: str = "http://localhost:8001"
    ocr_timeout_seconds: float = 180.0

    # Resolution used to rasterise the PDF pages. The same image is sent to the
    # OCR service and shown in the review screen, so the boxes always match.
    page_render_dpi: int = 150


@lru_cache
def get_settings() -> Settings:
    """Return the settings singleton."""
    return Settings()
