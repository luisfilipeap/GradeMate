"""A question belonging to an assessment's question paper."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment


class Question(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One question of an assessment's question paper.

    ``number`` is the teacher's own numbering ("1", "1a", "2.1"...), kept as
    text rather than assumed to be an integer. ``position`` is the question's
    order within the assessment, independent of what the number happens to
    read.
    """

    __tablename__ = "questions"
    __table_args__ = (
        UniqueConstraint("assessment_id", "number", name="uq_questions_assessment_number"),
        UniqueConstraint("assessment_id", "position", name="uq_questions_assessment_position"),
        CheckConstraint("position > 0", name="position_positive"),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # The teacher's own numbering, e.g. "1", "1a", "2.1". Not assumed numeric.
    number: Mapped[str] = mapped_column(String(20), nullable=False)

    statement: Mapped[str] = mapped_column(Text, nullable=False)

    # Reading order within the assessment.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    assessment: Mapped[Assessment] = relationship(back_populates="questions")

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Question assessment={self.assessment_id} number={self.number!r}>"
