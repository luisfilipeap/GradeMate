#!/usr/bin/env python3
"""Resolve and validate the custom reviewer selected for codebase review."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import NoReturn


def blocked(message: str) -> NoReturn:
    print(f"BLOCKED: {message}", file=sys.stderr)
    raise SystemExit(2)


def find_yaml_block(
    lines: list[str], key: str, start: int, end: int, parent_indent: int
) -> tuple[int, int, int]:
    marker = f"{key}:"
    for index in range(start, end):
        stripped = lines[index].strip()
        indent = len(lines[index]) - len(lines[index].lstrip(" "))
        if stripped != marker or indent <= parent_indent:
            continue

        block_end = index + 1
        while block_end < end:
            candidate = lines[block_end].strip()
            candidate_indent = len(lines[block_end]) - len(
                lines[block_end].lstrip(" ")
            )
            if (
                candidate
                and not candidate.startswith("#")
                and candidate_indent <= indent
            ):
                break
            block_end += 1
        return index + 1, block_end, indent
    blocked(f"PERMISSIONS.yml is missing {key}")


def review_roles(path: Path) -> set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    skills_start, skills_end, skills_indent = find_yaml_block(
        lines, "skills", 0, len(lines), -1
    )
    review_start, review_end, review_indent = find_yaml_block(
        lines, "review", skills_start, skills_end, skills_indent
    )
    roles_start, roles_end, _ = find_yaml_block(
        lines, "allowed_roles", review_start, review_end, review_indent
    )
    roles = {
        line.strip()[2:].strip().strip("\"'")
        for line in lines[roles_start:roles_end]
        if line.strip().startswith("- ")
    }
    if not roles:
        blocked("PERMISSIONS.yml grants no role permission to review")
    return roles


def main() -> None:
    if len(sys.argv) != 2:
        blocked("expected exactly one agent_id argument")
    agent_id = sys.argv[1]

    root = Path.cwd().resolve()
    principles = root / "docs/architecture/PRINCIPLES.md"
    permissions = root / "PERMISSIONS.yml"
    agents_dir = root / ".codex/agents"
    for required in (principles, permissions, agents_dir):
        if not required.exists():
            blocked(f"required path does not exist: {required.relative_to(root)}")

    matches: list[tuple[Path, dict[str, object]]] = []
    for path in sorted(agents_dir.glob("*.toml")):
        try:
            config = tomllib.loads(path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as error:
            blocked(f"cannot parse {path.relative_to(root)}: {error}")
        if config.get("name") == agent_id:
            matches.append((path, config))

    if len(matches) != 1:
        blocked(f"agent_id must match exactly one custom agent; found {len(matches)}")

    agent_path, config = matches[0]
    role = agent_path.stem
    if role not in review_roles(permissions):
        blocked(f"role {role!r} is not allowed to review")

    model = config.get("model")
    effort = config.get("model_reasoning_effort")
    if not isinstance(model, str) or not model.strip():
        blocked("selected agent does not define model")
    if not isinstance(effort, str) or not effort.strip():
        blocked("selected agent does not define model_reasoning_effort")

    instructions = config.get("developer_instructions")
    language_match = re.search(
        r'^\s*COMMUNICATION_LANGUAGE\s*=\s*"([^"]+)"\s*$',
        instructions if isinstance(instructions, str) else "",
        re.MULTILINE,
    )
    language = language_match.group(1).strip() if language_match else ""
    if not language or "SELECT_" in language or "PLACEHOLDER" in language:
        blocked("selected agent has no explicit communication language")

    print(
        json.dumps(
            {
                "agent_id": agent_id,
                "agent_toml": str(agent_path.relative_to(root)),
                "role": role,
                "model": model,
                "model_reasoning_effort": effort,
                "communication_language": language,
                "fork_turns": "none",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
