---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, report-bundle bootstrap, or Claude subagent startup aligned with the repository's workflow families and write-scope rules.
---

# Subagent Bootstrap

1. Start from `agents/TASK_WORKFLOWS.md` and choose the workflow family first.
1. Bootstrap a run bundle with `python3 scripts/agent_tools/bootstrap_agent_run.py --task ... --owner ...`.
1. For repo-editing tasks, explicitly enable the specialists needed for planning, plan review, detailed design, and detailed design review.
1. Keep the plan reviewer and detailed design reviewer as separate agent instances.
1. Keep handoff and review state in `reports/agents/<run-id>/` artifacts described by `agents/COMMUNICATION_PROTOCOL.md`.
1. For Claude-native specialists, use `.claude/agents/` as the subagent inventory.
1. Validate role boundaries with `python3 scripts/agent_tools/validate_role_write_scope.py` when a specialist or reviewer writes files.
