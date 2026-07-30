<!--
@dependency-start
contract reference
responsibility Documents how to move AgentCanon in-tree hook and eval logs into the external runtime log archive.
upstream design runtime-log-archive.md runtime log archive ownership and branch policy
upstream design ../conventions/coding-conventions-logging.md JSONL logging convention
upstream implementation ../../tools/agent_tools/runtime_log_archive_git.py imports and pushes legacy hook JSONL and eval reports
downstream design ../../evidence/agent-evals/README.md points readers away from in-tree result paths
downstream implementation ../../tools/agent_tools/eval_accumulation_check.py validates mounted archive JSONL and eval reports
@dependency-end
-->

# Runtime Log Archive Migration

This document is procedure-only. It covers one-time or occasional migration of
old in-tree runtime logs into the external archive. Archive ownership, stable
branch policy, and steady-state mount rules stay in
`documents/runtime/runtime-log-archive.md` and the `agent-canon-log` policy
repository.
General artifact retention rules stay in
`documents/experiments/result-log-retention-and-visualization.md`.

This document is the AgentCanon-side boundary for old hook JSONL and accumulated
eval reports that still exist under `agents/evals/results/`. The policy-owner
inventory and any future branch migration are executed in `agent-canon-log`.

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

No migration, branch deletion, merge, rewrite, or source cleanup is performed
by the lifecycle redesign. The log repository policy branch contains a
deterministic read-only inventory of every legacy `logs/*` ref and the `main`
legacy-import tree.

## Required Future Migration Steps

Run the policy command from a checked-out `agent-canon-log` policy repository;
run any source inspection from the explicitly named source repository.

1. Generate and review the policy-owner dry-run inventory.

   ```bash
   cd <agent-canon-log-checkout>
   python3 tools/runtime_log_policy.py --root . inventory \
     --output docs/migration/legacy-inventory.json
   ```

1. Attach an explicit authority manifest naming each selected legacy branch,
   normalized source remote, expected source head, and destination stable branch.

   ```bash
   cd <explicit-source-repository>
   find agents/evals/results/hook-runs -type f -name '*.jsonl' -print 2>/dev/null | sort
   find agents/evals/results -type f -name '*.md' -print 2>/dev/null | sort
   ```

1. Execute only the separately reviewed migration implementation with the
   authority manifest. Producers must compare the expected remote head, push
   without force, and retain source snapshots on conflict.

1. Read back every destination remote ref and verify the exact expected head,
   tree, and content digest. A failed or uncertain readback blocks cleanup.

1. Retain legacy refs and `main` legacy-import data until a later policy
   decision explicitly authorizes retention changes.

The old `import-legacy --delete-source` and `import-eval-results --delete-source`
commands remain historical procedures, not a route for this redesign.

## Current Migration Evidence

The 2026-05-25 migration imported the old AgentCanon hook JSONL into:

```text
.agent-canon/log-archive/legacy-import/hook-runs/
.agent-canon/log-archive/legacy-import/eval-results/
```

The migrated set contains the former repo/runtime directories for
`docomo_bt_management`, `jax_solver_util`, a retired model-development workspace, `project_template`,
`workspace`, plus the old top-level hook JSONL files. AgentCanon now stages
those old JSONL files for deletion and keeps the migration notice README.

The same migration imported the former accumulated eval result families for
skill/workflow prompts, retired responsibility analysis, workflow selection,
and report quality into `legacy-import/eval-results/`. AgentCanon source no
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
