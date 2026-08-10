# TASK-004 — Reject unparseable PDFs on upload and handle render failures

Status: READY

Origin: review finding TNY-2026-08-09-010

## Objective

A PDF the product cannot read is refused at upload, and a rendering failure later returns a
controlled response instead of a 500.

## Context

Upload validation only checks that the file starts with `%PDF-`. `pdf.count_pages` already
notices a broken document and returns `None`, and the upload commits anyway.

The failure surfaces much later: `pdf.render_pages` raises inside `run_ocr`
(`app/api/routes/review.py:49`), which has no error handling, so the teacher gets a 500 for a
file the product told them was accepted — with an unusable artifact left on the volume.

## Relevant Code

- `app/core/pdf.py` — `looks_like_pdf`, `count_pages`, `render_pages`
- `app/api/routes/submissions.py` — `_validate` and `upload_submission`
- `app/api/routes/review.py` — `run_ocr`, line 49

## Requirements

- A PDF whose page count cannot be read is invalid: refuse it before anything is written to
  storage or to the database.
- `render_pages` failures inside `run_ocr` become a controlled 4xx carrying a message the
  interface can display.

## Non-Goals

- Do not attempt to repair damaged PDFs.
- Do not change the accepted file types.

## Architectural Constraints

Validation happens before persistence, so a rejected upload leaves no trace. The check belongs
in the backend, not the browser — the API must be safe when called directly.

## Expected Interfaces

The refusal reuses the existing error-message mechanism, so the interface shows it with no
special handling.

## Failure Behavior

Refusal must state that the file could not be read as a PDF, distinctly from the existing
"only PDF files are accepted" and size-limit messages — the teacher needs to know whether to
re-scan or to send a different file.

## Acceptance Criteria

- Uploading a file that starts with `%PDF-` but is otherwise corrupt returns a 4xx, creates no
  row, and leaves no file on the volume.
- Running the OCR on a submission whose file cannot be rendered returns a controlled response,
  not a 500.

## Tests Expected

Both paths, using a deliberately truncated PDF.

## Out of Scope

Size and page-count ceilings (TASK-008).
