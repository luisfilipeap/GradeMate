# TASK-012 — Extract the questions from the question paper, for the teacher to review

Status: READY

## Objective

Uploading a question paper proposes a list of questions — number and statement — which the
teacher reviews, edits and confirms before it becomes the assessment's question list.

## Context

TASK-011 gives questions a place to live; this task fills it without retyping the exam.

The pipeline is the one already proven for submissions: rasterise the paper, send the pages to
the OCR service, and get back labelled blocks. What OCR cannot do is tell a *question* from a
paragraph — the blocks come back as `text`, `inline_formula`, `table`, in reading order, with no
notion that block 4 begins question 2. Turning blocks into numbered questions with statements is
the LLM's job (TASK-010).

The review step is not a nicety. The model is a local Qwen3, smaller and less accurate than a
frontier model, and a mis-segmented statement propagates: it becomes the context every student's
answer is corrected against in TASK-013, and the label on the tab in TASK-014. Wrong here is
wrong everywhere, silently. The teacher confirms before it lands.

## Relevant Code

- `app/api/routes/review.py` — `run_ocr`: rasterise, call the OCR service, replace the previous reading
- `app/services/ocr_client.py` — the recognised-region shape (`text`, `box`, `label`)
- `app/core/pdf.py` — `render_pages` and the DPI setting
- The LLM client added by TASK-010
- The questions model and endpoints added by TASK-011

## Requirements

- An endpoint that reads the stored question paper and returns a **proposed** list of questions,
  each with its number and statement, in document order.
- The proposal is not persisted by that call. The teacher confirms — as a whole or after
  editing — and only then are the questions written.
- The extraction is repeatable: running it again on the same paper proposes afresh without
  destroying questions the teacher has already confirmed and edited, unless they ask for that.
- The prompt gives the model the recognised blocks with their labels and reading order, and asks
  for a structured result. Use the schema-constrained output path verified in TASK-010 rather
  than parsing prose.
- Mathematics in a statement is preserved as LaTeX, the same convention the OCR service already
  produces.

## Non-Goals

- Do not correct or normalise the student's answers here — that is TASK-013.
- Do not attach regions to questions here.
- Do not auto-confirm the proposal, even when it looks unambiguous.

## Architectural Constraints

- The LLM is reached over HTTP through the client from TASK-010. No inference code in the backend.
- The paper's pages go to the OCR service through its existing HTTP contract; do not add a second
  rasterisation path.
- Proposing and confirming are separate operations. A single call that extracts and writes would
  make the review step impossible to enforce.

## Expected Interfaces

The proposal response must carry enough for the teacher to judge each item: the number, the
statement, and where on the paper it came from, so a suspicious entry can be checked against the
page. Confirmation reuses the question endpoints from TASK-011 rather than inventing a parallel
write path.

## Failure Behavior

- OCR or LLM unreachable, or past its timeout: a controlled error naming which service failed, not
  a 500. The teacher must be able to fall back to typing the questions by hand.
- A response that does not satisfy the schema is a failure of the extraction, not a crash: report
  it as such and leave the assessment untouched.
- A paper the model reads badly — duplicate numbers, empty statements, a single question
  swallowing the whole paper — must still return, so the teacher sees and fixes it. Do not
  silently drop malformed items; surface them.

## Acceptance Criteria

- Uploading a real multi-question paper produces a proposal whose numbers and statements a
  teacher recognises as the exam's questions.
- The proposal alone writes nothing to the database; confirming writes exactly the reviewed list.
- Editing a statement before confirming stores the edited text.
- With the LLM service stopped, the endpoint returns a controlled error and the assessment is
  unchanged.

## Tests Expected

- A stubbed LLM returning a well-formed proposal, an ill-formed one, and an error.
- Proposal followed by confirmation writes the expected rows; proposal without confirmation
  writes none.
- Duplicate numbers in a proposal surface to the caller rather than raising a constraint error.

## Out of Scope

The correction of student answers, the region-to-question assignment, and any change to the
review screen.
