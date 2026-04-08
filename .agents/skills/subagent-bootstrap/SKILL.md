---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, report-bundle bootstrap, or Claude subagent startup aligned with the repository's workflow families and write-scope rules.
---

# Subagent Bootstrap

1. Start from `agents/TASK_WORKFLOWS.md` and choose the workflow family first.
1. In the first work update, declare `workflow=<family>`, `skills=<...>`, `review=<...>`.
1. Bootstrap a run bundle with `python3 scripts/agent_tools/bootstrap_agent_run.py --task ... --owner ... --workspace-root "$PWD" --enable scheduler --enable schedule_reviewer`.
1. Add `researcher` and `research_reviewer` for research-backed changes, or `infra_steward` and `infra_reviewer` for platform changes.
1. For academic writing, explicitly add `notation_definition_reviewer` and `logic_gap_reviewer`.
1. If the runtime supports it, use `/collab` Plan mode before planning and use `/agent` to inspect the Codex subagent inventory.
1. Keep the plan reviewer, detailed design reviewer, document flow reviewer, notation-definition reviewer, and logic-gap reviewer as separate agent instances.
1. Keep handoff and review state in `reports/agents/<run-id>/` artifacts described by `agents/COMMUNICATION_PROTOCOL.md`.
1. For Claude-native specialists, use `.claude/agents/` as the subagent inventory.
1. Validate role boundaries with `python3 scripts/agent_tools/validate_role_write_scope.py` when a specialist or reviewer writes files.
