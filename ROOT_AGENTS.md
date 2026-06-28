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

## Reader Map

- This file owns the template-root runtime entrypoint for Codex and points each
  runtime contract to its owner surface and checker.
- Start with Scope Discipline, then use the runtime owner map only to find the
  surface that owns the next decision. Task entry, base runtime packet, shared
  canon flow, closeout evidence, and validation commands are selected by the
  active profile or touched surface; they are not a default checklist.
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

Default to design-complete, responsibility-bounded work for substantive
changes. Completion is proportional to the changed surface: behavior or code
changes must have coherent behavior, design/OOP boundary, ownership boundary,
and required tests or docs; doc-only, format-only, and explicit small-scope
changes need the owner/path/design-boundary note and validation that exercises
that surface. Use "small", "quick", or "parent-direct" only as routing labels;
needed design still comes from the changed surface.

Design-complete stays scoped to the owning abstraction. Find that abstraction and finish
the requested behavior inside that replaceable responsibility unit; stop before
unrelated audits, historical cleanup, or adjacent workflow repair unless the
user asked for that scope or a blocking finding makes it necessary.

Owner-map entries, skill command packets, validation commands, and CI jobs are
routing menus, not automatic worklists. Run or read only the item that changes
the next decision: edit path, fix, validation, PR state, or explicit deferral.

Use parent-direct work when the ownership path and design boundary are clear and
the work stays inside one replaceable responsibility unit. Use multi-agent waves
only when the user asks for them, or when independent, replaceable workstreams
can run in parallel without expanding scope or weakening design responsibility.
Parallelism authorizes split execution while parent responsibility remains
single-owner; use subagents for distinct decisions instead of repeating the same
deterministic read, checker, or search.

Proceed after the selected evidence passes, and reserve repeated sync logs or
repo-wide audits for explicit user scope or blocking findings. Hook, archive, or
dashboard failures expand the task only when they
block the selected edit, validation, or PR route; otherwise record a concrete
deferral.

## Context Construction

Context construction is the primary runtime concern. Use
`vendor/agent-canon/agents/COMMUNICATION_PROTOCOL.md` as the schema owner for
context visibility, pre-edit investigation packets, and fresh subagent
capsules.

Build prompt context for shape, ownership, and traceability, not smallness.
LLM-visible context may be large when the next decision requires it, but each
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

## Shared Canon Flow

AgentCanon source changes are made in `vendor/agent-canon/`, reviewed through
the AgentCanon branch / PR workflow, then reflected in the template through the
submodule pin and shared root views. Root view repair is owned by:

```bash
bash tools/sync_agent_canon.sh link-root
bash tools/sync_agent_canon.sh check
```

Run these commands when AgentCanon source, the submodule pin, or shared root
views changed or appear stale. Reserve shared-canon sync for changed or stale
shared surfaces.

## Closeout Evidence

Closeout cites only evidence required by the active runtime profile and touched
surfaces. Create run bundles, dependency reviews, subagent lifecycle records,
log archive syncs, shared-canon syncs, or full validation evidence only when the
selected route requires them.

When the task used no subagents, close with a short
parent-direct/no-subagents note when closeout evidence is selected.

For CI and hook failures, first decide whether the failure belongs to the
changed surface or blocks the requested PR/update. Stale, duplicated, or legacy
check items are refactor findings; run the canonical shared script, and compare
old and new paths only when the refactor itself requires that comparison.
Mechanical readiness is owned by `task_close.py` and
`report_artifact_checks.py` when a run bundle closeout is selected.

## Validation Command Menu

These are common commands, not a default checklist. Select the narrowest command
that validates the changed responsibility unit, active profile, or blocking
finding.

- `python3 vendor/agent-canon/tools/agent_tools/check_agent_runtime_alignment.py`
- `python3 vendor/agent-canon/tools/agent_tools/repo_structure_contract.py --root vendor/agent-canon --contract vendor/agent-canon/documents/repo-structure-contract.toml`
- `python3 vendor/agent-canon/tools/agent_tools/responsibility_scope.py --root .`
- `bash tools/sync_agent_canon.sh check`
- `python3 vendor/agent-canon/tools/agent_tools/task_close.py ...`
