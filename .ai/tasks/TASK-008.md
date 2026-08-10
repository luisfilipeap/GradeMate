# TASK-008 — Enforce resource limits on upload, rasterisation and OCR

Status: READY

Origin: review finding TNY-2026-08-09-006

## Objective

No single upload or OCR run can exhaust memory, disk or the GPU, and the limits are enforced
before the damage rather than after.

## Context

Three gaps compound:

- the upload reads the whole body into memory and *then* checks `MAX_UPLOAD_MB`, so the limit
  does not protect the process it was meant to protect;
- an OCR run rasterises every page at once and holds all the PNGs in memory, and
  `OCR_TIMEOUT_SECONDS` applies per page rather than to the job, so a long document has no
  effective ceiling;
- the OCR service accepts any image size and any number of concurrent requests against a single
  GPU.

A page currently costs about 15 s of GPU time, so the last point is also what stops one teacher
from blocking the machine for a whole class.

## Relevant Code

- `app/api/routes/submissions.py` — `_validate`, and the `file.file.read()` that precedes it
- `app/api/routes/review.py` — `run_ocr`, the per-page loop
- `app/core/pdf.py` — `render_pages`
- `app/core/config.py` — `max_upload_mb`, `ocr_timeout_seconds`, `page_render_dpi`
- `services/ocr/app.py` — the request handler and its engine lock

## Requirements

- An oversized upload is refused before the whole body is buffered.
- A maximum page count and a maximum pixel area per page, refused with a controlled response.
- A job-level timeout for a whole OCR run, distinct from the per-page HTTP timeout.
- Concurrent OCR requests queue rather than competing for GPU memory; a saturated queue answers
  with a documented status rather than failing arbitrarily.

## Non-Goals

- Do not introduce a job queue, worker process or broker. Serialising within the service is
  enough at this scale.
- Do not change the rendering DPI or the OCR engine.

## Architectural Constraints

Limits belong on both sides: the backend protects itself, and the OCR service protects itself,
because it is published on its own port and can be called directly.

## Expected Interfaces

The limits are configuration, not hardcoded numbers, and are documented in the README beside
the existing settings.

## Failure Behavior

Each refusal must be distinguishable: too large, too many pages, too many pixels, timed out,
busy. A teacher who hits one needs to know whether to retry, split the document, or wait.

## Acceptance Criteria

- An oversized upload is refused without the process holding the whole file.
- A document beyond the page or pixel ceiling is refused with a controlled response.
- Two simultaneous OCR requests do not both occupy the GPU.

## Tests Expected

The size check ahead of buffering, the page and pixel ceilings, and the job timeout. The
concurrency limit is verified against the running service.

## Out of Scope

Background processing of a whole class, and the GPU sharing with the LLM (TASK-010).
