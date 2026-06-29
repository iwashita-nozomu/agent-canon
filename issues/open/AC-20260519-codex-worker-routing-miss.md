# Codex Worker Routing Miss

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where Codex used the broad worker role for a narrow implementation slice despite spark_worker being configured.
upstream design ../README.md defines durable AgentCanon operational issue conventions.
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md defines Codex subagent routing and spark_worker-first policy.
upstream design ../../agents/TASK_WORKFLOWS.md defines workflow-family implementation routing.
upstream design ../../agents/skills/agent-orchestration.md defines initial routing output requirements.
downstream design ../../agents/canonical/CODEX_SUBAGENTS.md should make worker selection evidence harder to skip.
downstream design ../../agents/skills/agent-orchestration.md should require citing the selected implementation role when code is delegated.
downstream implementation ../../.codex/agents/spark_worker.toml defines the intended narrow implementation role.
downstream implementation ../../.codex/agents/worker.toml defines the broader implementation alternate route role.
@dependency-end
-->

issue_id: AC-20260519-codex-worker-routing-miss
status: open
source: user
severity: S2
evidence: reports/dependency-review/agent-selection-routing-20260519/search_hits.txt
affected_surfaces: agents/canonical/CODEX_SUBAGENTS.md, agents/TASK_WORKFLOWS.md, agents/skills/agent-orchestration.md, .codex/agents/spark_worker.toml, .codex/agents/worker.toml
edit_scope: reports/dependency-review/agent-selection-routing-20260519/dependency_edit_scope.txt
required_action: Add a routing evidence step that makes Codex cite why implementation delegation selected spark_worker or worker before spawning the implementation agent.
close_condition: A workflow, skill, or eval gate fails or flags implementation delegation when a narrow design-traced slice skips the configured spark_worker role without an explicit alternate route reason.
github_issue: pending

## Reader Map

- Owns the open issue record for Codex implementation-role routing evidence
  misses.
- Main path: Finding, Impact, Required Fix, and Evidence.
- Read this before repairing or reviewing spark_worker/worker selection evidence
  in workflow or skill surfaces.
- Boundary: the issue records the defect and target surfaces; it does not itself
  change Codex subagent routing policy.

## Finding

On 2026-05-19, a narrow implementation cleanup for the demand-site experiment
runner was delegated to `worker` even though the repository configuration
already defines `spark_worker` as the first-choice role for design-traced,
low-ambiguity implementation slices.

The repository configuration was correct:

- `.codex/agents/spark_worker.toml` uses `gpt-5.3-codex-spark` with low
  reasoning effort for narrow implementation, docs sync, tests, and mechanical
  cleanup.
- `.codex/agents/worker.toml` uses `gpt-5.5` with high reasoning effort for
  broader implementation and ambiguity resolution.
- `agents/canonical/CODEX_SUBAGENTS.md` states that design-traced narrow
  implementation slices should use `spark_worker` first and reserve `worker`
  for broad or ambiguous implementation.

The miss was therefore not a bad agent definition. The defect was that the
parent did not cite and apply the configured implementation-role selection
before spawning the implementation agent.

## Impact

The immediate code result was usable, but the routing violated the intended
cost and latency split. It also obscured whether the implementation slice was
truly narrow enough for `spark_worker`, because no explicit alternate route rationale
was recorded before using `worker`.

## Required Fix

AgentCanon should make implementation delegation require a short role-selection
line before spawn:

1. identify whether the slice is narrow/design-traced or broad/ambiguous;
1. cite the selected implementation role;
1. cite `spark_worker` skip/alternate route reason when `worker` is chosen for a
   bounded implementation slice;
1. record that evidence in the run bundle or workflow-monitoring output.

An eval or workflow check should catch the regression where the configured
`spark_worker` path is silently skipped.

## Evidence

Durable surface search was recorded at
`reports/dependency-review/agent-selection-routing-20260519/search_hits.txt`.
The dependency-expanded edit scope was requested at
`reports/dependency-review/agent-selection-routing-20260519/dependency_edit_scope.txt`.
The dependency review also surfaced unrelated stale dependency headers in
current workspace data surfaces; those should be fixed separately and do not
change this finding.
