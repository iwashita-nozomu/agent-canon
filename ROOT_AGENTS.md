# AgentCanon Live-Integration Repository Instructions
<!--
@dependency-start
contract agent-runtime
responsibility Routes an explicitly selected live AgentCanon parent integration to vendored canonical owners without re-owning procedures.
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar and responsibility boundary
upstream design documents/runtime/SHARED_RUNTIME_SURFACES.md explicit live-agent-canon integration boundary
upstream design documents/runtime/shared-runtime-surfaces.toml live integration manifest
upstream design documents/runtime/task-contract-observation.md task contract observation and archive route
upstream design documents/runtime/runtime-log-archive.md durable agent-canon-log ownership
upstream design documents/tools/search-coordination.md coordinated search owner
upstream design documents/conventions/software-engineering-principles.md contract-complete engineering decision policy
upstream design agents/internal-routines/chatgpt-codex-routing.md request modality and Codex handoff owner
upstream design agents/canonical/CODEX_WORKFLOW.md executable task and closeout owner
upstream design agents/canonical/CODEX_SUBAGENTS.md subagent lifecycle owner
upstream design agents/workflows/agent-canon-pr-workflow.md shared AgentCanon PR workflow
downstream design evidence/agent-evals/skill_workflow_prompt_eval.toml validates root routing
downstream implementation tools/agent_tools/check_entrypoint_owner_map.py validates thin entrypoint structure
downstream implementation tools/agent_tools/check_agent_runtime_alignment.py validates runtime owner-map alignment
@dependency-end
-->

This file is the thin root entrypoint for a parent repository that explicitly
selects the `live-agent-canon` integration. It is not the default
`project_template` instruction source. Task procedures, command recipes,
implementation rules, role lifecycle, update mechanics, and closeout schemas
remain in the vendored canonical owners named below.

## Integration Role

The parent repository owns its product, project commands, local policy, and
tracked files. AgentCanon owns only the explicitly selected shared runtime
surface. Parent-local instructions take precedence for parent-owned behavior;
AgentCanon instructions may not infer authority over unrelated project state.

A source-free static-seed consumer does not load this file and must not acquire
`vendor/agent-canon`, root projections, source resolvers, update state, secrets,
or network access as a fallback.

## Reader Map

| Task intent | Canonical owner in an explicit live integration |
| --- | --- |
| ChatGPT conversation closure vs Codex workspace execution | `vendor/agent-canon/agents/internal-routines/chatgpt-codex-routing.md` |
| request interpretation and task transport after Codex admission | `vendor/agent-canon/agents/skills/agent-orchestration.md`, `vendor/agent-canon/agents/skills/codex-task-workflow.md` |
| search, read scope, and reuse survey | `vendor/agent-canon/documents/tools/search-coordination.md`, `tools/bin/agent-canon semantic-index`, `vendor/agent-canon/tools/agent_tools/search.py`, dependency review artifacts |
| contract-complete implementation and engineering basis | `vendor/agent-canon/documents/conventions/software-engineering-principles.md`, `vendor/agent-canon/agents/skills/comprehensive-development.md`, task-specific Skill |
| mathematical, algorithmic, and numerical obligations | `vendor/agent-canon/documents/design/semantic-responsibility-contract.md`, selected proof / optimization Skill |
| design-to-implementation correspondence | `vendor/agent-canon/agents/internal-routines/design-implementation-correspondence.md` |
| repository structure and responsibility boundaries | parent structure owner plus `vendor/agent-canon/agents/skills/structure-refactor.md` when selected |
| branch, worktree, and destructive Git safety | `vendor/agent-canon/agents/skills/worktree-health.md`, canonical workflow, active hooks |
| task contract observation and durable archive | `vendor/agent-canon/documents/runtime/task-contract-observation.md`, `vendor/agent-canon/tools/agent_tools/task_contract_observation.py`, `vendor/agent-canon/documents/runtime/runtime-log-archive.md`, `agent-canon-log` |
| shared AgentCanon update and PR evidence | `vendor/agent-canon/tools/update_agent_canon.sh`, `vendor/agent-canon/tools/sync_agent_canon.sh`, AgentCanon PR workflow, `agentcanon_structure_followup` |
| AgentCanon source update and root projection | `vendor/agent-canon/agents/skills/agent-canon-update.md`, update route |
| subagent activation and handoff | orchestration, subagent Skill, and canonical subagent inventory |
| validation profile and closeout | `vendor/agent-canon/documents/runtime/runtime-profiles-and-check-matrix.md`, canonical workflow, closeout tools |
| GitHub Issue / PR publication and status | `vendor/agent-canon/agents/skills/pr-processing.md`, GitHub status lifecycle owner |

