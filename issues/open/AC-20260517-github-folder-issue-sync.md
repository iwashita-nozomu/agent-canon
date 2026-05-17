# GitHub And Folder Issue Sync

<!--
@dependency-start
responsibility Records the finding that durable folder issues need a GitHub Issue sync path.
upstream design ../README.md defines durable AgentCanon operational issue storage.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md requires issue evidence in PR flow.
downstream implementation ../../tools/agent_tools/issue_sync.py validates and plans local/GitHub issue synchronization.
downstream implementation ../../tools/ci/check_github_workflows.py validates issue convention surfaces.
@dependency-end
-->

issue_id: AC-20260517-github-folder-issue-sync
status: in_progress
source: user
severity: S1
evidence: User feedback on 2026-05-17: GitHub Issues and the repository issues folder should synchronize.
affected_surfaces: issues/README.md, issues/open, issues/closed, .github/PULL_REQUEST_TEMPLATE.md, agents/workflows/agent-canon-pr-workflow.md, tools/ci/check_github_workflows.py
edit_scope: issues/README.md, tools/agent_tools/issue_sync.py, tests/agent_tools/test_issue_sync.py, tools/catalog.yaml, tools/README.md, documents/tools/README.md, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md
required_action: Define local issue files as the durable source and add a tool that checks fields and can plan or apply GitHub Issue mirrors.
close_condition: Local issue validation is automated, GitHub mirror fields are documented, and the tool can report unsynced local issues without requiring network access in CI.

## Finding

The current issue directory explicitly says it is not a GitHub Issue mirror.
That was useful while local durable findings were being established, but the
operational flow now needs GitHub visibility without losing file-based review
and dependency-header traceability.

## Required Fix

Keep `issues/open|closed/` as the durable source of truth and add a sync tool.
The tool should support offline validation in CI and an explicit opt-in apply
mode for creating or updating GitHub Issues through `gh`.
