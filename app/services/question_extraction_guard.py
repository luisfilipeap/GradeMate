"""Structural guard for the LLM's question-extraction proposal (issue #32).

Unlike `normalization_guard.guard_passes`, this guard has nothing to compare
the proposal against: there is no one-to-one original for a "question" the
way an `OcrLine` has its own OCR `text`, since one proposed question can
draw on any part of the transcript, or several lines of it. So this check is
purely structural — it only asks whether what the LLM proposed is usable at
all as a set of draft questions, not whether it faithfully preserved
anything from the source.

A proposal is rejected when:
  * `questions` is missing, not a list, or empty — nothing to show the
    teacher is not a usable extraction;
  * any entry's `number` is missing, not a string, or blank — an unlabeled
    question is not something a teacher/`POST .../questions` can use as
    `Question.number`, which is required and non-empty;
  * any entry's `statement` is missing, not a string, or blank — same
    reasoning, for `Question.statement`;
  * two entries share the same (stripped) `number` — `Question.number` is
    unique per assessment, and a proposal that already collides with itself
    would only fail later, at approval time, in a way harder to explain than
    rejecting it here.
"""

from __future__ import annotations


def extraction_passes(proposed: dict) -> bool:
    """True only if `proposed` is a well-formed, non-empty list of drafts."""
    questions = proposed.get("questions")
    if not isinstance(questions, list) or not questions:
        return False

    seen_numbers: set[str] = set()
    for entry in questions:
        if not isinstance(entry, dict):
            return False

        number = entry.get("number")
        if not isinstance(number, str) or not number.strip():
            return False

        statement = entry.get("statement")
        if not isinstance(statement, str) or not statement.strip():
            return False

        stripped_number = number.strip()
        if stripped_number in seen_numbers:
            return False
        seen_numbers.add(stripped_number)

    return True
