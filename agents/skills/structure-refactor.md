# structure-refactor
<!--
@dependency-start
responsibility Documents directory-structure refactor workflow for this repository.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design ../TASK_WORKFLOWS.md workflow routing contract
upstream design ../workflows/README.md workflow catalog routing guide
upstream design ../workflows/implementation-waterfall-workflow.md implementation gate contract
upstream design ../../AGENTS.md bounded handoff and subagent packet rules
upstream design refactor-loop.md behavior-preserving refactor loop
upstream design dependency-analysis.md dependency and change-impact packets
upstream design prose-reasoning-graph.md graph-backed prose and README analysis
downstream implementation ../../.agents/skills/structure-refactor/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Purpose

`structure-refactor` is the skill for changing or repairing repository
directory structure by responsibility. It treats directories, directory READMEs,
dependency manifests, root views, responsibility scopes, imports, and reader
navigation as one refactor surface.

The skill boundary is mechanical. It does not own generic behavior-preserving
refactor mechanics; use
`refactor-loop` for safety contracts, `dependency-analysis` for impact packets,
`prose-reasoning-graph` for README / prose graph diagnostics, and
`document-canon-cleanup` for stale or duplicate document surfaces. Those paired
skills define the boundary of this skill: select `structure-refactor` when the
directory layout itself is part of the requested change, when a task cannot
start because AgentCanon's expected repository structure no longer matches the
checkout, or when mechanical evidence shows a responsibility conflict that
documentation edits alone cannot repair; the next section defines that
mechanical evidence packet.

## Evidence Sources

The trigger, move rules, and handoff requirements below are checked against this
source packet:

- `responsibility-scope.toml` and `responsibility_scope.py` show primary scope
  ownership, `exclude_paths`, required coverage, and overlap findings.
- `documents/repo-structure-contract.toml` and
  `repo_structure_contract.py` show whether the checkout still satisfies the
  expected standalone, template, or derived-repository layout before a task
  creates, moves, or ignores paths.
- `import_responsibility.py` shows whether directories still need distinct
  import boundaries.
- Recursive directory `README.md`, `AGENTS.md`, and dependency manifests show
  whether a parent directory can honestly summarize its children.
- `AGENTS.md`, `agents/TASK_WORKFLOWS.md`, `agents/workflows/README.md`, and
  `agents/workflows/implementation-waterfall-workflow.md` define the workflow
  fields, bounded handoff rules, and packet requirements that structure
  refactors must freeze before implementation.
- `refactor-loop.md` defines behavior-preserving refactor safety contracts.

## Use When

- A user asks to refactor directory structure, not only update explanatory docs.
- The evidence sources above show that directory responsibilities must be
  split, merged, or moved.
- A directory README no longer matches the files below it.
- `responsibility-scope.toml` or root-view layout creates overlapping ownership.
- A shared canon path, root symlink view, tool directory, skill directory, or
  document hierarchy is being reorganized.
- A repo task is about to start, but expected AgentCanon paths, template root
  views, `vendor/agent-canon/`, `.gitmodules`, root `AGENTS.md`, or documented
  source/owned directories are missing, stale, moved, or unexpectedly local.
- An agent is tempted to recreate a missing file or implement in a nearby
  directory because the expected canonical path is absent.

## Pre-Task Structure Repair Contract

Use this mode before the ordinary task when the checkout no longer matches the
structure AgentCanon expects:

```text
structure_repair_root=<repo-root>
detected_repo_profile=<standalone-agent-canon|template|derived|unknown>
drift_symptom=<missing-path|wrong-root-view|submodule-state|scope-overlap|stale-document-route|other>
expected_owner=<agent-canon|template|derived-repo|unknown>
contract_check=<artifact path>
scope_check=<artifact path>
import_check=<artifact path|not_applicable>
missing_path_triage=<artifact path>
repair_action=<link-root|agent-canon-update|responsibility-scope-fix|document-route-fix|structure-refactor|defer>
ordinary_task_status=<blocked_until_repair|allowed_after_repair|deferred_with_issue>
```

If a missing path is involved, follow `CODEX_WORKFLOW.md` `Missing File Or Path
Triage` before recreating anything. For AgentCanon-owned root views or submodule
state, use the AgentCanon update route instead of creating a template-local
replacement.

## Required Structure Contract

Write this before moving files:

