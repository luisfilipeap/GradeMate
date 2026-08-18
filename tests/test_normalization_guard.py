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
    """Formulas are always eligible for normalization regardless of content."""
    assert guard.is_eligible("anything at all, even prose", label) is True


def test_a_text_line_with_no_math_is_not_eligible() -> None:
    """Plain prose without math hints should not be normalized."""
    assert guard.is_eligible("The student wrote a short essay.", "text") is False


def test_a_text_line_with_an_equation_is_eligible() -> None:
    """Text containing operators (=, +, etc.) qualifies as math-bearing."""
    assert guard.is_eligible("The answer is x = 5", "text") is True


def test_a_text_line_with_a_latex_command_is_eligible() -> None:
    """Text containing LaTeX commands (\\frac, \\sqrt, etc.) qualifies as math-bearing."""
    assert guard.is_eligible(r"\frac{1}{2} of the total", "text") is True


def test_a_text_line_with_a_bare_number_is_not_eligible() -> None:
    """Isolated numbers without operators are not considered math (no context)."""
    assert guard.is_eligible("Question 2", "text") is False


def test_an_unlabelled_line_falls_back_to_the_same_math_hint() -> None:
    """Unlabeled lines use the same math-hint detection as text lines."""
    assert guard.is_eligible("2+2=4", None) is True
    assert guard.is_eligible("no math here", None) is False


def test_a_table_label_is_never_eligible() -> None:
    """Table content is never normalized (treated as structured data)."""
    assert guard.is_eligible("2+2=4", "table") is False


def test_guard_passes_when_only_delimiters_and_spacing_change() -> None:
    """Reformatting (spacing, adding delimiters) is allowed; protected tokens unchanged."""
    assert guard.guard_passes("2+2=4", "$$2 + 2 = 4$$") is True


def test_guard_passes_on_an_identical_proposal() -> None:
    """Identical proposals pass trivially."""
    assert guard.guard_passes("x = 5", "x = 5") is True


def test_guard_rejects_the_2_plus_2_equals_5_case() -> None:
    """Changing a protected token (4→5) is rejected (core issue #21)."""
    assert guard.guard_passes("2+2=4", "2+2=5") is False


def test_guard_rejects_a_dropped_operand() -> None:
    """Dropping a number while keeping operators is rejected."""
    assert guard.guard_passes("2+2=4", "2=4") is False


def test_guard_rejects_a_changed_operator() -> None:
    """Changing an operator (+→-) is rejected."""
    assert guard.guard_passes("2+2=4", "2-2=4") is False


def test_guard_rejects_reordered_numbers() -> None:
    """Changing token order (5-2 → 2-5) is rejected."""
    assert guard.guard_passes("5-2=3", "2-5=3") is False


def test_guard_rejects_a_restructuring_that_drops_a_protected_symbol() -> None:
    """Rewriting 1/2 as \\frac{1}{2} drops the / operator, rejected conservatively."""
    assert guard.guard_passes("1/2", r"\frac{1}{2}") is False


def test_guard_rejects_a_bare_latex_command_outside_any_delimiter() -> None:
    """Bare LaTeX commands render as literal text without delimiters (issue #29)."""
    assert guard.guard_passes(r"\frac{1}{2}", r"\frac{1}{2}") is False


def test_guard_passes_a_latex_command_wrapped_in_inline_delimiters() -> None:
    """LaTeX in $ $ inline delimiters is recognized and passes."""
    assert guard.guard_passes(r"\frac{1}{2}", r"$\frac{1}{2}$") is True


def test_guard_passes_plain_arithmetic_with_no_latex_command() -> None:
    """Arithmetic without LaTeX passes; delimiters not required."""
    assert guard.guard_passes("2+2=4", "2 + 2 = 4") is True


def test_guard_passes_a_command_wrapped_in_display_dollars() -> None:
    """LaTeX in $$ $$ display delimiters is recognized and passes."""
    assert guard.guard_passes(r"\frac{1}{2}", r"$$\frac{1}{2}$$") is True


def test_guard_rejects_a_bare_command_alongside_a_properly_wrapped_one() -> None:
    """Mixed delimited and bare commands: one bare command causes rejection."""
    assert guard.guard_passes(r"\frac{1}{2} \sqrt{4}", r"$\frac{1}{2}$ \sqrt{4}") is False


def test_guard_passes_a_command_wrapped_in_bracket_delimiters() -> None:
    """LaTeX in \\[ \\] bracket delimiters is recognized and passes."""
    assert guard.guard_passes(r"\frac{1}{2}", r"\[\frac{1}{2}\]") is True


def test_guard_passes_a_command_wrapped_in_paren_delimiters() -> None:
    """LaTeX in \\( \\) paren delimiters is recognized and passes."""
    assert guard.guard_passes(r"\frac{1}{2}", r"\(\frac{1}{2}\)") is True
