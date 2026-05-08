<!--
@dependency-start
responsibility Upstream sync note:.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
upstream design ../../documents/github-copilot-configuration.md Copilot configuration and PR-template routing
upstream design ../../tools/catalog.yaml structured tool catalog
downstream implementation ../../tools/ci/check_github_workflows.py validates PR checklist and workflow conventions
downstream implementation ../../tools/agent_tools/tool_drift.py validates PR/tool trace contracts
@dependency-end
-->

<!-- Synced to /.github/PULL_REQUEST_TEMPLATE/agent_canon.md by tools/sync_agent_canon.sh link-root. -->
<!-- Edit vendor/agent-canon/.github/PULL_REQUEST_TEMPLATE/agent_canon.md, not the root copy. -->

## Summary

- changed shared canon surfaces:
- why shared canon needs this change:
- derived repo or template issue that exposed the need:
- AgentCanon source PR / proposal:
- template PR:

## Scope

- [ ] This PR edits `vendor/agent-canon/` as the source of truth.
- [ ] This PR does not mix repo-local implementation work with shared canon changes.
- [ ] Root symlink views were not edited directly.
- [ ] Standalone AgentCanon PR checklist was considered when the change should land in `iwashita-nozomu/agent-canon` first.
- [ ] Template / derived repo PR routing is separated from standalone AgentCanon repository PR routing.

## Plan Mode Evidence

- [ ] Plan mode was used before non-trivial AgentCanon sync, Copilot, PR-template, GitHub Actions, or shared runtime-surface changes.
- [ ] Written plan is included in the PR body, issue, run bundle, or linked comment when the runtime did not expose an explicit Plan mode.
- [ ] Trivial-change exception is explained below when Plan mode was not used.

Plan / exception:

## Copilot Configuration Impact

- [ ] `documents/github-copilot-configuration.md` was reviewed.
- [ ] `.github/copilot-instructions.md` changed / reviewed / not affected.
- [ ] `.github/instructions/*.instructions.md` changed / reviewed / not affected.
- [ ] `.github/agents/*.md` changed / reviewed / not affected.
- [ ] GitHub Copilot MCP, `copilot-setup-steps.yml`, or Copilot environment settings changed / reviewed / not affected.
- [ ] PR template routing still separates this template / derived repo AgentCanon-pin PR from standalone AgentCanon repository PRs.

Impact notes:

## Validation

- [ ] `bash tools/sync_agent_canon.sh link-root`
- [ ] `bash tools/sync_agent_canon.sh check`
- [ ] `make agent-canon-pr-check`
- [ ] `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- [ ] `python3 tools/agent_tools/tool_catalog.py`
- [ ] `python3 tools/agent_tools/tool_drift.py`
- [ ] GitHub workflow / PR template changes: `python3 tools/ci/check_github_workflows.py`
- [ ] GitHub workflow changes: every `actions/checkout` job uses `submodules: false`, then runs `.github/scripts/checkout_agent_canon_submodule.sh` in template / derived roots or `tools/ci/checkout_agent_canon_submodule.sh` in standalone AgentCanon source when AgentCanon is needed.
- [ ] Private AgentCanon submodule access is covered by repository secret `AGENT_CANON_REPO_TOKEN`, `AGENT_CANON_REPO_SSH_KEY` from a read-only deploy key, or the PR explains why the workflow does not need it.
- [ ] GitHub workflow changes: `persist-credentials: false` is set unless the job has documented write intent.
- [ ] GitHub workflow changes: `permissions:` is set at workflow or job level.
- [ ] GitHub workflow changes: `concurrency:` is present or explicitly not needed.

Validation output:

```text
paste the key pass lines here
```

## Shared Surface Changes

- new surfaces:
- removed surfaces:
- root copy surfaces touched:
- link spec changes:
- `.gitmodules` changed / reviewed:

## Integration

- [ ] No file-structure change is included
- [ ] File-structure change is included and `agents/workflows/main-integration-workflow.md` will be used

Integration notes:

## Upstream Sync

- [ ] AgentCanon source PR / proposal was opened and merged before this template pin update, or this is a pin-only update to existing AgentCanon `main`.
- [ ] After AgentCanon merge, ran `make agent-canon-ensure-latest`.
- [ ] Ran `bash tools/sync_agent_canon.sh link-root` and `bash tools/sync_agent_canon.sh check`.
- [ ] Direct `bash tools/sync_agent_canon.sh push` was not used, or a maintainer direct-push exception is explained below.
- [ ] Upstream sync is intentionally deferred and explained below.

Upstream sync note:

## Submodule Pin Change

- [ ] Template `vendor/agent-canon` pin changed.
- [ ] Template `vendor/agent-canon` pin unchanged.

Pin unchanged justification:

## GitHub Mirror / Submodule Evidence

- AgentCanon GitHub repo: `iwashita-nozomu/agent-canon`
- Template GitHub repo:
- template PR URL:
- AgentCanon PR URL or commit:
- template `vendor/agent-canon` pin:
- AgentCanon GitHub `main` SHA:
- AgentCanon GitHub SHA:
- template submodule SHA:
- template GitHub `main` SHA:
- local bare mirror SHA:
- `git submodule status vendor/agent-canon`:
- branch protection / vulnerability alert / Dependabot status:
- GitHub Actions workflow affected:
- private AgentCanon submodule secret affected:
- PR checklist affected:

## Risks

- stale route risk:
- backward drift risk:
- reviewer focus:
