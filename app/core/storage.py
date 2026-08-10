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
ASSESSMENTS_DIR = "assessments"


def submission_file_path(assessment_id: uuid.UUID, student_id: uuid.UUID) -> str:
    """Return the canonical relative path of a student's submission PDF."""
    return str(PurePosixPath(SUBMISSIONS_DIR, str(assessment_id), f"{student_id}.pdf"))


def question_paper_path(assessment_id: uuid.UUID) -> str:
    """Return the canonical relative path of an assessment's question paper PDF.

    Unlike submissions, there is exactly one per assessment, so the id alone
    determines the path.
    """
    return str(PurePosixPath(ASSESSMENTS_DIR, str(assessment_id), "question-paper.pdf"))


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


def stage(relative_path: str, content: bytes) -> Path:
    """Write ``content`` to a temporary file, not yet visible at ``relative_path``.

    Used when a caller must not publish a file until something else durable —
    typically a database commit — has actually happened: write here first,
    then ``publish`` once that fact holds, or ``discard`` if it does not.

    The temporary file lives next to its eventual final path, on the same
    filesystem, so ``publish`` can move it into place atomically.
    """
    absolute_target = ensure_parent_dir(relative_path)
    handle, scratch = tempfile.mkstemp(dir=absolute_target.parent, suffix=".part")
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
    except BaseException:
        Path(scratch).unlink(missing_ok=True)
        raise
    return Path(scratch)


def publish(staged_path: Path, relative_path: str) -> Path:
    """Atomically move a file staged by ``stage`` into its final location.

    This is the single instant at which the file becomes visible under
    ``relative_path``; nothing reading the storage volume can observe a
    partially written file at that path.
    """
    absolute_target = resolve(relative_path)
    os.replace(staged_path, absolute_target)
    return absolute_target


def discard(staged_path: Path) -> None:
    """Remove a file staged by ``stage`` that will not be published."""
    Path(staged_path).unlink(missing_ok=True)


def write(relative_path: str, content: bytes) -> Path:
    """Store ``content`` at ``relative_path`` immediately, replacing whatever was there.

    A one-shot convenience over ``stage`` + ``publish``, for callers with
    nothing else to make durable first (tests, fixtures, one-off scripts).
    Request handlers that write a file the database is about to reference
    should use ``stage``/``publish`` directly, so the file is only published
    once the transaction referencing it has actually committed.
    """
    return publish(stage(relative_path, content), relative_path)


def delete(relative_path: str) -> None:
    """Remove a stored file, ignoring the case where it is already gone."""
    resolve(relative_path).unlink(missing_ok=True)
