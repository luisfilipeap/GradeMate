"""Shared FastAPI dependencies."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_session
from app.models import Assessment, ClassGroup, Student

SessionDep = Annotated[Session, Depends(get_session)]


def get_class_or_404(class_id: Annotated[uuid.UUID, Path()], session: SessionDep) -> ClassGroup:
    """Load a class by id or raise 404."""
    class_group = session.get(ClassGroup, class_id)
    if class_group is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Class not found")
    return class_group


def get_student_or_404(student_id: Annotated[uuid.UUID, Path()], session: SessionDep) -> Student:
    """Load a student by id or raise 404."""
    student = session.get(Student, student_id)
    if student is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Student not found")
    return student


def get_assessment_or_404(
    assessment_id: Annotated[uuid.UUID, Path()], session: SessionDep
) -> Assessment:
    """Load an assessment by id or raise 404."""
    assessment = session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Assessment not found")
    return assessment


ClassDep = Annotated[ClassGroup, Depends(get_class_or_404)]
StudentDep = Annotated[Student, Depends(get_student_or_404)]
AssessmentDep = Annotated[Assessment, Depends(get_assessment_or_404)]
