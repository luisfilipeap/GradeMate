"""One rasterised page of a submission, and the OCR lines found on it."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.ocr_line import OcrLine
    from app.models.submission import Submission


class SubmissionPage(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A page of the submitted PDF, rendered to an image.

    The image is the exact raster that was sent to the OCR service, so the line
    boxes are expressed in its pixel coordinates and always line up when the
    interface draws them on top of it.
    """

    __tablename__ = "submission_pages"
    __table_args__ = (
        UniqueConstraint("submission_id", "number", name="uq_submission_pages_submission_number"),
        CheckConstraint("number > 0", name="number_positive"),
        CheckConstraint("width > 0 AND height > 0", name="size_positive"),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # 1-based page number inside the PDF.
    number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Size of the rendered image, in pixels.
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)

    # Path of the PNG relative to the storage root.
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # Which engine produced the lines of this page: "ocr" or "vl".
    engine: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ocr")

    submission: Mapped[Submission] = relationship(back_populates="pages")
    lines: Mapped[list[OcrLine]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="OcrLine.position",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<SubmissionPage submission={self.submission_id} number={self.number}>"