## Always-On Boundary

The explicit user request, parent-owned tracked policy, and selected canonical
owner define authority. Preserve unknown parent and vendored checkout state
until the Git safety owner classifies it. Do not use a parent-direct fallback,
compatibility wrapper, hidden source checkout, or copied policy to bypass an
owner or validation failure.

Implementation sufficiency is owned by the selected implementation and review
Skills. They select the smallest contract-complete owning unit and require
material mathematical, domain, or engineering grounds and a validation oracle.
This entrypoint only routes to that contract.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation / reader route |
| --- | --- | --- |
| workflow family, spawn budget, role topology | `vendor/agent-canon/agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| task bootstrap and CLI entrypoints | `vendor/agent-canon/agents/canonical/CLI_ENTRYPOINTS.md` | `bootstrap_agent_run.py` |
| subagent lifecycle, same-role instances, wave ledger | `vendor/agent-canon/agents/canonical/CODEX_SUBAGENTS.md` | `workflow_monitor.py` |
| role behavior and stage conditions | `vendor/agent-canon/.codex/agents/*.toml` | `check_agent_runtime_alignment.py` |
| skill routing and public skill surface | `vendor/agent-canon/agents/skills/catalog.yaml` | active `python3 vendor/agent-canon/tools/agent_tools/route.py --prompt`; retired `python3 tools/agent-canon/agent_tools/route.py --prompt` is not executable without the removed alias |
| contract observation and archive evidence | `vendor/agent-canon/documents/runtime/task-contract-observation.md` | `task_contract_observation.py`, then runtime-log archive readback |
| report and closeout structure | `vendor/agent-canon/tools/agent_tools/task_close.py` | `closeout gate` |
| explicit live integration surface | `vendor/agent-canon/documents/runtime/shared-runtime-surfaces.toml` | `surface_manifest.py` |
| entrypoint responsibility grammar | `vendor/agent-canon/documents/design/entrypoint-owner-map.md` | `check_entrypoint_owner_map.py` |

## Task Entry

Resolve request modality through the vendored
`agents/internal-routines/chatgpt-codex-routing.md` before repository
orchestration. A `chatgpt` route performs no parent or vendored workspace
execution. A `codex` route hands its typed scope and validation oracle to the
vendored `agent-orchestration` owner.

After Codex admission, resolve the parent or AgentCanon owner before reading
implementation detail. Use the parent owner for product behavior and the
vendored owner for the explicit shared runtime surface. Read the selected Skill
or canonical workflow before mutation. Bounded owner/path/validation work
remains bounded; activation of design, research, orchestration, or subagents
follows the selected owner's conditions.

Read-only web, connector, and supplied-material analysis remain ChatGPT work
unless the requested result depends on local parent/vendor state, command
observation, mutation, iterative validation, or durable repository delivery.
Repository-changing work follows the selected owner surface; this entrypoint
does not reproduce its steps or environment protocol.

## Validation Routing

Select checks from the changed responsibility and active integration profile.
Parent product validation remains parent-owned. AgentCanon validation applies
to the changed shared surface, and root projection or update readback applies
only when that integration surface changed. Use the canonical closeout owner
rather than a command list embedded in this file.
