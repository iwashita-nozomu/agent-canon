# structure-refactor
<!--
@dependency-start
contract skill
responsibility Documents directory-structure refactor workflow for this repository.
upstream design README.md shared skill canon index
upstream design catalog.yaml public skill family catalog
upstream design ../TASK_WORKFLOWS.md workflow routing contract
upstream design ../workflows/README.md workflow catalog routing guide
upstream design ../workflows/implementation-waterfall-workflow.md implementation gate contract
upstream design ../../AGENTS.md bounded handoff and subagent packet rules
upstream design ../canonical/CODEX_SUBAGENTS.md Codex runtime surface and subagent config ownership
upstream design ../../documents/SHARED_RUNTIME_SURFACES.md shared root runtime surface policy
upstream design refactor-loop.md behavior-preserving refactor loop
upstream design dependency-analysis.md dependency and change-impact packets
upstream design prose-reasoning-graph.md graph-backed prose and README analysis
upstream implementation ../../tools/agent_tools/check_design_doc_claims.py validates structure-related design evidence claims
downstream implementation ../../.agents/skills/structure-refactor/SKILL.md exposes this workflow as a runtime skill
@dependency-end
-->

## Reader Map

- Purpose: route repository layout, responsibility-map, root-view, and
  directory README changes through a structure contract.
- Section path: start with Purpose, Evidence Sources, Use When, Pre-Task
  Structure Repair Contract, Required Structure Contract, and Structure Review
  Gate; use Default Sequence, Move Rules, Multi-Agent Review, and Closeout
  Tokens for execution.
- Use when: repo structure, path ownership, AgentCanon root views, `.codex` /
  `.agents` boundaries, or directory responsibility evidence must change.
- Boundary: this skill classifies and validates structure surfaces; generic
  behavior-preserving mechanics belong to `refactor-loop`.

## Purpose

`structure-refactor` is the skill for changing or repairing repository
structure by responsibility. It treats repo roots, directories, directory
READMEs, dependency manifests, AgentCanon shared surfaces, project runtime
views, responsibility scopes, imports, and reader navigation as one refactor
surface. It also classifies personal Codex runtime state such as `~/.codex`
when that state may explain routing or skill discovery, while keeping personal
state out of shared repository canon unless the user explicitly asks for a
personal runtime edit.

The skill boundary is mechanical. It does not own generic behavior-preserving
refactor mechanics; use
`refactor-loop` for safety contracts, `dependency-analysis` for impact packets,
`prose-reasoning-graph` for README / prose graph diagnostics, and
`document-canon-cleanup` for stale or duplicate document surfaces. Those paired
skills define the boundary of this skill: select `structure-refactor` when the
repository layout itself is part of the requested change, when a task cannot
start because AgentCanon's expected repository structure no longer matches the
checkout, when project `.codex` views and personal `~/.codex` state must be
separated before routing or subagent work, or when mechanical evidence shows a
responsibility conflict that documentation edits alone cannot repair; the next
section defines that mechanical evidence packet.

When this skill is reached from `$agent-log-analysis`, require the log-analysis
`Finding Route Packet` with `finding_class=structure_boundary`. Treat the
structured evidence cell as the trigger and then switch to this skill's structure
contract, responsibility graph, path mapping, and validation gates. Launch
mechanics stay with `$subagent-bootstrap`; log interpretation stays with
`$agent-log-analysis`.

## Evidence Sources

The trigger, move rules, and handoff requirements below are checked against this
source packet:

- `agents/COMMUNICATION_PROTOCOL.md` `Structure Intake Packet` is the
  canonical ordinary-task structure-reading entrypoint. It uses the tools below
  to classify structure before broad prose reading; this skill takes over when
  the packet shows a real layout, scope, view, or responsibility refactor.
- `responsibility-scope.toml` and `responsibility_scope.py` show primary scope
  ownership, `exclude_paths`, required coverage, and overlap findings.
- `documents/repo-structure-contract.toml` and
  `repo_structure_contract.py` show whether the checkout still satisfies the
  expected standalone, template, or derived-repository layout before a task
  creates, moves, or ignores paths.
- Project `.codex/config.toml`, `.codex/agents/*.toml`, `.agents/skills/`,
  and their symlink targets show the repo-local Codex runtime surface. In this
  template those paths are AgentCanon shared views.
- `~/.codex/config.toml`, `~/.codex/skills/`, user rules, and hook trust state
  are personal runtime surfaces. Inspect only keys, paths, and skill IDs needed
  for conflict triage; do not print secrets, auth state, history, logs, or
  cache contents. Do not mirror personal state into the repo.
