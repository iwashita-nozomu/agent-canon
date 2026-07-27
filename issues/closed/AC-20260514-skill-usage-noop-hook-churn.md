# Skill Usage No-Op Hook Churn

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where skill usage hooks dirtied AgentCanon logs for no-skill events.
upstream implementation ../../.codex/hooks/skill_usage_logger.py filters no-skill hook payloads.
upstream design ../../documents/runtime-log-archive.md defines durable hook result artifact handling.
downstream implementation ../../tests/agent_tools/test_codex_hooks.py verifies no-skill payloads do not dirty logs.
@dependency-end
-->

issue_id: AC-20260514-skill-usage-noop-hook-churn
status: resolved
source: user-observation
severity: S1
evidence: repeated `skill_count=0` entries in legacy hook JSONL during read-only GitHub workflow diagnosis.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/251
affected_surfaces: .codex/hooks/skill_usage_logger.py, documents/runtime-log-archive.md, tests/agent_tools/test_codex_hooks.py
edit_scope: .codex/hooks/skill_usage_logger.py, tests/agent_tools/test_codex_hooks.py, issues/closed/AC-20260514-skill-usage-noop-hook-churn.md
required_action: Keep real skill-use evidence append-only, but do not write durable hook JSONL for payloads where no skill was observed.
close_condition: Skill usage hook still logs observed `$skill-name` payloads and skips empty / no-skill payloads without creating a log file.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/31
resolved_at: 2026-05-14

## Finding

During GitHub workflow diagnosis, the skill usage hook appended durable
`UnknownHookEvent` records with `skill_count=0`. Those records are technically
AgentCanon-owned hook evidence once written, but they are not useful evidence:
they only prove that a hook fired without observing skill usage.

This made normal read-only diagnosis dirty `vendor/agent-canon`, which then
made the GitHub PR / submodule flow look broken even when no product source had
changed.

## Resolution

`skill_usage_logger.py` now returns without writing when no skill ids are
observed. Existing hook evidence remains append-only. The filter only prevents
future no-op hook invocations from becoming durable artifacts.
