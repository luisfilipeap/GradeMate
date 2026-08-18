"""Backend semantic-preservation guard for LaTeX/Markdown normalization
(issue #21, extended by issue #29).

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

Issue #29 adds a second, independent check: a proposal is also rejected if
it contains a bare LaTeX command (`\frac`, `\sqrt`, ...) outside one of the
delimiter pairs the frontend's KaTeX auto-render recognizes (see
`KATEX_DELIMITERS` in `frontend/src/pages/review-page.tsx`). Without a
delimiter pair around it, KaTeX renders the command as literal text instead
of the intended formula — a rendering failure the token-preservation check
alone cannot catch, since the tokens themselves are unchanged.
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

# The delimiter pairs KaTeX's auto-render recognizes (mirrors
# `KATEX_DELIMITERS` in frontend/src/pages/review-page.tsx). Stripped
# double-before-single so a `$$…$$` span is not misread as two empty
# `$…$` spans.
_DISPLAY_DOLLAR = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_DISPLAY_BRACKET = re.compile(r"\\\[.*?\\\]", re.DOTALL)
_INLINE_DOLLAR = re.compile(r"\$.*?\$", re.DOTALL)
_INLINE_PAREN = re.compile(r"\\\(.*?\\\)", re.DOTALL)

# A bare LaTeX command: a backslash followed by one or more letters.
_BARE_COMMAND = re.compile(r"\\[a-zA-Z]+")


def is_eligible(text: str, label: str | None) -> bool:
    """Whether an `OcrLine` with this `label`/`text` is a normalization candidate."""
    if label in _FORMULA_LABELS:
        return True
    if label is None or label == "text":
        return bool(_MATH_HINT.search(text))
    return False


def guard_passes(original: str, proposal: str) -> bool:
    """True only if `proposal` passes both the delimiter and token-preservation checks.

    The delimiter check runs first: a proposal containing a bare LaTeX
    command outside a recognized `$…$`/`$$…$$`/`\\(…\\)`/`\\[…\\]` pair is
    rejected outright, since KaTeX would render that command as literal text
    rather than a formula.

    The token-preservation check then requires a mismatch-free count, value,
    and order of every digit run or protected symbol — this is what actually
    enforces "never change a number", not just the prompt asking for it.
    """
    if _has_bare_command(proposal):
        return False
    return _protected_tokens(original) == _protected_tokens(proposal)


def _has_bare_command(text: str) -> bool:
    return bool(_BARE_COMMAND.search(_strip_delimited_math(text)))


def _strip_delimited_math(text: str) -> str:
    text = _DISPLAY_DOLLAR.sub("", text)
    text = _DISPLAY_BRACKET.sub("", text)
    text = _INLINE_DOLLAR.sub("", text)
    text = _INLINE_PAREN.sub("", text)
    return text


def _protected_tokens(text: str) -> list[str]:
    return _PROTECTED_TOKEN.findall(text)
