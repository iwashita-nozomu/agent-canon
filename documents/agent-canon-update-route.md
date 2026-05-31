<!--
@dependency-start
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
does not erase local AgentCanon source changes; local source commits route to an
AgentCanon PR.

## Command Responsibilities

| Command | Responsibility |
| --- | --- |
| `tools/update_agent_canon.sh plan` | observe/update route decision; read-only |
| `tools/update_agent_canon.sh latest` | high-level parent pin/root-view update route |
| `tools/update_agent_canon.sh apply` | compatibility low-level apply; not the canonical task-start route |
| `tools/update_agent_canon.sh merge-main-into-current` | local AgentCanon source branch PR route |
| `tools/sync_agent_canon.sh link-root` | repair root symlink/copy views |
| `tools/sync_agent_canon.sh check` | validate root views |
| `tools/ci/check_agent_canon_latest.sh` | latest-state gate; mutation must be explicit in output |

## Cases

1. Parent repo uses an old AgentCanon main pin: run the parent pin update route.
1. `vendor/agent-canon` has local source commits: merge GitHub main into that
   branch, push the branch, and open an AgentCanon PR.
1. Root view drift only: run `link-root` and `check`.
1. AgentCanon update TODO pending: treat it as first work, then rerun latest.
1. Legacy subtree/snapshot repos: compatibility appendix only.

## Eval Coverage

The update route must be covered by issue-derived evals for route consistency,
check-command mutation visibility, TODO acknowledgement explicitness, and
AgentCanon PR versus parent pin separation.
