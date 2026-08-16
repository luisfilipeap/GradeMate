# Claude Code Agent Governance for GradeMate

This document establishes rules for all AI agents working on GradeMate.

## Critical Rule: Never Commit MyDevOffice Governance Artifacts

**EVERY AGENT MUST READ THIS.**

The following files and directories are part of the **MyDevOffice agent governance framework** and exist ONLY for local agent-to-agent communication and skill execution. They must **NEVER** be committed to the remote repository:

### 🚫 DO NOT COMMIT

```
.claude/agents/               # Agent role definitions (architect, programmer, verifier)
.codex/agents/                # Codex agent definitions
.codex/config.toml            # Local configuration (MyDevOffice path, settings)
AGENTS.md                      # Agent registry
PERMISSIONS.yml               # Role permission policies
docs/architecture/decisions/  # Architecture decision records (local planning)
```

**Why?** These files are specific to this local working environment and the MyDevOffice framework. They are NOT part of GradeMate's production codebase. Publishing them creates:
- Framework version mismatch (MyDevOffice updates won't reflect in the repo)
- Confusion about what's "project policy" vs "agent governance"
- Risk of config leakage (API keys, paths, service URLs)

### ✅ DO PRESERVE LOCALLY (but DO NOT COMMIT)

The following files enable agent-to-agent communication and must **NEVER be deleted**, but also must **NEVER be committed**:

```
.ai/recommendations/          # Agent recommendations (REC-NNN.md) — LOCAL ONLY
.ai/reviews/                  # Code review findings — LOCAL ONLY
.ai/                          # All agent communication artifacts
```

**Why?** These files are how agents coordinate with each other and record decisions. Deleting them breaks agent-to-agent workflows. Committing them adds noise to the repository history.

---

## For Each Agent Type

### Architect (Yann)

- ✅ **DO:** Create recommendations in `.ai/recommendations/REC-NNN.md`
- ✅ **DO:** Read reviews from `.ai/reviews/`
- ✅ **DO:** Create GitHub issues (they WILL be committed)
- ❌ **DO NOT:** Commit recommendations or reviews
- ❌ **DO NOT:** Modify `.codex/config.toml`
- ❌ **DO NOT:** Delete `.ai/` artifacts

### Programmer (Geoffrey)

- ✅ **DO:** Read issues from GitHub (they're already committed)
- ✅ **DO:** Implement code, tests, documentation
- ✅ **DO:** Commit your work to feature branches
- ✅ **DO:** Create pull requests via the MyDevOffice wrapper
- ❌ **DO NOT:** Commit agent governance files (`.claude/agents/`, `PERMISSIONS.yml`, etc.)
- ❌ **DO NOT:** Delete `.ai/recommendations/` or `.ai/reviews/` (other agents use them)

### Verifier (Joshua)

- ✅ **DO:** Create reviews in `.ai/reviews/`
- ✅ **DO:** Analyze code and document findings
- ❌ **DO NOT:** Commit reviews to git
- ❌ **DO NOT:** Delete `.ai/recommendations/` (architect uses them)

---

## Git Rules

### What Gets Committed

- ✅ Application code (`app/`, `services/`, `frontend/`)
- ✅ Tests (`tests/`)
- ✅ Documentation (`README.md`, `docs/architecture/PRINCIPLES.md`)
- ✅ Configuration tracked by design (`.env.example`, `docker-compose.yml`)
- ✅ GitHub issues and pull requests (via GitHub API, not git)

### What NEVER Gets Committed

- ❌ Agent definitions or skill implementations (local MyDevOffice copies)
- ❌ Agent recommendations (`.ai/recommendations/`) — local communication
- ❌ Code reviews (`.ai/reviews/`) — local analysis records
- ❌ Local configuration (`.codex/config.toml`, `.env`)
- ❌ Architecture decisions directory (`docs/architecture/decisions/`) — local planning

---

## If You See Committed Governance Files in the Remote

If AGENTS.md, PERMISSIONS.yml, .claude/agents/, or .codex/agents/ appear in a pull request:

1. **Do NOT merge it**
2. **Inform the user:** These are MyDevOffice framework files and should not be in the production repository
3. **Ask the author** to:
   - Add the files to `.gitignore` (if not already done)
   - Remove them from the commit
   - Re-push

---

## Local Artifact Persistence

**Never delete these, even if they seem "old":**

- `.ai/recommendations/REC-NNN.md` — Used by `/approve-rec` skill
- `.ai/reviews/` — Used by Architect to evaluate findings
- `.ai/` directory and contents — Enables all agent-to-agent workflows

**If you need to clean up:** Move them to an archive, don't delete them.

---

## Questions?

- Ask the Technical Leader (Luis)
- Check this file before committing
- When in doubt: **Does this enable agent communication or governance? → Don't commit it**
