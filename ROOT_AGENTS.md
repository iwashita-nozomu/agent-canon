# AgentCanon integration compatibility entrypoint

<!--
@dependency-start
contract agent-runtime
responsibility Routes an explicitly selected parent integration to the standalone AgentCanon source and shared bootstrap runtime.
upstream design documents/runtime/bootstrap-runtime.md shared tool-runtime boundary
upstream design documents/design/entrypoint-owner-map.md root entrypoint grammar
upstream design agents/skills/agent-canon-update.md source update owner
downstream design documents/runtime/runtime-log-archive.md eval archive owner
@dependency-end
-->

This file is retained only for consumers that explicitly select an AgentCanon
integration. The normal AgentCanon source checkout reads `AGENTS.md`; a normal
parent repository has its own self-contained `AGENTS.md`. This compatibility
entrypoint never points at a vendor directory, submodule, source symlink, or
parent projection.

## Integration Role

An integrating parent obtains AgentCanon through a qualified, ignored clone at
`<parent>/workspace/agent-canondevelop/<qualified-task>/agent-canon`. The parent
owns its product, build, test, and CI policy. AgentCanon owns only its source,
shared Python/Rust/LSP tool runtime, skills, workflows, and evaluation/archive
contracts. The integration does not copy AgentCanon internals into the parent.

## Reader Map

| Task intent | Canonical owner |
| --- | --- |
| request modality and task transport | `agents/internal-routines/chatgpt-codex-routing.md`, `agents/skills/agent-orchestration.md` |
| implementation and review basis | `documents/conventions/software-engineering-principles.md`, selected implementation Skill |
| source update and PR lifecycle | `agents/skills/agent-canon-update.md`, `agents/workflows/agent-canon-pr-workflow.md` |
| shared tool runtime lifecycle | `documents/runtime/bootstrap-runtime.md`, `bootstrap.sh` |
| eval collection and archive publication | `documents/runtime/runtime-log-archive.md`, `iwashita-nozomu/agent-canon-log` |
| subagent activation and handoff | `agents/canonical/CODEX_SUBAGENTS.md`, orchestration Skill |
| validation and closeout | `documents/runtime/runtime-profiles-and-check-matrix.md`, canonical workflow |
| GitHub Issue / PR publication | `agents/skills/pr-processing.md` |

## Always-On Boundary

The explicit request and the selected canonical owner define authority. The
parent's tracked files and AgentCanon's standalone source remain separate.
Runtime state, task reports, evals, caches, Codex home, Cargo output, and
temporary files belong below the explicit parent workspace runtime root, never
inside the source checkout. Project tests run through the project's own test
entrypoint; the AgentCanon tool container does not mount or discover them.

## Runtime Owner Map

| Responsibility | Canonical owner | Validation route |
| --- | --- | --- |
| workflow family, spawn budget, role topology | `agents/task_catalog.yaml` | `check_agent_runtime_alignment.py` |
| task bootstrap and CLI entrypoints | `agents/canonical/CLI_ENTRYPOINTS.md` | `bootstrap_agent_run.py` |
| subagent lifecycle, same-role instances, wave ledger | `agents/canonical/CODEX_SUBAGENTS.md` | `workflow_monitor.py` |
| role behavior and stage conditions | `.codex/agents/*.toml` | `check_agent_runtime_alignment.py` |
| skill routing and public skill surface | `agents/skills/catalog.yaml` | `tools/agent_tools/route.py --prompt` |
| report and closeout structure | `tools/agent_tools/task_close.py` | `closeout gate` |
| entrypoint responsibility grammar | `documents/design/entrypoint-owner-map.md` | `check_entrypoint_owner_map.py` |
| bootstrap, image, and resident container | `bootstrap.sh`, `tools/agent_tools/bootstrap_runtime.py` | bootstrap/container profile |
| Python, Rust, and LSP tool dispatch | `tools/agent_tools/tool_dispatch.py`, `tools/catalog.yaml` | tool dispatch tests |
| skill and agent installation | `agents/skills/catalog.yaml`, `tools/agent_tools/skill_shim_materializer.py` | skill materializer check |
| source-side-effect boundary | `documents/runtime/bootstrap-runtime.md` | external runtime and source-unchanged checks |
| eval archive | `tools/agent_tools/runtime_log_archive_git.py` | archive readback |
| source update | `agents/skills/agent-canon-update.md` | qualified PR and merged-main readback |

## Task Entry

Resolve request modality, read the selected owner, and use the top-level
`bootstrap.sh` when AgentCanon tools are needed. A parent integration must
provide explicit control and runtime roots; no path is inferred from `$HOME`, a
Git submodule, or the current directory. Use a qualified development clone for
source changes and remove it only after PR, merged-main, and evidence readback.

## Validation Routing

Select checks from the changed AgentCanon responsibility and active runtime
profile. Parent product validation remains parent-owned. Bootstrap validation
must include runtime cleanup and source-unchanged readback; eval validation
must include collection status and archive publication/readback. This entrypoint
does not duplicate the procedure owned by those documents and skills.
