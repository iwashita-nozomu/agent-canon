---
name: worktree-start
description: "Legacy cleanup only. Use when inspecting or retiring stale WORKTREE_SCOPE.md/action-log state; do not use to create, recreate, resume, or move work into a git worktree."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:worktree-start -->
<!-- canonical: agents/skills/worktree-start.md sha256=9a65991d0ac390f6bc064a2255c592186505ef3ecd38537deabf7556ae5b09ec -->
<!-- route: agents/skills/catalog.yaml#skill:worktree-start.routing digest=f9cb6b221d17d0308bd040347c11e94ddab13575ca018a72f23e2020ad098eba -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:worktree-start digest=a3a886ec15c580c1586816563a2dd29fdc3d03db0757a415f63f01309926f73e -->
<!-- commands: agents/skills/catalog.yaml#skill:worktree-start.tool_commands digest=7f3f195ccf4aaef1447728299a30b1f513e045f79387330f24c943ab1b5b69fb -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/worktree-start.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# worktree-start

## Canonical Skill

Canonical workflow and policy: [worktree-start](../../../agents/skills/worktree-start.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill worktree-start --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `7f3f195ccf4aaef1447728299a30b1f513e045f79387330f24c943ab1b5b69fb`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
