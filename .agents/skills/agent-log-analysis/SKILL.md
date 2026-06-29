---
name: agent-log-analysis
description: Use when analyzing accumulated AgentCanon skill/tool/workflow/hook/eval logs, missed or late skill invocation, routing misses, weak skills, over-constrained related-skill coverage, or selection gaps; first convert raw logs into a structured dashboard summary with AgentCanon source generate_agent_runtime_dashboard.py before reading or interpreting evidence.
---
<!--
@dependency-start
contract skill
responsibility Documents Agent Log Analysis for this repository.
upstream design ../../../agents/skills/agent-log-analysis.md documents the human-facing skill
upstream design ../../../agents/skills/agent-eval-accumulation.md repairs missing accumulated eval evidence
downstream design ../../../agents/skills/issue-finding-report.md converts compact log findings into durable issues
upstream design ../../../documents/runtime-log-archive.md defines the external log archive mount
upstream implementation ../../../tools/agent_tools/generate_agent_runtime_dashboard.py owns structured dashboard API fields
upstream implementation ../../../tools/agent_tools/runtime_log_archive_git.py resolves the mounted log archive
@dependency-end
-->


# Agent Log Analysis

## Reader Map

- Purpose: runtime skill for compacting AgentCanon log evidence before
  diagnosing routing misses, weak skills, or workflow drift.
- Use When: accumulated skill, tool, workflow, hook, eval, or wave logs need
  analysis.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/agent-log-analysis.md` workflow.
- Boundary: generate the structured dashboard first; do not start with broad raw
  log reading.

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill agent-log-analysis --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/agent-log-analysis.md`.
1. Use the structured dashboard API / Markdown summary as the normal analysis input.
1. Select this skill when the observed problem is that a skill, tool, workflow, or related-skill candidate was missed, delayed, over-constrained, or routed to the wrong follow-up surface, even when the user describes the symptom without explicitly asking for logs.
1. Resolve or mount the external log archive before dashboard generation:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py sync
python3 tools/agent_tools/runtime_log_archive_git.py check-clean --porcelain
```

1. Use this archive hygiene sequence: `sync`, `check-clean`, dashboard
   generation, final `sync`. Preferred closed state is
   `RUNTIME_LOG_ARCHIVE_CLEAN=yes`. When `check-clean` reports only
   current-repo live hook files after the immediately preceding command, with
   `RUNTIME_LOG_ARCHIVE_FOREIGN_DIRTY=no`, record those paths as
   `live_hook_tail_dirty`, continue to dashboard generation, and close the task
   after the final `sync` reports `RUNTIME_LOG_ARCHIVE_SYNC=pass`. Foreign dirty
   keys remain archive hygiene repair targets before closeout.
1. Call the AgentCanon source dashboard tool from the source repository root.
   The tool resolves the AgentCanon root and the mounted log archive; keep
   `<source-root>` as the repository being analyzed:

```bash
python3 tools/agent_tools/generate_agent_runtime_dashboard.py \
  --root <source-root> \
  --compact-out reports/agent-runtime-dashboard/agent-log-analysis-compact.md \
  --api-out reports/agent-runtime-dashboard/agent-log-analysis-api.json
```

1. Read the API JSON or compact Markdown as the default analysis input. The
   archive repo owns append-only evidence; the AgentCanon source dashboard owns
   aggregation, moving averages, and routing evidence cells.
1. Confirm the API JSON includes the normal analysis fields `unknown_event_count`, `status_by_hook_family`, `failure_by_hook_family`, `skip_by_hook_family`, `namespace_debt_by_hook_family`, and `oop_applicability`.
1. When `generate_agent_runtime_dashboard.py` lacks a needed compact field,
   record `dashboard_api_contract_gap`, route that finding to the dashboard API owner,
   and rerun it after the source tool is repaired.
1. For eval family gaps, run `python3 tools/agent_tools/eval_accumulation_check.py --root . --compact-out reports/agents/<run-id>/eval-accumulation-before.json --format text`; if it reports missing, stale, or failing families, add `$agent-eval-accumulation` and use its producer/checker/archive loop.
1. Event-file drilldown is for tool development, schema debugging, corruption audit, or an API-named drilldown path; record an explicit rationale before reading it.
1. Answer token-use questions from the API token coverage/moving-average fields. If token status is missing, say token claims are unsupported.
1. Report observations separately from interpretation, repair target, and unknowns.
1. When the user asks to turn structured evidence into durable skill issues, hand
   the structured API output, structured Markdown summary, and Finding Route Packet to
   `$issue-finding-report`.
1. If the analysis drives a prompt, skill, workflow, or tool change, write the `Finding Route Packet` from `agents/skills/agent-log-analysis.md` before editing or spawning the repair wave. The packet must include `finding_class`, `evidence_cells`, `route_target`, `instance_partition`, `required_packet`, and `closeout_gate`.
1. Route by finding class:
   wave execution findings to `$subagent-bootstrap`;
   skill selection findings to the affected skill plus `prompt_config_reviewer`;
   tool selection findings to `tools/catalog.yaml` plus the owning tool docs;
   workflow selection findings to `agents/TASK_WORKFLOWS.md` plus the owning
   workflow guide; workflow attribution or token coverage findings to
   `$agent-learning` or the logging owner; eval gaps to
   `$agent-eval-accumulation`; archive hygiene findings to
   `$result-artifact-writeout` or the log archive owner; prompt/config drift to
   `prompt_config_reviewer`; and structure-boundary findings to
   `$structure-refactor`.
1. When one structured summary contains independent findings, split same-role review instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope. Use an instance id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>`.
1. If the user asks for a durable report, pair this skill with `$result-artifact-writeout`.
