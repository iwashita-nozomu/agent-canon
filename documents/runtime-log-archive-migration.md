<!--
@dependency-start
contract reference
responsibility Documents how to move AgentCanon in-tree hook and eval logs into the external runtime log archive.
upstream design runtime-log-archive.md runtime log archive ownership and branch policy
upstream design coding-conventions-logging.md JSONL logging convention
upstream implementation ../tools/agent_tools/runtime_log_archive_git.py imports and pushes legacy hook JSONL and eval reports
downstream design ../evidence/agent-evals/README.md points readers away from in-tree result paths
downstream implementation ../tools/agent_tools/eval_accumulation_check.py validates mounted archive JSONL and eval reports
@dependency-end
-->

# Runtime Log Archive Migration

This document is procedure-only. It covers one-time or occasional migration of
old in-tree runtime logs into the external archive. Archive ownership, branch
policy, and steady-state mount rules stay in `documents/runtime-log-archive.md`.
General artifact retention rules stay in
`documents/result-log-retention-and-visualization.md`.

This document is the AgentCanon-side migration procedure for old hook JSONL and
accumulated eval reports that still exist under `agents/evals/results/`.

Runtime hook JSONL and accumulated eval reports belong in the external archive
repository mounted at `.agent-canon/log-archive/`. AgentCanon source keeps
reader-facing documentation, schemas, and tool tests, but no
`agents/evals/results/` result tree.

## Reader Map

- Owns the procedure for migrating old in-tree hook JSONL and eval reports into
  the external runtime log archive.
- Main path: Required Migration Steps, Current Migration Evidence, and Failure
  Handling.
- Read this during one-time or occasional archive migration work.
- Boundary: steady-state archive ownership and retention policy stay in
  `runtime-log-archive.md` and `result-log-retention-and-visualization.md`.

## Required Migration Steps

Run the commands from the AgentCanon repository root.

1. Mount or repair the archive clone.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py ensure
   ```

1. Inventory old in-tree hook JSONL and eval reports.

   ```bash
   find agents/evals/results/hook-runs -type f -name '*.jsonl' -print 2>/dev/null | sort
   find agents/evals/results -type f -name '*.md' -print 2>/dev/null | sort
   ```

1. Copy old JSONL into the archive and remove the source files.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py import-legacy --delete-source
   ```

1. Copy old eval reports into the archive and remove the source files.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py import-eval-results --delete-source
   ```

1. Commit and push the archive branch.

   ```bash
   python3 tools/agent_tools/runtime_log_archive_git.py push \
     --message "Import legacy AgentCanon logs"
   ```

1. Verify that AgentCanon source no longer contains raw hook JSONL or eval
   report artifacts or the old result tree.

   ```bash
   test ! -e agents/evals/results
   python3 tools/agent_tools/runtime_log_archive_git.py status --porcelain
   ```

1. If `agents/evals/results/` is empty after import, remove the directory from
   Git. The migration notice and schema pointers now live in
   `documents/runtime-log-archive.md` and `evidence/agent-evals/README.md`.

## Current Migration Evidence

The 2026-05-25 migration imported the old AgentCanon hook JSONL into:

```text
.agent-canon/log-archive/legacy-import/hook-runs/
.agent-canon/log-archive/legacy-import/eval-results/
```

The migrated set contains the former repo/runtime directories for
`docomo_bt_management`, `jax_solver_util`, `localllm_dev`, `project_template`,
`workspace`, plus the old top-level hook JSONL files. AgentCanon now stages
those old JSONL files for deletion and keeps the migration notice README.

The same migration imported the former accumulated eval result families
`skill-workflow-prompt`, `local-llm-responsibility`, `workflow-selection`, and
`report-quality` into `legacy-import/eval-results/`. AgentCanon source no
longer keeps `agents/evals/results/`.

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
