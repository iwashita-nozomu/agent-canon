---
name: pr-processing
description: "Use when processing GitHub pull requests or issue queues: inventory open PRs, preserve PR Essence in bodies and run bundles, resolve conflicts, order merges, update branch protection evidence, merge only with authority, triage stale issues, and sync AgentCanon source PRs with parent pin PRs."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:pr-processing -->
<!-- canonical: agents/skills/pr-processing.md sha256=220fd388ae070a110e20de0dfe0c32c949268f626ad2ad691175c3436e516635 -->
<!-- route: agents/skills/catalog.yaml#skill:pr-processing.routing digest=4a43623e00425e7a17ac09a698dc0a10620b1b5132f324301cc2c787aa59ab68 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:pr-processing digest=0ea9eac3476dae094ad8dcb6ad81cb1e80d77420bc6e108599c09c05f2f95c7b -->
<!-- commands: agents/skills/catalog.yaml#skill:pr-processing.tool_commands digest=d12c2598ba7b8d0177368d0cf192b3b4365a53f91537eb88d64805701a4b2e72 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
upstream implementation ../../../agents/skills/pr-processing.md
@dependency-end
-->

# pr-processing

## Canonical Skill

Canonical workflow and policy: [pr-processing](../../../agents/skills/pr-processing.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill pr-processing --format text`; schema `skill_tool_commands.v2`, digest: `d12c2598ba7b8d0177368d0cf192b3b4365a53f91537eb88d64805701a4b2e72`.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
