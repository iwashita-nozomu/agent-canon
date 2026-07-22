---
name: subagent-bootstrap
description: Use when a task needs specialist delegation, run-bundle bootstrap, explicit stage subagents, or Codex implementation routing.
---

<!--
@dependency-start
contract skill
responsibility Documents Subagent Bootstrap for this repository.
upstream design ../../../agents/canonical/skills.md skill canon registry
upstream design ../../../agents/COMMUNICATION_PROTOCOL.md defines pre-edit tool rejection handoff fields
upstream design ../../../agents/internal-routines/subagent-startup.md owns the canonical private subagent startup route
@dependency-end
-->

# Subagent Bootstrap

## Reader Map

- Purpose: runtime skill for preparing specialist delegation, run-bundle
  bootstrap, stage subagents, and Codex implementation routing.
- Use When: a task needs a fresh subagent, explicit handoff packet, wave ledger
  update, or write-capable implementation routing. Compatible active agents may
  be reused for revised scope.
- Tool Commands: run this skill's command packet, then read the canonical
  `agents/skills/subagent-bootstrap.md` route before spawning or recording waves.
- Boundary: do not spawn or reuse agents without bounded scope, validation
  route, review gate, and lifecycle evidence.

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
1. Read `agents/internal-routines/subagent-startup.md` before preparing
   subagent-only startup or internal skill route handoffs. The canonical private
   startup route is `agents/internal-routines/subagent-startup.md`; historical
   startup labels are not public skills or accepted route aliases.
1. Treat `agents/COMMUNICATION_PROTOCOL.md` as the single owner of handoff and
   capsule fields. This skill owns launch timing, role selection, wave ledger,
   authorization, and closeout mechanics; it does not create a second capsule
   schema.
1. For repo-changing tasks, create or inspect a run bundle only when
   coordination, resumption, or the selected workflow needs durable lifecycle
   evidence. A semantically complete structured handoff can satisfy the packet
   contract.
1. For goal-driven repo-changing tasks, materialize a provisional intake wave
   only when its owner-critical evidence can change the next decision. The
   catalog `manager`, `requirements_organizer`, `explorer`, `execution_planner`,
   and `plan_reviewer` roles remain candidates until activated.
1. For goal-driven tasks only, keep write-capable implementation subagents blocked until `goal.md` is parseable, the Codex goal view is mirrored or queued, and Plan-mode evidence mapping exists.
1. For ordinary repo-changing coding, implementation, patch, or doc-edit work, do not apply the goal-driven `goal.md` block. After the structured handoff or, when selected, the run bundle and pre-handoff investigation packet derive dependency-expanded handoff scope, validation plan, and tool-rejection preflight evidence, launch or schedule the selected write-capable implementer; read-only waves are setup evidence, not a substitute for the implementation handoff. The parent remains orchestrator / integrator and does not become the default implementer.
1. If the active runtime requires explicit user authorization before `spawn_agent`, do not silently spawn even read-only pre-goal agents. Record the fan-out plan, handoff packets, and `PRE_GOAL_SUBAGENT_AUTHORIZATION=required` in the run bundle, then wait for or request authorization.
1. Use `--task-id` when the selected route needs catalog evidence; task-default
   specialists and review packs are candidates, not automatic work.
1. Keep independent requirements, plan, detailed-design, and document-flow
   reviews separate when the selected validation route activates them.
1. Check the command output for `IMPLEMENTATION_CODEX_AGENTS` when an
   implementation wave is selected.
1. Treat `STANDARD_AGENT_WAVE_SEQUENCE=selected_stages_only` as a candidate
   projection, not a mandatory plan-review-edit sequence.
   Record only selected plan, review, or edit evidence; no fixed sequence creates
   an unselected stage.
1. Check the command output for `DEFAULT_QUALITY_CHECKS=candidate_only`,
   `DEFAULT_QUALITY_CHECK_ROLES`, and `DEFAULT_QUALITY_CHECK_AGENT_TYPES`.
   Review and edit handoffs include `team_manifest.yaml`
   `run.default_quality_check_policy`.
