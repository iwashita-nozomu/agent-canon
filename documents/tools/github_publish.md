<!--
@dependency-start
contract reference
responsibility Documents the gh-backed GitHub publish and PR tool.
upstream design ../agent-canon-github-remote.md defines canonical GitHub remote policy.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md defines PR workflow usage.
upstream design ../../ROOT_AGENTS.md defines PR mutation authority.
downstream implementation ../../tools/agent_tools/github_publish.py implements the tool.
downstream implementation ../../tests/agent_tools/test_github_publish.py validates the tool contract.
@dependency-end
-->

# GitHub Publish Tool

`tools/agent_tools/github_publish.py` is the canonical AgentCanon entrypoint for
GitHub branch publication, pull request creation/update, and PR check evidence.
It is `gh`-based for repository identity and PR operations, and uses `git push`
only after `gh repo view` and `git remote get-url origin` agree on the same
`owner/name`.

The tool requires `--user-task` on every action. The compact stdout and optional
`--summary-out` JSON include the task, repository, branch, remote verification,
and next action. It rejects literal URL push, `.git/config` remote inference,
branch-name inference, PR-context inference, and machine-local remote inference.

## Commands

Push the current topic branch:

```bash
python3 tools/agent_tools/github_publish.py push \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon
```

Push and create or update a pull request:

```bash
python3 tools/agent_tools/github_publish.py publish-pr \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --title "<PR title>" \
  --body-file reports/agents/<run-id>/pr_body.md \
  --summary-out reports/agents/<run-id>/github_publish.json
```

Read PR checks:

```bash
python3 tools/agent_tools/github_publish.py checks \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --pr <number-or-branch>
```

## Hook Boundary

GitHub publish and PR evidence are user task execution, not edit-time code
quality checks. The hook dispatcher skips child guard hooks for `GitPush`,
simple `git push`, safe `gh pr` create/edit/view/list/checks/comment commands,
and this tool. Publish safety remains in the tool's explicit `gh` remote
verification and the PR workflow gates.

Non-critical hook, style, OOP, log-surface, planning, or closeout findings are
recorded as warning or closeout evidence. They do not stop branch publication or
PR body/check updates.

## Retired Shell Route

`tools/push_origin.sh` no longer performs push work. It prints the replacement
command and exits so old shell snippets cannot become a second publish
implementation or bypass the required user-task evidence.
