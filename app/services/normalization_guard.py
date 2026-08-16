"""Backend semantic-preservation guard for LaTeX/Markdown normalization
(issue #21).

The LLM is asked, via prompt, not to change any number or symbol while
reformatting an OCR reading into valid LaTeX/Markdown — but a prompt is not
enforcement. This module is the enforcement: it decides which `OcrLine`s are
worth normalizing at all, and rejects a proposal outright if it does not
preserve every numeral or core math symbol found in the original text, in
the same order.

Deliberately scoped to digits and a small set of arithmetic/relational
operators, not every character: reformatting markup (adding `$…$` delimiters,
spacing, braces) is exactly what normalization is for and must stay allowed,
so only the tokens that could change what the text *means* mathematically
are compared, in order.

This is intentionally conservative rather than clever: a restructuring that
drops one of those protected symbols even while arguably preserving the
value — turning `1/2` into `\frac{1}{2}`, say — is rejected too, because the
guard has no reliable way to tell that case apart from one that actually
changed the value. Favoring "reject a safe rewrite" over "accept an unsafe
one" is the point of the guard.
"""

from __future__ import annotations

import re

# Formula regions are always eligible; a `text` line is only eligible when it
# looks like it contains a math snippet worth normalizing (see `is_eligible`).
_FORMULA_LABELS = frozenset({"inline_formula", "display_formula"})

# Digits (with an optional decimal point) or one of the arithmetic/relational/
# grouping-affecting symbols whose meaning a normalization must not change.
_PROTECTED_TOKEN = re.compile(r"\d+(?:\.\d+)?|[+\-*/=<>≤≥≠^_]")

# A `text` line counts as "math-bearing" when it has a digit alongside an
# operator/relation, or an obvious LaTeX command — plain prose full of digits
# (a date, a question number) has neither and is left alone.
_MATH_HINT = re.compile(r"(?:\d\s*[+\-*/=<>≤≥≠^_]|[+\-*/=<>≤≥≠^_]\s*\d|\\[a-zA-Z]+)")


def is_eligible(text: str, label: str | None) -> bool:
    """Whether an `OcrLine` with this `label`/`text` is a normalization candidate."""
    if label in _FORMULA_LABELS:
        return True
    if label is None or label == "text":
        return bool(_MATH_HINT.search(text))
    return False


def guard_passes(original: str, proposal: str) -> bool:
    """True only if `proposal` preserves every protected token of `original`, in order.

    A mismatch in count, value, or order of any digit run or protected symbol
    rejects the proposal — this is what actually enforces "never change a
    number", not just the prompt asking for it.
    """
    return _protected_tokens(original) == _protected_tokens(proposal)


def _protected_tokens(text: str) -> list[str]:
    return _PROTECTED_TOKEN.findall(text)
