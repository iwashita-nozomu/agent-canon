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
[CODEX_SUBAGENTS](../canonical/CODEX_SUBAGENTS.md). Use the existing structured
handoff; bootstrap a run bundle only when coordination or resumption needs
durable lifecycle evidence.

[COMMUNICATION_PROTOCOL](../COMMUNICATION_PROTOCOL.md) owns handoff and context
fields. For a write-capable child, use its prepared writer target and allowed
paths; [repository-topic-clone](repository-topic-clone.md) owns checkout
preparation. Do not duplicate their packet or checkout rules here. Read
[direct-luna-communication](direct-luna-communication.md) only when Luna is the
selected profile, and [subagent-startup](../internal-routines/subagent-startup.md)
only when that private route is selected.

The parent relays packets, dependency order, and status. The child acts within
its assigned authority; a blocked write-capable child is not a parent-write
fallback.

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

