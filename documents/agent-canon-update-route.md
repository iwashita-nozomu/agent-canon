<!--
@dependency-start
contract reference
responsibility Defines the canonical AgentCanon update route and command responsibility split.
upstream implementation ../tools/update_agent_canon.sh provides high-level update commands.
upstream implementation ../tools/sync_agent_canon.sh provides low-level root view and submodule sync.
upstream implementation ../tools/ci/check_agent_canon_latest.sh checks update freshness.
upstream design ./agent-canon-parent-repo-latest-checklist.md defines task-start latest checks.
downstream design ../agents/skills/agent-update-branch.md separates canon-pin and source PR lanes.
@dependency-end
-->

# AgentCanon Update Route

The canonical parent-repo route is:

```bash
make agent-canon-update-plan
make agent-canon-latest
```

`latest` is the user-facing high-level route. It may update the parent pin,
repair root views, rebuild shared tools, and report pending parent TODOs. It
does not erase local AgentCanon source changes. Safe dirty checkout state is
preserved while AgentCanon `main` is merged, root views are repaired and
checked, and local source commits route to an AgentCanon PR.

The update route reuses existing branch / PR ownership by default. If the
current AgentCanon source branch or parent update branch already owns the same
surface, continue it. Do not create a branch just to start fresh, avoid dirty
state, split a small addendum, or handle an additional user instruction. A new
branch requires `branch_creation_reason=<reason>` in run evidence or the PR body
before it is created.

Every AgentCanon source, parent submodule pin, `.gitmodules`, root runtime
view, shared root-copy surface, and parent root sync change opens the mandatory
`agentcanon_structure_followup` gate. Record
`agentcanon_structure_followup=required`, then run the root-view repair and
check commands from the template / derived parent root that consumes the
AgentCanon pin:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

Record `agentcanon_structure_followup=pass` only after the sync check passes.
For standalone AgentCanon source PRs, this parent-root follow-up runs after the
source change is integrated or while preparing the parent pin/root-view PR; it
is not an optional propagation note.

## Command Responsibilities

| Command | Responsibility |
| --- | --- |
| `tools/update_agent_canon.sh plan` | observe/update route decision; read-only |
| `tools/update_agent_canon.sh latest` | high-level parent pin/root-view update route; uses preserve-dirty merge when safe |
| `tools/update_agent_canon.sh apply` | compatibility low-level apply; not the canonical task-start route |
| `tools/update_agent_canon.sh merge-main-into-current` | strict clean-worktree local AgentCanon source branch PR route |
| `tools/update_agent_canon.sh merge-main-into-current-preserve-dirty` | dirty-preserving local AgentCanon source branch PR route |
| `tools/sync_agent_canon.sh link-root` | repair root symlink/copy views |
| `tools/sync_agent_canon.sh check` | validate root views |
| `tools/ci/check_agent_canon_latest.sh` | latest-state gate; mutation must be explicit in output |

## Cases

1. Parent repo uses an old AgentCanon main pin: run the parent pin update route.
1. `vendor/agent-canon` has safe dirty checkout state: `latest` preserves the
   dirt, merges GitHub main into the current named branch, restores the dirt,
   repairs/checks root views, and reports the AgentCanon branch/PR next action.
1. `vendor/agent-canon` has local source commits: merge GitHub main into that
   branch, push the existing branch, and open or update the AgentCanon PR. Use a
   new branch only when the existing branch / PR cannot safely continue, and
   record the reason first.
1. Root view drift only: run `link-root` and `check`.
1. AgentCanon update TODO pending: treat it as first work, then rerun latest.
1. Legacy subtree/snapshot repos: compatibility appendix only.

## Mandatory Structure Follow-Up Gate

Use `agentcanon_structure_followup=required` for:

- AgentCanon source PRs and source commits that change shared canon behavior or
  synced surfaces.
- Parent `vendor/agent-canon` gitlink updates and `.gitmodules` changes.
- AgentCanon-owned root runtime views and shared root-copy surfaces.
- Parent root sync PRs in template or derived repositories.

The gate passes only when the parent root has run both root-view commands and
the PR/run evidence records `agentcanon_structure_followup=pass`:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

Parent readiness and structure checks selected by the active parent profile
remain required after this gate; the structure follow-up gate does not replace
`make agent-canon-pr-check` or the runtime profile validation route.

## Eval Coverage

The update route must be covered by issue-derived evals for route consistency,
check-command mutation visibility, TODO acknowledgement explicitness, and
AgentCanon PR versus parent pin separation.
