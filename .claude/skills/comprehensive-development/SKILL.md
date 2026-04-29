---
name: comprehensive-development
description: Use when a repo-wide task spans code, docs, tools, workflows, and runtime surfaces and needs explicit subagent routing.
---
<!--
@dependency-start
responsibility Documents Comprehensive Development for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
@dependency-end
-->


# Comprehensive Development

1. Read `agents/skills/comprehensive-development.md`.
1. Set `workflow=Comprehensive Development` and declare `skills=<...>`, `review=<...>`.
1. Bootstrap the standard bundle with `scheduler`, `schedule_reviewer`, `researcher`, `research_reviewer`, `infra_steward`, `infra_reviewer`, and `critical_guardian`.
1. If available, use `/collab` Plan mode before planning and `/agent` to inspect the Codex inventory.
1. Always add `project_reviewer`, `docs_workflow_steward`, and `python_reviewer` as the fixed integration stack.
1. Keep one writer per worktree. Do not run same-directory parallel writes in the same worktree; use separate worktrees if you need multiple writers.
