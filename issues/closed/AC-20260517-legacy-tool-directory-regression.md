# Legacy Tool Directory Regression

<!--
@dependency-start
contract issue
responsibility Records the resolved regression where retired tools/legacy paths returned to AgentCanon main.
upstream design ../README.md defines durable AgentCanon operational issue storage.
upstream design ../../documents/repo-local-tool-imports.md retires tools/legacy provenance paths.
upstream design ../../tools/README.md defines canonical shared tool families.
downstream implementation ../../tools/agent_tools/tool_drift.py rejects tools/legacy directories.
@dependency-end
-->

issue_id: AC-20260517-legacy-tool-directory-regression
status: resolved
source: reviewer
severity: S1
evidence: `python3 tools/agent_tools/tool_drift.py` reported `retired-legacy-tool:tool_catalog:tools/legacy:legacy-directory-present` on latest main after PR #72.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/255
affected_surfaces: tools/legacy/jax_solver_util/oop_check_support, documents/repo-local-tool-imports.md, tools/README.md, tools/agent_tools/tool_drift.py, .github/workflows/agent-canon-static-gates.yml
edit_scope: tools/legacy/jax_solver_util/oop_check_support, issues/closed/AC-20260517-legacy-tool-directory-regression.md, documents/repo-local-tool-imports.md, tools/README.md, tools/agent_tools/tool_drift.py, .github/workflows/agent-canon-static-gates.yml, tools/ci/check_github_workflows.py, .github/PULL_REQUEST_TEMPLATE.md, agents/workflows/agent-canon-pr-workflow.md
required_action: Remove the restored legacy provenance directory and keep OOP convention support represented by canonical `tools/oop/*` entrypoints.
close_condition: `tools/legacy/` is absent, `python3 tools/agent_tools/tool_drift.py` passes, and GitHub has a static gate that runs tool drift on PRs and branch pushes.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/75
resolved_at: 2026-05-17

## Finding

Latest AgentCanon `main` restored `tools/legacy/jax_solver_util/oop_check_support`
as tracked files. This contradicts the existing repo-local tool import policy:
AgentCanon no longer keeps `tools/legacy/` provenance paths, and legacy OOP
support should be represented by canonical OOP readability and rule inventory
entrypoints.

The regression is mechanically detectable. `tool_drift.py` already rejects a
tracked `tools/legacy` directory, but the GitHub check set on the merged PR only
ran the improvement-guide workflow, so the local drift gate did not block the
merge.

## Resolution

The restored `tools/legacy/jax_solver_util/oop_check_support` files were removed.
No canonical behavior is lost because the same disposition is already recorded
in `documents/repo-local-tool-imports.md`, and current OOP checking lives under
`tools/oop/python/`, `tools/oop/cpp/`, and `tools/oop/shared/`.

The standalone AgentCanon repository also gained
`.github/workflows/agent-canon-static-gates.yml`, which runs `tool_drift.py`
and adjacent lightweight static gates on PRs and branch pushes so this class of
regression is visible before merge.
