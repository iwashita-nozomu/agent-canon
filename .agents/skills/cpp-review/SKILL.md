---
name: cpp-review
description: "Use when C or C++ code changes need strict review for build evidence, header boundaries, ownership, and native-code behavior."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:cpp-review -->
<!-- canonical: agents/skills/cpp-review.md sha256=84fcc0adb3df46f6370937cae8a54f8d1c75e21cc9184a5feddd7f9d03d6af5b -->
<!-- route: agents/skills/catalog.yaml#skill:cpp-review.routing digest=ceaab753e28c451e305a7975b509970e1acd93904d57f6ac720895db9cfa5161 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:cpp-review digest=c3013ba138342b1334c435f9470870a3936b334cc2a31a880fe856b06a78b1ca -->
<!-- commands: agents/skills/catalog.yaml#skill:cpp-review.tool_commands digest=22db59fd443eb29d7f3adc24ba1b6cfe0c437a2e3bf11e37332b28cfbba6ec7f -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/cpp-review.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# cpp-review

## Canonical Skill

Canonical workflow and policy: [cpp-review](../../../agents/skills/cpp-review.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill cpp-review --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `22db59fd443eb29d7f3adc24ba1b6cfe0c437a2e3bf11e37332b28cfbba6ec7f`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
