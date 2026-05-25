<!--
@dependency-start
responsibility Defines the external GitHub archive for AgentCanon runtime hook logs.
upstream design coding-conventions-logging.md JSONL logging convention
upstream design result-log-retention-and-visualization.md retention and visualization policy
downstream implementation ../tools/agent_tools/runtime_log_paths.py resolves archive paths
downstream implementation ../tools/agent_tools/runtime_log_archive_git.py manages clone, branch, status, and push operations
downstream design runtime-log-archive-migration.md documents in-tree hook JSONL migration into the archive
downstream implementation ../.codex/hooks/hook_event_log.py writes hook JSONL into the archive
downstream implementation ../tools/agent_tools/eval_accumulation_check.py validates archive JSONL when mounted
downstream implementation ../tools/agent_tools/generate_agent_improvement_guide.py reads mounted archive JSONL
downstream implementation ../tools/agent_tools/generate_agent_runtime_dashboard.py displays mounted archive evidence
@dependency-end
-->

# Runtime Log Archive

AgentCanon runtime hook JSONL is stored in the separate GitHub repository
`git@github.com:iwashita-nozomu/agent-canon-log.git`, mounted locally at:

```text
.agent-canon/log-archive/
```

The mount is intentionally ignored by AgentCanon Git. It is not a submodule and
does not create a gitlink that can dirty AgentCanon source branches or parent
repo AgentCanon pins.

## Layout

Normal hook writers use:

```text
.agent-canon/log-archive/hook-runs/<repo-key>/<runtime-namespace>/<hook-name>.jsonl
```

`<repo-key>` is derived from the source repository root name plus a short hash.
`<runtime-namespace>` is derived from `AGENT_CANON_HOOK_RUN_NAMESPACE`,
devcontainer/Compose metadata, or the existing host/repo fallback.

The initial import from the former in-tree log surface is preserved under:

```text
hook-runs/legacy-import/
```

## Branch Policy

- `main` stores archive-level policy, merge attributes, and one-time imports.
- Normal runtime writes use `logs/<repo-key>` branches.
- Source repos do not update AgentCanon source branches or template submodule
  pins when runtime logs change.
- JSONL files are append-only. The log repo uses `*.jsonl merge=union` so
  independent append lines can be kept during rebase conflict repair.

## Mount

```bash
python3 tools/agent_tools/runtime_log_archive_git.py ensure
```

If the mount is absent, hooks fall back to a local state directory outside the
repository tree. Set `AGENT_CANON_HOOK_ARCHIVE_DIR` to route logs to another
archive root. Existing `AGENT_CANON_HOOK_RESULTS_DIR` and per-hook
`*_HOOK_LOG_PATH` variables remain explicit test/debug overrides.

## Push

```bash
python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
python3 tools/agent_tools/runtime_log_archive_git.py push
```

Do not copy raw log JSONL back into AgentCanon source. Analysis artifacts such
as SQLite caches and dashboards belong to each source repo's ignored
`reports/.cache/` or `reports/agent-runtime-dashboard/` paths.

## Legacy In-Tree Log Migration

If `agents/evals/results/hook-runs/` contains old `*.jsonl`, migrate it with
`documents/runtime-log-archive-migration.md`. The normal command is:

```bash
python3 tools/agent_tools/runtime_log_archive_git.py import-legacy --delete-source
python3 tools/agent_tools/runtime_log_archive_git.py push \
  --message "Import legacy AgentCanon hook logs"
```

The AgentCanon source tree must keep only the README notice and non-hook eval
reports. Raw hook streams move to `hook-runs/legacy-import/` in the log archive.

When invoking the helper from a wrapper repository, keep the AgentCanon
submodule as the working directory and let the tool derive the superproject
source root. For unusual layouts, pass `--source-root <repo>` and
`--canon-root <agent-canon>` explicitly.
