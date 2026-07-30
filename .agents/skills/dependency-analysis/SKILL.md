---
name: dependency-analysis
description: "Use when checking, validating, or diagnosing repository dependency manifests, expanding code/header/search dependencies into a change-impact packet, or preparing repair-planning and subagent handoff context before editing, review, or closeout."
---
<!-- generated: agent_canon.skill_runtime_shim.v1 -->
<!-- source: agents/skills/catalog.yaml#skill:dependency-analysis -->
<!-- canonical: agents/skills/dependency-analysis.md sha256=9baa50adac05626d3ad5cc86c278844d89cf7eb0b351979c13d5b443a7cb0098 -->
<!-- route: agents/skills/catalog.yaml#skill:dependency-analysis.routing digest=16584206a3b7cd1747d112850220a0c705bf7f156d5aea6d9152b029b5ff8819 -->
<!-- dependencies: agents/skills/skill-dependencies.yaml#invocation:dependency-analysis digest=87001901117d908accf231c34b624bd8663bc562ce1f4f78bba0700317f90ac7 -->
<!-- commands: agents/skills/catalog.yaml#skill:dependency-analysis.tool_commands digest=560633aa5d07d2d2feaef85399ce5835465efc1f1b04a5448a1f71ca3f713dcc -->
<!-- materializer: skill_shim_materializer.v1 -->

<!--
@dependency-start
contract reference
responsibility Exposes the catalog-owned Codex discovery adapter for this skill.
upstream design ../../../agents/skills/catalog.yaml catalog-owner
upstream design ../../../agents/skills/skill-dependencies.yaml dependency-owner
upstream implementation ../../../agents/skills/dependency-analysis.md canonical-owner
downstream implementation ../../../tools/agent_tools/skill_shim_materializer.py shim-writer
downstream implementation ../../../tools/agent_tools/skill_tool_commands.py packet-reader
downstream implementation ../../../tools/agent_tools/route.py route-owner
downstream implementation ../../../tools/agent_tools/check_agent_runtime_alignment.py host-readback
@dependency-end
-->

# dependency-analysis

## Canonical Skill

Canonical workflow and policy: [dependency-analysis](../../../agents/skills/dependency-analysis.md).
Read that owner before applying the skill. This file is only the Codex discovery
adapter; it does not restate the canonical skill prose.

## Tool Commands

<!-- skill-tool-commands:start -->
Read-only command packet: `python3 tools/agent_tools/skill_tool_commands.py show --skill dependency-analysis --format text`.
Packet schema: `skill_tool_commands.v2`; packet digest: `560633aa5d07d2d2feaef85399ce5835465efc1f1b04a5448a1f71ca3f713dcc`.
The command packet is the complete catalog-backed packet, including every command
phase and resolved command tuple; this line is its executable read path, not a second
writer or an alternate write route.
<!-- skill-tool-commands:end -->

1. Read the canonical owner above before applying this skill; use the read-only command packet for its ToolCall commands.
