# AC-20260513 Durable Finding Auto Promotion

<!--
@dependency-start
contract issue
responsibility Records the workflow defect where run-bundle findings were not promoted into durable AgentCanon issue or memory surfaces.
upstream design ../README.md defines AgentCanon operational issue conventions
upstream design ../../agents/workflows/agent-learning-workflow.md defines durable learning capture
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR route and issue gate
upstream design ../../documents/dependency-manifest-design.md defines search-to-edit-scope evidence
downstream implementation ../../tools/ci/check_github_workflows.py validates issue and PR-template gates
@dependency-end
-->

issue_id: AC-20260513-durable-finding-auto-promotion
status: resolved
source: user
severity: S0
evidence: reports/agents/20260513-071352-fix-duplicated-agentcanon-freshness-skil/
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/247
affected_surfaces: ROOT_AGENTS.md, issues/README.md, agents/canonical/CODEX_WORKFLOW.md, agents/workflows/agent-learning-workflow.md, agents/workflows/agent-canon-pr-workflow.md, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, tools/ci/check_github_workflows.py, documents/dependency-manifest-design.md
edit_scope: reports/agents/20260513-093806-detail-agentcanon-pr-template-workflow-a/dependency_edit_scope.txt
required_action: Make AgentCanon workflow and PR gates require durable operational finding capture instead of leaving defects only in run bundles.
close_condition: The AgentCanon PR workflow, PR templates, issue conventions, and CI checks require durable issue search/write evidence, and focused tests validate the rule.
resolved_by: PR #6; current issue conventions, PR templates, AgentCanon PR workflow, dependency review route, and check_github_workflows.py enforce durable finding evidence.
resolved_at: 2026-06-07

## Finding

A prior workflow defect was recorded in a run bundle but was not promoted into durable AgentCanon `memory/`, `notes/failures/`, or `issues/` storage.
The issue directory did not exist before this task, so an agent could truthfully complete a run bundle while leaving the defect invisible to future AgentCanon work.

## Required Fix

- Add `issues/` conventions and machine-readable required fields.
- Require AgentCanon PRs and template-side AgentCanon PRs to search and cite operational issues.
- Require workflow/tool/memory/eval changes to use a dedicated AgentCanon branch and PR path.
- Generate dependency graph/edit-scope artifacts so issue files can name likely edit and verification surfaces.
- Add CI checks that fail when issue conventions or PR-template issue gates are removed.

## Notes

This issue is intentionally small and operational.
It should not absorb unrelated closeout defects; create separate `AC-YYYYMMDD-*` issue files for distinct findings.