1. Require `IMPLEMENTATION_CODEX_AGENTS=worker,spark_worker`; `worker` is the default. Select `spark_worker` only when the parent packet supplies `--select-agent-type implementer=spark_worker:<evidence>`, and require the selection in `SUBAGENT_AGENT_TYPE_SELECTIONS` and `team_manifest.yaml`.
1. Read the corresponding `.codex/agents/<role>.toml` before choosing model / reasoning for a spawned role.
1. Before assigning read-only exploration, run the canonical checker, router, semantic index, or dashboard when one owns the question. Use subagents to interpret ambiguous structured tool artifacts or independently review non-tool-covered judgment, not to repeat deterministic tool checks by reading the same documents.
1. For repo inventory, tool drift survey, machine-report summarization, and experiment/log execution, use the ordinary `gpt-5.6-luna/high` roles when they are independent verification or bounded execution that does not delay the implementation critical path. Reserve `gpt-5.4-mini/medium` for the fresh, read-only, artifact-only `skill_evaluator` in explicit T14 `skill_evaluation`; it is absent from permanent team roles.
1. For static validation triage, diff-local Python / C++ review, bounded review, report traceability, and checklist-style review gates, select one accountable `gpt-5.6-luna/high` review role for the active decision; use `gpt-5.6-luna/xhigh` only for `ship_reviewer` findings.
1. For coding / implementation / patch / doc-edit requests, describe the default route as write-capable handoff first. Once route seed, responsibility search, reuse survey, stale-surface scan, dependency expansion, validation plan, and tool-rejection preflight produce a handoff packet, schedule or launch the selected write-capable implementer; parent owns the handoff packet, integration order, review gate, and final responsibility.
1. Treat a bounded implementation slice as `spark_worker` eligible only when it is derived from the Abstract Design Frame and is one file or one abstraction unit, public interface unchanged, no dependency change, no specification interpretation, and locally testable. Eligibility does not replace the explicit typed parent-packet selection.
1. Keep every handoff packet owned after discovery: include dependency-expanded `allowed_paths`, relevant canon sections, explicit `do_not_read` surfaces, and expected output schema, with context artifacts referenced through the protocol-owned capsule. Use `/workspace` or the repo root only as workspace identity, then derive handoff scope from route seed, responsibility search, reuse survey, stale-surface scan, and dependency expansion. For implementation handoff, seed `allowed_paths` from implementation-surface router `PRIMARY_PATHS` and `do_not_read` from `FORBIDDEN_PATHS`; if the router is unavailable, retain deterministic router recovery output only as local provisional source-packet evidence or record `router_unavailable_blocker` before handoff. This evidence does not select a new candidate or public route; confirm the handoff paths through responsibility search and dependency scope.
1. For a fresh launch, build the `Fresh Subagent Context Capsule` through
   `agents/COMMUNICATION_PROTOCOL.md` and its `Context Visibility Contract`.
   Reuse an active agent when owner, responsibility, context, write authority,
   and validation route remain compatible, including revised scope. New turns or
   renamed packets alone do not require fresh launch. Keep full packets, raw
   stdout, raw logs, broad chat summaries, and full dashboards in local/tool
   context by path instead of pasting them into the prompt.
1. When `team_manifest.yaml` provides
   `run.subagent_prompt_packet.subagent_startup_route`, carry that structural
   route field into the handoff packet and downstream review result. Do not
   convert it into prompt keyword routing, public `ACTIVE_SKILLS`, or a
   duplicated capsule schema.
1. For theorem-driven, algorithm, or implementation handoffs, include the
   protocol-owned `Target Binding Packet` in the capsule before spawning. If the
   packet is incomplete, repair the capsule or source packet first. A subagent's
   unchecked theorem sketch, type-incompatible formula, local counterexample, or
   code suggestion is not an implementation instruction until the parent has run
   the stated checker / validation route and confirmed it targets the same public
   root.
1. Build `allowed_paths` from dependency headers when possible: expand edited paths, search hits, checker findings, or changed files through `run_repo_dependency_review.sh` and pass `dependency_edit_scope.txt` / `dependency_graph.tsv` instead of only a hand-written file list.
1. If the selected candidate cannot launch, record local/tool evidence with `selected_agent_type`, `write_capable_handoff_blocker`, `evidence`, `parent_packet_ref`, and `status=blocked`; changing candidates requires an explicit revised parent packet and wave.
1. Send broad implementation, design interpretation, conflict resolution, or architecture-sensitive work to `worker`.
1. For T12, treat `scheduler`, `schedule_reviewer`, `project_reviewer`,
   `docs_workflow_steward`, and `prompt_config_reviewer` as candidates. Activate
   only owner-critical roles or roles selected by the validation route. When the
   change-review decision activates, use `diff_triage_reviewer` as its default
   executable; materialize `python_reviewer` / `cpp_reviewer` only from
   changed-path evidence, parent packet evidence, or explicit review-pack
   activation.
