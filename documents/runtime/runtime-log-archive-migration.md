<!--
@dependency-start
contract reference
responsibility Documents how to move AgentCanon in-tree hook and eval logs into the external runtime log archive.
upstream design runtime-log-archive.md runtime log archive ownership and branch policy
upstream design ../conventions/coding-conventions-logging.md JSONL logging convention
upstream implementation ../../tools/runtime/archive/runtime_log_archive_git.py imports and pushes legacy hook JSONL and eval reports
downstream design ../../eval/definitions/README.md points readers away from in-tree result paths
downstream implementation ../../eval/checkers/eval_accumulation_check.py validates mounted archive JSONL and eval reports
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

No legacy branch migration, branch deletion, merge, or rewrite is performed by
the lifecycle redesign. The log repository policy branch contains a
deterministic read-only inventory of every legacy `logs/*` ref and the `main`
legacy-import tree. AgentCanon import commands are limited to source-tree
cleanup: they may delete only mapped source files after archive commit, tree,
import-index, remote push, and exact ref/blob readback succeed.

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
   without force, and retain source snapshots on conflict. The AgentCanon-side
   `import-legacy --delete-source` and `import-eval-results --delete-source`
   commands are the only source-delete routes; normal `sync` and `push` have no
   delete authority.

1. Read back every destination remote ref and verify the exact expected head,
   tree, and content digest. A failed or uncertain readback blocks cleanup.

1. Retain legacy refs and `main` legacy-import data until a later policy
   decision explicitly authorizes retention changes.

The import commands create append-only `legacy-import/import-index.jsonl`
evidence before publication. A failed copy, digest/inventory check, commit,
push, or readback leaves every source file in place. The flag is not a shortcut
for policy-owner branch migration or retention deletion.

## Current Migration Evidence

The 2026-05-25 migration imported the old AgentCanon hook JSONL into:

```text
.agent-canon/log-archive/legacy-import/hook-runs/
.agent-canon/log-archive/legacy-import/eval-results/
```

The migrated set contains the former repo/runtime directories for
`docomo_bt_management`, `jax_solver_util`, a retired model-development workspace, `project_template`,
`workspace`, plus the old top-level hook JSONL files. AgentCanon now records
those files in `legacy-import/import-index.jsonl` and deletes them only in the
explicit post-readback finalize phase; failed or uncertain publication keeps
the source files and local archive evidence.

The same migration imported the former accumulated eval result families for
skill/workflow prompts, retired responsibility analysis, workflow selection,
and report quality into `legacy-import/eval-results/`. AgentCanon source no
longer keeps imported `agents/evals/results/` files. Plan records without a
concrete destination, such as `hook-runs/README.md`, are preserved at the
source and reported as preserved/not-imported; being listed in a plan is not
deletion authority.

Link-audit diagnostics are external task-scoped docs-check output, not a runtime
hook JSONL stream. They must not be created under `reports/` or copied into the
runtime hook archive.

## Failure Handling

- If `import-legacy` reports that an archive destination already exists with
  different content, stop and inspect both files before deleting the source.
- If `push` fails during `pull --rebase`, keep all JSONL lines during conflict
  resolution. The log archive uses `*.jsonl merge=union` to reduce append-only
  conflicts, but manual conflict repair must still preserve every line.
- If the archive clone has unrelated local changes, run
  `python3 tools/runtime/archive/runtime_log_archive_git.py status --porcelain` and
  commit, push, or move those changes before importing more logs.
