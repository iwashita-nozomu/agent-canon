---
name: structure-refactor
description: Use when repository structure review, repo-refactor requests, expected AgentCanon layout, directory responsibilities, canonical README ownership, path layout, root views, project .codex/.agents views, personal ~/.codex runtime boundaries, or responsibility-scope maps must be reviewed, repaired, or refactored using structure contracts, recursive directory README analysis, source/view ownership checks, stale-surface sweeps, dependency manifests, and behavior-preserving move/rename gates.
---
<!--
@dependency-start
contract skill
responsibility Documents Structure Refactor runtime skill for this repository.
upstream design ../../../agents/skills/structure-refactor.md documents the human-facing skill canon
upstream design ../../../agents/skills/refactor-loop.md defines behavior-preserving refactor gates
upstream design ../../../agents/skills/dependency-analysis.md defines change-impact packets
upstream design ../../../agents/skills/prose-reasoning-graph.md defines directory README graph evidence
upstream design ../../../agents/canonical/CODEX_SUBAGENTS.md documents Codex runtime surface ownership
upstream design ../../../documents/SHARED_RUNTIME_SURFACES.md defines shared runtime views
upstream implementation ../../../tools/agent_tools/responsibility_scope.py validates responsibility scopes
upstream implementation ../../../tools/agent_tools/import_responsibility.py validates import boundaries
upstream implementation ../../../tools/agent_tools/check_design_doc_claims.py validates structure-related design evidence claims
@dependency-end
-->

# Structure Refactor

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill structure-refactor --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


1. Read `agents/skills/structure-refactor.md`.
1. Use this for structure review requests, repo-refactor requests, directory layout refactors, pre-task repair of AgentCanon expected repository-structure drift, directory responsibility splits or merges, canonical README ownership changes, root-view / submodule-view layout changes, project `.codex` / `.agents` view changes, personal `~/.codex` boundary triage, and responsibility-scope map changes.
1. When reached from `$agent-log-analysis`, require a `Finding Route Packet` with `finding_class=structure_boundary`, then use this skill's structure contract and validation gates. Keep log interpretation with `$agent-log-analysis` and launch mechanics with `$subagent-bootstrap`.
1. Route before reading broad prose. Use `python3 tools/agent_tools/route.py --prompt "<request>" --format json` for prompt-derived skill routing and `python3 tools/agent_tools/route.py --name <candidate>` for proposed route names. If repo-refactor, structure-review, or `~/.codex` boundary prompts do not route here, fix the deterministic router instead of adding prose-only workarounds.
1. Pair with `$refactor-loop`, `$dependency-analysis`, `$prose-reasoning-graph`, and `$document-canon-cleanup` when the evidence shows a real source-layout refactor, directory README/prose ownership change, or stale document-canon cleanup. For pre-task expected-layout drift, start with the compact structure repair checks below and add those paired skills only after the repair action requires them.
1. For pre-task structure repair, classify the checkout before reading broad packets or recreating missing paths:
   - run `python3 tools/agent_tools/repo_structure_contract.py --root <root> --format json > <run>/repo_structure_contract.json`; in template or derived roots where the contract is not a root view, add `--contract vendor/agent-canon/documents/repo-structure-contract.toml`
   - run `python3 tools/agent_tools/responsibility_scope.py --root <root> --format json > <run>/responsibility_scope.json`
   - run `python3 tools/agent_tools/import_responsibility.py --root <root> --format json > <run>/import_responsibility.json` when import boundaries are implicated
   - follow `agents/canonical/CODEX_WORKFLOW.md` `Missing File Or Path Triage` before creating or ignoring any missing path
   - if drift is AgentCanon-owned root views or submodule state, route to `$agent-canon-update`, `make agent-canon-ensure-latest`, and `bash tools/sync_agent_canon.sh link-root` / `check` before ordinary task work