1. If a write-capable coding / docs-edit subagent cannot be launched because authorization or tool gates are missing, record `WRITE_SUBAGENT_AUTHORIZATION=required` or the gate-specific blocker in the run bundle and stop expanding read-only analysis for that slice. Parent-direct is allowed only as a recorded exception with blocked route, exception rationale, owner boundary, and targeted validation.
1. Default to one writer in the current checkout. If multiple writers are necessary, use them only when `team_manifest.yaml` fixes dependency order, wave plan, disjoint write scope, integration order, and review gate; colliding writers are serialized into later waves in the current checkout instead of split into separate worktrees.
1. For multiple independent workstreams, schedule a stage owner per workstream and let that owner create a vertical dynamic wave under `run.delegated_spawn_policy` instead of flattening every role into one parent wave. Only sibling waves with disjoint input packets, write scopes, validation routes, and review gates may run together.
1. For log-analysis-driven launches, require the `Finding Route Packet` from `agents/skills/agent-log-analysis.md`. Use `finding_class` to choose the destination owner and `instance_partition` to shard same-role instances by `repo_key`, `hook_family`, `skill_name`, `workflow_name`, `issue_id`, or path scope.
1. For same-role log-analysis instances, use an id shaped like `<role_type>:<repo_key>:<finding_class>:<partition>:<seq>` and give each instance its own structured evidence cell, allowed paths, expected output, validation route, and review gate.
1. After the parent or delegated stage owner actually spawns, skips, or replaces a wave, record it with `python3 tools/agent_tools/workflow_monitor.py --subagent-wave ...`; delegated child waves must include `remaining_spawn_budget`.
1. Treat a wave as an adaptive loop, not a fixed one-shot fan-out. The parent integrates each wave result, reruns the same checker / validation route, turns remaining frontier rows into the next bounded handoff queue, and spawns fresh follow-up agents when repository / code / tool action can advance the frontier. Do not return `unverified_with_next_witness`, `connection_unconnected`, or bridge gaps as user-facing stopping points while the next frontier can still be worked.
1. When returning a validation failure to the next writer, include
   `failing_contract`, `observation_level`, `cause_classification`,
   `intent_preservation`, and `evidence` in the handoff, and forbid pass-only
   simplification, revert, intended behavior/test deletion, oracle weakening,
   or validation downscope.
1. Classify each user input as `same_active_task_delta`, `scope_or_contract_change`,
   or `new_task`, but do not start fresh solely because the turn or packet name
   changed. Reuse an active agent when owner, responsibility, context, write
   authority, and validation route remain compatible. Start a fresh agent/wave
   only for independent review, disjoint write authority, incompatible
   owner/context, or failed context integrity. Durable checkpoint and updated
   packet paths are required only for coordination or resumption.
1. When context changes mid-task, update the capsule artifact path and send that path; do not append unbounded chat summaries to old handoff prompts.
1. Include the selected lifecycle decision and fresh-agent conditions from
   `team_manifest.yaml` in handoff prompts; do not require
   `fresh_subagents_required: true` or `reuse_for_new_task: forbidden` as
   universal values.
1. For every nonterminal subagent, treat a `wait_agent` timeout as a polling boundary rather than a lifecycle deadline. Each blocking poll must use `timeout_ms <= 60000`; an overall completion wait may span repeated bounded polls, with required user-facing progress updates and the existing new-state or revised-packet gate between polls. A timeout, empty update, or slow response alone never authorizes interruption or cancellation. Resolve the active runtime's status, message, interrupt, and close capabilities before acting: in this runtime, use `list_agents` for noninterrupting status inspection, `send_message` for same-task packet delivery, and `interrupt_agent` only after explicit user cancellation. Do not invent unavailable `send_input(interrupt=...)` or `close_agent` operations.
1. If a bounded poll times out, returns empty status, or a run-local subagent has no final response at a wave decision point, record `subagent_no_return_investigation` with agent id, wave id, wait command and timeout, last known status, last workflow-monitor event, runtime or tool error, log / dashboard pointers, and cause hypothesis. Record the current status and recovered evidence, then return control to the parent decision point. Another wait or status probe requires `new state evidence` or `explicit revised packet`; scope, owner, allowed-path, or review-gate changes require a fresh follow-up wave from that packet. Map timeout, empty status, and absent final response to `termination_action=preserve_running_instance`, `resolution_decision=await_new_state|continue_disjoint_parent_work`, `write_scope=reserved`, and `overlapping_writer=blocked`.
1. Before assigning write-capable work, run or cite `python3 tools/agent_tools/tool_rejection_preflight.py --root . <planned-edit-paths>` and include `TOOL_REJECTION_PREDICTED_GATE` lines, `rejection_preflight_command`, and the gate-specific repair plan in the handoff. Treat hook runtime, skill mirror sync, tool catalog, agent protocol convention, and log-surface inventory gates as implementation blockers until the repair command is run or explicitly scheduled in the same handoff.
1. Use an active runtime close operation only when that capability exists and the runtime reports `completed|errored|shutdown`, or after explicit user cancellation. When the active runtime provides no close operation, preserve the instance until a terminal status is observed and record `runtime_no_close_operation:terminal_status_observed` as `Subagent Lifecycle Evidence` in `closeout_gate.md`. A nonterminal no-return instance records `subagents_closed=no` and `lifecycle_gate=pending`.
