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