```text
structure_refactor_root=<repo-or-subtree>
behavior_contract=<what must keep working>
directory_responsibility_graph=<artifact path>
primary_responsibility_map=<directory -> responsibility>
recursive_readme_sources=<README/AGENTS/dependency manifest paths>
allowed_structural_delta=<moves, splits, merges, renames>
forbidden_semantic_delta=<behavior, policy, API, validation changes not allowed>
path_mapping=<old path -> new path, or unchanged with reason>
scope_delta=<responsibility-scope additions/removals/exclude_paths>
reader_delta=<README/index/navigation updates>
validation_gate=<scope/import/docs/tests/build commands>
```

## Default Sequence

1. Identify the requested root and non-goals.
1. If this is a pre-task drift repair, classify the repository structure before
   reading broad document packets:

```bash
python3 tools/agent_tools/repo_structure_contract.py --root <root> --format json \
  > <run>/repo_structure_contract.json
```

   In template or derived roots where the contract is not a checked-in root
   view, pass the vendored contract explicitly:

```bash
python3 tools/agent_tools/repo_structure_contract.py --root <root> \
  --contract vendor/agent-canon/documents/repo-structure-contract.toml \
  --format json > <run>/repo_structure_contract.json
```

   If the result shows only AgentCanon-owned root view or submodule drift, route
   to `agent-canon-update`, `make agent-canon-ensure-latest`, and
   `bash tools/sync_agent_canon.sh link-root` / `check` before continuing the
   ordinary task. If the result shows real source-layout conflict, continue with
   the structure refactor sequence below.
1. Collect recursive directory evidence:
   - every directory `README.md`
   - relevant `AGENTS.md` / `ROOT_AGENTS.md`
   - dependency manifests
   - `responsibility-scope.toml`
   - root-view / shared-surface manifests when present
1. Run the mechanical inventory:

```bash
agent-canon structured-analysis document-inventory --root <root> \
  --json-out <run>/document_inventory.json \
  --markdown-out <run>/document_inventory.md
python3 tools/agent_tools/responsibility_scope.py --root <root> --format json \
  > <run>/responsibility_scope.json
python3 tools/agent_tools/import_responsibility.py --root <root> --format json \
  > <run>/import_responsibility.json
```

1. Build or update a scope-overlap report after `exclude_paths` are applied.
   Any tracked file claimed by multiple primary scopes is a refactor finding,
   not a documentation note.

1. Run graph-backed prose diagnostics on the top README and any directory
   README whose responsibility changes:

```bash
python3 tools/agent_tools/prose_reasoning_graph.py check-document <readme-path> \
  --out-dir <run>/prose/<readme-id> \
  --profile all \
  --stats-out <run>/prose/<readme-id>.stats.json
```

   Each README gets its own `--out-dir`; do not merge diagnostics for unrelated
   directories into one evidence folder.

1. Propose the smallest responsibility-preserving path mapping.

1. Split work into waves:
   - root/scope contract wave
   - directory move wave
   - import/link repair wave
   - README/index repair wave
   - stale-path sweep wave

1. Use write-capable subagents only for disjoint waves with explicit
   `allowed_paths`; keep root/scope contract and final judgment with the parent
   or reviewer.

1. After each wave, rerun scope, import, document inventory, dependency header,
   and docs checks before starting the next wave.

## Move Rules

- Prefer responsibility-preserving moves over cosmetic grouping.
- Do not split a directory unless the child responsibilities cannot be
  faithfully summarized by one README.
- Do not merge directories when they still need distinct import, validation, or
  owner boundaries; those boundaries are evidence in `import_responsibility.py`,
  validation gates, and `responsibility-scope.toml`.
- If a cross-directory surface has a primary responsibility, give it an
  explicit scope and remove it from broad scopes with `exclude_paths`.
- Directory README text must match the recursive child responsibility graph,
  not merely list files.
- Generated reports are evidence, not structure sources. Do not move generated
  artifacts to make the source tree look cleaner.

## Multi-Agent Review

Use separate agents for:

- recursive responsibility inventory
- path mapping / structural design review
- write-capable move/update wave
- document-flow review of READMEs and indexes
- language-specific import/build review
- final stale-surface sweep

Each handoff must include `allowed_paths`, the structure contract, the current
path mapping, validation commands, and explicit non-goals. `AGENTS.md` requires
bounded path lists and packet-based subagent input, while the workflow docs above
require write-scope and integration-order records. These fields connect the
subagent write scope to the source packet above, so the parent can integrate
waves without relying on chat memory.

## Closeout Tokens

```text
structure_refactor=complete
directory_responsibility_graph=<path>
path_mapping=<path>
scope_overlap_report=<path>
moves_applied=<count>
stale_path_sweep=<path>
validation_scope=<pass|fail>
validation_imports=<pass|fail>
validation_docs=<pass|fail>
```
