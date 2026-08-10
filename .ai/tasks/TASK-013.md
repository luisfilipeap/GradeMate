# TASK-013 — Assign recognised regions to questions and repair their LaTeX, never their numbers

Status: READY

## Objective

Opening a student's exam for correction sends the OCR reading to the LLM, which — using the
questions' statements as context — says which question each region answers and returns the
region's text as valid LaTeX. Numbers are guaranteed untouched, by verification in code.

## Context

The OCR output is usable but rough: PaddleOCR-VL produces text like
`$ W^{(3)} \sim 9 $ parâmetros (total) \rightarrow 21` — mostly right, with malformed delimiters,
broken environments and inconsistent spacing. Fixing that by hand, region by region, is the
tedium this feature removes.

The boundary the owner drew is sharp and load-bearing: **the LLM fixes format, never content.**
If a student wrote `2 + 2 = 5`, that stays `2 + 2 = 5` — a model that "helps" by correcting the
arithmetic destroys the evidence the teacher is grading. The teacher fixes wrong numbers, not
the machine.

A prompt instruction is not enough for a guarantee of that weight, especially from a local
Qwen3. Enforce it: extract every numeric literal from the original and from the returned text,
compare them, and reject the correction when they differ, keeping the OCR reading and flagging
the region for the teacher. That turns "please don't" into an invariant the test suite can hold.

## Relevant Code

- `app/models/ocr_line.py` — `text`, `corrected_text`, `accepted`, `label`, `box`
- `app/api/routes/review.py` — `run_ocr` and `update_line`, the existing correction path
- `app/schemas/review.py` — the review payload the interface consumes
- The LLM client from TASK-010; the questions from TASK-011 and TASK-012

## Requirements

- Each recognised region can carry the question it belongs to; a region that answers no question
  (a header, the student's name, a stray mark) must be representable as such rather than forced
  into one.
- An endpoint that runs the assignment-and-repair pass over a submission's regions and stores the
  result. Like the OCR pass, it is explicit — the teacher triggers it.
- The model receives the questions' statements as context, the regions in reading order with their
  labels, and returns, per region, the question and the repaired text, through the
  schema-constrained path from TASK-010.
- **The numeric guard is mandatory.** Compare the numeric literals of the original and the
  proposed text. On any difference, discard the proposal for that region, keep the OCR text, and
  record that it was rejected so the interface can show it.
- The repair never overwrites `text`. It is a proposal, stored where a teacher's own edit would
  go, and the teacher keeps the last word — the existing accept/rewrite flow still applies.
- Re-running the pass must be safe: it must not silently discard regions the teacher has already
  accepted or rewritten.

## Non-Goals

- Do not grade, score, or judge whether an answer is correct. Nothing in this task assigns marks.
- Do not touch the student's mathematics, spelling, or wording beyond making the LaTeX valid.
- Do not change how regions are detected — the OCR pass stays as it is.

## Architectural Constraints

- Exam content stays on the machine; the model is the local one from TASK-010.
- The original OCR reading is never destroyed. `ocr_lines.text` is the record of what the student
  wrote as read; every layer above it is an overlay.
- The numeric guard belongs in the backend, not in the prompt and not in the interface. A future
  caller that bypasses the interface must still be unable to alter a number.

## Expected Interfaces

The review payload must let the interface show, per region: the question it was assigned to, the
proposed LaTeX, and whether a proposal was rejected by the guard. A rejected region is not an
error state — it is a normal outcome meaning "the teacher should look at this one".

## Failure Behavior

- LLM unreachable or past timeout: controlled error, no partial write. The submission keeps its
  OCR reading and stays correctable by hand.
- A malformed or schema-violating response fails the pass without corrupting stored regions.
- A region the model assigns to a question that does not exist is treated as unassigned, not as a
  reason to fail the whole pass.
- A response that drops or duplicates regions must not silently reorder or lose data — match
  proposals to regions by identity, not by position in a list.

## Acceptance Criteria

- On the real 4-page handwritten exam, running the pass assigns regions to questions and
  produces LaTeX that renders, with the teacher's accept/rewrite flow still working.
- A model response that alters any number is rejected: the stored text is the original OCR
  reading, and the region is marked as such. This holds even when the change would be
  arithmetically correct.
- Running the pass twice does not destroy accepted or rewritten regions.
- With the LLM stopped, the endpoint fails cleanly and the submission is unchanged.

## Tests Expected

- The numeric guard, as the centrepiece: proposals that keep every number pass; proposals that
  change, add or drop one are rejected. Include a case where the model "fixes" `2 + 2 = 5`.
- Formatting-only repairs are accepted and stored as proposals, not as `text`.
- A region assigned to an unknown question ends up unassigned.
- Unreachable service, timeout, and malformed response each leave stored regions untouched.

## Out of Scope

Scoring, the question-tab navigation (TASK-014), and any change to OCR detection.
