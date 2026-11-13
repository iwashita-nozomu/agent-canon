<!--
@dependency-start
contract reference
responsibility Documents the gh-backed GitHub publish and PR tool.
upstream design ../agent-canon/agent-canon-github-remote.md defines canonical GitHub remote policy.
upstream design ../../agents/skills/agent-canon-update.md defines PR workflow usage.
upstream design ../../ROOT_AGENTS.md defines PR mutation authority.
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/github_publish.rs implements the tool.
downstream implementation ../../tools/runtime/dispatch/agent-canon/tests/github_publish_native.rs validates the tool contract.
@dependency-end
-->

# GitHub Publish Tool

`agent-canon github-publish` is the AgentCanon command for
GitHub branch publication, pull request creation/update, and PR check evidence.
It is `gh`-based for repository identity and PR operations, and uses `git push`
only after `gh repo view` and `git remote get-url origin` agree on the same
`owner/name`.

The standalone `push` action is reversible branch transport, not correctness,
review, or PR publication. It requires the verified remote identity/permission
and a named current branch, captures local `HEAD`/tree, sends that commit with
the normal non-forced
`git push -u <remote> <commit-sha>:refs/heads/<branch>` through the configured Git
transport, reads exactly one
`git ls-remote <remote> refs/heads/<branch>` result, and verifies the remote SHA
and unchanged local branch/HEAD/tree. It does not generate or claim G1/G2/G3 or
PR lifecycle evidence; summaries use `publication_boundary=branch_transport_only`.
Identity mismatches return a failure summary with the next action.

The tool requires `--user-task` on every action. The compact stdout and optional
`--summary-out` JSON include the task, repository, branch, remote verification,
and next action. It rejects literal URL push, `.git/config` remote inference,
branch-name inference, PR-context inference, and machine-local remote inference.
PR readback requests fields supported by `gh pr view`, then reads `base.ref` and
the current PR identity from `gh api repos/{owner}/{repo}/pulls/{number}`. It
checks that the API number, URL, state, draft/merged status, base/head refs and
SHAs, and head repository agree with `gh pr view` before accepting the identity.
For merged PRs, the API merge SHA must also match; an unmerged PR's REST
`merge_commit_sha` can be a synthetic test merge SHA and is not treated as an
actual merge commit.

## Commands

Push the current topic branch:

```bash
agent-canon github-publish push \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon
```

Push and create or update a pull request:

```bash
agent-canon github-publish publish-pr \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --title "<PR title>" \
  --body-file reports/agents/<run-id>/pr_body.md \
  --summary-out reports/agents/<run-id>/github_publish.json
```

Read PR checks:

```bash
agent-canon github-publish checks \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --pr <number-or-branch>
```

CI fresh-clone fixtures validate clone/bootstrap or update behavior only. They
are not ordinary publication evidence; publication evidence comes from the
exact SHA ref push and the remote readback.
If a PR create or update succeeds but its following readback fails, the failure
summary retains the completed mutation and known PR selector, URL, repository,
and expected base/head identity from the frozen lifecycle. The
`expected_pr_*` fields describe publication inputs, not verified remote readback.
The summary marks `recovery_mode=readback_only`; callers should resolve the PR
through that identity before considering another publication attempt.
`pr` and `publish-pr` derive a direct lifecycle from the user task, verified
repository/permission, exact local candidate and base identities, and PR body;
they do not materialize `.agent-canon/update-lifecycle` state. `checks` is
read-only and consumes native `gh pr checks` output.

## Hook Boundary

GitHub publish and PR evidence are user task execution, not edit-time code
quality checks. The hook dispatcher skips child guard hooks for `GitPush`,
simple `git push`, safe `gh pr` create/edit/view/list/checks/comment commands,
and this tool. Publish safety remains in the tool's explicit `gh` remote
verification and the PR workflow gates.

Non-critical hook, style, OOP, log-surface, planning, or closeout findings are
recorded as warning or closeout evidence. They do not stop branch publication or
PR body/check updates.
