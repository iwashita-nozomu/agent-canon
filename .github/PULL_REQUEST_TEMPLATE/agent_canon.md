## Summary

- changed shared canon surfaces:
- why shared canon needs this change:

## Scope

- [ ] This PR edits `vendor/agent-canon/` as the source of truth.
- [ ] This PR does not mix repo-local implementation work with shared canon changes.
- [ ] Root symlink views were not edited directly.

## Validation

- [ ] `bash tools/sync_agent_canon.sh link-root`
- [ ] `bash tools/sync_agent_canon.sh check`
- [ ] `make agent-canon-pr-check`

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

## Risks

- stale route risk:
- backward drift risk:
- reviewer focus:
