<!--
@dependency-start
contract reference
responsibility Documents rollback procedure for AgentCanon submodule pin updates in template and derived repositories.
upstream design ./agent-canon-parent-repo-latest-checklist.md defines parent update readiness checks.
upstream design ./agent-canon-update-route.md defines canonical update route ownership.
upstream implementation ../tools/sync_agent_canon.sh repairs root views and validates shared surfaces.
downstream design ./derived-repo-bootstrap-runbook.md links rollback from derived repo onboarding.
@dependency-end
-->

# AgentCanon Submodule Rollback

Use this when a template or derived repository moved `vendor/agent-canon` to a
new SHA and the new shared canon breaks root views, hooks, workflows, MCP, or
validation.

## Copy-Paste Rollback

Replace `<previous-sha>` with the last known good AgentCanon commit recorded in
the parent PR, branch log, or `git reflog`.

```bash
git submodule update --init vendor/agent-canon
git -C vendor/agent-canon fetch origin main
git -C vendor/agent-canon checkout <previous-sha>
git add vendor/agent-canon
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
git status --short
```

Commit the rollback in the parent repo:

```bash
git commit -m "Rollback AgentCanon pin to <previous-sha>"
```

## Validation After Rollback

```bash
git submodule status vendor/agent-canon
bash tools/sync_agent_canon.sh check
python3 tools/agent_tools/classify_path_risk.py --path vendor/agent-canon --format text
bash tools/ci/check_agent_canon_pr.sh
```

Run profile-specific checks from
`documents/runtime-profiles-and-check-matrix.md` when the failure involved
Docker, GitHub Actions, MCP, Python tooling, or docs.

## Remote Authority

GitHub `iwashita-nozomu/agent-canon` is the canonical shared-canon remote.
Do not roll back to an unpushed local-only SHA unless the parent issue or PR
explicitly records that emergency route and the recovery branch is published to
GitHub before normal work resumes.

## Re-Advance Condition

Move forward again only after the AgentCanon source issue is fixed on a branch
or main, the parent pin is updated with `make agent-canon-ensure-latest`, and
root views are rechecked with `bash tools/sync_agent_canon.sh link-root`.
