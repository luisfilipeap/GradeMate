"""A line of text the OCR found on a page, plus the teacher's review of it."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.submission_page import SubmissionPage


class OcrLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One recognised line.

    ``text`` is kept exactly as the OCR produced it, so the teacher's edit in
    ``corrected_text`` never destroys the original reading.
    """

    __tablename__ = "ocr_lines"
    __table_args__ = (
        UniqueConstraint("page_id", "position", name="uq_ocr_lines_page_position"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
    )

    page_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("submission_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Reading order within the page, as returned by the OCR.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    # Set when the teacher rewrites the line; NULL means "as recognised".
    corrected_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # True once the teacher has confirmed the line, edited or not.
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # PaddleOCR-VL reports no per-block score, so this stays NULL for that engine.
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Region type given by PaddleOCR-VL: "text", "inline_formula", "table"…
    label: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Polygon around the line, as [[x, y], ...] in pixels of the page image.
    box: Mapped[list[list[float]]] = mapped_column(JSONB, nullable=False)

    page: Mapped[SubmissionPage] = relationship(back_populates="lines")

    @property
    def final_text(self) -> str:
        """What the transcript should show for this line."""
        return self.corrected_text if self.corrected_text is not None else self.text

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<OcrLine page={self.page_id} position={self.position}>"


def normalise_box(box: Any) -> list[list[float]]:
    """Coerce a polygon coming from the OCR service into plain floats."""
    return [[float(point[0]), float(point[1])] for point in box]
