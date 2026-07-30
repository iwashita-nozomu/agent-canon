---
name: mvp-skeleton
description: "Use when creating, scaffolding, planning, or implementing an MVP, prototype, runnable vertical slice, product skeleton, v0, or thin vertical slice and the agent must prevent overbuilding. Trigger for MVP作成, プロトタイプ, 骨格だけ, core runnable path, thin vertical slice, scope creep, over-polish, and cases where early implementation is getting unnecessary UI, architecture, features, or tests."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:mvp-skeleton -->
<!-- canonical: agents/skills/mvp-skeleton.md sha256=09afe3de3faf18ef47df7db81e2eb0e9616815b41a9dd4f310d4ebe5cbb68444 -->
<!-- route: agents/skills/catalog.yaml#skill:mvp-skeleton.routing digest=32e6568f225e0f4f90cdb0c7f05bb9e64460e942a6f17059169fd61a212c8a3b -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:mvp-skeleton digest=0b5b8e1bca847516fbf435d8a9ccb0114dcdd4de7fc07b23dd8b1b09572967ee -->
<!-- commands: agents/skills/catalog.yaml#skill:mvp-skeleton.tool_commands digest=b39796e94dba3d17b1f4e930d50867a7c1d042eeafee6a9f8e36e7298f7e1fa9 -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/mvp-skeleton.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# mvp-skeleton

## Canonical Skill

Canonical workflow and policy: [mvp-skeleton](../../../agents/skills/mvp-skeleton.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill mvp-skeleton --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `b39796e94dba3d17b1f4e930d50867a7c1d042eeafee6a9f8e36e7298f7e1fa9`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
