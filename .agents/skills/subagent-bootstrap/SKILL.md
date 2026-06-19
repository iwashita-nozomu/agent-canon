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

## Tool Commands

<!-- skill-tool-commands:start -->
Use the command packet before applying this skill's workflow:

```bash
python3 tools/agent_tools/skill_tool_commands.py show --skill subagent-bootstrap --format text
```

Execute the required and task-matching conditional commands that the packet prints.
<!-- skill-tool-commands:end -->


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
1. If `IMPLEMENTATION_CODEX_AGENTS` starts with `spark_worker,worker`, send only approved, low-risk implementation slices derived from the Abstract Design Frame and design trace to `spark_worker` first.
1. Read the corresponding `.codex/agents/<role>.toml` before choosing model / reasoning for a spawned role.
1. Before assigning read-only exploration, run the canonical checker, router, semantic index, or dashboard when one owns the question. Use subagents to interpret ambiguous compact tool artifacts or independently review non-tool-covered judgment, not to repeat deterministic tool checks by reading the same documents.
1. For repo inventory, tool drift survey, static validation triage, diff-local Python / C++ review, and machine-report summarization, use read-only roles only when they are independent verification that does not delay the implementation critical path.
1. For coding / implementation / patch requests, describe the default route as write-capable handoff first. Once bounded `allowed_paths`, write scope, validation plan, and tool-rejection preflight are fixed, schedule or launch `spark_worker` / `worker`; parent owns the handoff packet, integration order, review gate, and final responsibility.
1. For bounded review, report traceability, and checklist-style review gates, use mini review role TOMLs only when they can run alongside or after the implementation slice without replacing the write-capable handoff.
1. Treat a narrow implementation slice as `spark_worker` eligible only when it is derived from the Abstract Design Frame and is one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable.
1. Keep every handoff packet bounded: include role-specific `allowed_paths`, checker or compact artifact paths, relevant canon sections, explicit `do_not_read` surfaces, and expected output schema. Do not use `/workspace` or the repo root as the only scope. For implementation handoff, seed `allowed_paths` from implementation-surface router `PRIMARY_PATHS` and `do_not_read` from `FORBIDDEN_PATHS`; if the router is unavailable, pass the deterministic fallback output or a blocker instead of choosing paths from chat context.
1. Treat every spawned subagent as fresh: include the `Fresh Subagent Context Capsule` from `agents/COMMUNICATION_PROTOCOL.md` with objective, request clauses, state snapshot, exact read-before-work paths, compact artifacts, allowed / forbidden paths, expected output schema, validation route, and return contract. Do not rely on accumulated chat history, full transcripts, raw logs, full dashboards, or repo-root scope.
1. For theorem-driven, algorithm, or implementation handoffs, include the
   capsule's `Target Binding Packet` before spawning: exact target theorem or
   behavior, public root / entrypoint and signature, return projection or call
   path, identifier naming plan, accepted top-level assumptions, forbidden
   assumptions, current generated/checker evidence, completion condition,
   validation commands, and unchecked-output policy. If any field is missing,
   do not spawn a subagent;
   repair the capsule or source packet first. A subagent's unchecked theorem
   sketch, type-incompatible formula, local counterexample, or code suggestion is
   not an implementation instruction until the parent has run the stated
   checker / validation route and confirmed it targets the same public root.
1. Build `allowed_paths` from dependency headers when possible: expand edited paths, search hits, checker findings, or changed files through `run_repo_dependency_review.sh` and pass `dependency_edit_scope.txt` / `dependency_graph.tsv` instead of only a hand-written file list.
1. If a project-defined Spark role fails because runtime tools conflict with its effort profile, retry as a fresh default subagent using that role TOML's `model` and `model_reasoning_effort` before escalating to the parent or a frontier role.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. If a write-capable coding subagent cannot be launched because authorization or tool gates are missing, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle and stop expanding read-only analysis for that slice.
1. Default to one writer in the current checkout. If multiple writers are necessary, use them only when `team_manifest.yaml` fixes dependency order, wave plan, disjoint write scope, integration order, and review gate; colliding writers are serialized into later waves in the current checkout instead of split into separate worktrees.
1. For multiple independent workstreams, schedule a stage owner per workstream and let that owner create a vertical dynamic wave under `run.delegated_spawn_policy` instead of flattening every role into one parent wave. Only sibling waves with disjoint input packets, write scopes, validation routes, and review gates may run together.
1. For log-analysis-driven launches, require the `Finding Route Packet` from `agents/skills/agent-log-analysis.md`. Use `finding_class` to choose the destination owner and `instance_partition` to shard same-role instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope.
1. For same-role log-analysis instances, use an id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` and give each instance its own compact evidence cell, allowed paths, expected output, validation route, and review gate.
1. After the parent or delegated stage owner actually spawns, skips, or replaces a wave, record it with `python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...`; delegated child waves must include `remaining_spawn_budget`.
1. For each new user request, start fresh run-local subagents; do not `send_input` a new task into subagents from a previous request.
1. For user instructions added while the same active task is still running, do not drop the active multi-agent wave. The parent must classify the input as `same_active_task_delta`, `scope_or_contract_change`, or `new_task`; record a checkpoint in the run bundle, Agent Wave Ledger, and workflow monitoring; then either send the updated packet to the still-valid run-local agent or spawn a fresh follow-up wave when scope, allowed paths, owner, or review gate changed.
1. When context changes mid-task, update the capsule artifact path and send that path; do not append unbounded chat summaries to old handoff prompts.
1. Include `team_manifest.yaml` `run.subagent_lifecycle_policy` in every subagent handoff prompt, especially `fresh_subagents_required: true` and `reuse_for_new_task: forbidden`.
1. If `wait_agent` times out, returns empty status, or a run-local subagent has no final response at a wave decision point, record `subagent_no_return_investigation` before closing, replacing, or escalating that agent. Include agent id, wave id, wait command and timeout, last known status, last workflow-monitor event, runtime or tool error, log / dashboard pointers, cause hypothesis, and selected action: `continue_wait`, `status_probe_same_task`, `close_and_replace_fresh_wave`, or `escalate_runtime_issue`.
1. Before assigning write-capable work, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and include `TOOL_REJECTION_PREDICTED_GATE` lines, `rejection_preflight_command`, and the gate-specific repair plan in the handoff. Treat hook runtime, skill mirror sync, tool catalog, agent protocol convention, and log-surface inventory gates as implementation blockers until the repair command is run or explicitly scheduled in the same handoff.
1. Before closeout, close run-local subagents and record `subagents_closed=yes` plus `Subagent Lifecycle Evidence` in `closeout_gate.md`.