1. If `~/.codex` is implicated, inspect only non-secret routing metadata: config keys, project entries, user skill IDs, and project `.codex` symlink targets. Do not read or print auth, history, sessions, logs, or caches. Treat `~/.codex` as personal runtime state and edit it only when the user explicitly asked for a personal Codex configuration fix.
1. Record the pre-task repair contract with `structure_repair_root`, `structure_surface`, detected repo profile, drift symptom, expected owner, contract/scope/import/personal-runtime artifacts, repair action, runtime boundary, and ordinary task status.
1. Build a recursive directory responsibility graph before editing:
   - collect every directory `README.md`, `AGENTS.md`, and dependency manifest under the proposed root
   - run `agent-canon structured-analysis document-inventory --root <root>`
   - run `python3 tools/agent_tools/responsibility_scope.py --root <root> --format json`
   - run or update a scope-overlap report that applies `exclude_paths`
   - run `python3 tools/agent_tools/prose_reasoning_graph.py check-document <readme-path> --out-dir <run>/prose/<readme-id> --profile all --stats-out <run>/prose/<readme-id>.stats.json` on changed directory README files
   - run `python3 tools/agent_tools/check_design_doc_claims.py --root <root> <design-doc>` when a design document justifies the structure change
1. Treat directory structure as a product contract. Fix `Behavior Contract`, `Allowed Structural Delta`, `Forbidden Semantic Delta`, `Path Mapping`, `Directory Responsibility Map`, and `Reader Impact` before moving files.
1. Derive target layout from responsibilities, not from path aesthetics:
   - split a directory when one README must describe unrelated primary responsibilities
   - merge directories when their READMEs describe the same primary responsibility and no separate validation/import boundary remains
   - keep cross-directory evidence or runtime surfaces in their own primary scope, and remove overlap by `exclude_paths` or explicit path mapping
1. Do not move files until reverse edges, import paths, public root views, docs links, and generated artifact paths have a repair plan.
1. For structure review, run the Structure Review Gate from `agents/skills/structure-refactor.md` before the first edit and before closeout. Reject shallow packets with `reviewer_decision=revise` or `reviewer_decision=block` when they lack recursive responsibility evidence, source/view boundary classification, explicit path mapping, scope-overlap review, reverse-edge review, stale-surface sweep, generated-artifact boundary, or an independent structure judgement.
1. Hand dynamic wave planning to `$refactor-loop`. This skill owns the validated structure surface classification, path mapping, runtime boundary, and structure validation gates; `$refactor-loop` owns repair batch sizing, `blocked_by`, sequential/parallel wave choice, and write-capable subagent orchestration.
1. For nontrivial structure refactors, use separate agents for recursive responsibility inventory, path mapping / structural design review, write-capable disjoint move/update waves, document-flow review, language-specific import/build fallout, and final stale-surface sweep. Each handoff must include `allowed_paths`, the structure contract, runtime boundary, validation commands, and explicit non-goals.
1. After each move/update wave, rerun:
   - `python3 tools/agent_tools/responsibility_scope.py --root <root>`
   - `python3 tools/agent_tools/import_responsibility.py --root <root>`
   - `agent-canon structured-analysis document-inventory --root <root>`
   - changed-file dependency header checks and docs check
1. Sweep old paths before closeout. Do not leave `_old`, `_copy`, backup docs, parallel canonical READMEs, stale skill shims, or compatibility wrappers unless a migration wrapper emits a fix-now warning and has an owner.
1. Record closeout tokens: `structure_refactor=complete`, `structure_review_decision=<approve|revise|block>`, `directory_responsibility_graph=<path>`, `path_mapping=<path>`, `scope_overlap_report=<path>`, `source_view_boundary_check=<path>`, `reverse_edge_check=<path>`, `moves_applied=<count>`, `stale_path_sweep=<path>`, `validation_scope=<pass|fail>`, `validation_imports=<pass|fail>`, and `validation_docs=<pass|fail>`.
