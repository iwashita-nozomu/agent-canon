<!--
@dependency-start
responsibility Documents the GitHub canonical remote policy for AgentCanon.
upstream design ./agent-canon-subtree-migration.md defines AgentCanon vendoring.
upstream implementation ../tools/sync_agent_canon.sh chooses the default remote.
upstream implementation ../tools/update_agent_canon.sh manages derived repo updates.
downstream design ../agents/workflows/agent-canon-pr-workflow.md consumes GitHub evidence.
@dependency-end
-->

# AgentCanon GitHub Remote

`iwashita-nozomu/agent-canon` on GitHub is the canonical AgentCanon repository.
Local bare repositories under `/mnt/git` are compatibility mirrors or proposal
targets, not the source of truth.

## Canonical Defaults

- Canonical URL: `https://github.com/iwashita-nozomu/agent-canon.git`
- Canonical branch: `main`
- Preferred submodule URL for template and derived repos:
  `https://github.com/iwashita-nozomu/agent-canon.git`
- Optional local mirror: `/mnt/git/agent-canon.git`
- Optional project-local proposal remote:
  `/mnt/git/<project>-agent-canon.git`

`tools/sync_agent_canon.sh` uses the GitHub URL when `AGENT_CANON_REMOTE_URL`
is unset. Set `AGENT_CANON_REMOTE_URL=/mnt/git/agent-canon.git` only when a
repo intentionally works against a local mirror.

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
name instead of making it the canonical remote:

```bash
git remote add agent-canon-local /mnt/git/agent-canon.git
```

## Source Repo Configuration

`agent-canon.sourceRepo` is optional. Use it only when a derived repo must
refresh a local mirror from a checked-out AgentCanon worktree before applying a
snapshot. GitHub-backed repos should normally leave it unset and fetch directly
from the submodule origin.

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