- `import_responsibility.py` shows whether directories still need distinct
  import boundaries.
- Recursive directory `README.md`, `AGENTS.md`, and dependency manifests show
  whether a parent directory can honestly summarize its children.
- `AGENTS.md`, `agents/TASK_WORKFLOWS.md`, `agents/workflows/README.md`, and
  `agents/workflows/implementation-waterfall-workflow.md` define the workflow
  fields, bounded handoff rules, and packet requirements that structure
  refactors must freeze before implementation.
- `refactor-loop.md` defines behavior-preserving refactor safety contracts.
- `check_design_doc_claims.py` shows whether a design document's structural
  claim is backed by code, dependency-header closure, and parent-document
  alignment before the refactor packet is accepted.

## Use When

- A user asks to refactor repository structure, repo layout, or a repo-refactor
  skill, not only update explanatory docs.
- The evidence sources above show that directory responsibilities must be
  split, merged, or moved.
- A directory README no longer matches the files below it.
- `responsibility-scope.toml` or root-view layout creates overlapping ownership.
- A shared canon path, root symlink view, tool directory, skill directory, or
  document hierarchy is being reorganized.
- A prompt, skill, tool, subagent, or hook routing issue may come from a
  boundary between project `.codex` / `.agents` views and personal `~/.codex`
  configuration.
- A repo task is about to start, but expected AgentCanon paths, template root
  views, `vendor/agent-canon/`, `.gitmodules`, root `AGENTS.md`, or documented
  source/owned directories are missing, stale, moved, or unexpectedly local.
- An agent is tempted to recreate a missing file or implement in a nearby
  directory because the expected canonical path is absent.
- A design doc justifies a structure change, route shift, directory ownership
  change, or root-view change and needs code/dependency-backed evidence before
  the refactor slice is selected.

## Pre-Task Structure Repair Contract

Use this mode before the ordinary task when the checkout no longer matches the
structure AgentCanon expects:

```text
structure_repair_root=<repo-root>
structure_surface=<repo-source|agentcanon-shared|project-runtime-view|personal-runtime|mixed|unknown>
detected_repo_profile=<standalone-agent-canon|template|derived|unknown>
drift_symptom=<missing-path|wrong-root-view|submodule-state|scope-overlap|stale-document-route|personal-runtime-conflict|project-user-config-conflict|other>
expected_owner=<agent-canon|template|derived-repo|personal-runtime|unknown>
contract_check=<artifact path>
scope_check=<artifact path>
import_check=<artifact path|not_applicable>
personal_runtime_check=<artifact path|not_applicable>
missing_path_triage=<artifact path>
repair_action=<link-root|agent-canon-update|responsibility-scope-fix|document-route-fix|project-runtime-fix|personal-runtime-fix|structure-refactor|defer>
ordinary_task_status=<blocked_until_repair|allowed_after_repair|deferred_with_issue>
```

If a missing path is involved, follow `CODEX_WORKFLOW.md` `Missing File Or Path
Triage` before recreating anything. For AgentCanon-owned root views or submodule
state, use the AgentCanon update route instead of creating a template-local
replacement. For `~/.codex`, treat user config, user skills, hook trust state,
history, logs, auth, and caches as personal runtime state. Only edit those
files when the user explicitly asks to fix personal Codex configuration and the
planned change is not a shared repo contract.

## Required Structure Contract

Write this before moving files:

```text
structure_refactor_root=<repo-or-subtree>
structure_surface=<repo-source|agentcanon-shared|project-runtime-view|personal-runtime|mixed>
behavior_contract=<what must keep working>
directory_responsibility_graph=<artifact path>
primary_responsibility_map=<directory -> responsibility>
recursive_readme_sources=<README/AGENTS/dependency manifest paths>
allowed_structural_delta=<moves, splits, merges, renames>
forbidden_semantic_delta=<behavior, policy, API, validation changes not allowed>
path_mapping=<old path -> new path, or unchanged with reason>
scope_delta=<responsibility-scope additions/removals/exclude_paths>
reader_delta=<README/index/navigation updates>
runtime_boundary=<project .codex/.agents views vs personal ~/.codex state>
validation_gate=<scope/import/docs/tests/build commands>
```

## Structure Review Gate

Use this gate whenever the task asks for structure review, a structure review
skill, a repo-layout review, or final approval of a structure refactor. The
review is findings-first and must decide whether the structure contract is
actionable before edits or acceptable before closeout.

