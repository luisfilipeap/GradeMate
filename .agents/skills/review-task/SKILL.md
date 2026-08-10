---
name: review-task
description: Delegate a task review to a named custom Codex agent. Use for `$review-task` with task and agent IDs; abort unless both resolve exactly.
---

# Review Task

Invocation: `$review-task <task_id> <agent_id>`

## Guard

- Require exactly two arguments, `task_id` matching `TASK-NNN`, and `.ai/tasks/<task_id>.md`.
- Resolve `agent_id` by one exact `name` match in a project `.codex/agents/*.toml`; filenames do not identify agents.
- Abort before writes or implementation reads if any check fails, spawning fails, or a required language is unset. Never fall back, impersonate, or let the parent review.

## Delegate

Spawn exactly `agent_id` in a fresh thread. Require the reviewer to:

- follow `AGENTS.md` and its config; keep project documentation English and use its communication language;
- before inspection, commit the non-review worktree or use clean `HEAD` without an empty commit; record full `reviewed_commit` and `config_commit` hashes;
- read the task and `docs/architecture/PRINCIPLES.md`; review code, tests, regressions, and architecture;
- compare implementation with the latest review while excluding `.ai/reviews/`; if unchanged, create no new review;
- preserve prior files and write the next `.ai/reviews/REVIEW-NNN-NN.md` with `ai-review/v1` and global finding letters `A`, `B`, `C` per `AGENTS.md`;
- make no production changes, tasks, recommendations, or instructions to the Programmer;
- when only the new review is pending, commit it alone while keeping `reviewed_commit` equal to the code snapshot.

Wait for completion; perform no second technical review.

Report only: task, reviewer, reviewed commit, review file, and total findings.
