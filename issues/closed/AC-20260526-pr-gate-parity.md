# PR Gate Parity Drift

<!--
@dependency-start
contract issue
responsibility Records the recurring AgentCanon PR gate failure pattern and the required prevention surface.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines AgentCanon PR routing and gate expectations.
upstream implementation ../../.github/workflows/agent-canon-static-gates.yml runs branch and PR static gates.
upstream implementation ../../tools/ci/check_agent_canon_pr.sh runs local AgentCanon PR readiness checks.
upstream implementation ../../tools/ci/check_github_workflows.py verifies workflow and PR-template gate wiring.
downstream implementation ../../tests/tools/test_check_github_workflows.py tests static gate parity enforcement.
downstream implementation ../../tests/agent_tools/test_tool_drift.py tests PR check prompt-eval wiring.
@dependency-end
-->

issue_id: AC-20260526-pr-gate-parity
status: resolved
source: ci
severity: S1
evidence: GitHub Actions run 26450128761 failed dependency review after PR #143 moved runtime log evidence out of agents/evals/results.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/258
affected_surfaces: .github/workflows/agent-canon-static-gates.yml, tools/ci/check_agent_canon_pr.sh, tools/ci/check_github_workflows.py, tools/agent_tools/tool_drift.py, tools/agent_tools/evaluate_codex_agent_roles.py, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md
edit_scope: .github/workflows/agent-canon-static-gates.yml, tools/ci/check_agent_canon_pr.sh, tools/ci/check_github_workflows.py, tools/agent_tools/tool_drift.py, tools/agent_tools/evaluate_codex_agent_roles.py, tests/tools/test_check_github_workflows.py, tests/agent_tools/test_tool_drift.py, tests/agent_tools/test_evaluate_codex_agent_roles.py, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, agents/workflows/agent-canon-pr-workflow.md, tools/README.md, documents/tools/README.md
required_action: Keep GitHub static gates, local AgentCanon PR checks, PR templates, and drift checkers aligned for dependency headers, Codex skill shims, runtime role alignment, prompt eval, and convention compliance.
close_condition: Removing any local PR parity check from GitHub static gates or check_agent_canon_pr.sh fails a machine check before merge.
resolved_by: PR #147; static gates, local PR check, workflow checker, and tool drift tests now enforce parity.
resolved_at: 2026-06-07

## Finding

Recent AgentCanon PR gate failures had the same structural shape: a canonical
surface moved or a generated/runtime-facing surface changed, but not every
gate entrypoint checked the same invariants.

Observed root causes:

- `agents/evals/results/**` was retired in favor of the runtime log archive,
  while dependency headers and issue metadata still pointed at the old path.
  The strict dependency review caught the broken references only after PR
  creation.
- legacy non-Codex skill views drifted from canonical skill sources until the
  local Codex skill-shim check was run manually.
- Runtime role / model policy checks and skill/workflow prompt evals were
  part of local practice, but not protected by the GitHub static-gates
  workflow.
- Codex agent role eval carried a second hardcoded model policy after
  `.codex/config.toml` became the centralized policy source, so cost-tier
  changes could make local PR checks fail even when the runtime config was
  intentional.
- The local PR check treated standalone AgentCanon as if it were a
  template/derived checkout and called submodule shared-surface checks that
  require `vendor/agent-canon`.
- Stacked AgentCanon PRs became behind or dirty after related shared surfaces
  merged, which amplified late CI failures.

## Required Prevention

The GitHub static-gates workflow must run the same cheap parity checks that
local PR readiness depends on. The workflow checker must require those command
snippets, and the tool drift checker must require the local PR check to keep
strict dependency review, Codex skill-shim parity, runtime alignment, and prompt
eval wiring.

## Mitigation In This Branch

- GitHub static gates now run Codex skill-shim parity, runtime role alignment, Codex
  agent role eval, research pack smoke, skill/workflow prompt eval, and
  convention compliance checks.
- Workflow and tool drift checkers now fail if those parity checks disappear
  from the workflow or local PR readiness script.
- The standalone AgentCanon PR check reports shared-surface checks as
  `not_applicable_standalone_source` instead of failing on missing submodule
  paths, then runs the same static-gates suite used by GitHub.
- Codex agent role eval now loads role model buckets from `.codex/config.toml`
  instead of maintaining a second hardcoded table.