```text
structure_review_root=<repo-or-subtree>
structure_review_surface=<repo-source|agentcanon-shared|project-runtime-view|personal-runtime|mixed>
reviewed_contract=<artifact path>
directory_responsibility_graph=<artifact path>
source_view_boundary_check=<artifact path>
path_mapping=<artifact path>
scope_overlap_report=<artifact path>
reverse_edge_check=<artifact path>
design_claim_evidence=<check_design_doc_claims artifact path|not_applicable>
stale_surface_sweep=<artifact path>
generated_artifact_boundary=<artifact path>
validation_scope=<pass|fail|not_run>
validation_imports=<pass|fail|not_run>
validation_docs=<pass|fail|not_run>
reviewer_decision=<approve|revise|block>
```

Reject the packet with `reviewer_decision=revise` or
`reviewer_decision=block` when any of these findings is present:

- The review reads only nearby files or top-level prose and does not include a
  recursive directory responsibility graph.
- The target path is chosen from naming aesthetics, proximity, or chat
  impression instead of responsibility, source ownership, and dependency
  evidence.
- AgentCanon source files, template root views, project `.codex` / `.agents`
  views, and personal `~/.codex` state are not classified before a shared
  surface is edited.
- `path_mapping` omits unchanged legacy paths, reverse edges, import fallout,
  public entrypoints, document links, generated output locations, or caller
  chains affected by the move.
- `scope_overlap_report` ignores `exclude_paths` or leaves a tracked file under
  multiple primary responsibilities.
- A responsibility conflict is papered over by docs text while source layout,
  route alias, dependency header, checker, or workflow ownership stays wrong.
- Generated reports, log archives, notebooks, or eval outputs are treated as
  structure sources instead of evidence artifacts.
- The packet leaves `_old`, `_copy`, backup docs, stale root views, duplicate
  READMEs, compatibility wrappers, or old route names without a fix-now owner
  and removal plan.
- The reviewer accepts tool success as reader-flow approval without a separate
  structure judgement.

Approve only when every changed or intentionally unchanged path is covered by
the contract, old and new routes are both accounted for, the source/view
boundary is explicit, and the validation commands above are either passing or
recorded as task-appropriate `not_run` evidence with a reason.

## Default Sequence

1. Identify the requested root and non-goals.
1. Route before reading broad prose. For prompt-derived routing, run
   `python3 tools/agent_tools/route.py --prompt "<request>" --format json`.
   For proposed tool or skill names such as `repo_refactor_skill.py`, run
   `python3 tools/agent_tools/route.py --name <candidate>`. If these tools do
   not route repo-refactor or `~/.codex` boundary work to
   `structure-refactor`, fix the deterministic router before compensating with
   more instructions.
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
1. If `~/.codex` is implicated, inspect only non-secret routing metadata:
   user config keys, project entries, user skill IDs, and project `.codex`
   symlink targets. Classify the outcome as `no_conflict`,
   `personal-runtime-fix`, `project-runtime-fix`, or `defer`. Do not scan
   personal history, sessions, auth, logs, or caches for structure evidence.
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

1. Propose a responsibility-preserving path mapping.
1. Before the first edit and again before closeout, run the Structure Review
   Gate. Do not approve a structure refactor whose packet is missing recursive
   responsibility evidence, source/view boundary classification, path mapping,
   scope overlap review, reverse-edge review, stale-surface sweep, or explicit
   structure judgement.

1. Hand wave planning to `refactor-loop`. This skill owns the validated
   structure surface classification, root/scope contract, path mapping, runtime
   boundary, and structure validation gates. `refactor-loop` owns repair batch
   sizing, `blocked_by`, sequential/parallel wave choice, and write-capable
   subagent orchestration.
1. Use write-capable subagents only for disjoint waves with explicit
   `allowed_paths`; keep root/scope contract, personal-runtime boundary, and
   final judgment with the parent or reviewer. After each wave, rerun the
   relevant scope, import, document inventory, dependency header, docs, and
   runtime alignment checks before starting the next wave.

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
- structure review gate and reject/approve judgement
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
structure_review_decision=<approve|revise|block>
directory_responsibility_graph=<path>
path_mapping=<path>
scope_overlap_report=<path>
source_view_boundary_check=<path>
reverse_edge_check=<path>
moves_applied=<count>
stale_path_sweep=<path>
validation_scope=<pass|fail>
validation_imports=<pass|fail>
validation_docs=<pass|fail>
```
