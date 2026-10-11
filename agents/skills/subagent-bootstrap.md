# subagent-bootstrap

<!--
@dependency-start
contract skill
responsibility Launches selected child handoffs and durable coordination without duplicating role policy.
upstream design ../task_catalog.yaml typed child and run-bundle selection
upstream design ../canonical/CODEX_SUBAGENTS.md role, authority, and lifecycle policy
upstream design ../COMMUNICATION_PROTOCOL.md handoff and context boundary
upstream design ./direct-luna-communication.md selected Luna runtime exchange
upstream design ../internal-routines/subagent-startup.md selected private startup route
upstream design ./repository-topic-clone.md prepared writer checkout
downstream design ../../.codex/personal/skills/subagent-bootstrap/SKILL.md runtime discovery adapter
@dependency-end
-->

## Purpose

Prepare and launch a selected specialist handoff or durable coordination run.
Workflow and role selection remain with their existing owners.

## Use When

Use when the typed task route requires a child or durable coordination or
resumption. Repository-changing work alone does not select either.

## Launch and Handoff

Resolve the task and role from the selected catalog route and
[CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md). For an AgentCanon run,
`bootstrap_agent_run.py` owns the execution transition: use only the returned
`EXECUTION_GRAPH_READY_TOOL_CALLS_JSON` and re-enter that same `RUN_ID` with the
host's actual ToolCall results. A spawn result means launched, not completed;
dependent waves remain blocked until the child completion result arrives. Do
not select a second wave manually or treat a monitor row as the result.

The graph reads only currently selected canonical Skill documents and their
required prerequisites through file EOF before dispatch. Related candidates and
deferred Skills remain unloaded until their route activates. Carry the loaded
canonical body in the dispatch context; a generated shim or a different agent's
read does not satisfy it. Use the existing structured handoff and run bundle for
durable lifecycle evidence; `task_close.py` remains the terminal owner.

Result re-entry uses `--execution-results` keyed by the existing
`role_id:instance_id:agent_type`. Supply the actual host `spawn_result` and the
child's actual `completion_result` in the standard ToolCall result shape
(`isError`, `content`). Only completion results unlock dependents. The
IssueWorker route uses the same role entry's `publication_result` for its
existing follow-up ToolCall. Do not synthesize success from a monitor status.

[COMMUNICATION_PROTOCOL](../COMMUNICATION_PROTOCOL.md) owns handoff and context
fields. For a write-capable child, use its prepared writer target and allowed
paths; [repository-topic-clone](repository-topic-clone.md) owns checkout
preparation. Do not duplicate their packet or checkout rules here. Read
[direct-luna-communication](direct-luna-communication.md) only when Luna is the
selected profile, and [subagent-startup](../internal-routines/subagent-startup.md)
only when that private route is selected.

The parent relays packets and actual results. The child acts within its
assigned authority; a failed or incomplete child result does not unlock a
dependent node or become a parent-write fallback.

## Reuse and Parallel Work

Reuse an active agent when owner, responsibility, context, write authority, and
validation remain compatible. Use a fresh instance only for independent review,
disjoint authority, incompatible context, or failed context integrity.

Serialize writers that share a checkout. Parallel writers require disjoint
scopes and distinct checkouts prepared by the repository-topic owner.

## Subagent Return Investigation

A timeout or empty update is an observation, not a cancellation or replacement
decision. Preserve a nonterminal writer's scope and follow CODEX_SUBAGENTS for
the active runtime's status, message, interrupt, and close capabilities. Return
the concrete blocker and recovered evidence to the parent.

## Validation

Use only the selected validation and owning review gate. A child result is
evidence for its assigned action, not proof of unrelated work or an unrun check.
For a selected Skill or tool, read its current owner and invoke its native CLI/API/script entrypoint with argv and process-result semantics preserved.
