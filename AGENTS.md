## Verification

Use the custom verifier agent defined in `.codex/agents/verifier.toml` for
independent code review. The invoking repository skill defines the review
scope; the verifier defines the reviewer's communication, evidence, writing,
and independence rules.

For a completed issue implementation review, invoke the repository skill as
`$review-task <issue-number> <agent_id>`. Work items in this project are
GitHub issues, not local `TASK-NNN` files — there is no `.ai/tasks/`. The
supplied `agent_id` must equal the
current `name` in `.codex/agents/verifier.toml` and resolve to exactly one
custom agent; otherwise no review may run. During that workflow, all review
rules below apply equally to the selected reviewer. The parent does not perform
another technical review.

For a whole-codebase baseline, regression, or architectural compliance audit,
invoke `$codebase-review <agent_id>`. The argument must resolve by an exact
`name` match to one project custom agent whose filename-stem role is allowed to
review by `PERMISSIONS.yml`. Do not use it for a single issue or patch.

The selected codebase reviewer TOML must explicitly define `model` and
`model_reasoning_effort`. Spawn that exact custom agent in a fresh thread with
no model or reasoning override. Its TOML values—not the parent CLI model,
spawn defaults, or inference—must control the review. If the fields or exact
custom-agent resolution are unavailable, the review must stop as `BLOCKED`.
Before spawning, `$codebase-review` must successfully run its bundled
`scripts/resolve_reviewer.py` with the supplied `agent_id` and use that result.

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
under `.ai/reviews/`. Machine-readable metadata keys
and values defined by the `ai-review/v1` schema remain unchanged.

The repository documentation language is a separate, invariant policy: all
in-repository documentation must always be written in English, regardless of
the selected communication language. This includes `README*`, `docs/`, ADRs,
task specifications, contributor guides, code comments, docstrings, and
configuration documentation. Preserve source-language text only when quoting
existing material as evidence. Artifacts under `.ai/reviews/` are communication
records and therefore use the selected communication language in their
Markdown body.

`$codebase-review` owns whole-repository coverage and must require the verifier
to read all of `docs/architecture/PRINCIPLES.md` before inspecting
implementation. `$review-task` owns one completed issue review and limits
architectural assessment to the surfaces affected by that issue.

The verifier does not implement fixes, create recommendations, or instruct the
Programmer. Findings state evidence and impact without prescribing a solution.

Before starting a review, the verifier must ensure that the exact code to be
reviewed is committed. If the worktree contains pending non-review changes, the
verifier must create one snapshot commit containing the version presented for
review. Existing artifacts under `.ai/reviews/` are never part of that snapshot.
If there are no pending non-review changes, the current `HEAD` is the snapshot;
do not create an empty commit. The verifier must not review uncommitted code.

After the snapshot is committed, the verifier must resolve the full commit hash
with `git rev-parse HEAD` and use that exact revision as the review baseline.

