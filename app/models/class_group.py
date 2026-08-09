"""Class (a group of students taught over an academic term)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.assessment import Assessment
    from app.models.student import Student


class ClassGroup(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A class taught by the teacher, holding its students and assessments."""

    __tablename__ = "classes"

    # Human-readable name, e.g. "Calculus I - 2026/1".
    name: Mapped[str] = mapped_column(String(160), nullable=False)

    # Institutional course/section code, e.g. "MAT101-A". Optional.
    code: Mapped[str | None] = mapped_column(String(60), nullable=True, unique=True)

    # Academic term the class belongs to, e.g. "2026.1". Optional.
    academic_term: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    students: Mapped[list[Student]] = relationship(
        back_populates="class_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    assessments: Mapped[list[Assessment]] = relationship(
        back_populates="class_group",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"<ClassGroup id={self.id} name={self.name!r}>"
