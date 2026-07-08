<!--
@dependency-start
contract agent-runtime
responsibility Documents Agent Instructions for this repository.
upstream design README.md repository entrypoint and clone/update guidance.
upstream design documents/SHARED_RUNTIME_SURFACES.md shared AgentCanon surface policy.
upstream design documents/runtime-profiles-and-check-matrix.md runtime profile and validation routing policy.
upstream design documents/template-agent-canon-audit-resolution.md audit resolution ledger for profile and gate simplification.
upstream design issues/README.md durable AgentCanon operational finding storage.
downstream implementation tools/sync_agent_canon.sh updates AgentCanon submodule pins and shared root views.
downstream implementation tools/agent_tools/task_start.py emits task workflow packets.
downstream implementation tools/agent_tools/bootstrap_agent_run.py creates run bundles.
downstream implementation tools/agent_tools/task_close.py validates run-bundle closeout gates.
downstream implementation tools/agent_tools/check_agent_runtime_alignment.py validates runtime owner-map alignment.
downstream implementation .codex/hooks/branch_worktree_guard.py blocks unconfirmed branch and worktree creation.
@dependency-end
-->

# Agent Instructions

This file is the template-root runtime entrypoint for Codex. The shared agent
canon lives in `vendor/agent-canon/`; root discovery paths are runtime views into
that pin.

Path note: `documents/...` entries in AgentCanon-owned packets are logical
AgentCanon source paths. In standalone AgentCanon they resolve under `documents/`.
In template or derived repo roots they resolve under
`vendor/agent-canon/documents/` unless `documents/README.md` lists a
template-owned active contract.

## Codex Loading Priority

Codex instruction loading is runtime-defined and must be reflected in this
repository's rule layout:

1. User/global Codex guidance loads from Codex home before repository guidance.
1. Project guidance loads from the project root down to the current working
   directory. In each directory, an override file wins over `AGENTS.md`, and
   Codex includes at most one instruction file per directory.
1. Files closer to the current working directory appear later in the combined
   prompt and therefore carry the local override surface.
1. Skills are selected from metadata first; `SKILL.md` is read only after the
   skill is chosen.

For this template, `/AGENTS.md` is the top repo instruction surface and is a
runtime view of `vendor/agent-canon/ROOT_AGENTS.md`. Nested files such as
`/.github/AGENTS.md` are local overlays for that subtree. When Codex is started
inside `vendor/agent-canon/`, the AgentCanon source tree's own `AGENTS.md`
becomes the repo-local entrypoint for that submodule checkout. README files,
closed issues, reports, notes, and generated inventories are evidence or human
navigation unless this file or an owner surface explicitly routes to them.

## Reader Map

- This file owns the template-root runtime entrypoint for Codex and points each
  runtime contract to its owner surface and checker.
- Start with Scope Discipline and Structure-First Scope Formation, then use the
  runtime owner map only to find the surface that owns the next decision. Task
  entry, base runtime packet, shared canon flow, closeout evidence, and
  validation commands are selected by the active profile or touched surface;
  they are not a default checklist.
- Read it at the beginning of repository work or when resolving whether a rule
  belongs to the root view, AgentCanon source, a generated task packet, or a
  checker.
- This entrypoint routes to owner surfaces; workflow stages, skills, role
  behavior, validation matrices, and closeout gates are updated in their owner
  documents first.

## Scope Discipline

Scope Discipline takes precedence over this file's owner map and command lists.
If an owner surface names required evidence for its own workflow, apply that
requirement only after the active task, profile, or touched surface selects that
workflow.

The user's request has authority over agent-side interpretation. Carry the
user's literal request clauses into routing, edit-target selection, validation,
and closeout. Treat changes to the target, requested scope, or success
condition as authorized only by explicit user evidence or owner-surface
evidence; convenience, nearby files, prior habits, and inferred intent carry
zero authority. Scope is not frozen by the first plausible reading of the
request: it is formed from request clauses plus repository structure, owner
surface evidence, dependency edges, root-view state, and checker evidence.
Adding a surface required by that evidence is part of scope formation; omitting
it because it was not in the first edit guess is a scope error.

## Structure-First Scope Formation

Fix structure before ordinary task work when the repository shape, root views,
path ownership, directory responsibility, submodule state, `.codex` / `.agents`
views, or missing canonical paths affect where the task belongs. The reference
route is `vendor/agent-canon/agents/skills/structure-refactor.md`
`Pre-Task Structure Repair Contract`, backed by
`vendor/agent-canon/documents/repo-structure-contract.toml`,
`vendor/agent-canon/tools/agent_tools/repo_structure_contract.py`,
`vendor/agent-canon/tools/agent_tools/responsibility_scope.py`, and
`vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md` `Missing File Or Path
Triage`.

