---
name: agent-log-analysis
description: Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, routing misses, weak skills, or selection gaps; first convert raw logs into a token-light compact summary with the external runtime_log_dashboard.py API before reading or interpreting evidence.
---
<!--
@dependency-start
responsibility Documents Agent Log Analysis for this repository.
upstream design ../../../agents/skills/agent-log-analysis.md documents the human-facing skill
upstream design ../../../agents/skills/agent-eval-accumulation.md repairs missing accumulated eval evidence
upstream design ../../../documents/runtime-log-archive.md defines the external log archive mount
upstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py owns compact dashboard API fields
upstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py resolves the mounted log archive
@dependency-end
-->


# Agent Log Analysis

1. Read `agents/skills/agent-log-analysis.md`.
1. Use the compact dashboard API / Markdown summary as the normal analysis input.
1. Use the external log archive API first. Resolve or mount the archive:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py sync
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

1. Complete log analysis and task closeout after `check-clean` reports `RUNTIME_LOG_ARCHIVE_CLEAN=yes`. If it reports `RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=yes`, resolve the listed foreign repo-key logs before returning to the user.
1. Call the log archive repository tool. Replace `<archive-root>` with `RUNTIME_LOG_ARCHIVE_ROOT` from `status --porcelain` or `check-clean --porcelain`:

```bash
python3 <archive-root>/tools/runtime_log_dashboard.py \
  --root <archive-root> \
  --profile log-analysis \
  --output reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-output reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

1. Read the API JSON or compact Markdown as the default analysis input. The log archive repo owns aggregation, moving averages, and manuscript-structure evidence cells.
1. Confirm the API JSON includes the normal analysis fields `unknown_event_count`, `status_by_hook_family`, `failure_by_hook_family`, `skip_by_hook_family`, `namespace_debt_by_hook_family`, and `oop_applicability`.
1. If `<archive-root>/tools/runtime_log_dashboard.py` is missing, stop with `log_archive_api_missing` and return to the dashboard API owner.
1. If the compact report lacks enough context for a specific claim, extend the log archive repository API/report profile and rerun it.
1. For eval family gaps, run `python3 tools/agent_tools/eval_accumulation_check.py --root . --compact-out reports/agents/<run-id>/eval-accumulation-before.json --format text`; if it reports missing, stale, or failing families, add `$agent-eval-accumulation` and use its producer/checker/archive loop.
1. Event-file drilldown is for tool development, schema debugging, corruption audit, or an API-named drilldown path; record an explicit rationale before reading it.
1. Answer token-use questions from the API token coverage/moving-average fields. If token status is missing, say token claims are unsupported.
1. Report observations separately from interpretation, repair target, and unknowns.
1. If the analysis drives a prompt, skill, workflow, or tool change, write the `Finding Route Packet` from `agents/skills/agent-log-analysis.md` before editing or spawning the repair wave. The packet must include `finding_class`, `evidence_cells`, `route_target`, `instance_partition`, `required_packet`, and `closeout_gate`.
1. Route by finding class: wave execution findings to `$subagent-bootstrap`, skill selection findings to the affected skill plus `prompt_config_reviewer`, workflow attribution or token coverage findings to `$agent-learning` or the logging owner, eval gaps to `$agent-eval-accumulation`, archive hygiene findings to `$result-artifact-writeout` or the log archive owner, prompt/config drift to `prompt_config_reviewer`, and structure-boundary findings to `$structure-refactor`.
1. When one compact summary contains independent findings, split same-role review instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope. Use an instance id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.
1. If the user asks for a durable report, pair this skill with `$result-artifact-writeout`.
