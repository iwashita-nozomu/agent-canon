# subagent-bootstrap

<!--
@dependency-start
contract skill
responsibility Launches selected child handoffs and durable coordination without duplicating role policy.
upstream design ../task_catalog.yaml workflow and role guidance
upstream design ../canonical/CODEX_SUBAGENTS.md role, authority, and lifecycle policy
upstream design ./agent-orchestration.md current-agent default and delegation selection
upstream design ../COMMUNICATION_PROTOCOL.md handoff and context boundary
upstream design ./direct-luna-communication.md selected Luna runtime exchange
upstream design ../internal-routines/subagent-startup.md selected private startup route
upstream design ./repository-topic-clone.md prepared writer checkout
downstream design ../../.codex/personal/skills/subagent-bootstrap/SKILL.md runtime discovery adapter
@dependency-end
-->

## Purpose

Prepare and launch a selected specialist through native Codex collaboration.

## Use When

Use when the task route calls for a child, coordination, or resumption.

## Launch and Handoff

Apply [Delegation selection](agent-orchestration.md#delegation-selection) before
preparing a child handoff. Durable coordination can remain with the current agent.

Resolve the task and role from the selected catalog route and
[CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md). Use [In-flight Skill reads](task-routing.md#in-flight-skill-reads)
for the handoff and its prerequisites. Read the actual child result to confirm
completion, and record the result or failure through the selected workflow.

[COMMUNICATION_PROTOCOL](../COMMUNICATION_PROTOCOL.md#handoff-packet) owns handoff and context
fields. For a write-capable child, pass its agreed Git checkout and allowed paths in the message; [repository-topic-clone](repository-topic-clone.md) owns checkout
preparation. Read
[direct-luna-communication](direct-luna-communication.md) only when Luna is the
selected profile, and [subagent-startup](../internal-routines/subagent-startup.md)
only when that private route is selected.

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
the concrete blocker and recovered evidence to the parent. Confirm the
parent's execution authority before taking over blocked child work.

## Validation

Use the selected validation and review to confirm the assigned result.
