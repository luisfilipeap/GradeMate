---
name: codebase-review
description: Audit the repository against docs/architecture/PRINCIPLES.md using a required reviewer agent. Use for `$codebase-review`; never for task or patch reviews.
---

# Codebase Review

Invocation: `$codebase-review <agent_id>`

## Guard

- Require one `agent_id`.
- From the repository root, run `python3 .agents/skills/codebase-review/scripts/resolve_reviewer.py <agent_id>`.
- Treat a nonzero exit, invalid JSON, or returned alias mismatch as `BLOCKED` before review or writes. Never fall back or let the parent review.

## Delegate

Spawn the resolved agent with returned `fork_turns` and no model or reasoning override; its TOML controls both.

Require the reviewer to:

- follow `AGENTS.md`, this skill, `PERMISSIONS.yml`, and its TOML;
- snapshot presented work or use clean `HEAD`; capture full `reviewed_commit` and `config_commit` hashes before inspection;
- read all of `PRINCIPLES.md`; audit the whole repository, not only its latest diff;
- state coverage limits and create no artifact when unchanged;
- preserve reviews, create `.ai/reviews/codebase/` if absent, write its next `review-codebase-NNN.md` as the human email required by `AGENTS.md`, and leave it uncommitted;
- make no production changes, tasks, recommendations, or Programmer instructions.

Wait; perform no second review.

Report only: reviewer, configured model, reviewed commit, review file, verdict, and total findings.