The review configuration (`AGENTS.md`, `PERMISSIONS.yml`, the actual invoking
skill's `SKILL.md` and executed scripts, `.codex/config.toml`, and the selected
project agent's TOML) must also be tracked, committed, and clean. Resolve the
full configuration commit with the actual invoking-skill and selected-agent
paths:

`git log -1 --format=%H -- AGENTS.md PERMISSIONS.yml <invoking-skill-files> .codex/config.toml <selected-agent-toml>`

If either commit hash cannot be resolved, the review must stop as `BLOCKED`.

Issue-review findings must be persisted under:

`.ai/reviews/`


The review sequence records how many times the verifier has pronounced on an
issue after the programmer presented a changed implementation. Start at `01`.
After the implementation changes and the verifier reviews the issue again,
increment the sequence to `02`, then `03`, and so on. Never overwrite or rename
an earlier review to reuse its sequence number. If the implementation has not
changed since the latest `reviewed_commit`, do not create another review file;
report that the latest review remains current.

Whole-codebase review results must be persisted using this exact format:

`.ai/reviews/codebase/review-codebase-NNN.md`

`NNN` is the three-digit codebase-review sequence. Start at `001`, create the
directory if absent, preserve every earlier review, and increment only after the
reviewed repository snapshot has changed. If it matches the latest codebase
review's `reviewed_commit`, create no new file and report that the latest review
remains current.

Pull-request review results must be kept below:

`.ai/reviews/PR-<pull-request-number>/review-PR<pull-request-number>-NNN.md`

Use the pull request's actual numeric identifier in both positions. For example,
the first review of PR 23 is `.ai/reviews/PR-23/review-PR23-001.md`. `NNN` is the
three-digit review sequence for that pull request. Do not store codebase, issue,
or unrelated review artifacts in a pull-request directory.

Every review must begin at the first byte of the file with valid YAML front
matter conforming to `ai-review/v1`. An issue review uses this exact structure:

```yaml
---
schema: ai-review/v1
id: REVIEW-023-001
task_id: "023"
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
- For issue reviews, `id` must be
  `REVIEW-<task_id>-<iteration padded to three digits>` and `task_id` must
  exactly match the reviewed GitHub issue's number, zero-padded to at least
  three digits and quoted as a string — this field is still named `task_id`
  for schema-compatibility reasons, but it identifies the reviewed issue,
  never a local task file; this project has no `.ai/tasks/`.
- For codebase reviews, `id` must be
  `REVIEW-CODEBASE-<iteration padded to three digits>` and `task_id` must be
  exactly `CODEBASE`.
- For pull-request reviews, `id` must be
  `REVIEW-PR<pull-request-number>-<iteration padded to three digits>` and
  `task_id` must be exactly `PR-<pull-request-number>`.
- `iteration` starts at `1`. It equals the integer represented by `NN` in an
  issue review filename or by `NNN` in a codebase or pull-request review
  filename, and increments after each changed subject snapshot is reviewed.
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
  immediately preceding review `id` for the same review series.

Do not rename, omit, or add metadata keys without introducing a new schema
version. Markdown review content must begin only after the closing `---`.

Write the Markdown body as a concise human-to-human email from the selected
verifier alias to the project's human Technical Leader. Use this template in
`COMMUNICATION_LANGUAGE`; the field labels shown here are structural examples,
not prescribed translations:

```markdown
# Subject: <review subject and verdict>

To: Technical Leader
From: <selected verifier alias>
Date: <human-readable creation date>
Reviewed commit: <full reviewed_commit>

<greeting to the Technical Leader>,

<concise purpose and overall assessment>

## Findings

### A — <finding title>

ID: <series-specific finding ID>
Severity: <severity>
Confidence: <confidence>
Category: <category>
Affected code: <paths and lines>
Evidence: <evidence>
Impact: <impact>

<concise closing that states the verdict>

<sign-off>,
<selected verifier alias>
```

The sender must be the current `name` from the selected agent TOML, never the
role name unless they are identical. The recipient is always the human
Technical Leader. Keep the email framing outside finding headings; it does not
change metadata, finding counts, evidence requirements, or verdict semantics.

Organize all documented findings in one alphabetical sequence across the whole
review body: `A`, `B`, `C`, and so on. Do not restart the sequence in a new
category. Each finding heading must begin with its letter, for example
`### A — Missing cleanup`. Its `ID` must be `REVIEW-NNN-NN-A` for issue reviews,
`REVIEW-CODEBASE-NNN-A` for codebase reviews, or
`REVIEW-PR<pull-request-number>-NNN-A` for pull-request reviews. Findings
counts in the YAML front matter count these lettered items.

After validating the artifact, leave it uncommitted. Never stage or commit a
review artifact. The front-matter `reviewed_commit` remains the pre-review code
snapshot. If any unexpected non-review change appears during verification,
stop as `BLOCKED`; do not include it in a snapshot or touch it.

## Permissions

`PERMISSIONS.yml`, at the repository root, is the project's role -> capability
policy. It applies to every agent regardless of runtime: a role such as
`verifier` may be implemented as a Codex agent
(`.codex/agents/verifier.toml`) or, for a different role, as a Claude Code
subagent (`.claude/agents/<role>.md`) — the policy is written in terms of
roles only and never mentions which runtime backs one. Any agent, in any
runtime, that is about to perform an action this file gates must read it
first and refuse if its own role is not listed as permitted. Do not
duplicate a rule from this file into a runtime-specific definition; extend
`PERMISSIONS.yml` itself instead, so the two never drift apart.
