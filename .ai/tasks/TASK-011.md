# TASK-011 — Store an assessment's question paper and the questions it contains

Status: READY

## Objective

An assessment can hold the PDF of the blank question paper, and the questions that paper
contains — each with its number and statement — as first-class rows the rest of the feature
can reference.

## Objective is not the upload flow alone

The questions are the point. The paper is how they get there.

## Context

Today an assessment has a title, a date and a maximum score, and the only PDFs GradeMate
stores are the students' answered exams (`submissions`). There is nowhere to record what the
exam actually *asked*.

Two later tasks need that: the correction step sends each question's statement to the LLM as
the context for fixing a student's answer (TASK-013), and the review screen groups regions by
question instead of by page (TASK-014). Both are blocked on questions existing.

Note the asymmetry with `submissions`: a submission belongs to a *student and* an assessment,
while the question paper belongs to the assessment alone — there is exactly one per assessment.

## Relevant Code

- `app/models/assessment.py` — where the relationship to questions belongs
- `app/models/submission.py` — the closest existing precedent for a stored PDF with metadata
- `app/core/storage.py` — `submission_file_path`, `write`, `resolve`; the paper needs its own path helper
- `app/api/routes/submissions.py` — the upload, validation and download pattern to follow
- `app/core/pdf.py` — `looks_like_pdf`, `count_pages`, `render_pages`
- `migrations/versions/` — the numbering and naming convention, and the composite-key precedent in `0002`

## Requirements

- A migration adding storage for the question paper and a `questions` table.
- A question carries at least its number, its statement, and its order within the assessment.
  Numbers are the teacher's, not ours: they may be `1`, `1a`, `2.1`. Do not assume integers.
- Question numbers are unique within an assessment.
- Deleting an assessment deletes its questions and removes the stored paper from the volume,
  consistent with what TASK-003 requires for the other artifacts.
- Endpoints to upload and replace the question paper, to read it back, and full CRUD on the
  questions themselves — the teacher must be able to fix a statement by hand at any point.
- The upload reuses the existing PDF validation: header check, size limit, and a page count that
  proves the document parses.

## Non-Goals

- Do not run OCR or the LLM here. This task stores what it is given; TASK-012 fills it
  automatically.
- Do not link questions to OCR regions yet — that is TASK-013.
- Do not build the interface for managing questions beyond what the API needs.

## Architectural Constraints

- The paper is stored on the volume like every other file, with the database holding a path
  relative to `STORAGE_ROOT`. Never an absolute path, never the bytes.
- The API must not expose the stored path, only a download endpoint, as `submissions` already does.
- A question belongs to exactly one assessment, enforced by the schema.

## Expected Interfaces

Follow the shapes already established: `PUT` to upload-or-replace, `GET .../file` to read the PDF
back inline, `POST`/`PATCH`/`DELETE` for the questions. Read models must not leak storage paths.

## Failure Behavior

- Replacing the paper must not silently orphan the questions extracted from the previous one:
  decide and document whether they are cleared or kept, and make the API say which.
- A corrupt or unparseable PDF is refused before anything is written, as in TASK-004.
- A duplicate question number returns a 409 with a message the interface can show, using the
  existing constraint-to-message mechanism.

## Acceptance Criteria

- An assessment can receive a question paper, serve it back as `application/pdf`, and have it
  replaced.
- Questions can be created, listed in order, edited and deleted through the API.
- Two questions with the same number in one assessment are rejected with 409.
- Deleting the assessment leaves no question rows and no file on the volume.
- `alembic upgrade head` from `base`, and the downgrade, both run clean.

## Tests Expected

- The migration chain in both directions.
- Upload, replace and download of the paper.
- The uniqueness constraint on question numbers within an assessment, and the absence of a
  constraint across different assessments.
- Cascade cleanup of rows and files when the assessment is deleted.

## Out of Scope

Automatic extraction, the correction flow, and the review screen.
