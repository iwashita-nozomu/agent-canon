---
name: structure-refactor
description: Use when repository directory structure, directory responsibilities, canonical README ownership, path layout, root views, or responsibility-scope maps must be refactored using recursive directory README analysis, dependency manifests, and behavior-preserving move/rename gates.
---
<!--
@dependency-start
responsibility Documents Structure Refactor runtime skill for this repository.
upstream design ../../../agents/skills/structure-refactor.md documents the human-facing skill canon
upstream design ../../../agents/skills/refactor-loop.md defines behavior-preserving refactor gates
upstream design ../../../agents/skills/dependency-analysis.md defines change-impact packets
upstream design ../../../agents/skills/prose-reasoning-graph.md defines directory README graph evidence
upstream implementation ../../../tools/agent_tools/responsibility_scope.py validates responsibility scopes
upstream implementation ../../../tools/agent_tools/import_responsibility.py validates import boundaries
@dependency-end
-->

# Structure Refactor

1. Read `agents/skills/structure-refactor.md`.
1. Use this for directory layout refactors, directory responsibility splits or merges, canonical README ownership changes, root-view / submodule-view layout changes, and responsibility-scope map changes.
1. Always pair with `$refactor-loop`, `$dependency-analysis`, `$prose-reasoning-graph`, and `$document-canon-cleanup`; add `$subagent-bootstrap` when the user requests multi-agent work or the refactor touches shared canon.
1. Build a recursive directory responsibility graph before editing:
   - collect every directory `README.md`, `AGENTS.md`, and dependency manifest under the proposed root
   - run `agent-canon structured-analysis document-inventory --root <root>`
   - run `python3 tools/agent_tools/responsibility_scope.py --root <root> --format json`
   - run or update a scope-overlap report that applies `exclude_paths`
   - run `python3 tools/agent_tools/prose_reasoning_graph.py check-document <readme-path> --out-dir <run>/prose/<readme-id> --profile all --stats-out <run>/prose/<readme-id>.stats.json` on changed directory README files
1. Treat directory structure as a product contract. Fix `Behavior Contract`, `Allowed Structural Delta`, `Forbidden Semantic Delta`, `Path Mapping`, `Directory Responsibility Map`, and `Reader Impact` before moving files.
1. Derive target layout from responsibilities, not from path aesthetics:
   - split a directory when one README must describe unrelated primary responsibilities
   - merge directories when their READMEs describe the same primary responsibility and no separate validation/import boundary remains
   - keep cross-directory evidence or runtime surfaces in their own primary scope, and remove overlap by `exclude_paths` or explicit path mapping
1. Do not move files until reverse edges, import paths, public root views, docs links, and generated artifact paths have a repair plan.
1. Use multi-agent routing for nontrivial structure refactors:
   - `explorer`: recursive README / manifest / scope graph inventory
   - `detailed_designer`: path mapping and responsibility delta
   - `worker` or `spark_worker`: one disjoint move/update wave
   - `document_flow_reviewer`: reader path and README consistency
   - `python_reviewer` / `cpp_reviewer`: import/build fallout
   - `project_reviewer`: final tree ownership and stale-surface sweep
1. After each move/update wave, rerun:
   - `python3 tools/agent_tools/responsibility_scope.py --root <root>`
   - `python3 tools/agent_tools/import_responsibility.py --root <root>`
   - `agent-canon structured-analysis document-inventory --root <root>`
   - changed-file dependency header checks and docs check
1. Sweep old paths before closeout. Do not leave `_old`, `_copy`, backup docs, parallel canonical READMEs, stale skill shims, or compatibility wrappers unless a migration wrapper emits a fix-now warning and has an owner.
1. Record closeout tokens: `structure_refactor=complete`, `directory_responsibility_graph=<path>`, `path_mapping=<path>`, `scope_overlap_report=<path>`, `moves_applied=<count>`, `stale_path_sweep=<path>`, `validation_scope=<pass|fail>`, `validation_imports=<pass|fail>`, and `validation_docs=<pass|fail>`.
