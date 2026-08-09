"""Helpers to translate between database file references and the storage volume.

The database only ever stores paths relative to ``Settings.storage_root``, so the
same rows keep working when the volume is mounted somewhere else.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from app.core.config import get_settings

SUBMISSIONS_DIR = "submissions"


def submission_file_path(assessment_id: uuid.UUID, student_id: uuid.UUID) -> str:
    """Return the canonical relative path of a student's submission PDF."""
    return str(PurePosixPath(SUBMISSIONS_DIR, str(assessment_id), f"{student_id}.pdf"))


def submission_page_image_path(
    assessment_id: uuid.UUID, student_id: uuid.UUID, page_number: int
) -> str:
    """Return the relative path of a rendered page image of a submission."""
    return str(
        PurePosixPath(
            SUBMISSIONS_DIR, str(assessment_id), f"{student_id}-pages", f"{page_number}.png"
        )
    )


def resolve(relative_path: str) -> Path:
    """Resolve a stored relative path against the storage root.

    Raises:
        ValueError: if the path escapes the storage root.
    """
    root = get_settings().storage_root.resolve()
    absolute = (root / relative_path).resolve()
    if not absolute.is_relative_to(root):
        raise ValueError(f"Path {relative_path!r} escapes the storage root")
    return absolute


def ensure_parent_dir(relative_path: str) -> Path:
    """Create the directory that will hold ``relative_path`` and return its absolute path."""
    absolute = resolve(relative_path)
    absolute.parent.mkdir(parents=True, exist_ok=True)
    return absolute


def write(relative_path: str, content: bytes) -> Path:
    """Store ``content`` at ``relative_path``, replacing whatever was there.

    The bytes land in a temporary file first and are then moved into place, so a
    failed upload can never leave a half-written PDF behind.
    """
    absolute = ensure_parent_dir(relative_path)
    handle, scratch = tempfile.mkstemp(dir=absolute.parent, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
        os.replace(scratch, absolute)
    except BaseException:
        Path(scratch).unlink(missing_ok=True)
        raise
    return absolute


def delete(relative_path: str) -> None:
    """Remove a stored file, ignoring the case where it is already gone."""
    resolve(relative_path).unlink(missing_ok=True)
