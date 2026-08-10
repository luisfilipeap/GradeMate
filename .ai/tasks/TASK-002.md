# TASK-002 — Invalidate the derived OCR when a submission's PDF is replaced

Status: READY

Origin: review finding TNY-2026-08-09-002

## Objective

Replacing a student's PDF discards everything derived from the previous one, so the review
screen can never show boxes, text or accepted regions belonging to a document that is gone.

## Context

`upload_submission` overwrites the file and updates its metadata, but leaves `submission_pages`
and `ocr_lines` untouched. The review endpoint returns whatever is stored, and only a fresh OCR
run replaces it.

So a teacher who re-scans a page — the exact situation the replace flow exists for — sees the
old reading over the new document: boxes in the wrong places, and accepted regions transcribing
text the new PDF may not contain. The transcript that results is a record of the wrong exam.
This is the most severe confirmed finding in the audit.

## Relevant Code

- `app/api/routes/submissions.py` — `upload_submission`, and `delete_submission` for the
  cleanup pattern it already implements
- `app/models/submission.py` — the `pages` relationship
- `app/models/submission_page.py`, `app/models/ocr_line.py` — the cascade already declared
- `app/core/storage.py` — `write`, `delete`, `submission_page_image_path`

## Requirements

- Storing a replacement PDF removes the submission's pages, their lines, and the rendered page
  images, atomically with the replacement.
- A missing image file must not fail the upload.

## Non-Goals

- Do not re-run the OCR automatically after a replacement; the teacher triggers it.
- Do not add versioning or history of previous readings.

## Architectural Constraints

The database is the record of what exists; the volume follows it. A row deleted must not leave
its file, and this task must not introduce a second cleanup path — reuse the one
`delete_submission` uses.

## Expected Interfaces

No new endpoint. The existing upload keeps its contract; only its effects change.

## Failure Behavior

If the replacement fails, the previous state must survive intact — a half-replaced submission
with the new file and the old reading is worse than a failed upload.

## Acceptance Criteria

- Uploading a second PDF for a student who already had OCR run and regions accepted leaves zero
  rows in `submission_pages` and `ocr_lines` for that submission, and no PNG under the
  submission's page directory.
- `GET /api/submissions/{id}/review` reports no pages immediately after the replacement.

## Tests Expected

Accept a region, re-upload, and assert rows and files are gone; a missing image file does not
break the upload.

## Out of Scope

Cascade cleanup on student, assessment or class deletion — that is TASK-003.
