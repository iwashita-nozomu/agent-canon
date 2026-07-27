<!--
@dependency-start
contract reference
responsibility Documents the GitHub canonical remote policy for AgentCanon.
downstream design ../../agents/workflows/agent-canon-pr-workflow.md consumes GitHub evidence.
downstream implementation ../../tools/sync_agent_canon.sh chooses the default remote.
downstream implementation ../../tools/update_agent_canon.sh manages derived repo updates.
@dependency-end
-->

# AgentCanon GitHub Remote

`iwashita-nozomu/agent-canon` on GitHub is the canonical AgentCanon repository.

## Reader Map

Use this reference to answer which GitHub remote, branch, and submodule URL are
canonical for AgentCanon and how derived repos should handle non-GitHub remotes.
Read Canonical Defaults first, then Existing Non-GitHub Remotes and Local
Branches From Derived Repos for migration cases. The final sections cover commit
message notes, branch protection baseline, and GitHub Actions access.

## Canonical Defaults

- Canonical URL: `https://github.com/iwashita-nozomu/agent-canon.git`
- Canonical branch: `main`
- Preferred submodule URL for template and derived repos:
  `https://github.com/iwashita-nozomu/agent-canon.git`

`tools/sync_agent_canon.sh` uses the GitHub URL when `AGENT_CANON_REMOTE_URL`
is unset.
AgentCanon latest checks run with `GIT_TERMINAL_PROMPT=0` by default so GitHub
auth problems fail non-interactively instead of hanging inside task startup.

## Existing Non-GitHub Remotes

Repos that already have `agent-canon` pointed at a non-GitHub remote should
switch the remote when the repo is otherwise clean.

```bash
git remote get-url agent-canon
git submodule status vendor/agent-canon
git config -f .gitmodules submodule.vendor/agent-canon.url \
  https://github.com/iwashita-nozomu/agent-canon.git
git submodule sync vendor/agent-canon
git -C vendor/agent-canon remote set-url origin \
  https://github.com/iwashita-nozomu/agent-canon.git
make agent-canon-update-plan
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  make agent-canon-latest
AGENT_CANON_COMMIT_REQUEST_EVIDENCE="evidence:$(sha256sum agents/workflows/agent-canon-pr-workflow.md | awk '{print $1}')" \
  bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

The canonical command responsibility split is
`documents/agent-canon/agent-canon-update-route.md`. `apply` is compatibility/low-level;
normal parent repo updates use the high-level `latest` route.

## Local Branches From Derived Repos

Derived repos that discover AgentCanon changes should prepare a workspace-root
branch clone with `dependency-module-change`, commit there, push the branch to
`iwashita-nozomu/agent-canon`, and open or update the AgentCanon PR. Parent
`vendor/agent-canon` is a clean pin projection, not a source branch; do not
route new work through project-local compatibility remotes.

Use the gh-backed publish tool for the branch push and PR operation:

```bash
python3 tools/agent_tools/github_publish.py publish-pr \
  --user-task "<current user task>" \
  --repo iwashita-nozomu/agent-canon \
  --title "<PR title>" \
  --body-file reports/agents/<run-id>/pr_body.md
```

The tool verifies `origin` with `gh repo view` and `git remote get-url origin`.
If verification fails, fix the remote or the explicit `--repo` and rerun the
same tool. Do not infer the destination repository from PR context, branch
naming, template repository names, `.git/config` alternate route, or literal URL push.

Parent mode `tools/update_agent_canon.sh merge-main-into-current*` refuses vendor
source mutation. Standalone source mode retains its source-branch merge route.

## Commit Message Note

When migrating an existing repo to GitHub, include this in the commit body:

```text
AgentCanon remote migration:
- canonical remote: https://github.com/iwashita-nozomu/agent-canon.git
- vendor/agent-canon remains a submodule pinned to main
```

## Branch Protection Baseline

AgentCanon `main` should be protected because template and derived repos consume
it through submodule pins.

Minimum settings:

- Require pull request before merge unless the user explicitly authorizes a
  direct maintenance update.
- Require status checks for dependency review, skill mirror sync, runtime
  alignment, convention compliance, and relevant pytest / pyright / ruff gates.
- Restrict force-push and deletion on `main`.
- Keep vulnerability alerts and Dependabot alerts enabled for the canonical
  GitHub repository.

If GitHub API access cannot read branch protection, record
`missing_or_unavailable` in PR evidence instead of assuming protection is absent.

## GitHub Actions Access From Template Repos

`iwashita-nozomu/agent-canon` may be private. In that case, a workflow running
inside a different private repository cannot read the AgentCanon submodule with
only that repository's default `GITHUB_TOKEN`.

Template and derived repos should checkout the root repository with
`submodules: false`, then run:

```bash
bash .github/scripts/checkout_agent_canon_submodule.sh
```

The workflow must pass:

```yaml
env:
  AGENT_CANON_REPO_TOKEN: ${{ secrets.AGENT_CANON_REPO_TOKEN }}
```

`AGENT_CANON_REPO_TOKEN` should be a fine-grained PAT or equivalent GitHub App
token with read-only Contents access to the AgentCanon repository. If the
secret is missing, the helper fails with `AGENT_CANON_SUBMODULE_AUTH=missing`
instead of letting `actions/checkout` fail during an opaque automatic submodule
clone.

If a personal or app token is not desired, use a repository deploy key instead:

- Add the public key to `iwashita-nozomu/agent-canon` as read-only.
- Store the private key in the consuming repository secret
  `AGENT_CANON_REPO_SSH_KEY`.
- Keep `AGENT_CANON_REPO_TOKEN` unset, or use it only when a GitHub App /
  fine-grained PAT is the chosen credential.

The checkout helper prefers `AGENT_CANON_REPO_TOKEN` when present, then falls
back to `AGENT_CANON_REPO_SSH_KEY`.

When `AGENT_CANON_REPO_TOKEN` or `AGENT_CANON_REPO_SSH_KEY` is used inside
GitHub Actions, pass it only to the checkout-helper step. The helper unsets the
credential variables in its process, does not write them to `$GITHUB_ENV`, and
does not leave a global URL rewrite behind. Later validation steps consume the
initialized submodule checkout without receiving the secret. A later step that
must fetch AgentCanon again invokes the helper with the same step-local secret.
