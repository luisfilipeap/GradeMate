# TASK-014 — Navigate the correction screen by question instead of by page

Status: READY

## Objective

The correction screen is organised around questions. The `Page 1 / Page 2 / Page 3` tabs become
`Question 1 / Question 2 / …`, and choosing one shows that question's statement, the regions the
student wrote for it, and the page image with those regions highlighted.

## Context

Pages are an artifact of how the exam was scanned; questions are what the teacher is actually
grading. A teacher marking question 2 for thirty students wants question 2, not page 1 of each
exam — and a single question's answer often spills across a page break, which page tabs split in
exactly the wrong place.

TASK-013 provides the missing link by assigning each region to a question. This task is the
payoff in the interface.

There is a layout problem to solve rather than ignore: today the left pane shows one page image
and the boxes drawn on it, which works because a page *is* the unit. A question's regions can
span two pages, so the pane must handle a selection that is no longer one image. Decide
deliberately — it changes what the teacher sees on a page-crossing answer.

## Relevant Code

- `frontend/src/pages/review-page.tsx` — the page tabs, the region list, the transcript
- `frontend/src/components/page-canvas.tsx` — the image with the box overlay, positioned as
  percentages of the page raster
- `frontend/src/lib/api.ts` — `Review`, `SubmissionPage`, `OcrLine`
- `app/schemas/review.py` — the payload shape to extend

## Requirements

- Navigation is by question, in the order the questions were defined, labelled with the teacher's
  own numbering.
- The selected question shows its statement — the teacher is checking the answer against the
  question, and should not have to remember what was asked.
- Regions that belong to no question remain reachable. The student's name is in one of them; an
  interface that only shows questions hides part of the exam.
- The page image keeps its boxes aligned. The existing percentage-based positioning is what makes
  that work — preserve it rather than recomputing coordinates.
- Progress is expressed per question, so the teacher can see which answers are still unreviewed.
- The transcript keeps building from accepted regions, grouped by question.
- A submission whose regions have not been assigned yet must still be usable: fall back to the
  page view rather than showing an empty screen.

## Non-Goals

- Do not add scoring, marks, or any judgement of the answer.
- Do not change the accept/rewrite interaction itself.
- Do not redesign the screen beyond what question-based navigation requires.

## Architectural Constraints

- The interface renders what the API gives it. Do not infer question membership in the browser by
  parsing text or guessing from box positions.
- The boxes must stay pixel-accurate against the rendered page — that alignment was the point of
  rasterising in the backend, and it must not regress.

## Expected Interfaces

The review payload should let the interface group by question without a second round trip, and
should include the question's statement and number. Regions without a question need an explicit,
unambiguous representation — not a null the interface has to guess about.

## Failure Behavior

- No questions defined for the assessment: fall back to page navigation, with a hint pointing at
  where questions are defined.
- Regions assigned to a question that was later deleted must not break the screen.
- A question with no regions still appears, shown as unanswered — a blank answer is information
  the teacher needs, not a row to hide.

## Acceptance Criteria

- On the real 4-page exam with questions assigned, the tabs read as questions, each showing its
  statement and its regions, with the boxes still landing on the handwriting.
- An answer spanning two pages is fully reachable from its question tab.
- Unassigned regions, including the student's name, are still reachable.
- A submission with no assignment falls back to page navigation instead of breaking.
- No console errors; the build and type-check pass.

## Tests Expected

Exercised in the browser against a real submission: question navigation, a page-crossing answer,
the unassigned regions, a question with no answer, and the fallback when no questions exist.

## Out of Scope

Scoring, cross-student navigation (marking question 2 for the whole class in one screen), and any
change to the OCR or correction pipeline.
