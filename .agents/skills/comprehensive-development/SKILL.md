---
name: comprehensive-development
description: Use when a repo-wide task spans code, docs, tools, workflows, and runtime surfaces and needs explicit subagent routing.
---

# Comprehensive Development

1. Read `agents/skills/comprehensive-development.md`.
1. Set `workflow=Comprehensive Development` and declare `skills=<...>`, `review=<...>`.
1. Bootstrap the standard bundle with `scheduler`, `schedule_reviewer`, `researcher`, `research_reviewer`, `infra_steward`, `infra_reviewer`, and `critical_guardian`.
1. If available, use `/collab` Plan mode before planning and `/agent` to inspect the Codex inventory.
1. Add `project_reviewer` as the intake and closeout integration gate, plus `docs_workflow_steward` or `python_reviewer` when needed.
1. Do not assign the same file to two write-capable subagents. Same-directory parallel work is allowed only with disjoint file scopes or separate worktrees.
