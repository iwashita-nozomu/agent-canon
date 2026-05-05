<!--
@dependency-start
responsibility Upstream sync note:.
upstream design ../../agents/workflows/agent-canon-pr-workflow.md agent-canon PR workflow
@dependency-end
-->

## Summary

- changed shared canon surfaces:
- why shared canon needs this change:
- derived repo or template issue that exposed the need:

## Scope

- [ ] This PR edits `vendor/agent-canon/` as the source of truth.
- [ ] This PR does not mix repo-local implementation work with shared canon changes.
- [ ] Root symlink views were not edited directly.
- [ ] Standalone AgentCanon PR checklist was considered when the change should land in `iwashita-nozomu/agent-canon` first.

## Validation

- [ ] `bash tools/sync_agent_canon.sh link-root`
- [ ] `bash tools/sync_agent_canon.sh check`
- [ ] `make agent-canon-pr-check`
- [ ] `bash tools/agent_tools/run_repo_dependency_review.sh --fail-missing`
- [ ] GitHub workflow or PR checklist changes were checked for submodule-aware checkout, least-privilege permissions, and review evidence fields.

Validation output:

```text
paste the key pass lines here
```

## Shared Surface Changes

- new surfaces:
- removed surfaces:
- root copy surfaces touched:
- link spec changes:

## Integration

- [ ] No file-structure change is included
- [ ] File-structure change is included and `agents/workflows/main-integration-workflow.md` will be used

Integration notes:

## Upstream Sync

- [ ] After template `main` merge, run `bash tools/sync_agent_canon.sh push`
- [ ] Upstream sync is intentionally deferred and explained below

Upstream sync note:

## GitHub Mirror / Submodule Evidence

- AgentCanon GitHub repo: `iwashita-nozomu/agent-canon`
- Template GitHub repo:
- template PR URL:
- AgentCanon PR URL or commit:
- template `vendor/agent-canon` pin:
- AgentCanon GitHub `main` SHA:
- template GitHub `main` SHA:
- local bare mirror SHA:
- `git submodule status vendor/agent-canon`:
- branch protection / vulnerability alert / Dependabot status:
- GitHub Actions workflow affected:
- PR checklist affected:

## Risks

- stale route risk:
- backward drift risk:
- reviewer focus:
