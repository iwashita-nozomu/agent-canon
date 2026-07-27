# Hook Result Accumulation

<!--
@dependency-start
contract issue
responsibility Records the resolved workflow defect where hook results were root-local, duplicated, and hard to use for improvement.
upstream design ../README.md defines AgentCanon operational issue conventions
upstream design ../../documents/runtime-log-archive.md defines hook result accumulation
upstream implementation ../../.codex/hooks/oop_readability_guard.py records OOP hook outcomes
upstream implementation ../../.codex/hooks/skill_usage_logger.py records skill hook outcomes
downstream implementation ../../tools/agent_tools/generate_agent_improvement_guide.py summarizes hook results
@dependency-end
-->

issue_id: AC-20260513-hook-result-accumulation
status: resolved
source: user
severity: S0
evidence: documents/runtime-log-archive.md
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/248
affected_surfaces: .codex/hooks/oop_readability_guard.py, .codex/hooks/skill_usage_logger.py, .codex/hooks/hook_event_log.py, documents/runtime-log-archive.md, tools/agent_tools/generate_agent_improvement_guide.py
edit_scope: .codex/hooks/oop_readability_guard.py, .codex/hooks/skill_usage_logger.py, .codex/hooks/hook_event_log.py, documents/runtime-log-archive.md, tools/agent_tools/generate_agent_improvement_guide.py, tests/agent_tools/test_codex_hooks.py
required_action: Store hook results in AgentCanon-owned append-only logs with unique hook_run_id, payload fingerprints, and actionable status fields.
close_condition: Hook logs default to AgentCanon result storage, read-only Bash payloads do not trigger OOP reruns, and tests validate unique IDs plus skip/failure fields.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/16

## Finding

OOP hook output was repeating the same failure without a unique run id, while
non-actionable payloads produced blank `event` and `tool_name` pass rows.
Because the default path was `reports/hooks/`, the evidence was local and easy
to lose instead of being accumulated with AgentCanon eval results.

## Resolution

- Added Canon-owned hook result storage under `agents/evals/results/hook-runs/`.
- Added `hook_run_id`, `payload_fingerprint`, `failure_fingerprint`, and
  `skip_reason` where applicable.
- Changed read-only `Bash` payloads, including direct checker invocations, to
  log as skipped rather than source-edit signals.
- Fed hook logs into the PR / push improvement-guide workflow.
