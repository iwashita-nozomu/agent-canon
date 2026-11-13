<!--
@dependency-start
contract design
responsibility Documents the retained Codex role/model configuration owners and their boundary from task execution state.
upstream design ../../agents/agents_config.json owns permanent role identities and responsibilities
upstream design ../../agents/model_profiles.toml owns model/profile values and role bindings
upstream design ../../agents/canonical/CODEX_SUBAGENTS.md owns role descriptions and selection guidance
upstream design ../../agents/skills/agent-orchestration.md owns workflow and capability selection
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/codex_agent_role_eval/model_profiles.rs materializes role profile views
downstream implementation ../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py checks role/profile projections
downstream design ../../agents/skills/computational-optimization.md owns mathematical-intent review
downstream design ../../agents/skills/formal-proof-workflow.md owns formal proof work
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs owns the native hook route
downstream implementation ../../tools/runtime/dispatch/agent-canon/src/run_evaluation.rs owns native Eval execution
@dependency-end
-->

# Codex Role and Model Selection

This document is a short map of the retained role and model configuration. The
listed source files remain canonical; this page does not define a second role
registry or a task execution protocol.

## Canonical sources

| Concern | Owner | Role |
| --- | --- | --- |
| Permanent role identities, responsibilities, and Codex agent mapping | [`agents/agents_config.json`](../../agents/agents_config.json) | Selects the logical role and its responsibility. |
| Model, reasoning effort, and role/profile bindings | [`agents/model_profiles.toml`](../../agents/model_profiles.toml) | Supplies the configured model profile for each role. |
| Role descriptions and selection guidance | [`CODEX_SUBAGENTS.md`](../../agents/canonical/CODEX_SUBAGENTS.md) | Explains how the configured roles fit current workflows. |
| Generated role views | [`evaluate-codex-agent-roles`](../../documents/tools/agent-canon.md) | Materializes `.codex/agents/*.toml` from the canonical configuration. |
| Generated-view consistency | [`check_agent_runtime_alignment.py`](../../tools/validation/semantic/runtime/check_agent_runtime_alignment.py) | Checks current role and profile projections. |

Update the owning source when a persistent role or model selection changes.
Treat generated views as readback. Do not copy model values or role instructions
into another registry.

## Role selection

Select a logical role from the task and the workflow owner. Sol remains the
parent for overall task coordination. Luna profiles cover reasoning, design,
implementation, integration, and review according to their configured
responsibilities. Spark remains an optional low-latency implementation role
when the parent can assign a bounded change. Terra remains a conditional
read-only cross-cutting reviewer. The skill evaluator remains for explicit
skill-evaluation work. The exact IDs, model aliases, reasoning effort, and role
bindings are in the canonical profile and role files above.

Role and model configuration does not authorize repository changes. The current
user request, repository instructions, selected workflow, and native Codex
tools define the active scope and authority. Use Codex collaboration tools when
delegation is selected; use the current conversation and Git history to track
the task and its result.

## Independent domain owners

Mathematical intent remains a domain contract consumed by the mathematical
reviewer and implementation owner. Use
[`computational-optimization`](../../agents/skills/computational-optimization.md)
for optimization work; proof exploration and Lean evidence remain with
[`algorithm-proof-exploration`](../../agents/skills/algorithm-proof-exploration.md)
and [`formal-proof-workflow`](../../agents/skills/formal-proof-workflow.md).
These artifacts retain their own inputs, expected results, and validation.

Codex hooks keep their behavior in [`hook_dispatcher.rs`](../../tools/runtime/dispatch/agent-canon/src/hook_dispatcher.rs)
and append-only event records in [`hook_event_log.rs`](../../tools/runtime/dispatch/agent-canon/src/hook_event_log.rs).
Their archive lifecycle remains with
[`runtime_log_archive_git.py`](../../tools/runtime/archive/runtime_log_archive_git.py).
Eval execution and manifest resolution remain with
[`run_evaluation.rs`](../../tools/runtime/dispatch/agent-canon/src/run_evaluation.rs)
and [`eval_manifest_paths.rs`](../../tools/runtime/dispatch/agent-canon/src/eval_manifest_paths.rs).
These independent domain artifacts retain their own paths and formats; they do
not create a general task run bundle.

## Execution boundary

Repository work proceeds through the selected Codex tools, the user's
conversation, and Git. There is no repository-owned per-task run lifecycle,
progress record, spawn receipt, writer-identity packet, or close token required
for role selection or implementation. A role profile selects model settings and
instructions; it does not establish platform capacity or effective runtime
readback.
