"""#12: whitespace-only required text fields must be rejected.

The ``min_length=1`` constraint on these fields only means something if
stripping happens before it runs. These are plain Pydantic model tests -
no database or HTTP client needed.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.assessment import AssessmentCreate, AssessmentUpdate
from app.schemas.class_group import ClassCreate, ClassUpdate
from app.schemas.question import QuestionCreate, QuestionUpdate
from app.schemas.student import StudentCreate, StudentUpdate


class TestClassSchemas:
    def test_create_rejects_whitespace_only_name(self) -> None:
        with pytest.raises(ValidationError):
            ClassCreate(name=" ")

    def test_create_strips_surrounding_whitespace(self) -> None:
        assert ClassCreate(name="  Turma A  ").name == "Turma A"

    def test_update_rejects_whitespace_only_name(self) -> None:
        with pytest.raises(ValidationError):
            ClassUpdate(name="   ")

    def test_update_strips_surrounding_whitespace(self) -> None:
        assert ClassUpdate(name="  Turma A  ").name == "Turma A"

    def test_update_allows_omitted_name(self) -> None:
        assert ClassUpdate().name is None


class TestStudentSchemas:
    def test_create_rejects_whitespace_only_full_name(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(
                full_name=" ", registration_number="123", email="a@example.com"
            )

    def test_create_rejects_whitespace_only_registration_number(self) -> None:
        with pytest.raises(ValidationError):
            StudentCreate(
                full_name="Ana", registration_number="  ", email="a@example.com"
            )

    def test_create_strips_surrounding_whitespace(self) -> None:
        student = StudentCreate(
            full_name="  Ana  ", registration_number=" 123 ", email="a@example.com"
        )
        assert student.full_name == "Ana"
        assert student.registration_number == "123"

    def test_update_rejects_whitespace_only_full_name(self) -> None:
        with pytest.raises(ValidationError):
            StudentUpdate(full_name=" ")

    def test_update_rejects_whitespace_only_registration_number(self) -> None:
        with pytest.raises(ValidationError):
            StudentUpdate(registration_number=" ")

    def test_update_strips_surrounding_whitespace(self) -> None:
        student = StudentUpdate(full_name="  Ana  ")
        assert student.full_name == "Ana"


class TestAssessmentSchemas:
    def test_create_rejects_whitespace_only_title(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentCreate(title=" ")

    def test_create_strips_surrounding_whitespace(self) -> None:
        assert AssessmentCreate(title="  Midterm  ").title == "Midterm"

    def test_update_rejects_whitespace_only_title(self) -> None:
        with pytest.raises(ValidationError):
            AssessmentUpdate(title="   ")

    def test_update_strips_surrounding_whitespace(self) -> None:
        assert AssessmentUpdate(title="  Midterm  ").title == "Midterm"

    def test_update_allows_omitted_title(self) -> None:
        assert AssessmentUpdate().title is None


class TestQuestionSchemas:
    def test_create_rejects_whitespace_only_statement(self) -> None:
        with pytest.raises(ValidationError):
            QuestionCreate(number="1", statement=" ")

    def test_create_rejects_whitespace_only_number(self) -> None:
        with pytest.raises(ValidationError):
            QuestionCreate(number=" ", statement="What is 1+1?")

    def test_create_strips_surrounding_whitespace(self) -> None:
        question = QuestionCreate(number=" 1 ", statement="  What is 1+1?  ")
        assert question.number == "1"
        assert question.statement == "What is 1+1?"

    def test_update_rejects_whitespace_only_statement(self) -> None:
        with pytest.raises(ValidationError):
            QuestionUpdate(statement=" ")

    def test_update_rejects_whitespace_only_number(self) -> None:
        with pytest.raises(ValidationError):
            QuestionUpdate(number=" ")

    def test_update_strips_surrounding_whitespace(self) -> None:
        question = QuestionUpdate(number=" 1 ", statement="  What is 1+1?  ")
        assert question.number == "1"
        assert question.statement == "What is 1+1?"

    def test_update_allows_omitted_fields(self) -> None:
        question = QuestionUpdate()
        assert question.number is None
        assert question.statement is None
