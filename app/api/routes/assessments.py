"""Endpoints for assessments, always scoped to a class."""

from __future__ import annotations

from fastapi import APIRouter, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import AssessmentDep, ClassDep, SessionDep
from app.models import Assessment, Question, Submission
from app.schemas import AssessmentCreate, AssessmentRead, AssessmentUpdate
from app.services.cleanup import (
    collect_question_paper_files,
    collect_submission_files,
    delete_files,
)

router = APIRouter(tags=["assessments"])

_submission_count = (
    select(func.count(Submission.id))
    .where(Submission.assessment_id == Assessment.id)
    .scalar_subquery()
)
_question_count = (
    select(func.count(Question.id)).where(Question.assessment_id == Assessment.id).scalar_subquery()
)


def _read(assessment: Assessment, submissions: int, questions: int) -> AssessmentRead:
    return AssessmentRead.model_validate(assessment).model_copy(
        update={"submission_count": submissions, "question_count": questions}
    )


def _read_one(session: Session, assessment: Assessment) -> AssessmentRead:
    submissions, questions = session.execute(
        select(_submission_count, _question_count).where(Assessment.id == assessment.id)
    ).one()
    return _read(assessment, submissions or 0, questions or 0)


@router.get("/classes/{class_id}/assessments", response_model=list[AssessmentRead])
def list_assessments(class_group: ClassDep, session: SessionDep) -> list[AssessmentRead]:
    """List the assessments of a class, newest application date first."""
    rows = session.execute(
        select(Assessment, _submission_count, _question_count)
        .where(Assessment.class_id == class_group.id)
        .order_by(Assessment.applied_on.desc().nullslast(), Assessment.created_at.desc())
    ).all()
    return [
        _read(assessment, submissions, questions) for assessment, submissions, questions in rows
    ]


@router.post(
    "/classes/{class_id}/assessments",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_assessment(
    class_group: ClassDep, payload: AssessmentCreate, session: SessionDep
) -> AssessmentRead:
    """Create an assessment for a class."""
    assessment = Assessment(class_id=class_group.id, **payload.model_dump())
    session.add(assessment)
    session.commit()
    session.refresh(assessment)
    return _read(assessment, 0, 0)


@router.get("/assessments/{assessment_id}", response_model=AssessmentRead)
def get_assessment(assessment: AssessmentDep, session: SessionDep) -> AssessmentRead:
    """Retrieve a single assessment."""
    return _read_one(session, assessment)


@router.patch("/assessments/{assessment_id}", response_model=AssessmentRead)
def update_assessment(
    assessment: AssessmentDep, payload: AssessmentUpdate, session: SessionDep
) -> AssessmentRead:
    """Update the fields provided in the payload."""
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(assessment, field, value)
    session.commit()
    session.refresh(assessment)
    return _read_one(session, assessment)


@router.delete("/assessments/{assessment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assessment(assessment: AssessmentDep, session: SessionDep) -> None:
    """Delete an assessment, its submissions and questions, and their stored files."""
    stored_files = collect_submission_files(
        session, assessment_id=assessment.id
    ) + collect_question_paper_files(session, assessment_id=assessment.id)
    session.delete(assessment)
    session.commit()
    delete_files(stored_files)
