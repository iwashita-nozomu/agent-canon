# GitHub And Folder Issue Sync

<!--
@dependency-start
contract issue
responsibility Records the finding that durable folder issues need a GitHub Issue sync path.
upstream design ../README.md defines durable AgentCanon operational issue storage.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md requires issue evidence in PR flow.
downstream implementation ../../tools/agent_tools/issue_sync.py validates and plans local/GitHub issue synchronization.
downstream implementation ../../.github/workflows/issue-mirror.yml checks issue mirror drift on PRs.
downstream implementation ../../tools/ci/check_github_workflows.py validates issue convention surfaces.
@dependency-end
-->

issue_id: AC-20260517-github-folder-issue-sync
status: resolved
source: user
severity: S1
evidence: User feedback on 2026-05-17: GitHub Issues and the repository issues folder should synchronize.
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/254
affected_surfaces: issues/README.md, issues/open, issues/closed, .github/workflows/issue-mirror.yml, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, agents/workflows/agent-canon-pr-workflow.md, tools/ci/check_github_workflows.py
edit_scope: issues/README.md, .github/workflows/issue-mirror.yml, tools/agent_tools/issue_sync.py, tests/agent_tools/test_issue_sync.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, tools/ci/check_github_workflows.py, tests/tools/test_check_github_workflows.py, documents/shared-runtime-surfaces.toml
required_action: Define local issue files as the durable source and add PR-visible read-only GitHub mirror checks plus explicit operator sync tooling.
close_condition: Local issue validation is automated, GitHub mirror fields are documented, PR Actions report missing mirrors and linked mirror drift, and explicit sync mode can update linked GitHub Issues.
resolved_by: https://github.com/iwashita-nozomu/agent-canon/pull/95

## Finding

The current issue directory explicitly says it is not a GitHub Issue mirror.
That was useful while local durable findings were being established, but the
operational flow now needs GitHub visibility without losing file-based review
and dependency-header traceability.

## Required Fix

Keep `issues/open|closed/` as the durable source of truth and add a sync tool.
The tool should support offline validation in CI and an explicit opt-in apply
mode for creating or updating GitHub Issues through `gh`.
