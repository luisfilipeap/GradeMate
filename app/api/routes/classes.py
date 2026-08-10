"""Endpoints for classes."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import ClassDep, SessionDep
from app.models import Assessment, ClassGroup, Student
from app.schemas import ClassCreate, ClassRead, ClassUpdate
from app.services.cleanup import (
    collect_question_paper_files,
    collect_submission_files,
    delete_files,
)

router = APIRouter(prefix="/classes", tags=["classes"])

_student_count = (
    select(func.count(Student.id)).where(Student.class_id == ClassGroup.id).scalar_subquery()
)
_assessment_count = (
    select(func.count(Assessment.id)).where(Assessment.class_id == ClassGroup.id).scalar_subquery()
)


def _read(class_group: ClassGroup, students: int, assessments: int) -> ClassRead:
    return ClassRead.model_validate(class_group).model_copy(
        update={"student_count": students, "assessment_count": assessments}
    )


def _read_one(session: Session, class_group: ClassGroup) -> ClassRead:
    """Build the response for a single class, fetching its counters."""
    students, assessments = session.execute(
        select(_student_count, _assessment_count).where(ClassGroup.id == class_group.id)
    ).one()
    return _read(class_group, students, assessments)


@router.get("", response_model=list[ClassRead])
def list_classes(session: SessionDep) -> list[ClassRead]:
    """List every class, most recently created first."""
    rows = session.execute(
        select(ClassGroup, _student_count, _assessment_count).order_by(ClassGroup.created_at.desc())
    ).all()
    return [
        _read(class_group, students, assessments) for class_group, students, assessments in rows
    ]


@router.post("", response_model=ClassRead, status_code=status.HTTP_201_CREATED)
def create_class(payload: ClassCreate, session: SessionDep) -> ClassRead:
    """Create a class."""
    class_group = ClassGroup(**payload.model_dump())
    session.add(class_group)
    session.commit()
    session.refresh(class_group)
    return _read(class_group, 0, 0)


@router.get("/{class_id}", response_model=ClassRead)
def get_class(class_group: ClassDep, session: SessionDep) -> ClassRead:
    """Retrieve a single class."""
    return _read_one(session, class_group)


@router.patch("/{class_id}", response_model=ClassRead)
def update_class(class_group: ClassDep, payload: ClassUpdate, session: SessionDep) -> ClassRead:
    """Update the fields provided in the payload."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(class_group, field, value)
    session.commit()
    session.refresh(class_group)
    return _read_one(session, class_group)


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(class_group: ClassDep, session: SessionDep) -> None:
    """Delete a class, its students and assessments, and every stored exam file."""
    stored_files = collect_submission_files(
        session, class_id=class_group.id
    ) + collect_question_paper_files(session, class_id=class_group.id)
    session.delete(class_group)
    session.commit()
    delete_files(stored_files)
