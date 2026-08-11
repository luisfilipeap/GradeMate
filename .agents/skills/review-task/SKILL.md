---
name: review-task
description: Review completed TASK-NNN with the configured verifier. Use for explicit `$review-task` calls with task ID and agent alias; never for codebase audits.
---

# Review Task

Invocation: `$review-task <task_id> <agent_id>`

## Guard

- Require two arguments, `task_id` matching `TASK-NNN`, and `.ai/tasks/<task_id>.md`.
- Require verifier review permission. Read its TOML; require `agent_id` to equal the current `name` and resolve to exactly one custom agent.
- Abort before writes or implementation reads if a check, spawn, or required language fails. Never fall back, impersonate, or let the parent review.

## Delegate

Spawn `agent_id` in a fresh thread. Require it to:

- follow `AGENTS.md`, this skill, `PERMISSIONS.yml`, and its TOML;
- snapshot the presented non-review worktree or use clean `HEAD`; capture `reviewed_commit` and `config_commit` hashes before inspection;
- read the task and `docs/architecture/PRINCIPLES.md`; assess its implementation, tests, regressions, and affected architecture surfaces;
- compare with the latest task review, excluding `.ai/reviews/`, and create no artifact when unchanged;
- preserve earlier reviews, write the next `.ai/reviews/REVIEW-NNN-NN.md` as the human email required by `AGENTS.md`, and leave it uncommitted;
- make no production changes, tasks, recommendations, or instructions to the Programmer.

Wait; perform no second review.

Report only: task, reviewer, reviewed commit, review file, and total findings.
