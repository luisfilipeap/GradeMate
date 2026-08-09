"""Student enrolled in a class."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.class_group import ClassGroup
    from app.models.submission import Submission


class Student(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A student belonging to exactly one class."""

    __tablename__ = "students"
    __table_args__ = (
        # A registration number and an e-mail address identify a single student
        # inside a class; they may reappear in other classes of the same teacher.
        UniqueConstraint("class_id", "registration_number", name="uq_students_class_registration"),
        UniqueConstraint("class_id", "email", name="uq_students_class_email"),
        # Redundant on its own, but required as the target of the composite foreign
        # key that keeps a submission's student and assessment in the same class.
        UniqueConstraint("id", "class_id", name="uq_students_id_class"),
    )

    class_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("classes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(160), nullable=False)

    # Institutional registration number ("matricula").
    registration_number: Mapped[str] = mapped_column(String(40), nullable=False)

    # Stored lower-cased so the per-class uniqueness check is case-insensitive.
    email: Mapped[str] = mapped_column(String(255), nullable=False)

    class_group: Mapped[ClassGroup] = relationship(back_populates="students")
    submissions: Mapped[list[Submission]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="[Submission.student_id, Submission.class_id]",
        # Both composite foreign keys write submissions.class_id; the database
        # constraints guarantee the two writers always agree on its value.
        overlaps="submissions,assessment,student",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<Student id={self.id} registration_number={self.registration_number!r}>"
