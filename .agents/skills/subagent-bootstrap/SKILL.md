---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing.
---
<!--
@dependency-start
responsibility Documents Subagent Bootstrap for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/COMMUNICATION_PROTOCOL.md defines pre-edit tool rejection handoff fields
@dependency-end
-->


# Subagent Bootstrap

1. Read `agents/skills/subagent-bootstrap.md`.
1. Read `agents/canonical/CODEX_SUBAGENTS.md`.
1. For repo-changing tasks, create or inspect a run bundle before implementation.
1. For goal-driven repo-changing tasks, create a provisional run bundle and start read-only `requirements_organizer` / `explorer` before `/goal` is finalized when the exact objective is not yet fixed.
1. For goal-driven tasks only, keep write-capable implementation subagents blocked until `goal.md` is parseable, the Codex goal view is mirrored or queued, and Plan-mode evidence mapping exists.
1. For ordinary repo-changing tasks where the user explicitly requested coding, implementation, or patch work through subagents, do not apply the goal-driven `goal.md` block. After the run bundle, bounded `allowed_paths`, write scope, validation plan, and tool-rejection preflight are fixed, launch or schedule `spark_worker` / `worker`; read-only waves are setup evidence, not a substitute for the implementation handoff.
1. If the active runtime requires explicit user authorization before `spawn_agent`, do not silently spawn even read-only pre-goal agents. Record the fan-out plan, handoff packets, and `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` in the run bundle, then wait for or request authorization.
1. Use `--task-id` so `agents/task_catalog.yaml` expands default specialists and review packs.
1. Keep requirements review, plan review, detailed design review, and document flow review as separate agents.
1. Check the command output for `IMPLEMENTATION_CODEX_AGENTS`.
1. If `IMPLEMENTATION_CODEX_AGENTS` starts with `spark_worker,worker`, send approved, design-traced, low-risk implementation slices to `spark_worker` first.
1. Read the corresponding `.codex/agents/<role>.toml` before choosing model / reasoning for a spawned role.
1. For repo inventory, tool drift survey, static validation triage, diff-local Python / C++ review, and machine-report summarization, use read-only roles only when they are independent verification that does not delay the implementation critical path.
1. For coding / implementation / patch requests, describe the default route as write-capable handoff first. Once bounded `allowed_paths`, write scope, validation plan, and tool-rejection preflight are fixed, schedule or launch `spark_worker` / `worker`; parent owns the handoff packet, integration order, review gate, and final responsibility.
1. For bounded review, report traceability, and checklist-style review gates, use mini review role TOMLs only when they can run alongside or after the implementation slice without replacing the write-capable handoff.
1. Treat a narrow implementation slice as `spark_worker` eligible only when it is one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable.
1. Keep every handoff packet bounded: include role-specific `allowed_paths`, checker or compact artifact paths, relevant canon sections, explicit `do_not_read` surfaces, and expected output schema. Do not use `/workspace` or the repo root as the only scope.
1. Build `allowed_paths` from dependency headers when possible: expand edited paths, search hits, checker findings, or changed files through `run_repo_dependency_review.sh` and pass `dependency_edit_scope.txt` / `dependency_graph.tsv` instead of only a hand-written file list.
1. If a project-defined Spark role fails because runtime tools conflict with its effort profile, retry as a fresh default subagent using that role TOML's `model` and `model_reasoning_effort` before escalating to the parent or a frontier role.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. If a write-capable coding subagent cannot be launched because authorization or tool gates are missing, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle and stop expanding read-only analysis for that slice.
1. Use one writer per worktree. If multiple writers are necessary, split worktrees before implementation.
1. For each new user request, start fresh run-local subagents; do not `send_input` a new task into subagents from a previous request.
1. Include `team_manifest.yaml` `run.subagent_lifecycle_policy` in every subagent handoff prompt, especially `fresh_subagents_required: true` and `reuse_for_new_task: forbidden`.
1. Before assigning write-capable work, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and include `TOOL_REJECTION_PREDICTED_GATE` lines, `rejection_preflight_command`, and the gate-specific repair plan in the handoff. Treat hook runtime, skill mirror sync, tool catalog, agent protocol convention, and log-surface inventory gates as implementation blockers until the repair command is run or explicitly scheduled in the same handoff.
1. Before closeout, close run-local subagents and record `subagents_closed=yes` plus `Subagent Lifecycle Evidence` in `closeout_gate.md`.
