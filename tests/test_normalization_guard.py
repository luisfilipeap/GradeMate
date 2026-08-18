"""Backend semantic-preservation guard (issue #21): a proposal is rejected
outright when it does not preserve every numeral or protected symbol found
in the original OCR text, in order — the guard is what actually enforces
this, not merely the prompt asking the LLM not to change anything.
"""

from __future__ import annotations

import pytest

from app.services import normalization_guard as guard


@pytest.mark.parametrize("label", ["inline_formula", "display_formula"])
def test_formula_labels_are_always_eligible(label: str) -> None:
    assert guard.is_eligible("anything at all, even prose", label) is True


def test_a_text_line_with_no_math_is_not_eligible() -> None:
    assert guard.is_eligible("The student wrote a short essay.", "text") is False


def test_a_text_line_with_an_equation_is_eligible() -> None:
    assert guard.is_eligible("The answer is x = 5", "text") is True


def test_a_text_line_with_a_latex_command_is_eligible() -> None:
    assert guard.is_eligible(r"\frac{1}{2} of the total", "text") is True


def test_a_text_line_with_a_bare_number_is_not_eligible() -> None:
    # A question number or a date is not "math" on its own.
    assert guard.is_eligible("Question 2", "text") is False


def test_an_unlabelled_line_falls_back_to_the_same_math_hint() -> None:
    assert guard.is_eligible("2+2=4", None) is True
    assert guard.is_eligible("no math here", None) is False


def test_a_table_label_is_never_eligible() -> None:
    assert guard.is_eligible("2+2=4", "table") is False


def test_guard_passes_when_only_delimiters_and_spacing_change() -> None:
    assert guard.guard_passes("2+2=4", "$$2 + 2 = 4$$") is True


def test_guard_passes_on_an_identical_proposal() -> None:
    assert guard.guard_passes("x = 5", "x = 5") is True


def test_guard_rejects_the_2_plus_2_equals_5_case() -> None:
    # The acceptance criterion from issue #21, verbatim.
    assert guard.guard_passes("2+2=4", "2+2=5") is False


def test_guard_rejects_a_dropped_operand() -> None:
    assert guard.guard_passes("2+2=4", "2=4") is False


def test_guard_rejects_a_changed_operator() -> None:
    assert guard.guard_passes("2+2=4", "2-2=4") is False


def test_guard_rejects_reordered_numbers() -> None:
    assert guard.guard_passes("5-2=3", "2-5=3") is False


def test_guard_rejects_a_restructuring_that_drops_a_protected_symbol() -> None:
    # Conservative by design: even a plausibly value-preserving rewrite is
    # rejected if it does not keep every protected symbol (see the guard's
    # module docstring for why).
    assert guard.guard_passes("1/2", r"\frac{1}{2}") is False


def test_guard_rejects_a_bare_latex_command_outside_any_delimiter() -> None:
    # issue #29: KaTeX only renders math inside a recognized delimiter pair;
    # a bare command left outside one would render as literal text.
    assert guard.guard_passes(r"\frac{1}{2}", r"\frac{1}{2}") is False


def test_guard_passes_a_latex_command_wrapped_in_inline_delimiters() -> None:
    assert guard.guard_passes(r"\frac{1}{2}", r"$\frac{1}{2}$") is True


def test_guard_passes_plain_arithmetic_with_no_latex_command() -> None:
    assert guard.guard_passes("2+2=4", "2 + 2 = 4") is True


def test_guard_passes_a_command_wrapped_in_display_dollars() -> None:
    assert guard.guard_passes(r"\frac{1}{2}", r"$$\frac{1}{2}$$") is True


def test_guard_rejects_a_bare_command_alongside_a_properly_wrapped_one() -> None:
    # One command is delimited, the other is not — still rejected.
    assert guard.guard_passes(r"\frac{1}{2} \sqrt{4}", r"$\frac{1}{2}$ \sqrt{4}") is False


def test_guard_passes_a_command_wrapped_in_bracket_delimiters() -> None:
    assert guard.guard_passes(r"\frac{1}{2}", r"\[\frac{1}{2}\]") is True


def test_guard_passes_a_command_wrapped_in_paren_delimiters() -> None:
    assert guard.guard_passes(r"\frac{1}{2}", r"\(\frac{1}{2}\)") is True
