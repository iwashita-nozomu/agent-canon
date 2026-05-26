<!--
@dependency-start
responsibility Documents the GitHub canonical remote policy for AgentCanon.
downstream design ../agents/workflows/agent-canon-pr-workflow.md consumes GitHub evidence.
downstream implementation ../tools/sync_agent_canon.sh chooses the default remote.
downstream implementation ../tools/update_agent_canon.sh manages derived repo updates.
@dependency-end
-->

# AgentCanon GitHub Remote

`iwashita-nozomu/agent-canon` on GitHub is the canonical AgentCanon repository.
Local bare repositories under `/mnt/git` are compatibility mirrors, not
proposal targets and not the source of truth.

## Canonical Defaults

- Canonical URL: `https://github.com/iwashita-nozomu/agent-canon.git`
- Canonical branch: `main`
- Preferred submodule URL for template and derived repos:
  `https://github.com/iwashita-nozomu/agent-canon.git`
- Optional local mirror for read-only speed or offline validation:
  `/mnt/git/agent-canon.git`

`tools/sync_agent_canon.sh` uses the GitHub URL when `AGENT_CANON_REMOTE_URL`
is unset. Set `AGENT_CANON_REMOTE_URL=/mnt/git/agent-canon.git` only when a
repo intentionally works against a local mirror.
AgentCanon latest checks run with `GIT_TERMINAL_PROMPT=0` by default so GitHub
auth problems fail non-interactively instead of hanging inside task startup.

## Existing Local-Bare Repos

Repos that already have `agent-canon` pointed at `/mnt/git/agent-canon.git` do
not need an emergency rewrite. Leave a small migration commit that records the
current pin, then switch the remote when the repo is otherwise clean.

```bash
git remote get-url agent-canon
git submodule status vendor/agent-canon
git config -f .gitmodules submodule.vendor/agent-canon.url \
  https://github.com/iwashita-nozomu/agent-canon.git
git submodule sync vendor/agent-canon
git -C vendor/agent-canon remote set-url origin \
  https://github.com/iwashita-nozomu/agent-canon.git
bash tools/update_agent_canon.sh plan
bash tools/update_agent_canon.sh apply
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

If the repo keeps a local bare remote for fast validation, add it with a clear
non-canonical name instead of making it the canonical remote:

```bash
git remote add agent-canon-local /mnt/git/agent-canon.git
```

## Local Branches From Derived Repos

Derived repos that discover AgentCanon changes should commit them inside
`vendor/agent-canon/`, merge GitHub `main` into that branch, push the branch to
`iwashita-nozomu/agent-canon`, and open or update the AgentCanon PR. Do not
route new work through project-local compatibility remotes.

Before the branch push, verify the current repo remote and tracking state first:

- Check `git status --short --branch`. If it already shows tracking such as
  `...origin/<branch>`, prefer a normal `git push`.
- Confirm the actual remote with `git remote -v` or `git remote get-url`.
- If hook output hides `git remote -v`, fall back to
  `git config --get-regexp '^remote\\..*\\.url$'` and `.git/config`.
- Do not infer the destination repository from PR context, branch naming, or a
  template repository name.
- Treat literal URL push as an exception that needs explicit evidence that the
  verified remote/upstream is unavailable or insufficient.

```bash
bash tools/update_agent_canon.sh merge-main-into-current
git -C vendor/agent-canon push origin HEAD
```

## Commit Message Note

When migrating an existing repo from local bare to GitHub, include this in the
commit body:

```text
AgentCanon remote migration:
- canonical remote: https://github.com/iwashita-nozomu/agent-canon.git
- previous local mirror: /mnt/git/agent-canon.git
- vendor/agent-canon remains a submodule pinned to main
- local bare remotes are compatibility mirrors, not source of truth
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
GitHub Actions, the checkout helper persists AgentCanon-specific auth for later
steps in the same job. The token path adds an exact AgentCanon URL rewrite. The
deploy-key path persists a job-local `GIT_SSH_COMMAND` through `$GITHUB_ENV`
and adds an AgentCanon-specific HTTPS-to-SSH rewrite for the submodule URL.
This is intentional: later steps such as `make ci`, `make fresh-clone-check`,
and `make agent-canon-pr-check` may fetch `vendor/agent-canon` again after the
initial checkout helper has exited. The rewrite must stay scoped to the
AgentCanon URL, not all of `https://github.com/`, so the job does not
accidentally route unrelated repository access through the AgentCanon
credential.
