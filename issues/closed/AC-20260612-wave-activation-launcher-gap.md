# Wave Activation Launcher Gap

<!--
@dependency-start
contract issue
responsibility Records the defect where recommended subagent waves do not become executable runtime waves.
upstream design ../README.md defines durable AgentCanon operational issue conventions.
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md defines Codex subagent routing and lifecycle policy.
upstream design ../../agents/TASK_WORKFLOWS.md defines dynamic expansion wave expectations.
upstream design ../../agents/skills/subagent-bootstrap.md defines run-bundle bootstrap and subagent packet expectations.
downstream implementation ../../tools/agent_tools/bootstrap_agent_run.py emits recommended initial and expansion waves.
downstream implementation ../../tools/agent_tools/task_start.py emits task-start workflow recommendations.
downstream implementation ../../tools/agent_tools/agent_team.py defines team manifests and role routing.
downstream implementation ../../tools/agent_tools/generate_agent_runtime_dashboard.py should expose runtime wave/subagent evidence.
@dependency-end
-->

issue_id: AC-20260612-wave-activation-launcher-gap
status: resolved
source: user
severity: S1
evidence: reports/agents/20260612-091338-diagnose-wave-activation-blockers/wave_activation_diagnosis.md
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/259
affected_surfaces: tools/agent_tools/bootstrap_agent_run.py, tools/agent_tools/task_start.py, tools/agent_tools/agent_team.py, tools/agent_tools/generate_agent_runtime_dashboard.py, agents/canonical/CODEX_SUBAGENTS.md, agents/TASK_WORKFLOWS.md, agents/templates/schedule.md, agents/skills/subagent-bootstrap.md, .codex/config.toml
edit_scope: reports/agents/20260612-091338-diagnose-wave-activation-blockers/dependency-review/dependency_edit_scope.txt
required_action: Add an explicit launcher or parent-execution gate that turns recommended waves into actual runtime spawns when authority exists, and expose wave/subagent execution health in compact runtime diagnostics.
close_condition: A bootstrapped multi-agent task either records actual spawned/skipped wave rows from the recommended waves or emits a clear authority blocker, and the compact dashboard/API reports wave/subagent execution metrics without requiring raw log or run-bundle reading.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/196

## Finding

On 2026-06-12, a Wave activation diagnosis showed that AgentCanon can recommend
an initial subagent wave and later dynamic expansion waves without causing any
runtime subagent execution. The bootstrap output included
`RECOMMENDED_INITIAL_SUBAGENT_WAVE` and
`RECOMMENDED_DYNAMIC_EXPANSION_WAVES`, but the generated run bundle initially
had an empty `schedule.md` Agent Wave Ledger.

This is not the same defect as choosing the wrong implementation role after a
spawn decision. The missing step is earlier: there is no deterministic launcher
or mandatory parent execution gate that converts recommendations into actual
spawn, skipped-role, or authority-blocker evidence.

## Impact

The workflow can appear to support dynamic Wave expansion while the parent agent
continues alone after bootstrap. That makes it easy to miss requirements,
design, configuration, and review specialists, especially when a prescribed
tool fails mid-task and should be delegated immediately to a write-capable
repair agent.

The compact log-analysis dashboard also does not report Wave or subagent
execution metrics. It can summarize hook/status/recent-event counts, but cannot
answer whether a recommended Wave actually spawned, was skipped for authority,
or was deferred by budget/depth policy.

## Required Fix

AgentCanon should add one of the following execution paths:

1. a parent-visible launcher bridge that reads the recommended Wave packet and
   calls the available runtime spawn mechanism when explicit authority exists;
1. or a mandatory parent execution gate after bootstrap that writes concrete
   spawned/skipped/blocked rows into `schedule.md` and `workflow_monitoring.md`
   before implementation continues.

The same fix branch should extend compact runtime diagnostics so Wave health is
visible without broad raw-log reading.

## Evidence

The run bundle at
`reports/agents/20260612-091338-diagnose-wave-activation-blockers/` records:

- the initial recommendation-only bootstrap output;
- the empty initial Wave ledger;
- the first prescribed-tool blocker from `runtime_log_archive_git.py ensure`;
- subsequent explicit subagent delegation after user correction;
- root-cause review identifying recommendation-only bootstrap behavior and
  runtime authority veto as separate causes.

Dependency-expanded edit-scope evidence is recorded at
`reports/agents/20260612-091338-diagnose-wave-activation-blockers/dependency-review/dependency_edit_scope.txt`.

## Resolution

Closed on 2026-06-12.

AgentCanon now uses the mandatory parent execution gate path:

- `tools/agent_tools/agent_team.py` writes an initial `WAVE-1` row into
  `schedule.md` for workflow-family run bundles.
- The same helper writes a matching `wave_event=recorded` row into
  `workflow_monitoring.md` under `## Actual Wave Events`.
- `bootstrap_agent_run.py` and `task_start.py` print
  `PARENT_WAVE_EXECUTION_GATE=*` machine keys so parent runtimes can see that
  implementation must not silently continue without spawned/skipped/blocked
  wave evidence.
- `generate_agent_runtime_dashboard.py` reports Wave/subagent execution metrics
  in the machine summary, compact drilldown, full dashboard, problem component
  table, and next-action table. The Wave reader uses run-bundle
  `schedule.md` / `workflow_monitoring.md` artifacts and can run without a
  mounted raw log archive.

## Validation

- `python3 -m py_compile tools/agent_tools/agent_team.py tools/agent_tools/bootstrap_agent_run.py tools/agent_tools/task_start.py tools/agent_tools/generate_agent_runtime_dashboard.py`
- `python3 -m ruff check tools/agent_tools/agent_team.py tools/agent_tools/bootstrap_agent_run.py tools/agent_tools/task_start.py tools/agent_tools/generate_agent_runtime_dashboard.py tests/agent_tools/test_task_start_and_close.py tests/agent_tools/test_generate_agent_runtime_dashboard.py`
- `python3 -m pytest tests/agent_tools/test_generate_agent_runtime_dashboard.py -q`
- `python3 -m pytest tests/agent_tools/test_task_start_and_close.py -q`
- Manual bootstrap smoke: `bootstrap_agent_run.py --task-id T12` generated a
  `WAVE-1` authority-blocker row in `schedule.md` and a matching
  `wave_event=recorded` row in `workflow_monitoring.md`.
- Manual compact-dashboard smoke: a run-bundle-only fixture produced
  `AGENT_RUNTIME_DASHBOARD_WAVE_EVENTS=1` and
  `AGENT_RUNTIME_DASHBOARD_WAVE_BLOCKED=1` without `.agent-canon/log-archive`.
