"""Puts the OCR service's own directory on sys.path.

``services/ocr/app.py`` is a standalone module (its own deployable service,
with its own dependency set), not part of the ``app`` package tested by the
top-level ``tests/`` suite. These tests run separately:

    .venv/bin/pytest services/ocr/tests
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
