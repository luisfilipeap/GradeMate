"""Submission: the scanned PDF a student handed in for an assessment."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.class_group import ClassGroup
    from app.models.student import Student
    from app.models.submission_page import SubmissionPage


class Submission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One student's answered exam for one assessment, stored as a PDF file.

    The PDF itself lives on the storage volume mounted into the container; the
    database only keeps ``file_path``, a path relative to ``STORAGE_ROOT``.
    """

    __tablename__ = "submissions"
    __table_args__ = (
        # A student hands in a single PDF per assessment.
        UniqueConstraint("assessment_id", "student_id", name="uq_submissions_assessment_student"),
        # Two submissions must never point at the same file on the volume.
        UniqueConstraint("file_path", name="uq_submissions_file_path"),
        # Composite foreign keys: they carry class_id along, which makes it
        # impossible to attach a student to an assessment of a different class.
        ForeignKeyConstraint(
            ["assessment_id", "class_id"],
            ["assessments.id", "assessments.class_id"],
            name="fk_submissions_assessment_id_assessments",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["student_id", "class_id"],
            ["students.id", "students.class_id"],
            name="fk_submissions_student_id_students",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "file_size_bytes IS NULL OR file_size_bytes > 0", name="file_size_positive"
        ),
        CheckConstraint("page_count IS NULL OR page_count > 0", name="page_count_positive"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), nullable=False, index=True
    )

    student_id: Mapped[uuid.UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False, index=True)

    # Path of the PDF relative to the storage root, e.g.
    # "submissions/<assessment_id>/<student_id>.pdf".
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)

    # Name of the file as uploaded by the teacher, kept for display purposes.
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)

    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Hex-encoded SHA-256 of the PDF, used to detect duplicate or corrupted uploads.
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    assessment: Mapped[Assessment] = relationship(
        back_populates="submissions",
        foreign_keys=[assessment_id, class_id],
        overlaps="submissions,student",
    )
    student: Mapped[Student] = relationship(
        back_populates="submissions",
        foreign_keys=[student_id, class_id],
        overlaps="submissions,assessment",
    )
    pages: Mapped[list[SubmissionPage]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="SubmissionPage.number",
    )

    @property
    def class_group(self) -> ClassGroup:
        """The class this submission belongs to (shared by student and assessment)."""
        return self.assessment.class_group

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Submission id={self.id} file_path={self.file_path!r}>"
