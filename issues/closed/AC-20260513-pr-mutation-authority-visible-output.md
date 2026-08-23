# PR Mutation Authority Requires Visible Copilot Output

<!--
@dependency-start
contract issue
responsibility Records the operational finding that PR mutation authority needs visible Copilot evidence.
upstream design ../README.md defines durable AgentCanon issue conventions.
upstream design ../../ROOT_AGENTS.md defines PR mutation authority policy.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR automation evidence surfaces.
upstream implementation ../../tools/ci/check_github_workflows.py validates PR template and Copilot surface coverage.
downstream design ../../.github/PULL_REQUEST_TEMPLATE.md requires Copilot / Automation Output fields.
downstream design ../../.github/PULL_REQUEST_TEMPLATE/agent_canon.md requires template-side Copilot / Automation Output fields.
@dependency-end
-->

issue_id: AC-20260513-pr-mutation-authority-visible-output
status: resolved
source: user
severity: S1
evidence: agents/workflows/agent-canon-pr-workflow.md
github_issue: https://github.com/iwashita-nozomu/agent-canon/issues/249
affected_surfaces: ROOT_AGENTS.md, .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, agents/workflows/agent-canon-pr-workflow.md, agents/workflows/codex-goals-workflow.md, tools/agent_tools/goal_loop.py, tools/ci/check_github_workflows.py
edit_scope: .github/PULL_REQUEST_TEMPLATE.md, .github/PULL_REQUEST_TEMPLATE/agent_canon.md, ROOT_AGENTS.md, agents/workflows/agent-canon-pr-workflow.md, agents/workflows/codex-goals-workflow.md, agents/workflows/goal-plan-implementation-loop.md, tools/README.md, tools/agent_tools/goal_loop.py, tests/agent_tools/test_goal_loop.py, tools/ci/check_github_workflows.py
required_action: Define goal-level PR mutation authority and require GitHub-hosted Copilot / PR automation to publish machine-readable PR-visible output before readiness or merge actions.
close_condition: PR templates, Copilot instructions, goal loop status, workflow docs, and check_github_workflows.py enforce visible Copilot evidence and validation passes.
resolved_by: PR #175 and PR #176; current PR templates, ROOT_AGENTS.md, AgentCanon PR workflow, and github-copilot configuration expose automation authority fields.
resolved_at: 2026-06-07

## Finding

`gh` availability was being conflated with permission to mutate PR state.
The earlier rule correctly blocked local Codex from arbitrary merge / close /
ready-for-review actions, but it did not provide a low-friction way for a
goal-driven run to delegate merge-after-green behavior to GitHub-hosted Copilot
or PR automation.

The missing contract had two risks:

- A user could intend "let Copilot merge when green" while local Codex still
  treats the goal as blocked by missing mutation authority.
- GitHub-hosted Copilot could make or recommend readiness / merge decisions
  without leaving machine-readable evidence that Codex, reviewers, or future
  runs can inspect with `gh pr view` or `gh pr checks`.

## Required Surfaces

The fix must cover both standalone AgentCanon PRs and template / derived
AgentCanon-pin PRs:

- `goal.md` and `goal_loop.py` expose `pr_mutation_authority`.
- `.github/PULL_REQUEST_TEMPLATE.md` and
  `.github/PULL_REQUEST_TEMPLATE/agent_canon.md` contain
  `Copilot / Automation Output` fields.
- `agents/workflows/agent-canon-pr-workflow.md` and
  `agents/workflows/codex-goals-workflow.md` require visible PR output.
- `agents/workflows/agent-canon-pr-workflow.md` documents what Codex can inspect:
  GitHub-visible PR bodies, comments, reviews, and check runs, not hidden
  Copilot reasoning.
- `tools/ci/check_github_workflows.py` fails when the visible-output contract
  disappears from required GitHub / Copilot surfaces.

## Evidence

Search-to-edit-scope was run with:

```bash
rg -l "PR Mutation Authority|github_copilot_merge_when_green|COPILOT_PR_DECISION|Copilot / Automation Output" \
  .github agents documents ROOT_AGENTS.md tools tests issues \
  > reports/dependency-review/pr-mutation-authority-20260513/search_hits.txt
bash tools/agent_tools/run_repo_dependency_review.sh \
  --report-dir reports/dependency-review/pr-mutation-authority-20260513 \
  --search-hits-file reports/dependency-review/pr-mutation-authority-20260513/search_hits.txt
```

The review produced `REPO_DEPENDENCY_REVIEW=pass` and
`DEPENDENCY_EDIT_SCOPE_PATHS=1169`; the directly actionable search hits were
the PR templates, Copilot instructions, PR maintainer agent, goal workflow docs,
goal loop tool, its tests, and `check_github_workflows.py`.