Structure-first repair is not an optional broad audit. It is the intake path
that decides the owning abstraction and edit surface before implementation,
document edits, validation, PR cleanup, or subagent handoff. If the expected
AgentCanon root view, `vendor/agent-canon/` state, `.gitmodules`, shared root
copy, directory README responsibility, or responsibility-scope map is stale or
missing, record the structure symptom and repair it through the owner route
before proceeding with the ordinary task. If structure evidence shows no drift
or no ownership impact, cite that evidence and continue without repo-wide
cleanup.

Default to design-complete, responsibility-bounded work for substantive
changes. Completion is proportional to the changed surface: behavior or code
changes must have coherent behavior, design/OOP boundary, ownership boundary,
and required tests or docs; doc-only, format-only, and explicit bounded-route
changes need the owner/path/design-boundary note and validation that exercises
that surface. Parent-direct is only an execution route; needed design still
comes from the changed surface.

Design-complete is resolved through the owning abstraction. Find the full
replaceable responsibility unit from structure and owner evidence, then finish
the requested behavior inside that unit. Keep optional audits, historical
cleanup, and adjacent workflow repair separate unless structure evidence,
owner-surface evidence, or a blocking finding makes them part of the same
responsibility unit.

Owner-map entries, skill command packets, validation commands, and CI jobs are
routing menus, not automatic worklists. Run or read only the item that changes
the next decision: edit path, fix, validation, PR state, or explicit deferral.

For repo-changing implementation, patch, or doc-edit work, parent is the default
orchestrator and integrator, with implementation assigned through the selected
write-capable handoff route. Parent owns route selection, monitoring, write-capable
agent launch or recorded blocker
evidence, additional instructions, integration, review gates, validation
evidence, and closeout. After owner boundary, replaceable responsibility
unit, context packet, and validation route are evidenced, implementation/doc-edit
slices are handed to `spark_worker` or `worker`.

Parent-direct repository edits are an exception with recorded evidence:
`PARENT_DIRECT_WRITE_EXCEPTION_REQUIRED=yes` and
`PARENT_DIRECT_WRITE_EXCEPTION=<explicit_user_approval|runtime_blocker>`, plus
owner boundary, exception rationale, targeted validation, and fallback status.

Split work only when coordination requires it; otherwise keep one replaceable
responsibility unit in one packet and one writer unless independent workstreams
have disjoint write scope, dependency order, integration order, and
review/validation gates. Use subagents for distinct decisions and
write-capable handoffs; reserve deterministic reads/checkers/searches for the
owner-selected evidence path.

Proceed after the selected evidence passes, and reserve repeated sync logs or
repo-wide audits for owner-selected structure repair, explicit user evidence, or
blocking findings. Hook, archive, or dashboard failures change the task route
only when they block the selected edit, validation, or PR route; otherwise
record a concrete deferral.

## Design Integrity Gate

Before implementation or write-capable handoff, prove that the work is derived
from an owning responsibility model rather than from a nearby file, current
finding, or chat impression. Full staged and subagent-implemented work uses the
`Abstract Design Frame`, `Implementation Source Packet`,
`Design Side-Effect Map`, and `Design-To-Implementation Trace`. A
parent-direct write exception may use the short owner/path/design-boundary note
only after the exception route is recorded; the note is exception evidence and
not authorization to bypass `spark_worker` or `worker`.

Treat API shape, responsibility boundary, path layout, naming, algorithm,
test oracle, dependency direction, runtime contract, and config-surface gaps as
design issues. The valid route is `design_issue_blocker=<issue>` with evidence,
then return to the owning design/review gate. Local fallback, wrapper, helper,
branch, compatibility route, test relaxation, docs overwrite, and
implementation shortcut are outside the gate.

Algorithm repairs start from the algorithm contract and the implemented
mechanism. Establish the public entrypoint, state transition or recurrence,
invariants, stopping or acceptance rule, and failure semantics; then compare the
current implementation to that contract and identify the first code-side
mechanism that must change. Existing tests are evidence for contract
classification and regression placement. Test edits, new expected values,
tolerance changes, and oracle design enter after the algorithm contract and
repair mechanism are fixed.

## Context Construction

Context construction is the primary runtime concern. Use
`vendor/agent-canon/agents/COMMUNICATION_PROTOCOL.md` as the schema owner for
context visibility, pre-edit investigation packets, and fresh subagent
capsules.

Build prompt context for shape, ownership, and traceability.
LLM-visible context may be large when the next decision requires it, and each
piece must tie to a request clause, owner, source packet, exact file section, or
artifact path. Raw search output, full dashboards, logs, long histories, and
broad workflow packets stay in local/tool context until selected.

