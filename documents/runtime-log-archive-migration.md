<!--
@dependency-start
responsibility Documents how to move AgentCanon in-tree hook logs into the external runtime log archive.
upstream design runtime-log-archive.md runtime log archive ownership and branch policy
upstream design coding-conventions-logging.md JSONL logging convention
upstream implementation ../tools/agent_tools/runtime_log_archive_git.py imports and pushes legacy hook JSONL
downstream implementation ../agents/evals/results/hook-runs/README.md points readers away from raw in-tree JSONL
downstream implementation ../tools/agent_tools/eval_accumulation_check.py validates mounted archive JSONL
@dependency-end
-->

# Runtime Log Archive Migration

This document is the AgentCanon-side migration procedure for old hook JSONL that
still exists under `agents/evals/results/hook-runs/`.

Runtime hook JSONL belongs in the external archive repository mounted at
`.agent-canon/log-archive/`. AgentCanon source keeps only reader-facing
documentation, schemas, tool tests, and durable eval reports that are not raw
runtime hook streams.

## Required Migration Steps

Run the commands from the AgentCanon repository root.

1. Mount or repair the archive clone.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py ensure
   ```

1. Inventory old in-tree hook JSONL.

   ```bash
   find agents/evals/results/hook-runs -type f -name '*.jsonl' -print | sort
   ```

1. Copy old JSONL into the archive and remove the source files.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py import-legacy --delete-source
   ```

1. Commit and push the archive branch.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py push \
     --message "Import legacy AgentCanon hook logs"
   ```

1. Verify that AgentCanon source no longer contains raw hook JSONL.

   ```bash
   find agents/evals/results/hook-runs -type f -name '*.jsonl' -print | sort
   python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
   ```

1. Keep `agents/evals/results/hook-runs/README.md` in AgentCanon. It is the
   migration notice and schema pointer for the old in-tree location.

## Current Migration Evidence

The 2026-05-25 migration imported the old AgentCanon hook JSONL into:

```text
.agent-canon/log-archive/hook-runs/legacy-import/
```

The migrated set contains the former repo/runtime directories for
`docomo_bt_management`, `jax_solver_util`, `localllm_dev`, `project_template`,
`workspace`, plus the old top-level hook JSONL files. AgentCanon now stages
those old JSONL files for deletion and keeps the migration notice README.

`reports/broken_links.txt` is local docs-check output, not a runtime hook JSONL
stream. It remains ignored local validation output and must not be copied into
the runtime hook archive.

## Failure Handling

- If `import-legacy` reports that an archive destination already exists with
  different content, stop and inspect both files before deleting the source.
- If `push` fails during `pull --rebase`, keep all JSONL lines during conflict
  resolution. The log archive uses `*.jsonl merge=union` to reduce append-only
  conflicts, but manual conflict repair must still preserve every line.
- If the archive clone has unrelated local changes, run
  `python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain` and
  commit, push, or move those changes before importing more logs.
