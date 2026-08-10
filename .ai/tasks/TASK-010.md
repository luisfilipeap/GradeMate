# TASK-010 — Serve a local LLM with Ollama and make it share the GPU with the OCR service

Status: READY

## Objective

A local LLM is reachable from the backend at a documented HTTP contract, running on the
same GPU as the OCR service without either starving the other. No exam content leaves the
machine.

## Context

GradeMate is about to use an LLM for two jobs: extracting questions from a question paper
(TASK-012) and correcting the LaTeX of recognised regions (TASK-013). The owner chose a
**local** model over a hosted API, because the transcripts contain students' handwriting
and names, and chose a **ready-made image from Docker Hub** rather than a service we build.

There is a hard constraint the design must solve. The machine has a single 12 GB card, and
the OCR container currently holds **11.1 GB of it**:

```
$ nvidia-smi --query-gpu=memory.total,memory.free --format=csv,noheader
12288 MiB, 219 MiB
```

### Correction (measured on the machine, 2026-08-09) — capping the pool does not work

The paragraph above assumed that PaddlePaddle's 11.1 GB was mostly idle reservation, and that
capping its allocator pool would let it coexist with the LLM. **That assumption is wrong,** and
this correction exists so the next reader does not repeat it. Measured with an RTX 3060
(12288 MiB total):

| OCR service configuration | VRAM held | Result |
| --- | --- | --- |
| As it ships today (no flags) | 11098 MiB | Works. Almost all of it is allocator cache, not real need. |
| `FLAGS_fraction_of_gpu_memory_to_use=0.40` | ~8600 MiB | Works, but the flag does not actually cap anything real — see below. |
| `FLAGS_allocator_strategy=auto_growth` + `FLAGS_gpu_memory_limit_mb=5000` | ~5000 MiB | **Breaks.** `Out of memory` / `ResourceExhausted` inside PaddleOCR-VL on the first page, surfaced to the caller as an HTTP 500. |
| OCR service stopped | 521 MiB used, **11383 MiB free** | — |

PaddleOCR-VL genuinely needs more than 5 GB to run inference — the model does not fit in a
capped 5 GB pool, it does not give back what it caches once it has more room, and there is no
middle ground where both the resident OCR engine and a useful Qwen3 model fit at once: with the
OCR engine resident, only ~3.4 GB remains, which is not enough even for Qwen3-8B.

The consequence: alternation cannot happen at the allocator level. It has to happen at the
**container** level — one of the two services stopped, not just idle, while the other runs. With
the OCR container stopped, 11.4 GB is free, which is why the owner can afford Qwen3-14B rather
than a smaller model.

The owner chose to **alternate**: one model resident at a time, so the LLM can be the larger
Qwen3-14B. Ollama does its half of that natively (it unloads the *model* after an idle period,
which is enough — the idle `ollama/ollama` server itself holds no GPU memory once nothing is
loaded). **PaddleOCR does not release anything by going idle; the container itself has to stop**
for the memory to come back. Whether that stop/start is automated or left as a manual step for
the teacher is this task's judgment call — see Requirements.

## Relevant Code

- `docker-compose.yml` — the `ocr` service, its GPU reservation and `grademate_ocr_models` volume
- `services/ocr/app.py` — lazy engine loading (`get_engine`), `OCR_DEVICE`, `OCR_PRELOAD`
- `app/core/config.py` — where `ocr_service_url` and its timeout live; the LLM settings belong beside them
- `app/services/ocr_client.py` — the shape a service client takes in this project
- `README.md` — the OCR service section and the process-lifetime table

## Requirements

- An `llm` service in `docker-compose.yml`, built from the official `ollama/ollama` image, with
  a named volume for model weights so they survive `docker compose down`.
- The service serves a Qwen3 model chosen to fit the alternating budget; the model name is
  configurable, not hardcoded in application code.
- The model unloads after a documented idle period so the GPU returns to the OCR service.
- The OCR service gives its GPU memory back when it is not needed. Measured (see the correction
  above): capping PaddlePaddle's allocator pool is not viable — the engine needs more than the
  budget that would leave room for the LLM, and it does not release what it caches anyway. The
  memory can only be reclaimed by stopping the `ocr` container. Whether that stop/start is
  automated or documented as a manual operational step is this task's judgment call; either way
  it must be explained in the README, because it is not obvious from the code.
- Backend settings for the LLM base URL, model name and timeout, alongside the OCR ones.
- The README documents the VRAM budget: what each model needs, what the alternation costs in
  latency, and how to move to a smaller model on a smaller card.

## Non-Goals

- Do not call the LLM from any endpoint yet — TASK-012 and TASK-013 own that.
- Do not design the prompts here.
- Do not add a queue or worker.

## Architectural Constraints

- The LLM is a service boundary reached over HTTP, exactly like the OCR service. The backend
  must not import or embed inference code.
- Nothing in this feature may send exam content off the machine. That is the reason the
  local model was chosen; a hosted fallback would defeat it.
- The service must be optional to *start*: a developer without an NVIDIA card must still be able
  to run the rest of GradeMate, as documented for the OCR service.

## Expected Interfaces

Ollama exposes an OpenAI-compatible API. The backend needs, at minimum, chat completion with a
JSON schema constraining the response — later tasks depend on structured output, so verify that
path works against the chosen model before closing this task.

## Failure Behavior

- The LLM service unreachable, or slow past the timeout, must be a distinct, catchable error in
  the backend client — never an unhandled exception. The mapping to an HTTP status belongs to the
  tasks that call it.
- A model that does not fit in the available VRAM must fail loudly at startup, with the
  measured numbers in the log, rather than falling back to CPU and appearing merely slow.

## Acceptance Criteria

- `docker compose up -d` starts `db`, `ocr` and `llm` (`adminer` stays opt-in, as today); the LLM
  answers a trivial prompt through its HTTP API.
- A request with a JSON schema returns a response that validates against that schema.
- Running an OCR pass, switching the GPU over (per whatever mechanism this task chose), and then
  an LLM call, works repeatedly with no out-of-memory error from either side, and `nvidia-smi`
  shows the memory changing hands between the two. Both cannot be expected to answer at the same
  moment — see the correction above.
- The README states the measured VRAM figures, the alternation latency, and the
  smaller-card path.

## Tests Expected

- The backend client turns an unreachable service and a timeout into its own error type.
- The client parses a well-formed structured response, and rejects a malformed one without
  raising a bare `KeyError` or `JSONDecodeError`.

## Out of Scope

Prompt design, question extraction, LaTeX correction, and any interface change.