Treat AGENTS/root entrypoints as routing and context-construction guidance.
Keep missing packet fields in the owning packet, hand off structured context
capsules instead of broad chat summaries, and treat each subagent launch as
fresh.

## Repository Discovery and Reading

Start from repository structure, dependency headers, and the runtime owner map
before text search. In this repository, start with `find`,
`git grep`, or targeted `grep` from known owner directories after the structure
route is clear.

When structure may determine the owner, run the structure intake route before
manual broad reading: use `repo_structure_contract.py` for expected layout,
`responsibility_scope.py` for ownership coverage and overlaps, and
`import_responsibility.py` when import boundaries are implicated. Classify a
missing path through `CODEX_WORKFLOW.md` `Missing File Or Path Triage` before
creating it or treating it as absent, so the route records whether the path is
an AgentCanon source, template root view, generated artifact, project-local
surface, or personal runtime state.

For long documents, read the reader map and section outline first. Split reads
only at stable semantic boundaries such as headings, tables, generated blocks,
or independent records. Keep a mathematical derivation, OOP abstraction,
proof obligation, or replacement unit together even when the chunk is long.

## Runtime Owner Map

| Contract | Owner Surface | Evidence / Checker |
| -------- | ------------- | ------------------ |
| workflow family, spawn budget, role topology | `vendor/agent-canon/agents/task_catalog.yaml` | `task_start.py`; `bootstrap_agent_run.py`; `check_agent_runtime_alignment.py` |
| task bootstrap and CLI entrypoints | `vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md`; `task_start.py`; `bootstrap_agent_run.py` | generated task packet |
| subagent lifecycle, same-role instances, wave ledger | `vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md`; `team_manifest.yaml`; `schedule.md`; `workflow_monitoring.md` | `workflow_monitor.py`; closeout lifecycle evidence |
| role behavior and stage conditions | `vendor/agent-canon/.codex/agents/*.toml`; `vendor/agent-canon/agents/agents_config.json` | `check_agent_runtime_alignment.py` |
| skill routing and public skill surface | `vendor/agent-canon/agents/skills/catalog.yaml`; `vendor/agent-canon/.agents/skills/*/SKILL.md` | `python3 tools/agent_tools/route.py --prompt`; `check_agent_runtime_alignment.py` |
| internal workflow routines | `vendor/agent-canon/agents/internal-routines/README.md` | `repo_structure_contract.py`; runtime alignment |
| implementation flow graph and source packet | run bundle design packet; `vendor/agent-canon/agents/workflows/implementation-waterfall-workflow.md`; `vendor/agent-canon/agents/COMMUNICATION_PROTOCOL.md` | design review; dependency review |
| search, read scope, and reuse survey | semantic-index, local-llm search, dependency review artifacts | `run_repo_dependency_review.sh`; bounded search artifacts |
| repo structure and root views | `vendor/agent-canon/documents/repo-structure-contract.toml`; `responsibility-scope.toml`; `documents/shared-runtime-surfaces.toml` | structure/scope/import tools; `sync_agent_canon.sh` |
| branch/worktree creation route | `vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md`; `vendor/agent-canon/.codex/hooks/branch_worktree_guard.py`; `vendor/agent-canon/agents/skills/worktree-health.md` | `branch_creation_reason=<reason>` / `worktree_creation_reason=<reason>`; PreToolUse guard; `check_convention_compliance.py` |
| runtime profile and validation route | `vendor/agent-canon/documents/runtime-profiles-and-check-matrix.md` | profile-selected validation |
| report and closeout structure | `task_close.py`; `report_artifact_checks.py`; run bundle `closeout_gate.md` | profile-selected closeout gate |
| shared AgentCanon update | `vendor/agent-canon/tools/update_agent_canon.sh`; `tools/sync_agent_canon.sh`; AgentCanon PR workflow | submodule pin and PR evidence |

This map is a routing index, not a checklist. Stage rules, skill selection, role
behavior, validation matrices, and closeout gates are updated in their owner
surfaces first, but the evidence/checker column is used only when the active
profile, touched surface, or blocking finding selects it.

## Task Entry

Task bootstrap commands and CLI-specific entry behavior are owned by
`vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md`. Generated task packets
from `task_start.py` or `bootstrap_agent_run.py` provide the active
`workflow=...`, `skills=...`, `review=...`, source packet, wave plan, and
validation route.

Create a task packet or run bundle when the user asks for kickoff/run-bundle evidence, the
task needs wave coordination, or the selected workflow requires more than a
short owner/design/validation note.

## Base Runtime Packet Owner

