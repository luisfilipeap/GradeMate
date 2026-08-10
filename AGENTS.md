## Verification

Use the custom verifier agent defined in `.codex/agents/verifier.toml` for
independent code review.

For a completed task implementation review, invoke the repository skill as
`$review-task TASK-NNN <agent_id>`. The skill must resolve exactly one custom
agent by its `name`; if it cannot, no review may run. During that workflow, all
review rules below apply equally to the selected reviewer. The parent does not
perform another technical review.

The verifier's invocation alias is the value of the required `name` field in
`.codex/agents/verifier.toml`. The user may replace that value with any preferred
alias. Always read the current `name` value before invoking the verifier and use
that exact alias; do not assume a hard-coded agent name.

> [!WARNING]
> **A communication language must be explicitly selected before invoking the
> verifier.** Set `COMMUNICATION_LANGUAGE` in
> `.codex/agents/verifier.toml`. The verifier must not infer this setting from
> the language used in a prompt. If the placeholder remains unchanged, the
> verifier must pause before committing or reviewing and ask the user to choose
> a language.

The selected communication language applies to the verifier's chat messages,
status updates, questions, summaries, and the Markdown body of review artifacts
under `.ai/reviews/`. Machine-readable metadata keys and values defined by the
`ai-review/v1` schema remain unchanged.

The repository documentation language is a separate, invariant policy: all
in-repository documentation must always be written in English, regardless of
the selected communication language. This includes `README*`, `docs/`, ADRs,
task specifications, contributor guides, code comments, docstrings, and
configuration documentation. Preserve source-language text only when quoting
existing material as evidence. Review artifacts under `.ai/reviews/` are
communication records and therefore use the selected communication language in
their Markdown body.

The verifier must be used for:

- baseline repository audits;
- regression analysis;
- architectural compliance review.

The verifier must read:

`docs/architecture/PRINCIPLES.md`

before performing architectural review.

The verifier does not implement fixes, create recommendations, or instruct the
Programmer. Findings state evidence and impact without prescribing a solution.

Before starting a review, the verifier must ensure that the exact code to be
reviewed is committed. If the worktree contains pending changes, the verifier
must create a snapshot commit containing the version presented for review. If
the worktree is already clean, the current `HEAD` is the snapshot; do not create
an empty commit. The verifier must not review uncommitted code.

After the snapshot is committed, the verifier must resolve the full commit hash
with `git rev-parse HEAD` and use that exact revision as the review baseline.

The review configuration (`AGENTS.md`, `.agents/skills/review-task/SKILL.md`,
`.codex/config.toml`, and the selected project agent's TOML) must also be
tracked and committed. Resolve the full configuration commit with the actual
selected-agent path:

`git log -1 --format=%H -- AGENTS.md .agents/skills/review-task/SKILL.md .codex/config.toml <selected-agent-toml>`

If either commit hash cannot be resolved, the review must stop as `BLOCKED`.

Verifier findings must be persisted under:

`.ai/reviews/`

Task review filenames must follow this exact format:

`.ai/reviews/REVIEW-NNN-NN.md`

`NNN` is the three-digit numeric part of the task identifier, and `NN` is the
two-digit review sequence for that task. For example, the verifier's first
pronouncement on `TASK-023` is `.ai/reviews/REVIEW-023-01.md`.

The review sequence records how many times the verifier has pronounced on a
task after the programmer presented a changed implementation. Start at `01`.
After the implementation changes and the verifier reviews the task again,
increment the sequence to `02`, then `03`, and so on. Never overwrite or rename
an earlier review to reuse its sequence number. If the implementation has not
changed since the latest `reviewed_commit`, do not create another review file;
report that the latest review remains current.

Every task review must begin at the first byte of the file with valid YAML front
matter conforming to `ai-review/v1` and using this exact structure:

```yaml
---
schema: ai-review/v1
id: REVIEW-TASK-023-001
task_id: TASK-023
iteration: 1
actor:
  role: verifier
  agent: verifier
  runtime: codex
  model: gpt-5.6
  config_commit: "<full Git commit hash>"
created_at: 2026-08-10T11:17:00Z
reviewed_commit: "<full Git commit hash>"
verdict: CHANGES_REQUIRED
findings:
  critical: 0
  high: 1
  medium: 2
  low: 0
supersedes: null
---
```

Metadata rules:

- `schema` must be exactly `ai-review/v1`.
- `id` must be `REVIEW-<task_id>-<iteration padded to three digits>`.
- `task_id` must exactly match the reviewed task filename identifier.
- `iteration` starts at `1`, equals the integer represented by the filename's
  `NN` segment, and increments after each changed implementation is reviewed.
- `actor.role` is always `verifier`; `actor.agent` is the current custom-agent
  alias from `.codex/agents/verifier.toml`; `actor.runtime` is `codex`;
  `actor.model` is the effective model used for the review.
- `actor.config_commit` must be the full configuration commit resolved above.
- `created_at` must be the review creation time in UTC, formatted as
  `YYYY-MM-DDTHH:MM:SSZ`.
- `reviewed_commit` must be the full snapshot hash captured before inspection.
- `verdict` must be exactly one of `APPROVED`, `APPROVED_WITH_FINDINGS`,
  `CHANGES_REQUIRED`, or `BLOCKED`.
- `findings` values must be non-negative integers equal to the findings actually
  documented in the review body for each severity.
- `supersedes` is `null` on iteration 1; later iterations must contain the
  immediately preceding review `id`.

Do not rename, omit, or add metadata keys without introducing a new schema
version. Markdown review content must begin only after the closing `---`.

Organize all documented findings in one alphabetical sequence across the whole
review body: `A`, `B`, `C`, and so on. Do not restart the sequence in a new
category. Each finding heading must begin with its letter, for example
`### A — Missing cleanup`, and its `ID` must be
`REVIEW-NNN-NN-A`, using the filename's task and review numbers. Findings
counts in the YAML front matter count these lettered items.

After validating the artifact, the verifier must stage and commit only the new
review file in a separate commit. The front-matter `reviewed_commit` remains the
pre-review code snapshot, never the later review-artifact commit. If any
unexpected non-review change appears during verification, stop as `BLOCKED`
instead of including it in the review commit.
