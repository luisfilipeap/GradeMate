"""Endpoints for students, always scoped to a class."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import ClassDep, SessionDep, StudentDep
from app.models import Student
from app.schemas import StudentCreate, StudentRead, StudentUpdate
from app.services.cleanup import collect_submission_files, delete_files

router = APIRouter(tags=["students"])


@router.get("/classes/{class_id}/students", response_model=list[StudentRead])
def list_students(class_group: ClassDep, session: SessionDep) -> list[Student]:
    """List the students of a class, in alphabetical order."""
    return list(
        session.scalars(
            select(Student).where(Student.class_id == class_group.id).order_by(Student.full_name)
        )
    )


@router.post(
    "/classes/{class_id}/students",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_student(class_group: ClassDep, payload: StudentCreate, session: SessionDep) -> Student:
    """Add a student to a class."""
    student = Student(class_id=class_group.id, **payload.model_dump())
    session.add(student)
    session.commit()
    session.refresh(student)
    return student


@router.patch("/students/{student_id}", response_model=StudentRead)
def update_student(student: StudentDep, payload: StudentUpdate, session: SessionDep) -> Student:
    """Update the fields provided in the payload."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(student, field, value)
    session.commit()
    session.refresh(student)
    return student


@router.delete("/students/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_student(student: StudentDep, session: SessionDep) -> None:
    """Remove a student from the class, and the files of every exam they handed in."""
    stored_files = collect_submission_files(session, student_id=student.id)
    session.delete(student)
    session.commit()
    delete_files(stored_files)