- `README.md`
- `vendor/agent-canon/agents/README.md`
- `vendor/agent-canon/agents/TASK_WORKFLOWS.md`
- `vendor/agent-canon/agents/canonical/CODEX_WORKFLOW.md`
- `vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md`
- `vendor/agent-canon/documents/runtime-profiles-and-check-matrix.md`
- `vendor/agent-canon/documents/SHARED_RUNTIME_SURFACES.md`

Task-specific packet expansion is owned by the generated task packet,
semantic-index/local-llm search, and dependency review artifacts when those
routes are selected. The base packet is not a required reading list for every
task.

## Template Context

- Human-facing primary language is Japanese.
- The default integration branch is `main`.
- Template-default implementation lives in `python/`.
- Template-default environment and runtime guidance lives in `docker/`.
- Repo-wide durable contracts live in `documents/`.
- Experiment GPU allocation belongs to the scheduler or caller environment. Do
  keep available GPUs visible and keep topic code / checked-in config free of
  single-GPU or serial execution throttles. Serial debugging or a recorded
  environment limit is required before narrowing GPU visibility or worker
  parallelism.

## Implementation Discipline

- Keep production implementations aligned with the active design contract. If a
  change would deviate from that contract, update the design contract first or
  report the blocker.
- Keep algorithm branches, solver choices, tolerances, diagnostics, and runtime
  paths part of the product contract rather than adding test-only or
  experiment-only production behavior.
- For algorithm fixes, enter through contract, recurrence / state transition,
  invariant, and failure-semantics evidence before changing tests. Tests record
  the selected oracle and regression cases after the algorithm repair route is
  known.
- When an exploratory experiment is needed, keep it outside the production code path
  and label it as experimental evidence. Production code must reflect the
  approved design, not a temporary workaround.

## Shared Canon Flow

AgentCanon source changes are made in `vendor/agent-canon/`, reviewed through
the AgentCanon branch / PR workflow, then reflected in the template through the
submodule pin and shared root views. Root view repair is owned by:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

Run these commands when AgentCanon source, the submodule pin, `.gitmodules`,
shared root views, shared root-copy surfaces, or parent root sync state changed.
These changes always open `agentcanon_structure_followup=required`; record
`agentcanon_structure_followup=pass` only after `link-root` and `check` pass
from the template / derived parent root. For standalone AgentCanon source PRs,
the parent-root follow-up runs after the source change is integrated or while
preparing the parent pin/root-view PR. Reserve shared-canon sync for changed or
stale shared surfaces, and treat the gate as required evidence when those
surfaces changed.

## Closeout Evidence

Closeout cites only evidence required by the active runtime profile and touched
surfaces. Create run bundles, dependency reviews, subagent lifecycle records,
log archive syncs, shared-canon syncs, or full validation evidence only when the
selected route requires them.

For repo-changing implementation, patch, or doc-edit work, closeout cites the
write-capable handoff route, integration result, review gate, validation
evidence, and subagent lifecycle evidence.

For AgentCanon source, submodule pin, `.gitmodules`, root runtime view,
root-copy surface, or parent root sync changes, closeout also cites
`agentcanon_structure_followup=required` and
`agentcanon_structure_followup=pass`, including the parent-root
`bash tools/sync_agent_canon.sh link-root` and
`bash tools/sync_agent_canon.sh check` evidence.

A no-subagents closeout is valid only for routing-only/advisory tasks, read-only
audits, or recorded parent-direct write exceptions; cite the advisory/read-only
reason or recorded `PARENT_DIRECT_WRITE_EXCEPTION` evidence.

If write-capable handoff was blocked, closeout records
`WRITE_SUBAGENT_AUTHORIZATION=required` or
`write_capable_handoff_blocker=<gate>` plus `fallback_exit_status`; it records
the blocked-handoff fallback instead of ordinary `parent-direct/no-subagents`
completion for repo-changing work.

For CI and hook failures, first decide whether the failure belongs to the
changed surface or blocks the requested PR/update. Stale, duplicated, or legacy
check items are refactor findings; run the canonical shared script, and compare
old and new paths only when the refactor itself requires that comparison.
Mechanical readiness is owned by `task_close.py` and
`report_artifact_checks.py` when a run bundle closeout is selected.

## Validation Command Menu

These are common commands, not a default checklist. Select the most targeted command
that validates the changed responsibility unit, active profile, or blocking
finding.

- `python3 vendor/agent-canon/tools/agent_tools/check_agent_runtime_alignment.py`
- `python3 vendor/agent-canon/tools/agent_tools/repo_structure_contract.py --root vendor/agent-canon --contract vendor/agent-canon/documents/repo-structure-contract.toml`
- `python3 vendor/agent-canon/tools/agent_tools/responsibility_scope.py --root .`
- `bash tools/sync_agent_canon.sh check`
- `python3 vendor/agent-canon/tools/agent_tools/task_close.py ...`
