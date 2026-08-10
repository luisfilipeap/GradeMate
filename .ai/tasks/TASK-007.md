# TASK-007 — Validate the OCR service response and keep protocol failures out of the API

Status: READY

Origin: review finding TNY-2026-08-09-007

## Objective

A malformed response from the OCR service produces a gateway error, never a 500 from GradeMate.

## Context

`app/services/ocr_client.py` catches transport and status errors, so an unreachable service or
a 500 from it become `OcrServiceError` and then a 502. A malformed *body* does not: the client
indexes a raw `dict[str, Any]`, so non-JSON, a missing `blocks` or `content` key, or a box that
is not a pair of numbers raises straight through the adapter.

The OCR service defines Pydantic models for its response and the consumer trusts them by
convention rather than checking. The contract is real but unenforced, so the day the service
changes shape, GradeMate reports its own failure instead of the upstream one.

## Relevant Code

- `app/services/ocr_client.py` — `_post`, `_regions`, `recognise_image`
- `services/ocr/app.py` — `OcrResponse`, `Page`, `Block`, the producer's models
- `app/api/routes/review.py` — where `OcrServiceError` becomes a 502

## Requirements

- Transport models local to the adapter, parsed from the response rather than indexed.
- JSON, schema and type failures converted into `OcrServiceError`.
- The error message useful for diagnosis without echoing the raw upstream payload.

## Non-Goals

- Do not share model definitions between the two services; the duplication is the point of the
  boundary.
- Do not add API versioning to the OCR service.

## Architectural Constraints

The two services are separate. The consumer validates what it receives at the boundary and does
not import the producer's code — a shared model would couple deployments that are deliberately
independent.

## Expected Interfaces

`recognise_image` keeps its signature and its rescaling behaviour. Only the parsing inside it
changes.

## Failure Behavior

Every protocol-level failure maps to the same error type the transport failures already use, so
callers need no new handling.

## Acceptance Criteria

A stubbed OCR service returning non-JSON, valid JSON with missing keys, or a malformed box makes
`POST /api/submissions/{id}/ocr` answer 502 in each case, never 500.

## Tests Expected

The three malformed responses above, plus a well-formed one still parsing correctly, including
the coordinate rescaling.

## Out of Scope

Timeouts and concurrency limits (TASK-008).
