"""Assessment (exam or test) applied to a class."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.class_group import ClassGroup
    from app.models.submission import Submission


class Assessment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One graded assessment of a class; a class may have many of them."""

    __tablename__ = "assessments"
    __table_args__ = (
        UniqueConstraint("class_id", "title", name="uq_assessments_class_title"),
        # Redundant on its own, but required as the target of the composite foreign
        # key that keeps a submission's student and assessment in the same class.
        UniqueConstraint("id", "class_id", name="uq_assessments_id_class"),
        CheckConstraint("max_score > 0", name="max_score_positive"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title: Mapped[str] = mapped_column(String(160), nullable=False)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Date the assessment was applied. Optional while the exam is being prepared.
    applied_on: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Total number of points a student can earn in this assessment.
    max_score: Mapped[Decimal] = mapped_column(
        Numeric(6, 2),
        nullable=False,
        server_default="100",
    )

    class_group: Mapped[ClassGroup] = relationship(back_populates="assessments")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="assessment",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[Submission.assessment_id, Submission.class_id]",
        # Both composite foreign keys write submissions.class_id; the database
        # constraints guarantee the two writers always agree on its value.
        overlaps="submissions,assessment,student",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Assessment id={self.id} title={self.title!r}>"
