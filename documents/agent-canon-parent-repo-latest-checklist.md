# AgentCanon Parent Repository Latest-State Checklist
<!--
@dependency-start
responsibility Documents latest-state checklist for parent repositories that vendor AgentCanon.
upstream design ./agent-canon-subtree-migration.md submodule and legacy subtree update policy
upstream implementation ../tools/agent_tools/agent_canon_preflight.py emits checklist evidence at task start
downstream implementation ../tools/agent_tools/bootstrap_agent_run.py prints checklist evidence
downstream implementation ../tools/agent_tools/task_start.py prints checklist evidence
@dependency-end
-->

この checklist は、AgentCanon を `vendor/agent-canon/` Git submodule として持つ親 repo で agent task を始める前に確認する最新状態 checklist です。
この template と新規 migration 済み repo の通常系は submodule です。
legacy subtree / committed snapshot repo は末尾の互換 appendix だけを使い、通常の親 repo 構造として扱いません。
agent entrypoint は `tools/agent_tools/agent_canon_preflight.py` 経由でこの checklist の存在と freshness preflight を出力します。

## Expected Parent Repo Structure

親 repo は次の構造を持ちます。

| Path | Expected State | Owner | Check |
| --- | --- | --- | --- |
| `vendor/agent-canon/` | AgentCanon Git submodule checkout and parent gitlink | AgentCanon | `git submodule status vendor/agent-canon` and `git rev-parse HEAD:vendor/agent-canon` |
| `AGENTS.md`, `CLAUDE.md`, `agents/`, `.agents/`, `.claude/`, `.codex/`, `mcp/`, `tools/` | root runtime view of AgentCanon | AgentCanon | `bash tools/sync_agent_canon.sh check` |
| `.github/AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/`, `.github/agents/` | GitHub agent root views | AgentCanon | `bash tools/sync_agent_canon.sh check` |
| `.github/workflows/agent-coordination.yml`, `.github/PULL_REQUEST_TEMPLATE/agent_canon.md`, `.github/scripts/checkout_agent_canon_submodule.sh` | regular root copies forced by GitHub path constraints | AgentCanon source, root copy | `bash tools/sync_agent_canon.sh check` |
| `documents/SHARED_RUNTIME_SURFACES.md`, `documents/shared-runtime-surfaces.toml` | shared surface policy and machine manifest | AgentCanon | `python3 tools/agent_tools/check_convention_compliance.py` |
| `documents/README.md`, template bootstrap / host / server contract docs | parent repo active contracts | template or derived repo | regular file, not root symlink |
| `goal.md`, project notes, experiments, reports | repo-local durable state and generated evidence | parent repo | must not be restored from AgentCanon |

## Latest-State Checklist

Run this sequence before editing shared AgentCanon surfaces or starting a repo-changing task.

1. Confirm MCP inventory when the runtime supports it.

```bash
python3 tools/agent_tools/check_mcp_inventory.py --require repo_mcp_server
```

1. Check the parent worktree and classify dirty state.

```bash
git status --short --branch --untracked-files=all
git -C vendor/agent-canon status --short --branch --untracked-files=all 2>/dev/null || true
```

1. If `vendor/agent-canon/` is a submodule, unrelated parent dirty state does not block an AgentCanon update. The update may proceed when the AgentCanon update surface is clean:

- `vendor/agent-canon/` submodule worktree is clean.
- parent gitlink at `vendor/agent-canon` is not already an unresolved local pin change.
- `.gitmodules` is clean.
- AgentCanon-owned symlink and GitHub copy root views are clean.

Template-owned active contracts such as `documents/README.md`, bootstrap docs, host/server contracts, project notes, experiments, and reports do not block the submodule update just because they are dirty.

1. If the AgentCanon update surface is clean, update AgentCanon before planning or implementation.

```bash
make agent-canon-ensure-latest
```

1. If only unrelated parent paths are dirty, keep those changes intact and still run the latest update. Record that the dirty paths were outside the AgentCanon update surface.

1. If the dirty state is inside AgentCanon source, `.gitmodules`, the parent gitlink, or an AgentCanon-owned root view that `link-root` may overwrite, route the change through the AgentCanon PR or derived proposal workflow first.

```bash
bash tools/update_agent_canon.sh review-submodule
bash tools/update_agent_canon.sh push-proposal
```

1. After AgentCanon update or proposal merge, restore root views from the manifest and verify drift.

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

1. Record closeout evidence for parent repo runs.

```bash
git submodule status vendor/agent-canon 2>/dev/null || git rev-parse HEAD:vendor/agent-canon
python3 tools/agent_tools/check_convention_compliance.py
```

## Agent Task-Start Rule

When an agent starts through `task_start.py` or `bootstrap_agent_run.py`, the output must include:

- `AGENT_CANON_PREFLIGHT_COMMAND`
- `AGENT_CANON_PREFLIGHT_STATUS`
- `AGENT_CANON_PREFLIGHT_REASON`
- `AGENT_CANON_PREFLIGHT_NEXT`
- `AGENT_CANON_PREFLIGHT_CHECKLIST`
- `AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS`

`AGENT_CANON_PREFLIGHT_CHECKLIST_STATUS=present` means this checklist was found in the parent repo's vendored AgentCanon surface.
`missing` means the parent repo is stale or malformed; the agent must repair AgentCanon checkout/sync before treating repo-changing work as started.

## Failure Routes

- unrelated parent dirty state: allowed for submodule updates when the AgentCanon update surface is clean.
- stale parent gitlink: not latest, even when `vendor/agent-canon` worktree HEAD already equals AgentCanon remote main; commit the parent gitlink pin before treating the parent repo as latest.
- local-ahead parent gitlink: proposal / AgentCanon PR required; do not treat `local_contains_remote` as latest.
- `blocked_shared_canon_workflow`: do not hide shared-canon edits in a parent-only diff; commit/push proposal or open an AgentCanon PR.
- `skipped_source_canon`: running inside standalone AgentCanon; update parent repos after AgentCanon changes are committed.
- `missing checklist`: restore or update `vendor/agent-canon/`, then rerun `bash tools/sync_agent_canon.sh link-root`.

## Legacy Compatibility Appendix

Legacy subtree or committed snapshot repos should migrate to the submodule structure above.
Until migration, use `bash tools/update_agent_canon.sh plan` only to classify compatibility routes such as `already_current_tree`, `already_current_split`, `snapshot_import_*`, or `subtree_pull`.
Do not copy legacy route language into this template's normal task-start rules.
