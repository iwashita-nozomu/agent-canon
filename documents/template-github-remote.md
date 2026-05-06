<!--
@dependency-start
responsibility Documents the GitHub canonical remote policy for the project template.
upstream design ./agent-canon-github-remote.md defines AgentCanon remote policy.
downstream design ./template-bootstrap.md consumes template GitHub remote policy.
downstream design ../agents/workflows/agent-canon-pr-workflow.md consumes template GitHub evidence.
@dependency-end
-->

# Template GitHub Remote

`iwashita-nozomu/project_template` on GitHub is the canonical template
repository. Local bare repositories under `/mnt/git` are compatibility mirrors,
not the source of truth.

## Canonical Defaults

- Canonical URL: `https://github.com/iwashita-nozomu/project_template.git`
- Canonical branch: `main`
- Optional local mirror: `/mnt/git/template.git`
- Optional local remote name: `local-bare`

Use `origin` for GitHub and reserve `local-bare` for the local mirror:

```bash
git remote set-url origin https://github.com/iwashita-nozomu/project_template.git
git remote add local-bare /mnt/git/template.git
```

If `local-bare` already exists, use `git remote set-url local-bare
/mnt/git/template.git`.

## Existing Local-Bare Repos

Repos cloned from `/mnt/git/template.git` can migrate without rewriting
history. First fetch the GitHub canonical branch, then push the same current
tree to both remotes.

```bash
git fetch origin main
git push origin main
git push local-bare main
```

Commit messages for template remote migration should include:

```text
Template remote migration:
- canonical remote: https://github.com/iwashita-nozomu/project_template.git
- previous local mirror: /mnt/git/template.git
- local bare remotes are compatibility mirrors, not source of truth
```

## AgentCanon Submodule

Template `main` should point `vendor/agent-canon` at the GitHub canonical
AgentCanon remote:

```bash
git config -f .gitmodules submodule.vendor/agent-canon.url \
  https://github.com/iwashita-nozomu/agent-canon.git
git submodule sync vendor/agent-canon
```

## Private Submodule Workflow Secret

Because both the template repository and AgentCanon can be private, GitHub
Actions needs an explicit cross-repo read credential for `vendor/agent-canon`.

Configure one of these repository secrets in `iwashita-nozomu/project_template`:

- `AGENT_CANON_REPO_TOKEN`: read-only Contents access to
  `iwashita-nozomu/agent-canon`.
- `AGENT_CANON_REPO_SSH_KEY`: private half of a read-only deploy key whose
  public half is installed on `iwashita-nozomu/agent-canon`.

Do not rely on automatic `actions/checkout` submodule fetch for the private
AgentCanon submodule. Workflows should checkout the template root with
`submodules: false`, then run
`bash .github/scripts/checkout_agent_canon_submodule.sh` so missing credentials fail
with a precise remediation message. In GitHub Actions, the helper also
persists AgentCanon-specific auth for later `make ci`,
`make fresh-clone-check`, and `make agent-canon-pr-check` steps in the same
job, whether the credential is a token or a deploy key.

## Branch Protection Baseline

Template `main` should be protected in GitHub UI when the repository is used by
other projects as a source template.

Minimum settings:

- Require pull request before merge.
- Require status checks for `make ci` / CI, `make agent-canon-pr-check` when
  AgentCanon surfaces are touched, and Docker build checks when Docker paths are
  touched.
- Restrict force-push and deletion on `main`.
- Keep vulnerability alerts and Dependabot alerts enabled for the canonical
  GitHub repository.

Record `missing_or_unavailable` in PR evidence when private-repo permissions
prevent the agent from reading branch protection.
